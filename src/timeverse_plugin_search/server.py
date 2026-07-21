"""
timeverse-plugin-search MCP Server

功能简述:
    标准 MCP 协议服务器，提供四个工具：
    - search_skills: 从多个市场来源搜索可安装的技能包
    - search_mcp_servers: 从多个市场来源搜索可安装的 MCP 服务器
    - list_sources: 列出所有配置的数据源
    - get_plugin_detail: 获取单个插件的详细信息

    支持分层降级搜索策略，默认快速模式仅查询 REST API 源。

主要组件清单:
    - list_tools: 注册所有工具
    - call_tool: 处理工具调用分发
    - main: CLI 入口点（stdio 传输）

使用示例:
    timeverse-plugin-search
    # 或通过 uvx:
    # uvx timeverse-plugin-search
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from timeverse_plugin_search.config import load_config
from timeverse_plugin_search.searcher import (
    get_plugin_detail,
    list_sources,
    search_mcp_servers,
    search_skills,
)

logger = logging.getLogger("timeverse-plugin-search")


# ==================== MCP Server ====================

server = Server("timeverse-plugin-search")

# 加载配置
_config = load_config()


# ==================== 工具注册 ====================


@server.list_tools()  # type: ignore[untyped-decorator]
async def list_tools() -> list[Tool]:
    """注册所有 MCP 工具。"""
    return [
        Tool(
            name="search_skills",
            description=(
                "从多个市场来源搜索可安装的技能包（Skill）。"
                "支持按关键词搜索，可选指定平台。"
                "默认快速模式只查 REST API 源，结果不足时自动降级到深层源。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "搜索关键词，如 '翻译'、'代码审查'、'数据分析'",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["all", "skillhub", "ai_skill_store", "github", "web"],
                        "description": (
                            "指定搜索平台。默认 all（查询所有启用的 Skill 源），"
                            '也可指定单个平台，如 "skillhub" 只搜 SkillHub。'
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "每个来源返回的最大结果数，默认 10",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "deep"],
                        "description": (
                            "搜索深度: quick（默认，仅 REST API 源），"
                            "deep（含网页抓取和全网搜索）"
                        ),
                    },
                },
                "required": ["q"],
            },
        ),
        Tool(
            name="search_mcp_servers",
            description=(
                "从多个市场来源搜索可安装的 MCP 服务器。"
                "支持按关键词搜索，可选指定平台。"
                "默认快速模式只查 REST API 源，结果不足时自动降级到网页抓取源。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "搜索关键词，如 '数据库'、'文件系统'、'搜索'",
                    },
                    "source": {
                        "type": "string",
                        "enum": [
                            "all",
                            "smithery",
                            "registry",
                            "modelscope",
                            "mcp_so",
                            "mcpmarket_cn",
                            "github",
                            "web",
                        ],
                        "description": (
                            "指定搜索平台。默认 all（查询所有启用的 MCP Server 源），"
                            '也可指定单个平台，如 "smithery" 只搜 Smithery。'
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "每个来源返回的最大结果数，默认 10",
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["quick", "deep"],
                        "description": (
                            "搜索深度: quick（默认，仅 REST API 源），"
                            "deep（含网页抓取和全网搜索）"
                        ),
                    },
                },
                "required": ["q"],
            },
        ),
        Tool(
            name="list_sources",
            description="列出当前配置的所有数据源，按归属工具分组显示启用状态",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_plugin_detail",
            description="获取单个插件（技能包或 MCP 服务器）的详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "插件来源，如 github、skillhub、smithery",
                    },
                    "plugin_id": {
                        "type": "string",
                        "description": "插件的 ID 或标识",
                    },
                    "plugin_type": {
                        "type": "string",
                        "enum": ["skill", "mcp_server"],
                        "description": "插件类型，skill 或 mcp_server",
                    },
                },
                "required": ["source", "plugin_id", "plugin_type"],
            },
        ),
    ]


# ==================== 工具调用处理 ====================


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(
    name: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    处理工具调用请求。

    Args:
        name: 工具名称
        arguments: 工具参数

    Returns:
        TextContent 列表
    """
    try:
        results: list[str] = []
        async for chunk in _run_tool(name, arguments):
            results.append(chunk)
        return [TextContent(type="text", text="\n".join(results))]
    except Exception as e:
        logger.exception("Error handling tool call: %s", name)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {"error": str(e), "tool": name},
                    ensure_ascii=False,
                ),
            )
        ]


