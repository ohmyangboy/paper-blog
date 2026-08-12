# 04 — Mole CLI 风格 TUI 终端多选与 paper list 工作台

**What to build:**
使用 Python `termios` 与 `tty` 读取裸终端键盘按键（支持 `↑`/`↓`/`k`/`j` 导航、`Space` 勾选、`Enter` 提交），搭建 `paper list` 二级交互式文章工作台与 `paper publish` 多选草稿列表。

**Blocked by:** 
- 02 — macOS 原生 Finder 文件夹选择器与 paper link 关联
- 03 — index.md 驱动首页与 Lee Rob 极简 CSS 渲染

**Status:** ready-for-agent

- [x] 实现 `prompt_select` 与 `prompt_multiselect` 键盘交互选框
- [x] 实现 `paper list` 交互工作台（编辑、发布、下架归档）
- [x] 实现 `paper publish` 多选勾选发布
