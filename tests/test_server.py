"""
timeverse-plugin-search 测试

功能简述:
    测试 MCP Server 的工具注册、搜索编排和解析器功能。
    使用 pytest-asyncio 进行异步测试。

主要组件清单:
    - TestListTools: 验证工具列表注册
    - TestSearchSkills: 验证 search_skills 逻辑
    - TestSearchMcpServers: 验证 search_mcp_servers 逻辑
    - TestParsers: 验证 HTML 解析器
    - TestConfig: 验证配置加载与合并

使用示例:
    pytest -v --tb=short
"""

from __future__ import annotations

import json

import pytest

from timeverse_plugin_search.config import (
    SearchConfig,
    SourceConfig,
    _merge_sources,
    _parse_sources_config,
    load_config,
)
from timeverse_plugin_search.parsers import (
    _parse_stars,
    parse_mcp_aibase_html,
    parse_mcp_so_html,
    parse_mcpmarket_html,
)
from timeverse_plugin_search.searcher import (
    _format_results,
    list_sources,
)

# ==================== Test Config ====================


class TestConfig:
    """测试配置管理。"""

    def test_builtin_sources_count(self) -> None:
        """验证内置数据源数量。"""
        config = load_config()
        assert len(config.sources) == 10

    def test_default_timeout(self) -> None:
        """验证默认超时。"""
        config = load_config()
        assert config.timeout == 15

    def test_merge_sources_override(self) -> None:
        """验证覆盖内置源。"""
        builtin = [
            SourceConfig(id="github", name="GitHub", source_type="github"),
        ]
        overrides = [
            SourceConfig(
                id="github", name="GitHub Custom",
                source_type="github", config={"token": "xxx"},
            ),
        ]
        merged = _merge_sources(builtin, overrides)
        assert len(merged) == 1
        assert merged[0].config.get("token") == "xxx"

    def test_merge_sources_append(self) -> None:
        """验证追加新源。"""
        builtin = [
            SourceConfig(id="github", name="GitHub", source_type="github"),
        ]
        overrides = [
            SourceConfig(id="glama", name="Glama.ai", source_type="rest_api"),
        ]
        merged = _merge_sources(builtin, overrides)
        assert len(merged) == 2

    def test_parse_sources_config(self) -> None:
        """验证解析 SOURCES_CONFIG JSON。"""
        json_str = json.dumps({
            "sources": [
                {"id": "glama", "name": "Glama.ai", "type": "rest_api", "enabled": True},
            ],
            "timeout": 20,
        })
        config = _parse_sources_config(json_str)
        assert len(config) == 1
        assert config[0].id == "glama"
        assert config[0].source_type == "rest_api"

    def test_parse_sources_config_with_tool(self) -> None:
        """验证解析带 tool 字段的配置。"""
        json_str = json.dumps({
            "sources": [
                {
                    "id": "my_source", "name": "My Source",
                    "type": "rest_api", "tool": "search_skills",
                },
            ],
        })
        config = _parse_sources_config(json_str)
        assert config[0].tool == "search_skills"


# ==================== Test Parsers ====================


class TestParsers:
    """测试 HTML 解析器。"""

    def test_parse_stars_k(self) -> None:
        """解析 K 后缀。"""
        assert _parse_stars("90.7K") == 90700
        assert _parse_stars("108.3K") == 108300

    def test_parse_stars_plain(self) -> None:
        """解析纯数字。"""
        assert _parse_stars("128") == 128
        assert _parse_stars("2560") == 2560

    def test_parse_stars_score(self) -> None:
        """解析评分数字（忽略）。"""
        assert _parse_stars("4.5分") == 4

    def test_parse_mcp_so_html_empty(self) -> None:
        """空 HTML 返回空列表。"""
        assert parse_mcp_so_html("") == []
        assert parse_mcp_so_html("<html></html>") == []

    def test_parse_mcp_aibase_html_empty(self) -> None:
        """空 HTML 返回空列表。"""
        assert parse_mcp_aibase_html("") == []
        assert parse_mcp_aibase_html("<html></html>") == []

    def test_parse_mcpmarket_html_empty(self) -> None:
        """空 HTML 返回空列表。"""
        assert parse_mcpmarket_html("") == []
        assert parse_mcpmarket_html("<html></html>") == []

    def test_parse_mcp_so_html_with_cards(self) -> None:
        """模拟 mcp.so 卡片 HTML。"""
        html = """
        <html>
        <body>
            <a href="/server/test-server">
                <h3>Test MCP Server</h3>
                <p>A test MCP server description</p>
                <span class="stars">1.2K</span>
            </a>
            <a href="/skill/test-skill">
                <h3>Test Skill</h3>
                <p>A test skill description</p>
            </a>
        </body>
        </html>
        """
        results = parse_mcp_so_html(html)
        assert len(results) >= 1


# ==================== Test Searcher ====================


class TestSearcher:
    """测试搜索编排。"""

    def test_format_results_empty(self) -> None:
        """空结果。"""
        result = _format_results([], [], "search_skills")
        assert result["total"] == 0
        assert result["plugin_type"] == "skill"
        assert result["items"] == []

    def test_format_results_dedup(self) -> None:
        """去重逻辑。"""
        results = [
            {"id": "a", "source": "github", "name": "A", "stars": 10},
            {"id": "a", "source": "github", "name": "A", "stars": 10},  # 重复
            {"id": "b", "source": "github", "name": "B", "stars": 20},
        ]
        result = _format_results(results, ["github"], "search_mcp_servers")
        assert result["total"] == 2
        assert result["plugin_type"] == "mcp_server"

    def test_format_results_sort(self) -> None:
        """按 stars 排序。"""
        results = [
            {"id": "a", "source": "github", "name": "A", "stars": 5},
            {"id": "b", "source": "github", "name": "B", "stars": 100},
            {"id": "c", "source": "github", "name": "C", "stars": 20},
        ]
        result = _format_results(results, ["github"], "search_skills")
        assert result["items"][0]["name"] == "B"
        assert result["items"][1]["name"] == "C"
        assert result["items"][2]["name"] == "A"

    def test_list_sources(self) -> None:
        """列出数据源。"""
        config = SearchConfig(
            sources=[
                SourceConfig(
                    id="skillhub", name="SkillHub",
                    source_type="rest_api", tool="search_skills",
                ),
                SourceConfig(
                    id="smithery", name="Smithery",
                    source_type="rest_api", tool="search_mcp_servers",
                ),
                SourceConfig(id="github", name="GitHub", source_type="github", tool="both"),
            ],
        )
        result = list_sources(config)
        assert "search_skills" in result
        assert "search_mcp_servers" in result
        assert len(result["search_skills"]["tier1"]) >= 1
        assert len(result["search_mcp_servers"]["tier1"]) >= 1


# ==================== Test Server ====================


class TestServer:
    """测试 MCP Server。"""

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        """验证注册了 4 个工具。"""
        from timeverse_plugin_search.server import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]
        assert "search_skills" in tool_names
        assert "search_mcp_servers" in tool_names
        assert "list_sources" in tool_names
        assert "get_plugin_detail" in tool_names
        assert len(tools) == 4
