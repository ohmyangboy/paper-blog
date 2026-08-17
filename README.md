<div align="center">
  <img src="assets/paper-blog-icon.png" width="220" alt="Paper Blog 官方 zine 风格图标">

  <h1>Paper</h1>

  <p><strong>写简单的文字，做干净的博客。</strong></p>
  <p>从 Markdown 写作到 GitHub Pages 上线，一条专为创作者设计的极简路径。</p>

  <p>
    <a href="https://ohmyangboy.github.io/paper-blog/">官方网站</a> ·
    <a href="#-安装">安装指南</a> ·
    <a href="#-快速开始">快速开始</a> ·
    <a href="#-全局模式与局部项目模式">运行模式</a> ·
    <a href="https://github.com/ohmyangboy/paper-blog/issues">问题反馈</a>
  </p>

  <p>
    <img alt="GitHub Release" src="https://img.shields.io/github/v/release/ohmyangboy/paper-blog?include_prereleases&style=flat-square">
    <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
    <img alt="macOS first" src="https://img.shields.io/badge/macOS-first-111111?style=flat-square&logo=apple&logoColor=white">
    <img alt="GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-D97757?style=flat-square">
  </p>
</div>

---

## 软件简介

Paper 是一个 macOS 优先的 Markdown 静态站点生成器与写作 CLI。它把新建草稿、本地预览、文章发布和 GitHub Pages 部署收进同一个终端工作流，让个人博客把注意力留给文字，而不是复杂的构建配置。

正式运行时基于 Python。普通用户通过 Homebrew 一次安装，不需要 Node、npm，也不需要手动配置 pip 依赖。

---

## 核心亮点

- **全流程打通**：`paper new` $\rightarrow$ `paper serve` $\rightarrow$ `paper publish` 一气呵成。
- **方向键控制台**：直接输入 `paper` 唤出 TUI 控制台，首页置顶，草稿与已发布用 🟢 / ⚪ 清晰区分。
- **双运行模式**：支持随时随地写作的**全局模式**，也支持独立仓库管理的**项目目录模式（`-l`）**。
- **本地热更新预览**：内置极轻量 HTTP 服务，监听文件变更自动刷新；草稿不会意外流出到生产构建。
- **GitHub Pages 自动化**：配置一次仓库即可全自动构建并推送 `gh-pages` 分支。
- **Obsidian 深度兼容**：支持 `![[image.png]]` 等图片语法，可一键唤醒 Obsidian 原生应用编辑。
- **完整订阅与 SEO**：自动生成包含全文与作者信息的 RSS 2.0 订阅源与 sitemap.xml。
- **原稿安全保证**：Paper 仅管理静态输出与部署，无论升级或卸载均**绝不触碰**你的 Markdown 原稿。

---

## 📦 安装

### 推荐方式：Homebrew 安装

> 💡 **新 Mac 用户提示**：如果终端提示 `command not found: brew`，请先粘贴运行官方安装脚本：  
> `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`

拥有 Homebrew 后，直接运行：

```sh
brew install ohmyangboy/tap/paper
```

安装完成后验证环境：

```sh
paper --version
paper doctor
```

后续升级直接运行：

```sh
paper update
```

<details>
<summary>源码与开发环境安装（点击展开）</summary>

要求：Python 3.11+。

```sh
git clone https://github.com/ohmyangboy/paper-blog.git
cd paper-blog
pip install -e .
paper --version
```
</details>

---

## 🚀 快速开始（3 分钟从 0 到上线）

### 第 1 步：初始化博客

```sh
paper init
```

*CLI 会弹出交互菜单引导你选择初始化方式：*
1. **全局模式（推荐）**：统一保存在个人文档库中，随时随地在任何终端目录输入 `paper` 即可写作。
2. **当前目录模式（Local）**：在当前文件夹生成 `.paper-config.json` 与 `./posts`，适合独立 Git 仓库管理。

*(如果你已有 Markdown 笔记库，也可以直接运行 `paper link ~/Documents/MyNotes` 进行关联)*

---

### 第 2 步：写下第一篇草稿并本地预览

```sh
# 新建文章（会自动打开你的默认编辑器）
paper new "我的第一篇博客"

# 启动本地热更新预览（浏览器自动打开）
paper serve
```

---

### 第 3 步：一键上线到 GitHub Pages

