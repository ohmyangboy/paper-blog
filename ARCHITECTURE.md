# Paper v0.1 架构边界

## 唯一运行链

```text
paper CLI
  -> paper_runtime.core
      -> config + frontmatter + markdown-it-py/Pygments
      -> 静态 HTML/CSS/RSS/sitemap
      -> 本地预览或 Git subtree 推送
```

Python 是用户可见的唯一 runtime，也是唯一 build graph。Node、npm、React、Next.js 不应成为安装或构建前置条件；浏览器端只接收生成后的静态 HTML/CSS。

## 数据边界

- 原稿：`paper link` 关联的目录，默认只扫描顶层 `.md`。
- 配置：`~/.paper/config.json`（设置 `PAPER_HOME` 可用于测试或隔离环境）。
- 生成物：`~/.paper/site/out`，构建使用临时目录和备份交换，避免失败时先删除旧站点。
- 资源：渲染完成后从生成 HTML 收集当前引用，只把对应的 `posts/assets/` 文件复制到 `out/assets/`；生产构建不带草稿专属资源，预览构建包含草稿资源。源素材不做破坏性清理，符号链接直接拒绝。
- 草稿：缺少 `published: true` 时默认为草稿；生产构建不输出草稿，预览构建输出并标记草稿。

## Markdown Profile

CommonMark 基线 + 表格、删除线、任务列表和 Pygments 代码高亮；raw HTML 默认转义。不把“与 GitHub 完全一致”作为兼容性承诺，也不引入 MDX/React 组件。

Paper 在同一渲染链中额外保留顶层块间最多两行源文件留白，并兼容 Obsidian 图片嵌入、替代文本和数值尺寸。附件解析被限制在已关联文章目录：明确相对路径优先，纯文件名递归匹配必须唯一；缺失图片用可见占位表示，重名则中止构建。Obsidian 笔记嵌入不在支持范围内。

## 发布状态（v0.1.0）

1. ✅ Homebrew Formula 基于真实 tag（`v0.1.0`）、源码 sha256 与锁定依赖，通过 `ohmyangboy/tap/paper` 分发。
2. ✅ 历史 Next.js 原型已在发布前删除，仓库只保留 Python 一条构建链。
3. ⏳ `serve`/RSS/sitemap/部署的端到端测试与干净 Homebrew 安装 smoke test，由 v0.1.0 发布流程的隔离 `PAPER_HOME` 走查覆盖。
