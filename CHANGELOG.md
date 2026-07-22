# Changelog

## [0.1.1] - 2026-07-22

### Fixed
- 修复 MCP SDK 版本变更导致的 `stdio_server` 导入路径错误
- 修复 REST API 响应中 `owner` 字段为字符串时抛出的 `'str' object has no attribute 'get'` 错误

## [0.1.0] - 2026-07-21

### Added
- 初始发布
- `search_skills` 工具：从 SkillHub、AI Skill Store、GitHub、魔搭社区、mcp.so、全网搜索等来源搜索技能包
- `search_mcp_servers` 工具：从 Smithery、官方 MCP Registry、魔搭社区、mcp.so、mcp.aibase.cn、mcpmarket.cn、GitHub、全网搜索等来源搜索 MCP 服务器
- `list_sources` 工具：列出所有配置的数据源
- `get_plugin_detail` 工具：获取单个插件的详细信息
- 分层降级搜索策略（Tier 1/2/3），默认快速模式
- 支持通过环境变量 GITHUB_TOKEN 和 SOURCES_CONFIG 自定义配置
- 支持指定平台搜索（source 参数）
