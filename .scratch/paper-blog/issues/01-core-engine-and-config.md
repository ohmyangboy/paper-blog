# 01 — 零依赖 Python 核心引擎与 YAML Frontmatter 解析器

**What to build:**
基于 Python 3 标准库实现配置文件 `~/.paper-config.json` 读写模块，以及支持 YAML Frontmatter (`published: true/false`, `title`, `date`) 的超轻量 Markdown 解析转换引擎。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] 实现 `load_config` 与 `save_config` 读写 `~/.paper-config.json`
- [x] 实现 `parse_frontmatter` 提取 YAML 元数据
- [x] 实现纯 Python 3 超轻量 `markdown_to_html` 转换器
