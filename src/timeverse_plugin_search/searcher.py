"""
搜索编排 - 多源聚合搜索与分层降级策略

功能简述:
    提供 search_skills 和 search_mcp_servers 两个核心搜索流程，
    采用分层降级策略：Tier 1 REST API 源 → Tier 2 补充源 → Tier 3 网页抓取/全网搜索。
    每个层级的结果不足时自动降级到下一层。

主要函数清单:
    - search_skills: 搜索技能包（分层降级）
    - search_mcp_servers: 搜索 MCP 服务器（分层降级）
    - _search_single_source: 查询单个数据源
    - _parse_duckduckgo_results: 解析 DuckDuckGo 搜索结果

使用示例:
    results = await search_skills("翻译", depth="quick", limit=10, config=my_config)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from duckduckgo_search import DDGS

from timeverse_plugin_search.config import SearchConfig, SourceConfig
from timeverse_plugin_search.parsers import (
    parse_mcp_aibase_html,
    parse_mcp_so_html,
    parse_mcpmarket_html,
)

logger = logging.getLogger("timeverse-plugin-search.searcher")


# ==================== 类型定义 ====================


SearchResult = dict[str, Any]


# ==================== GitHub 搜索 ====================


async def _search_github(
    query: str,
    tool: str,
    config: SearchConfig,
    limit: int = 10,
) -> list[SearchResult]:
    """
    搜索 GitHub 仓库。

    根据工具类型构造不同的搜索关键词：
    - search_skills: 搜索 skill 相关仓库
    - search_mcp_servers: 搜索 mcp-server 相关仓库

    Args:
        query: 搜索关键词
        tool: 工具类型（search_skills / search_mcp_servers）
        config: 搜索配置
        limit: 每页结果数

    Returns:
        搜索结果列表
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github.v3+json",
    }
    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"

    results: list[SearchResult] = []

    async with httpx.AsyncClient(timeout=config.timeout, headers=headers) as client:
        if tool == "search_skills":
            queries = [
                f"{query} skill in:name,description,topics",
                f"skill.json {query}",
            ]
        else:
            queries = [
                f"{query} mcp-server in:name,description,topics",
                f"topic:mcp-server {query}",
            ]

        for q in queries:
            try:
                repo_url = "https://api.github.com/search/repositories"
                params = {"q": q, "per_page": limit, "sort": "stars", "order": "desc"}
                resp = await client.get(repo_url, params=params)
                if resp.status_code == 403:
                    logger.warning("GitHub API rate limited, skipping")
                    continue
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", [])[:limit]:
                    results.append({
                        "id": item.get("full_name", ""),
                        "name": item.get("name", ""),
                        "description": item.get("description") or "",
                        "plugin_type": "skill" if tool == "search_skills" else "mcp_server",
                        "source": "github",
                        "source_url": item.get("html_url", ""),
                        "download_url": f"{item.get('html_url', '')}/archive/refs/heads/main.zip",
                        "stars": item.get("stargazers_count", 0),
                        "tags": item.get("topics", []),
                        "author": (item.get("owner") or {}).get("login", ""),
                        "version": "latest",
                        "trust_level": "community",
                    })
            except httpx.HTTPError as e:
                logger.warning("GitHub search failed: %s", e)

    return results


# ==================== REST API 源搜索 ====================


async def _search_rest_api(
    source: SourceConfig,
    query: str,
    limit: int = 10,
    timeout: int = 15,
    tool: str = "",
) -> list[SearchResult]:
    """
    搜索 REST API 数据源。

    Args:
        source: 数据源配置
        query: 搜索关键词
        limit: 每页结果数
        timeout: 超时秒数
        tool: 当前工具类型

    Returns:
        搜索结果列表
    """
    cfg = source.config
    base_url = cfg.get("base_url", "")
    headers: dict[str, str] = {
        "User-Agent": "TimeVersePluginSearch/0.1",
        "Accept": "application/json",
    }

    # 针对魔搭社区：根据工具选择不同的 endpoint
    if source.id == "modelscope":
        if tool == "search_mcp_servers":
            endpoint = cfg.get("mcp_endpoint", "/api/v1/mcp/servers")
        else:
            endpoint = cfg.get("skill_endpoint", "/api/v1/skills")
    else:
        endpoint = cfg.get("endpoint", "")

    query_param = cfg.get("query_param", "q")
    limit_param = cfg.get("limit_param", "limit")
    extra_params = cfg.get("extra_params", {})

    params: dict[str, Any] = {
        query_param: query,
        limit_param: limit,
        **extra_params,
    }

    # 如果有自定义 headers
    custom_headers = cfg.get("headers", {})
    if isinstance(custom_headers, dict):
        headers.update(custom_headers)

    url = f"{base_url.rstrip('/')}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.warning("REST API search failed for %s: %s", source.id, e)
        return []

    return _parse_rest_response(source.id, data, tool)


