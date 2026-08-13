# Paper

Paper 是一个 macOS 优先的极简 Markdown SSG 与写作 CLI。目标版本 v0.1.0 的正式运行时只有 Python；用户不需要安装 Node、npm 或手动运行 pip。

## 本地开发

当前 checkout 直接运行：

```sh
python3 paper.py --version
python3 paper.py doctor
python3 -m unittest discover -s tests -v
```

第一次使用先关联文章目录，或者创建标准目录：

```sh
paper link ~/Documents/Notes
paper init
paper new "Hello Paper"
paper build
paper serve
```

直接执行 `paper` 会进入方向键控制台；支持 `↑/↓`、`j/k`、数字键和 Enter。控制台使用终端备用屏幕，不会把每次重绘写入滚动历史；在首页按一次 Esc/Q 会显示确认提示，再按一次才退出，Ctrl+C 则安静退出。`paper list` 将首页固定在第一项，其余文章按文件修改时间从新到旧排列；🟢 表示已上线，⚪ 表示草稿或已下线。选择文章后可以继续编辑、发布、下架或移到废纸篓，`paper publish` 可以用空格批量勾选草稿。

`paper serve` 会自动打开默认浏览器，并监听 Markdown 与 `assets/` 的变化；重建成功后浏览器自动刷新。预览只绑定 `127.0.0.1`，草稿不会进入生产构建。

Homebrew 安装的版本可以用 `paper update` 自更新：它会刷新 tap、对比当前版本与最新版本，发现新版本时自动 `brew upgrade`。

文章目录只扫描顶层 Markdown 文件。没有 `published: true` 的文章默认为草稿；`assets/` 目录中的资源会被复制到静态站点，正文里直接引用的其他本地图片（相对或绝对路径）在构建/预览时会自动拷贝进 `assets/`。文章的展示标题默认取文件名（不含扩展名），只有在前置元数据里显式写 `title:` 才覆盖它；`paper new` 生成的草稿不带 title。

## Markdown Profile

Paper 使用 `markdown-it-py` 的 CommonMark 基线，并启用表格、删除线、任务列表和代码高亮。原始 HTML 默认转义。Paper 不承诺与 GitHub 页面后处理结果完全一致，也不支持 MDX；额外兼容下文说明的 Obsidian 图片嵌入子集。

**单回车会渲染成换行（`breaks` 模式）**：编辑器里按下回车的地方，页面里就是一行换行。顶层内容块之间的空白行也会显示为留白，每处最多保留两行，避免误输入制造过大的页面空洞。这与 GitHub 的渲染不同，写给 GitHub 用的 Markdown 如需换行请用两个空格结尾。

本地图片推荐放在文章目录的 `assets/` 中，写作 `![说明](assets/image.png)`；也可以直接引用其他本地路径（如 `photos/a.png` 或绝对路径），构建/预览时会自动把这些图片拷进 `assets/`，保证线上可以展示。外链图片会输出 `referrerpolicy="no-referrer"`，避免部分 CDN 因本地预览 Referer 返回 403。

Obsidian 图片支持 `![[image.png]]`、`![[image.png|说明]]`、`![[image.png|300]]` 和 `![[image.png|300x200]]`。明确的相对路径优先；只有文件名时会递归查找已关联的文章目录，文件名必须唯一。找不到图片时页面显示占位提示，重名时构建会要求补充路径。Paper 不搜索关联目录之外的附件，也不展开 `![[笔记]]`。

选择 Obsidian 作为编辑器后，位于 Obsidian vault 内的文章会通过 Obsidian URI 作为库内笔记打开，以便索引、内部链接和附件按 vault 工作；不在 vault 内的文件仍按普通文件打开。Paper 不控制 Obsidian 左侧文件树是否自动展开。

`paper config` 可通过方向键设置主题高亮颜色、默认编辑器和 favicon。favicon 支持内置 P 图标、SVG/Data URI、图片 URL，或将本地图片复制到 `assets/`。

## 运行数据边界

- 用户原稿：由 `paper link` 关联，Paper 不会在卸载时删除。
- 配置：`~/.paper/config.json`。
- 静态托管目录：`~/.paper/site`。
- Homebrew 安装包：由 Homebrew 私有运行环境管理。

GitHub Pages 发布需要用户先提供已有仓库和 Git 凭据；Paper 只负责构建、推送 `gh-pages` 并报告推送结果。

## 当前发布边界

Python CLI 和静态构建链是唯一实现；早期 Next.js 原型（`app/`、`components/`、`lib/`、`bin/paper.mjs`、`package.json` 等）已在发布前移除，仓库只保留 Python 一条构建链。`Formula/paper.rb` 基于真实 GitHub tag 与源码校验和，通过 Homebrew tap（`ohmyangboy/tap/paper`）分发。