async def _run_tool(
    name: str,
    arguments: dict[str, Any],
) -> AsyncIterator[str]:
    """
    执行指定的工具。

    Args:
        name: 工具名称
        arguments: 工具参数

    Yields:
        结果的 JSON 字符串
    """
    q = arguments.get("q", "")
    source = arguments.get("source", "all")
    limit = arguments.get("limit", 10)
    depth = arguments.get("depth", "quick")

    if name == "search_skills":
        yield await _search_skills_handler(q, source, limit, depth)
    elif name == "search_mcp_servers":
        yield await _search_mcp_servers_handler(q, source, limit, depth)
    elif name == "list_sources":
        yield _list_sources_handler()
    elif name == "get_plugin_detail":
        yield await _get_plugin_detail_handler(arguments)
    else:
        yield json.dumps(
            {"error": f"Unknown tool: {name}"},
            ensure_ascii=False,
        )


async def _search_skills_handler(
    q: str,
    source: str,
    limit: int,
    depth: str,
) -> str:
    """
    处理 search_skills 工具调用。

    Args:
        q: 搜索关键词
        source: 指定平台（all 表示全平台）
        limit: 结果数
        depth: 搜索深度

    Returns:
        JSON 结果字符串
    """
    global _config

    # 如果指定了具体平台，临时限制源列表
    if source != "all":
        filtered_sources = [s for s in _config.sources if s.id == source]
        if not filtered_sources:
            return json.dumps(
                {"error": f"Unknown source: {source}", "total": 0, "items": []},
                ensure_ascii=False,
            )
        # 创建临时配置
        from timeverse_plugin_search.config import SearchConfig
        temp_config = SearchConfig(
            sources=filtered_sources,
            timeout=_config.timeout,
            github_token=_config.github_token,
        )
        result = await search_skills(q, depth=depth, limit=limit, config=temp_config)
    else:
        result = await search_skills(q, depth=depth, limit=limit, config=_config)

    return json.dumps(result, ensure_ascii=False)


async def _search_mcp_servers_handler(
    q: str,
    source: str,
    limit: int,
    depth: str,
) -> str:
    """
    处理 search_mcp_servers 工具调用。

    Args:
        q: 搜索关键词
        source: 指定平台（all 表示全平台）
        limit: 结果数
        depth: 搜索深度

    Returns:
        JSON 结果字符串
    """
    global _config

    if source != "all":
        filtered_sources = [s for s in _config.sources if s.id == source]
        if not filtered_sources:
            return json.dumps(
                {"error": f"Unknown source: {source}", "total": 0, "items": []},
                ensure_ascii=False,
            )
        from timeverse_plugin_search.config import SearchConfig
        temp_config = SearchConfig(
            sources=filtered_sources,
            timeout=_config.timeout,
            github_token=_config.github_token,
        )
        result = await search_mcp_servers(q, depth=depth, limit=limit, config=temp_config)
    else:
        result = await search_mcp_servers(q, depth=depth, limit=limit, config=_config)

    return json.dumps(result, ensure_ascii=False)


def _list_sources_handler() -> str:
    """处理 list_sources 工具调用。"""
    result = list_sources(_config)
    return json.dumps(result, ensure_ascii=False)


async def _get_plugin_detail_handler(arguments: dict[str, Any]) -> str:
    """
    处理 get_plugin_detail 工具调用。

    Args:
        arguments: 参数字典

    Returns:
        JSON 结果字符串
    """
    source = arguments.get("source", "")
    plugin_id = arguments.get("plugin_id", "")
    plugin_type = arguments.get("plugin_type", "skill")

    result = await get_plugin_detail(source, plugin_id, plugin_type, _config)
    if result:
        return json.dumps(result, ensure_ascii=False)
    else:
        return json.dumps(
            {"error": f"Plugin not found: {source}/{plugin_id}", "found": False},
            ensure_ascii=False,
        )


# ==================== 配置热重载 ====================


def reload_config() -> None:
    """
    重新加载配置。

    当环境变量发生变化时调用此函数刷新配置。
    """
    global _config
    _config = load_config()
    logger.info("Configuration reloaded")


# ==================== 传输层 ====================


async def _run_stdio() -> None:
    """通过 stdio 传输启动。"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI 入口点。

    默认通过 stdio 传输启动，适合 uvx 或 pip 安装后直接运行。
    """
    parser = argparse.ArgumentParser(description="timeverse-plugin-search MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="传输方式（仅支持 stdio）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="启用详细日志输出",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s | %(name)s | %(message)s",
        stream=__import__("sys").stderr,
    )

    asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