def _parse_rest_response(
    source_id: str,
    data: Any,
    tool: str,
) -> list[SearchResult]:
    """
    解析 REST API 的 JSON 响应为统一格式。

    处理不同数据源的响应结构差异（data.items、results、直接数组等）。

    Args:
        source_id: 数据源 ID
        data: JSON 响应数据
        tool: 当前工具类型

    Returns:
        搜索结果列表
    """
    items: list[dict[str, Any]] = []
    plugin_type = "skill" if tool == "search_skills" else "mcp_server"

    # 尝试多种常见的响应结构
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = (
            data.get("data", {}).get("items", [])
            or data.get("data", {}).get("list", [])
            or data.get("data", [])
            or data.get("items", [])
            or data.get("results", [])
            or data.get("records", [])
            or data.get("servers", [])
            or data.get("skills", [])
        )
    else:
        return []

    results: list[SearchResult] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue

        results.append({
            "id": item.get("id") or item.get("key") or item.get("name", ""),
            "name": item.get("name") or item.get("title", ""),
            "description": item.get("description") or item.get("summary", ""),
            "plugin_type": plugin_type,
            "source": source_id,
            "source_url": item.get("url") or item.get("link") or item.get("source_url", ""),
            "download_url": item.get("download_url") or item.get("download", ""),
            "install_command": item.get("install_command") or item.get("command", ""),
            "config_schema": item.get("config_schema") or item.get("schema"),
            "stars": item.get("stars") or item.get("star_count", 0),
            "tags": item.get("tags") or item.get("keywords", []),
            "author": item.get("author") or item.get("owner", {}).get("login", ""),
            "version": item.get("version", "latest"),
            "trust_level": item.get("trust_level", "community"),
        })

    return results


# ==================== 网页抓取 ====================


async def _search_web_scrape(
    source: SourceConfig,
    query: str,
    limit: int = 10,
    timeout: int = 15,
    tool: str = "",
) -> list[SearchResult]:
    """
    通过网页抓取搜索。

    Args:
        source: 数据源配置
        query: 搜索关键词
        limit: 每页结果数
        timeout: 超时秒数
        tool: 当前工具类型

    Returns:
        搜索结果列表
    """
    cfg = source.config
    base_url = cfg.get("base_url", "")
    search_path = cfg.get("search_path", "/search")
    query_param = cfg.get("query_param", "q")
    rate_limit_ms = cfg.get("rate_limit_ms", 1000)

    # 抓取间隔限制
    await asyncio.sleep(rate_limit_ms / 1000)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    params: dict[str, str] = {query_param: query}
    url = f"{base_url.rstrip('/')}{search_path}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as e:
        logger.warning("Web scrape failed for %s: %s", source.id, e)
        return []

    # 按源分发到对应的解析器
    if source.id == "mcp_so":
        results = parse_mcp_so_html(html)
    elif source.id == "mcp_aibase":
        results = parse_mcp_aibase_html(html)
    elif source.id == "mcpmarket_cn":
        results = parse_mcpmarket_html(html)
    else:
        logger.warning("Unknown web scrape source: %s", source.id)
        return []

    # mcp.so 是共用源，按工具过滤
    if source.id == "mcp_so" and tool:
        expected = "skill" if tool == "search_skills" else "mcp_server"
        results = [r for r in results if r.get("plugin_type") == expected]

    return results[:limit]


# ==================== 全网搜索（DuckDuckGo） ====================


async def _search_web(
    query: str,
    tool: str,
    limit: int = 10,
) -> list[SearchResult]:
    """
    通过 DuckDuckGo 全网搜索插件信息。

    根据工具类型构造不同的搜索词。

    Args:
        query: 搜索关键词
        tool: 工具类型
        limit: 结果数

    Returns:
        搜索结果列表
    """
    if tool == "search_skills":
        search_queries = [
            f"timeverse skill {query}",
            f"ai skill package {query}",
            f"{query} skill.json",
        ]
    else:
        search_queries = [
            f"mcp server {query}",
            f"{query} mcp-server",
        ]

    plugin_type = "skill" if tool == "search_skills" else "mcp_server"
    results: list[SearchResult] = []

    for sq in search_queries:
        try:
            # DuckDuckGo_search 是同步库，用 run_in_executor 包装
            max_results = limit // len(search_queries) + 1

            def _search(
                search_term: str = sq,
                _max_results: int = max_results,
            ) -> list[dict[str, str]]:
                with DDGS() as ddgs:
                    return list(ddgs.text(search_term, max_results=_max_results))

            search_results = await asyncio.get_event_loop().run_in_executor(
                None, _search
            )

            for item in search_results:
                title = item.get("title", "")
                snippet = item.get("body", "")
                href = item.get("href", "")

                if not title:
                    continue

                results.append({
                    "id": href.split("/")[-1] if href else title.lower().replace(" ", "-"),
                    "name": title,
                    "description": snippet,
                    "plugin_type": plugin_type,
                    "source": "web",
                    "source_url": href,
                    "trust_level": "community",
                    "tags": [],
                })
        except Exception as e:
            logger.warning("Web search failed for '%s': %s", sq, e)

    return results[:limit]