```sh
# 首次配置远程仓库（按终端提示输入用户名/仓库名即可）
paper config remote

# 审核并发布（自动编译生成静态站点并推送到 GitHub Pages）
paper publish
```

---

## 🧭 全局模式与局部项目模式

Paper 原生支持两种使用习惯，满足不同场景：

| 模式 | 适用场景 | 常用命令 | 配置文件位置 |
| :--- | :--- | :--- | :--- |
| **全局模式**（默认） | 个人博客、日常随手记录，希望在任何终端路径都能直接敲 `paper` 写作。 | `paper` / `paper new` / `paper serve` | `~/.paper/config.json` |
| **局部项目模式**（Local） | 博客本身是一个独立 Git 仓库，希望配置和文章完全随项目代码归档。 | `paper -l` / `paper -l serve` / `paper -C ./my-blog` | `./.paper-config.json` |

* **切换到局部模式**：在命令后加上 `-l` 或 `--local`，例如 `paper -l serve`。
* **指定目录执行**：使用 `-C <路径>`，例如 `paper -C ~/Work/blog publish`。

---

## 🛠️ 常用命令速查表

| 命令 | 作用 |
| --- | --- |
| `paper` | 打开交互式 TUI 文章控制台（方向键导航） |
| `paper new [标题]` | 新建草稿，并自动唤醒编辑器打开 |
| `paper serve` | 启动本地热更新预览服务（默认端口 8000） |
| `paper publish [slug]` | 发布指定草稿或更新已发布文章，并自动同步 GitHub Pages |
| `paper list` | 终端列出所有文章状态（🟢 已上线 / ⚪ 草稿） |
| `paper build` | 仅生成生产环境静态文件到 `out/` 目录（供 CI 或离线检查） |
| `paper deploy` | 手动把当前静态站点推送到 GitHub Pages（发布重试入口） |
| `paper config` | 进入交互式站点与外观设置控制台 |
| `paper config remote` | 快速配置或修改 GitHub 仓库与自定义域名 |
| `paper config editor` | 快捷配置默认编辑器（VS Code / Obsidian / Typora / 系统默认等） |
| `paper doctor` | 检查当前 Python 运行时、Git 及网络配置状态 |
| `paper update` | 一键检查并自更新 Paper 到最新版本 |
| `paper uninstall` | 显示卸载指南（加 `--clean` 可彻底清理配置缓存，不删原稿） |

---

## ✍️ 写作与 Markdown 规范

Paper 扫描文章目录顶层的 `.md` 文件。未标记 `published: true` 的文章默认为草稿，草稿在本地 `paper serve` 中可见，但不会进入生产发布。

```md
---
title: 自定义标题（可选，默认直接取文件名）
date: 2026-08-17
published: true
description: 这是一篇关于 Paper 的极简介绍
---

# 从这里开始写作

单回车直接换行，空行用于分段。
```

### 本地图片与 Obsidian 语法支持

推荐将图片放在文章目录的 `assets/` 下：
```md
![图片说明](assets/cover.png)
```

**完全兼容 Obsidian 图片内嵌语法**：
```md
![[image.png]]
![[image.png|图片说明]]
![[image.png|400]]
![[image.png|400x300]]
```
*构建时 Paper 会自动扫描关联目录，将正文引用的有效图片打包复制到输出资源中，并支持无损图片压缩。*

---

## 🎨 站点外观与品牌定制

输入 `paper config` 可随时自定义：
- **主题高亮色**：修改网站强调色（默认温润纸质橙 `#D97757`）。
- **网站图标（Favicon）**：支持使用 Paper 经典 zine 图标、自定义本地 PNG/SVG/ICO、或直接粘贴图标代码。
- **自定义域名与 Pages 路径**：支持形如 `https://username.github.io/repo` 或自定义独立域名 `https://blog.yourdomain.com`。

---

## 🔒 原稿安全与数据存储

- **用户原稿**：归属权始终在用户手中。即使彻底卸载 Paper，**也绝不会删除你的 Markdown 笔记原稿**。
- **全局配置与缓存**：存储于 `~/.paper/`（含静态发布目录与更新检查缓存）。
- **局部模式配置**：存储于项目根目录下的 `.paper-config.json`。

---

## 📄 开源协议

Paper 基于 [GNU General Public License v3.0](LICENSE) 开源。
