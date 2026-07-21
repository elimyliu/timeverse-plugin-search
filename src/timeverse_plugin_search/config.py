"""
配置管理 - 数据源配置与加载

功能简述:
    定义数据源配置模型，管理内置默认源和用户自定义配置的合并逻辑。
    支持通过 GITHUB_TOKEN 和 SOURCES_CONFIG 环境变量进行覆盖和扩展。

主要类和函数清单:
    - SourceConfig: 单个数据源的配置数据类
    - SearchConfig: 整体搜索配置，包含源列表和超时设置
    - load_config: 从环境变量加载配置，与内置默认配置合并

使用示例:
    config = load_config()
    sources = config.get_sources(tool="search_skills")
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

# ==================== 常量定义 ====================

DEFAULT_GITHUB_TOKEN: str | None = None
DEFAULT_TIMEOUT: int = 15


# ==================== 数据源配置模型 ====================


@dataclass
class SourceConfig:
    """
    单个数据源配置。

    Attributes:
        id: 数据源唯一标识
        name: 数据源显示名称
        source_type: 接入方式（rest_api / web_scrape / web_search / github）
        enabled: 是否启用
        tool: 归属工具（search_skills / search_mcp_servers / both）
        config: 具体配置项（base_url, endpoint, query_param 等）
    """

    id: str
    name: str
    source_type: str
    enabled: bool = True
    tool: str = "both"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchConfig:
    """
    整体搜索配置。

    Attributes:
        sources: 数据源列表
        timeout: HTTP 请求超时秒数
        github_token: GitHub API Token
    """

    sources: list[SourceConfig] = field(default_factory=list)
    timeout: int = DEFAULT_TIMEOUT
    github_token: str | None = None


# ==================== 内置默认源 ====================

_BUILTIN_SOURCES: list[SourceConfig] = [
    # ---- search_skills 专用 ----
    SourceConfig(
        id="skillhub",
        name="SkillHub",
        source_type="rest_api",
        tool="search_skills",
        config={
            "base_url": "https://skillhub.cn",
            "endpoint": "/api/v1/skills",
            "query_param": "query",
            "limit_param": "limit",
        },
    ),
    SourceConfig(
        id="ai_skill_store",
        name="AI Skill Store",
        source_type="rest_api",
        tool="search_skills",
        config={
            "base_url": "https://aiskillstore.io",
            "endpoint": "/v1/skills",
            "query_param": "query",
            "limit_param": "limit",
        },
    ),
    # ---- search_mcp_servers 专用 ----
    SourceConfig(
        id="smithery",
        name="Smithery",
        source_type="rest_api",
        tool="search_mcp_servers",
        config={
            "base_url": "https://api.smithery.ai",
            "endpoint": "/servers",
            "query_param": "q",
            "limit_param": "limit",
        },
    ),
    SourceConfig(
        id="registry",
        name="Official MCP Registry",
        source_type="rest_api",
        tool="search_mcp_servers",
        config={
            "base_url": "https://registry.modelcontextprotocol.io",
            "endpoint": "/v0/servers",
            "query_param": "search",
            "limit_param": "limit",
            "extra_params": {"status": "active"},
        },
    ),
    # ---- 两者共用 ----
    SourceConfig(
        id="github",
        name="GitHub",
        source_type="github",
        tool="both",
        config={
            "per_page": 10,
            "sort": "stars",
        },
    ),
    SourceConfig(
        id="modelscope",
        name="魔搭社区",
        source_type="rest_api",
        tool="both",
        config={
            "base_url": "https://modelscope.cn",
            "mcp_endpoint": "/api/v1/mcp/servers",
            "skill_endpoint": "/api/v1/skills",
            "query_param": "keyword",
            "limit_param": "limit",
        },
    ),
    # ---- 网页抓取源 (Tier 3) ----
    SourceConfig(
        id="mcp_so",
        name="mcp.so",
        source_type="web_scrape",
        tool="both",
        config={
            "base_url": "https://mcp.so",
            "search_path": "/servers",
            "query_param": "q",
            "rate_limit_ms": 1000,
        },
    ),
    SourceConfig(
        id="mcp_aibase",
        name="mcp.aibase.cn",
        source_type="web_scrape",
        tool="search_mcp_servers",
        config={
            "base_url": "https://mcp.aibase.cn",
            "search_path": "/search",
            "query_param": "q",
            "rate_limit_ms": 1000,
        },
    ),
    SourceConfig(
        id="mcpmarket_cn",
        name="mcpmarket.cn",
        source_type="web_scrape",
        tool="search_mcp_servers",
        config={
            "base_url": "https://mcpmarket.cn",
            "search_path": "/search",
            "query_param": "keyword",
            "rate_limit_ms": 1000,
        },
    ),
    # ---- 全网搜索（兜底）-  ----
    SourceConfig(
        id="web",
        name="全网搜索",
        source_type="web_search",
        tool="both",
        config={
            "provider": "duckduckgo",
        },
    ),
]


# ==================== 配置加载 ====================


def _parse_sources_config(json_str: str) -> list[SourceConfig]:
    """
    解析 SOURCES_CONFIG 环境变量中的源配置。

    Args:
        json_str: JSON 字符串

    Returns:
        解析后的数据源列表
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    sources_data = data.get("sources", [])
    result: list[SourceConfig] = []
    for item in sources_data:
        result.append(
            SourceConfig(
                id=item.get("id", ""),
                name=item.get("name", item.get("id", "")),
                source_type=item.get("type", "rest_api"),
                enabled=item.get("enabled", True),
                tool=item.get("tool", "both"),
                config=item.get("config", {}),
            )
        )
    return result


def _merge_sources(
    builtin: list[SourceConfig],
    overrides: list[SourceConfig],
) -> list[SourceConfig]:
    """
    合并内置源和用户自定义源。

    合并规则：同 id 覆盖，新 id 追加。

    Args:
        builtin: 内置源列表
        overrides: 用户自定义源列表

    Returns:
        合并后的源列表
    """
    source_map: dict[str, SourceConfig] = {s.id: s for s in builtin}
    for override in overrides:
        source_map[override.id] = override
    return list(source_map.values())


def load_config() -> SearchConfig:
    """
    加载搜索配置。

    从环境变量读取 GITHUB_TOKEN 和 SOURCES_CONFIG，
    与内置默认配置合并后返回。

    Returns:
        完整的搜索配置
    """
    github_token = os.environ.get("GITHUB_TOKEN") or DEFAULT_GITHUB_TOKEN

    sources_config_str = os.environ.get("SOURCES_CONFIG", "")
    user_sources: list[SourceConfig] = []
    timeout = DEFAULT_TIMEOUT

    if sources_config_str:
        try:
            data = json.loads(sources_config_str)
            timeout = data.get("timeout", DEFAULT_TIMEOUT)
            user_sources = _parse_sources_config(sources_config_str)
        except json.JSONDecodeError:
            pass

    merged = _merge_sources(_BUILTIN_SOURCES, user_sources)

    return SearchConfig(sources=merged, timeout=timeout, github_token=github_token)