# ==================== 搜索编排 ====================


async def _search_single_source(
    source: SourceConfig,
    query: str,
    limit: int,
    timeout: int,
    tool: str,
) -> list[SearchResult]:
    """
    查询单个数据源。

    Args:
        source: 数据源配置
        query: 搜索关键词
        limit: 结果数
        timeout: 超时
        tool: 工具类型

    Returns:
        搜索结果列表
    """
    if not source.enabled:
        return []

    if source.source_type == "rest_api":
        return await _search_rest_api(source, query, limit, timeout, tool)
    elif source.source_type == "github":
        return await _search_github(query, tool, SearchConfig(sources=[], timeout=timeout), limit)
    elif source.source_type == "web_scrape":
        return await _search_web_scrape(source, query, limit, timeout, tool)
    elif source.source_type == "web_search":
        return await _search_web(query, tool, limit)
    return []


def _source_belongs_to_tool(source: SourceConfig, tool: str) -> bool:
    """判断数据源是否属于指定工具。"""
    return source.tool in ("both", tool)


def _is_tier1(source: SourceConfig) -> bool:
    """判断是否是 Tier 1（快速 REST API 源）。"""
    return source.source_type == "rest_api" and source.id != "github"


def _is_tier2(source: SourceConfig) -> bool:
    """判断是否是 Tier 2（补充 REST API 源）。"""
    return source.source_type == "github"


def _is_tier3(source: SourceConfig) -> bool:
    """判断是否是 Tier 3（慢速源）。"""
    return source.source_type in ("web_scrape", "web_search")


async def search_skills(
    query: str,
    *,
    depth: str = "quick",
    limit: int = 10,
    config: SearchConfig,
) -> dict[str, Any]:
    """
    搜索技能包（分层降级）。

    搜索流程：
    Tier 1: SkillHub, AI Skill Store（REST API，~1-2s）
    Tier 2: GitHub, 魔搭社区（REST API，+1-2s）
    Tier 3: mcp.so, 全网搜索（网页抓取 + 搜索引擎，+2-5s）

    Args:
        query: 搜索关键词
        depth: 搜索深度（quick / deep）
        limit: 每个来源返回的最大结果数
        config: 搜索配置

    Returns:
        统一格式的搜索结果
    """
    return await _search_with_tiers(
        query=query,
        tool="search_skills",
        depth=depth,
        limit=limit,
        config=config,
    )


async def search_mcp_servers(
    query: str,
    *,
    depth: str = "quick",
    limit: int = 10,
    config: SearchConfig,
) -> dict[str, Any]:
    """
    搜索 MCP 服务器（分层降级）。

    搜索流程：
    Tier 1: Smithery, 官方 Registry, 魔搭社区（REST API，~1-2s）
    Tier 2: GitHub（REST API，+1-2s）
    Tier 3: mcp.so, mcp.aibase.cn, mcpmarket.cn, 全网搜索（网页抓取 + 搜索引擎，+3-8s）

    Args:
        query: 搜索关键词
        depth: 搜索深度（quick / deep）
        limit: 每个来源返回的最大结果数
        config: 搜索配置

    Returns:
        统一格式的搜索结果
    """
    return await _search_with_tiers(
        query=query,
        tool="search_mcp_servers",
        depth=depth,
        limit=limit,
        config=config,
    )


