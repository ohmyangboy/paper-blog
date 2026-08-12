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
- 资源：仅复制 `posts/assets/`，符号链接直接拒绝，避免把站点外文件发布出去。
- 草稿：缺少 `published: true` 时默认为草稿；生产构建不输出草稿，预览构建输出并标记草稿。

## Markdown Profile

CommonMark 基线 + 表格、删除线、任务列表和 Pygments 代码高亮；raw HTML 默认转义。不把“与 GitHub 完全一致”作为兼容性承诺，也不引入 MDX/React 组件。

## 发布前阻断项

1. Homebrew Formula 需要真实 GitHub tag、源码 sha256，并安装 `paper_cli.py`、`paper_runtime` 与锁定 Python 依赖。
2. 删除或隔离历史 Next.js 原型，避免用户误以为存在第二条构建链。
3. 补齐 `serve`/RSS/sitemap/部署的端到端测试，以及干净 Homebrew 安装 smoke test。
