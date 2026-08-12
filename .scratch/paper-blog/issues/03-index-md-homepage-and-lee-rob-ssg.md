# 03 — index.md 驱动首页与 Lee Rob 极简 CSS 渲染

**What to build:**
支持扫描 `index.md` / `README.md` 渲染为博客首页个人介绍与主要内容，结合 Lee Rob 极简风格 CSS（单列 `max-w-[60ch]`, 跟随系统暗黑模式），5ms 内编译导出纯静态 `out/index.html` 与 `out/posts/*.html` 网页。

**Blocked by:** 01 — 零依赖 Python 核心引擎与 YAML Frontmatter 解析器

**Status:** ready-for-agent

- [x] 实现 `index.md` 解析与首页组合渲染
- [x] 内置 Lee Rob 极简 CSS 样式与语法高亮
- [x] 实现 `build_site` 纯静态导出
