# 02 — macOS 原生 Finder 文件夹选择器与 paper link 关联

**What to build:**
使用 macOS 原生 AppleScript (`osascript`) 调起 Finder 可视化文件夹选择窗口，实现 `paper link` 命令直接弹窗绑定本地文章存储目录。

**Blocked by:** 01 — 零依赖 Python 核心引擎与 YAML Frontmatter 解析器

**Status:** ready-for-agent

- [x] 实现 `openNativeFolderPicker` 弹窗函数
- [x] 实现 `paper link` 逻辑与配置保存
