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

- 浏览器端只接收生成后的静态 HTML/CSS：主题（浅色/深色/跟随系统）由 `document.documentElement[data-theme]` 驱动，首屏脚本在绘制前写入，页脚图标零 JS 切换显示。

## 数据边界

- 原稿：`paper link` 关联的目录，默认只扫描顶层 `.md`。
- 配置：`~/.paper/config.json`（设置 `PAPER_HOME` 可用于测试或隔离环境）。
- 项目库：本地项目初始化后，其 `.paper-config.json` 会以软链接形式登记到 `~/.paper/projects/`；`paper all`（`paper -a`）只列出链接仍然有效的项目，项目删除或移动后自动从列表消失，不做复制。
- 生成物：`~/.paper/site/out`，构建使用临时目录和备份交换，避免失败时先删除旧站点。
- 资源：渲染完成后从生成 HTML 收集当前引用，只把对应的 `posts/assets/` 文件复制到 `out/assets/`；生产构建不带草稿专属资源，预览构建包含草稿资源。源素材不做破坏性清理，符号链接直接拒绝。
- 草稿：缺少 `published: true` 时默认为草稿；生产构建不输出草稿，预览构建输出并标记草稿。
- 预览监听：每 0.5 秒检查一次源文件，连续修改在最后一次变化后防抖 2 秒并合并构建；浏览器主动请求 HTML 时可立即处理待构建修改。启动阶段只构建一次。
- 控制台预览：`paper` 控制台进入时按项目文件夹在后台自动启动一个预览守护进程，并在顶部标题下方显示 `🌐预览` 地址（不自动打开浏览器）。同一文件夹多次打开会复用同一实例（引用计数），最后一个控制台退出时守护进程随之关闭。

## Markdown Profile

CommonMark 基线 + 表格、删除线、任务列表和 Pygments 代码高亮；raw HTML 默认转义。不把“与 GitHub 完全一致”作为兼容性承诺，也不引入 MDX/React 组件。

Paper 在同一渲染链中额外保留顶层块间最多两行源文件留白，并兼容 Obsidian 图片嵌入、替代文本和数值尺寸。附件解析被限制在已关联文章目录：明确相对路径优先，纯文件名递归匹配必须唯一；缺失图片用可见占位表示，重名则中止构建。Obsidian 笔记嵌入不在支持范围内。

图片的尺寸、圆角与对齐统一走一条提示解析：`?`/`#` 片段里的 `w=`/`h=`/`r=` 参数与 `left`/`right`/`center` 对齐词，加上 Obsidian 风格的 `|宽x高` 替代文本后缀。本地图片的查询串与片段在导入后从资源地址上移除；远程图片保留自己的查询串（`?w=` 常属于图片服务），只读取 `#` 片段。圆角默认值来自配置项 `imageRadius`，通过 CSS 变量 `--image-radius` 落到样式，单图参数以内联 `style` 覆盖。

视频由同一 Markdown 渲染链识别标准图片位置的视频直链与 Obsidian 视频附件，并由 `paper_runtime/video.py` 输出安全的播放器结构。原生视频使用本地打包的 CSS/JavaScript 渐进增强，无 JavaScript 时保留原生控件；Vimeo 链接只允许明确的平台域名与数字视频 ID，按需加载官方 Player SDK，失败时保留平台控件。视频资源沿用引用收集与构建复制流程，不转码或修改源视频。

## 发布状态（v0.1.0）

1. ✅ Homebrew Formula 基于真实 tag（`v0.1.0`）、源码 sha256 与锁定依赖，通过 `ohmyangboy/tap/paper` 分发。
2. ✅ 历史 Next.js 原型已在发布前删除，仓库只保留 Python 一条构建链。
3. ⏳ `serve`/RSS/sitemap/部署的端到端测试与干净 Homebrew 安装 smoke test，由 v0.1.0 发布流程的隔离 `PAPER_HOME` 走查覆盖。
