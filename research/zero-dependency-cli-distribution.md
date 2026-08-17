# 开源 CLI 工具零依赖分发机制调研与 Paper 架构演进方案

> 调研日期：2026-08-17  
> 调研对象：Hugo (Go), Mole (Shell+Go), uv/Ruff (Rust), 以及 Python CLI 生态（PyInstaller / Nuitka）  
> 目标：为 Paper Blog 提供全平台零依赖安装与自更新的工程落地参考。

---

## 1. 调研背景与核心问题

当前 `paper-blog` 采用 Python 编写，分发渠道单一依赖 Homebrew Tap。这导致两大硬伤：
1. **强环境前置依赖**：用户必须先安装 Homebrew 及 Python 3.11+ 运行环境；
2. **平台兼容性断层**：代码顶层依赖 POSIX 专有的 `termios`/`tty`，导致 Windows 原生环境直接崩溃，Linux 安装繁琐。

本调研深入分析业界标杆 CLI 是如何做到“纯净新电脑一行命令安装即用（Zero-Dependency）”的。

---

## 2. 业界标杆 CLI 的零依赖分发实现机制

### 2.1 Hugo（静态编译型语言的工业标准）
* **语言与构建**：Go 语言。开启 `CGO_ENABLED=0` 进行纯静态编译。
* **CI/CD 构建流**：
  - 使用 **GoReleaser** 配合 GitHub Actions。
  - 在一次 Release 流程中，自动交叉编译（Cross-Compilation）生成各平台原生二进制：
    - `hugo_darwin-arm64.tar.gz` (Apple Silicon)
    - `hugo_darwin-amd64.tar.gz` (Intel Mac)
    - `hugo_linux-amd64.tar.gz`
    - `hugo_windows-amd64.zip`
* **分发渠道**：
  - **GitHub Releases**：直链下载单个独立可执行文件；
  - **包管理器**：Homebrew (macOS/Linux)、Scoop/Winget (Windows)、Pacman/Apt (Linux) 均直接分发或包装预编译二进制；
  - **一键脚本**：提供 `install.sh` / `install.ps1`，自动探测 OS/Arch 并从 Release 下载解压放入 PATH。
* **特性**：**单文件原生执行，无任何动态链接库依赖，冷启动 < 10ms，体积 15MB 左右**。

### 2.2 Mole（脚本 + 预编译辅助的轻量混合体）
* **语言与构成**：82% Bash 脚本 + 18% Go 预编译辅助工具。
* **分发模式**：
  - **渠道一（Homebrew）**：`brew install mole`。
  - **渠道二（一键脚本）**：`curl -fsSL https://raw.githubusercontent.com/tw93/mole/main/install.sh | bash`。
* **零依赖机制**：
  - 利用 macOS 系统开箱自带的 `/bin/bash` 与原生 POSIX 命令（`defaults`, `launchctl`, `sysctl`, `mdfind` 等）。
  - `install.sh` 脚本从 GitHub Releases 拉取最新 tarball，解压到 `/usr/local/bin` 或 `~/.local/bin`，并配置别名与补全。
  - 内置 `mo update`，直接通过 GitHub Release API 获取最新版并原地原子替换，解耦包管理器。

### 2.3 uv / Ruff（现代 Rust 单二进制生态）
* **语言与构建**：Rust。通过 `cargo build --release --target ...` 静态编译。
* **分发模式**：
  - 一键安装脚本：`curl -LsSf https://astral.sh/uv/install.sh | sh`（Windows: `irm https://astral.sh/uv/install.ps1 | iex`）。
  - 脚本使用纯 Shell/PowerShell 探测系统架构，拉取 GitHub Releases 中的静态二进制，放入 `~/.cargo/bin` 或 `~/.local/bin` 并写入 PATH。
  - 内部实现自我升级命令（Self-Update）。

---

## 3. Paper Blog 架构演进方案评估

针对 Paper Blog 现有的 Python 架构，实现零依赖有两条可行技术路径：

```
                              ┌── 路径 A（短期低成本）：Python 单文件二进制化（PyInstaller / Nuitka）
Paper 零依赖演进技术选择 ──────┤
                              └── 路径 B（长期终极解）：迁移至 Go 语言（类似 Hugo / Mole 模式）
```

### 3.1 路径 A：Python 独立二进制打包（推荐短期落地）
* **核心做法**：
  1. 解耦 `paper_cli.py` 的 POSIX 强假设（条件懒加载 `termios`，增加 Windows `msvcrt` 分支）；
  2. 在 GitHub Actions CI 中通过 `pyinstaller --onefile`（或 `Nuitka`）针对 macOS (ARM/x86), Linux (x86_64), Windows (x64) 编译独立二进制；
  3. 编写 `install.sh` (macOS/Linux) 与 `install.ps1` (Windows)，实现 `curl | bash` 零前置安装；
  4. 改造 `paper update`，支持直接从 GitHub Releases 检测版本并热替换二进制。
* **关键风险与应对**：
  - **macOS Gatekeeper 拦截**：未签名二进制会被 macOS 隔离。应对策略：CI 接入 Apple Developer 证书与 `notarytool` 公证；或在 `install.sh` 中执行 `xattr -d com.apple.quarantine`。
  - **Windows 误报木马**：PyInstaller 易被报毒。应对策略：采用 Nuitka 编译或配置 Release SHA256 校验。
  - **产物体积**：单文件约为 30~45MB（内嵌 Python 运行时），可接受。

### 3.2 路径 B：Go 语言重写核心（长期终极方案）
* **技术平替**：
  - Markdown 渲染：`markdown-it-py` $\rightarrow$ `yuin/goldmark`
  - 代码语法高亮：`Pygments` $\rightarrow$ `alecthomas/chroma`
  - TUI 终端交互：手写 `termios` $\rightarrow$ `charmbracelet/bubbletea`
  - 预览 HTTP 服务：`http.server` $\rightarrow$ 原生 `net/http`
* **优势**：体积 < 15MB，冷启动 < 10ms，跨平台编译极简，无 Python 环境包袱。

---

## 4. 结论与第一轮整改建议

本周末第一轮整改建议优先落地 **“路径 A 阶段一”**：
1. **代码层**：消除 `termios`/`tty` 顶层导入，增加跨平台控制台与系统调用抽象；
2. **CI 流程**：搭建 GitHub Actions 自动构建 PyInstaller / Nuitka 跨平台二进制；
3. **分发层**：提供 `install.sh` 脚本，实现无需 Homebrew / Python 的独立安装。
