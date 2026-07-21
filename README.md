# timeverse-plugin-search

[![PyPI](https://img.shields.io/pypi/v/timeverse-plugin-search)](https://pypi.org/project/timeverse-plugin-search/)
[![Python](https://img.shields.io/pypi/pyversions/timeverse-plugin-search)](https://pypi.org/project/timeverse-plugin-search/)
[![CI](https://github.com/timeverse-studio/timeverse-plugin-search/actions/workflows/ci.yml/badge.svg)](https://github.com/timeverse-studio/timeverse-plugin-search/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

从多个来源搜索可安装的技能包和 MCP 服务器的开放工具。

## Tools

| 工具 | 描述 |
|------|------|
| `search_skills` | 从 SkillHub、AI Skill Store、GitHub、魔搭社区、mcp.so、全网搜索等来源搜索技能包 |
| `search_mcp_servers` | 从 Smithery、官方 MCP Registry、魔搭社区、mcp.so、mcp.aibase.cn、mcpmarket.cn、GitHub、全网搜索等来源搜索 MCP 服务器 |
| `list_sources` | 列出所有配置的数据源 |
| `get_plugin_detail` | 获取单个插件的详细信息 |

## 搜索策略

采用**分层降级**策略，默认只查快速源：

### search_skills

| 层级 | 源 | 延时 | 默认是否启用 |
|------|----|------|------------|
| Tier 1 | SkillHub, AI Skill Store | ~1-2s | ✅ 总是启用 |
| Tier 2 | GitHub, 魔搭社区 | ~+1-2s | ✅ 不足时自动降级 |
| Tier 3 | mcp.so, 全网搜索 | ~+2-5s | 🔲 深度模式或结果不足时 |

### search_mcp_servers

| 层级 | 源 | 延时 | 默认是否启用 |
|------|----|------|------------|
| Tier 1 | Smithery, 官方 Registry, 魔搭社区 | ~1-2s | ✅ 总是启用 |
| Tier 2 | GitHub | ~+1-2s | ✅ 不足时自动降级 |
| Tier 3 | mcp.so, mcp.aibase.cn, mcpmarket.cn, 全网搜索 | ~+3-8s | 🔲 深度模式或结果不足时 |

## 安装

```bash
pip install timeverse-plugin-search
```

或从源码安装：

```bash
git clone https://github.com/timeverse-studio/timeverse-plugin-search.git
cd timeverse-plugin-search
pip install -e ".[dev]"
```

## 使用

### 作为 CLI 工具

```bash
timeverse-plugin-search
```

### 与 TimeVerse Studio 集成

在 TimeVerse Studio 的 MCP Server 配置中通过 JSON 添加，可一并传入环境变量：

```json
{
  "mcpServers": {
    "timeverse-plugin-search": {
      "command": "uvx",
      "args": ["timeverse-plugin-search"],
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxxxxxxxxxxxxxx",
        "SOURCES_CONFIG": "{\"sources\":[{\"id\":\"glama\",\"name\":\"Glama.ai\",\"type\":\"rest_api\"}]}"
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `command` | 启动命令，`uvx` 或 `timeverse-plugin-search`（pip 安装后） |
| `args` | 传递给命令的参数 |
| `env` | （可选）传递给子进程的环境变量，优先级高于系统环境变量 |

`env` 字段中可设置的环境变量说明见下方[配置](#配置)章节。

### 配置

通过环境变量自定义配置：

```bash
# GitHub Token（提升 API 频率限制到 5000次/时）
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# 自定义数据源（合并模式）
SOURCES_CONFIG='{"sources":[{"id":"glama","name":"Glama.ai","type":"rest_api","enabled":true,"config":{"base_url":"https://glama.ai/api","endpoint":"/mcp/servers","query_param":"query"}}]}'

```

### 指定平台搜索

通过 `source` 参数可指定搜索平台：

```
用户: "帮我在 SkillHub 上搜一下翻译相关的技能包"
→ LLM 调用 search_skills(q="翻译", source="skillhub")

用户: "在官方 MCP Registry 上搜一下文件系统的"
→ LLM 调用 search_mcp_servers(q="filesystem", source="registry")
```

### 搜索深度

通过 `depth` 参数控制搜索范围：

- `"quick"`（默认）：仅查 REST API 源，快速返回
- `"deep"`：查所有源（含网页抓取和全网搜索），更全面

## 开发

```bash
pip install -e ".[dev]"
ruff check src/ tests/
ruff format src/ tests/
mypy src/
pytest -v
```

## License

MIT