async def _search_with_tiers(
    query: str,
    tool: str,
    depth: str,
    limit: int,
    config: SearchConfig,
) -> dict[str, Any]:
    """
    分层降级搜索核心逻辑。

    Args:
        query: 搜索关键词
        tool: 工具类型
        depth: 搜索深度
        limit: 结果数
        config: 搜索配置

    Returns:
        统一格式的搜索结果
    """
    sources = [s for s in config.sources if s.enabled and _source_belongs_to_tool(s, tool)]

    tier1_sources = [s for s in sources if _is_tier1(s)]
    tier2_sources = [s for s in sources if _is_tier2(s)]
    tier3_sources = [s for s in sources if _is_tier3(s)]

    all_results: list[SearchResult] = []
    sources_queried: list[str] = []

    # --- Tier 1: 快速 REST API ---
    if tier1_sources:
        tier1_tasks = [
            _search_single_source(s, query, limit, config.timeout, tool)
            for s in tier1_sources
        ]
        tier1_results = await asyncio.gather(*tier1_tasks)
        for source, results in zip(tier1_sources, tier1_results, strict=False):
            all_results.extend(results)
            sources_queried.append(source.id)

        # 结果足够则直接返回
        if depth != "deep" and len(all_results) >= limit:
            return _format_results(all_results, sources_queried, tool)

    # --- Tier 2: GitHub 等补充源 ---
    if tier2_sources and (depth == "deep" or len(all_results) < limit):
        tier2_tasks = [
            _search_single_source(s, query, limit, config.timeout, tool)
            for s in tier2_sources
        ]
        tier2_results = await asyncio.gather(*tier2_tasks)
        for source, results in zip(tier2_sources, tier2_results, strict=False):
            all_results.extend(results)
            sources_queried.append(source.id)

        if depth != "deep" and len(all_results) >= limit:
            return _format_results(all_results, sources_queried, tool)

    # --- Tier 3: 网页抓取 + 全网搜索（慢速兜底） ---
    if tier3_sources and (depth == "deep" or len(all_results) < limit // 2):
        tier3_tasks = [
            _search_single_source(s, query, limit, config.timeout, tool)
            for s in tier3_sources
        ]
        tier3_results = await asyncio.gather(*tier3_tasks)
        for source, results in zip(tier3_sources, tier3_results, strict=False):
            all_results.extend(results)
            sources_queried.append(source.id)

    return _format_results(all_results, sources_queried, tool)


def _format_results(
    results: list[SearchResult],
    sources_queried: list[str],
    tool: str,
) -> dict[str, Any]:
    """
    格式化搜索结果。

    Args:
        results: 原始结果列表
        sources_queried: 已查询的数据源 ID 列表
        tool: 工具类型

    Returns:
        统一格式的响应
    """
    # 去重（按 id + source 去重）
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for r in results:
        key = f"{r.get('source', '')}:{r.get('id', '')}"
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # 按 stars 降序排列
    deduped.sort(key=lambda x: x.get("stars", 0) or 0, reverse=True)

    plugin_type = "skill" if tool == "search_skills" else "mcp_server"

    return {
        "total": len(deduped),
        "plugin_type": plugin_type,
        "sources_queried": list(dict.fromkeys(sources_queried)),  # 去重保序
        "items": deduped,
    }


# ==================== 单插件详情 ====================


async def get_plugin_detail(
    source: str,
    plugin_id: str,
    plugin_type: str,
    config: SearchConfig,
) -> SearchResult | None:
    """
    获取单个插件的详细信息。

    通过搜索对应源并匹配 ID 来获取详情。
    部分源可能支持直接获取详情的 API。

    Args:
        source: 数据源 ID
        plugin_id: 插件 ID
        plugin_type: 插件类型（skill / mcp_server）
        config: 搜索配置

    Returns:
        插件详情，未找到返回 None
    """
    tool = "search_skills" if plugin_type == "skill" else "search_mcp_servers"

    # 先尝试搜索
    result = await _search_with_tiers(
        query=plugin_id,
        tool=tool,
        depth="deep",
        limit=20,
        config=config,
    )

    items = result.get("items", [])
    for item in items:
        if item.get("id") == plugin_id and item.get("source") == source:
            return item
        # 也尝试模糊匹配
        if plugin_id in item.get("id", "") and item.get("source") == source:
            return item

    return None


# ==================== 列出数据源 ====================


def list_sources(config: SearchConfig) -> dict[str, Any]:
    """
    列出所有数据源，按工具分组。

    Args:
        config: 搜索配置

    Returns:
        按工具分组的数据源列表
    """
    skill_sources: list[dict[str, Any]] = []
    mcp_sources: list[dict[str, Any]] = []

    for s in config.sources:
        entry = {
            "id": s.id,
            "name": s.name,
            "type": s.source_type,
            "enabled": s.enabled,
        }
        if s.tool in ("both", "search_skills"):
            skill_sources.append(entry)
        if s.tool in ("both", "search_mcp_servers"):
            mcp_sources.append(entry)

    return {
        "search_skills": {
            "tier1": [s for s in skill_sources if s["type"] == "rest_api" and s["id"] != "github"],
            "tier2": [s for s in skill_sources if s["type"] == "github"],
            "tier3": [s for s in skill_sources if s["type"] in ("web_scrape", "web_search")],
        },
        "search_mcp_servers": {
            "tier1": [s for s in mcp_sources if s["type"] == "rest_api" and s["id"] != "github"],
            "tier2": [s for s in mcp_sources if s["type"] == "github"],
            "tier3": [s for s in mcp_sources if s["type"] in ("web_scrape", "web_search")],
        },
    }
