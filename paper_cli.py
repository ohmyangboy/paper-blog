#!/usr/bin/env python3
"""The user-facing Paper command."""

from __future__ import annotations

import argparse
import atexit
import datetime as dt
import http.server
import os
import re
import select
import shutil
import socketserver
import subprocess
import sys
import termios
import threading
import time
import tty
import webbrowser
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from paper_runtime.core import (
    ConfigError,
    DEFAULT_COLOR,
    DEFAULT_ICON_SVG,
    DEFAULT_INDEX,
    GitRemoteInfo,
    PaperConfig,
    Post,
    build_site,
    config_path,
    discover_posts,
    load_config,
    normalize_git_remote,
    parse_frontmatter,
    save_config,
    set_post_published,
)

VERSION = "0.1.0"
DEFAULT_POSTS_DIR = Path.home() / "Documents" / "Paper" / "posts"
TERRACOTTA = "\033[38;2;217;119;87m"
BOLD = "\033[1m"
GRAY = "\033[90m"
RESET = "\033[0m"
PAPER_BANNER = f"  {TERRACOTTA}Paper{RESET} {BOLD}Blog{RESET}"
_ALT_SCREEN_ENTER = "\033[?1049h"
_ALT_SCREEN_LEAVE = "\033[?1049l"
_alt_screen_depth = 0


def enter_alt_screen() -> None:
    """Enter the terminal alternate buffer without disturbing scrollback."""

    global _alt_screen_depth
    if _alt_screen_depth == 0 and sys.stdout.isatty():
        sys.stdout.write(_ALT_SCREEN_ENTER)
        sys.stdout.flush()
    _alt_screen_depth += 1


def leave_alt_screen() -> None:
    global _alt_screen_depth
    if _alt_screen_depth <= 0:
        _alt_screen_depth = 0
        return
    _alt_screen_depth -= 1
    if _alt_screen_depth == 0 and sys.stdout.isatty():
        sys.stdout.write("\033[?25h" + _ALT_SCREEN_LEAVE)
        sys.stdout.flush()


def _restore_terminal_screen() -> None:
    """Best-effort atexit guard for exceptions and signal-driven exits."""

    global _alt_screen_depth
    if _alt_screen_depth > 0:
        _alt_screen_depth = 1
        leave_alt_screen()


atexit.register(_restore_terminal_screen)


@dataclass
class _PreviewState:
    revision: int = 0
    error: str = ""

    def bump(self) -> None:
        self.revision += 1
        self.error = ""


def _source_snapshot(posts_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not posts_dir.exists():
        return ()
    snapshot = []
    for path in sorted(posts_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot.append((str(path.relative_to(posts_dir)), stat.st_mtime_ns, stat.st_size))
    return tuple(snapshot)


def _watch_preview(config: PaperConfig, state: _PreviewState, stop: threading.Event) -> None:
    """Poll source files with no extra dependency and atomically rebuild previews."""

    previous = _source_snapshot(config.posts_dir)
    try:
        build_site(config, include_drafts=True, live_reload=True)
        state.bump()
    except Exception as exc:  # pragma: no cover - shown in the running terminal
        state.error = str(exc)
    while not stop.wait(0.25):
        current = _source_snapshot(config.posts_dir)
        if current == previous:
            continue
        try:
            build_site(config, include_drafts=True, live_reload=True)
        except Exception as exc:  # keep serving the last good output
            state.error = str(exc)
            previous = current
            print(f"\n⚠️ 预览重建失败，继续保留上一次结果：{exc}", file=sys.stderr)
        else:
            previous = current
            state.bump()
            print("\n↻ Markdown 已更新，浏览器即将自动刷新。")


def _error(message: str, code: int = 2) -> int:
    print(f"❌ {message}", file=sys.stderr)
    return code


def _clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")


def _read_terminal_key() -> str:
    descriptor = sys.stdin.fileno()
    first = os.read(descriptor, 1)
    if first != b"\x1b":
        return first.decode("utf-8", errors="ignore")
    sequence = bytearray(first)
    while select.select([descriptor], [], [], 0.025)[0] and len(sequence) < 3:
        sequence.extend(os.read(descriptor, 1))
    return bytes(sequence).decode("utf-8", errors="ignore")


def _menu_window(total: int, selected: int, *, reserved_lines: int) -> tuple[int, int]:
    terminal_lines = shutil.get_terminal_size(fallback=(100, 24)).lines
    capacity = max(3, terminal_lines - reserved_lines)
    if total <= capacity:
        return 0, total
    start = max(0, min(selected - capacity // 2, total - capacity))
    return start, start + capacity


def _terminal_menu(
    title: str,
    options: list[tuple[str, str, str]],
    *,
    footer_message: str = "",
) -> str | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    if not options:
        return None
    selected = 0
    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    enter_alt_screen()
    try:
        tty.setcbreak(descriptor)
        sys.stdout.write("\033[?25l")
        while True:
            _clear_screen()
            print(PAPER_BANNER)
            print(f"\n{title}\n")
            start, end = _menu_window(len(options), selected, reserved_lines=7 + title.count("\n") + bool(footer_message))
            if start:
                print(f"{GRAY}  ↑ 还有 {start} 项{RESET}")
            for index in range(start, end):
                _key, label, description = options[index]
                active = index == selected
                prefix = f"{TERRACOTTA}> {index + 1}.{RESET}" if active else f"  {index + 1}."
                label_cell = f"{label:<11}"
                rendered_label = f"{TERRACOTTA}{label_cell}{RESET}" if active else label_cell
                rendered_desc = f"{TERRACOTTA}{description}{RESET}" if active else f"{GRAY}{description}{RESET}"
                print(f"{prefix}  {rendered_label}  {rendered_desc}")
            if end < len(options):
                print(f"{GRAY}  ↓ 还有 {len(options) - end} 项{RESET}")
            print(f"\n{GRAY}↑↓ / kj  |  enter 选择  |  数字键直达  |  esc / q 返回{RESET}")
            if footer_message:
                print(f"{TERRACOTTA}{footer_message}{RESET}")
            sys.stdout.flush()
            key = _read_terminal_key()
            if key in {"\x1b[A", "k", "K"}:
                selected = (selected - 1) % len(options)
            elif key in {"\x1b[B", "j", "J"}:
                selected = (selected + 1) % len(options)
            elif key in {"\r", "\n"}:
                return options[selected][0]
            elif key in {"q", "Q", "\x1b", "\x03"}:
                return None
            elif key.isdigit() and 1 <= int(key) <= len(options):
                return options[int(key) - 1][0]
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        leave_alt_screen()


def _terminal_multiselect(title: str, options: list[tuple[str, str, str]]) -> list[str]:
    if not sys.stdin.isatty() or not sys.stdout.isatty() or not options:
        return []
    selected_index = 0
    checked: set[str] = set()
    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    enter_alt_screen()
    try:
        tty.setcbreak(descriptor)
        sys.stdout.write("\033[?25l")
        while True:
            _clear_screen()
            print(PAPER_BANNER)
            print(f"\n{title}\n")
            start, end = _menu_window(len(options), selected_index, reserved_lines=7 + title.count("\n"))
            if start:
                print(f"{GRAY}  ↑ 还有 {start} 项{RESET}")
            for index in range(start, end):
                key, label, description = options[index]
                active = index == selected_index
                mark = "[x]" if key in checked else "[ ]"
                prefix = f"{TERRACOTTA}> {mark}{RESET}" if active else f"  {mark}"
                rendered = f"{TERRACOTTA}{label}{RESET}" if active else label
                print(f"{prefix} {rendered}  {GRAY}{description}{RESET}")
            if end < len(options):
                print(f"{GRAY}  ↓ 还有 {len(options) - end} 项{RESET}")
            print(f"\n{GRAY}空格勾选  |  ↑↓ / kj 移动  |  enter 提交  |  esc / q 取消{RESET}")
            sys.stdout.flush()
            key = _read_terminal_key()
            if key in {"\x1b[A", "k", "K"}:
                selected_index = (selected_index - 1) % len(options)
            elif key in {"\x1b[B", "j", "J"}:
                selected_index = (selected_index + 1) % len(options)
            elif key == " ":
                option_key = options[selected_index][0]
                checked.discard(option_key) if option_key in checked else checked.add(option_key)
            elif key in {"\r", "\n"}:
                return [key for key, _label, _description in options if key in checked]
            elif key in {"q", "Q", "\x1b", "\x03"}:
                return []
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        leave_alt_screen()


def _pause() -> None:
    if not sys.stdin.isatty():
        return
    input("\n按 Enter 返回菜单……")


def _has_config() -> bool:
    return config_path().exists()


def _require_linked() -> PaperConfig | None:
    if not _has_config():
        _error("尚未关联 Markdown 目录。请先执行 paper link，或使用 paper init 创建标准目录。")
        return None
    try:
        return load_config(create=True)
    except ConfigError as exc:
        _error(str(exc))
        return None


def _folder_picker() -> Path | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose folder with prompt "选择 Paper 文章目录")'],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return Path(result.stdout.strip()).expanduser().resolve() if result.returncode == 0 and result.stdout.strip() else None


def _file_picker() -> Path | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose file with prompt "选择 Paper 网站图标")'],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return Path(result.stdout.strip()).expanduser().resolve() if result.returncode == 0 and result.stdout.strip() else None


def _install_favicon_file(config: PaperConfig, source: Path) -> PaperConfig | None:
    allowed = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
    suffix = source.suffix.lower()
    if not source.is_file() or suffix not in allowed:
        _error("图标文件必须是 SVG、PNG、JPG、WebP 或 ICO", 1)
        return None
    assets = config.posts_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / f"favicon{suffix}"
    shutil.copy2(source, target)
    return save_config(config, icon=f"assets/{target.name}")


def _editor_installed(command: str, app_name: str) -> bool:
    return shutil.which(command) is not None or (sys.platform == "darwin" and (Path("/Applications") / f"{app_name}.app").exists())


def cmd_brand_config(config: PaperConfig) -> int:
    while True:
        icon_label = "预设 P 图标" if config.icon.strip() == DEFAULT_ICON_SVG else "已自定义"
        action = _terminal_menu(
            "🏠 Paper 首页与品牌配置\n（使用 ↑/↓ 移动，enter 确认，esc 返回上一级）",
            [
                ("color", "🎨 网站高亮颜色", f"当前 [{config.color}]"),
                ("icon", "🖼️ 网站品牌图标", f"{icon_label} / 文件 / 粘贴代码"),
                ("back", "↩ 返回", "返回配置上级"),
            ],
        )
        if action in {None, "back"}:
            return 0
        if action == "color":
            value = input(f"高亮颜色 HEX（当前 {config.color}）：").strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                _error("颜色必须是 #D97757 这样的六位 HEX", 1)
                _pause()
                continue
            config = save_config(config, color=value.upper())
        elif action == "icon":
            icon_action = _terminal_menu(
                "选择网站品牌图标来源：",
                [
                    ("default", "预设 P 图标", "恢复 Paper 默认 favicon"),
                    ("file", "选择图片文件", "复制到文章目录 assets/"),
                    ("paste", "粘贴 SVG / Data URI", "直接保存图标代码"),
                    ("back", "返回", "不修改"),
                ],
            )
            if icon_action == "default":
                config = save_config(config, icon=DEFAULT_ICON_SVG)
            elif icon_action == "file":
                source = _file_picker()
                if source is None:
                    raw_path = input("图标文件路径（留空取消）：").strip()
                    source = Path(raw_path).expanduser().resolve() if raw_path else None
                if source is not None:
                    config = _install_favicon_file(config, source) or config
            elif icon_action == "paste":
                value = input("粘贴一行 SVG、Data URI 或图片 URL：").strip()
                if value and ("<svg" in value.lower() or value.startswith(("data:image/", "http://", "https://", "assets/"))):
                    config = save_config(config, icon=value)
                elif value:
                    _error("无法识别图标内容", 1)
                    _pause()


def cmd_config() -> int:
    try:
        config = load_config(create=True)
    except ConfigError as exc:
        return _error(str(exc))
    if not sys.stdin.isatty():
        pages = "（未配置远程）"
        if config.git_remote:
            info = normalize_git_remote(config.git_remote)
            if info:
                pages = info.pages_url
        print(
            f"文章目录：{config.posts_dir}\n编辑器：{config.editor}\n高亮颜色：{config.color}\n"
            f"网站图标：{'已配置' if config.icon else '未配置'}\nGit 远程：{config.git_remote or '未配置'}\n"
            f"Pages 地址：{pages}"
        )
        return 0
    while True:
        _state, readiness_label = _deployment_readiness(config)
        remote_info = normalize_git_remote(config.git_remote)
        action = _terminal_menu(
            "⚙️ Paper 配置控制台",
            [
                ("brand", "首页与品牌", "高亮颜色 / Favicon 图标"),
                ("editor", "默认编辑器", f"当前 {config.editor}"),
                ("link", "关联文章目录", str(config.posts_dir)),
                ("remote", "GitHub 远程", f"当前 {remote_info.owner}/{remote_info.repo} · 点入可重新绑定" if remote_info else "未配置 · 引导创建仓库"),
                ("pages-url", "站点地址", "Pages 地址 / 自定义域名"),
                ("test-conn", "测试连接", "检查 Git 与远程可达性"),
                ("status", "查看完整配置", f"路径 / 仓库 / 部署（{readiness_label}）"),
                ("back", "返回", "返回主菜单"),
            ],
        )
        if action in {None, "back"}:
            return 0
        if action == "brand":
            cmd_brand_config(config)
            config = load_config(create=True)
        elif action == "editor":
            candidates = [
                ("default", "系统默认", "macOS 默认 Markdown 应用"),
                ("code", "Visual Studio Code", "已安装" if _editor_installed("code", "Visual Studio Code") else "未检测到"),
                ("cursor", "Cursor", "已安装" if _editor_installed("cursor", "Cursor") else "未检测到"),
                ("typora", "Typora", "已安装" if _editor_installed("typora", "Typora") else "未检测到"),
                ("obsidian", "Obsidian", "已安装" if _editor_installed("obsidian", "Obsidian") else "未检测到"),
                ("back", "返回", "不修改"),
            ]
            editor = _terminal_menu("选择新建文章后自动打开的编辑器：", candidates)
            if editor not in {None, "back"}:
                config = save_config(config, editor=editor)
        elif action == "link":
            cmd_link(None)
            config = load_config(create=True)
        elif action == "remote":
            config = cmd_remote_entry(config)
        elif action == "pages-url":
            config = cmd_pages_url(config)
            _pause()
        elif action == "test-conn":
            _clear_screen()
            cmd_test_connection(config)
            _pause()
        elif action == "status":
            _clear_screen()
            cmd_status()
            _pause()


def _deployment_readiness(config: PaperConfig) -> tuple[str, str]:
    """Local-only deployment readiness, used for the dashboard menu label.

    Never touches the network; the ambiguous ``pushed`` state is refined in
    cmd_status with a single short ls-remote probe.
    """

    if not config.git_remote:
        return "not-configured", "未配置"
    info = normalize_git_remote(config.git_remote)
    if info is None or shutil.which("git") is None:
        return "unverified", "未校验"
    if not (config.site_dir / ".git").exists():
        return "unverified", "未校验"
    origin = _managed_origin(config)
    if origin is None or origin != info.ssh_url:
        return "unverified", "未校验"
    local = _git(config, "rev-parse", "--verify", "--quiet", "refs/heads/gh-pages", capture=True)
    if local.returncode == 0:
        return "pushed", "已推送"
    return "ready", "已就绪"


def _gh_pages_pushed(config: PaperConfig) -> bool:
    """Offline check that a publish has pushed gh-pages.

    ``git subtree push`` leaves the remote-tracking ref
    ``refs/remotes/origin/gh-pages`` behind (it does not create a local
    branch), so its presence is the reliable signal that gh-pages exists.
    """
    probe = _git(config, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/gh-pages", capture=True)
    return probe.returncode == 0


def _prompt(message: str) -> str | None:
    """Read a line, stripping whitespace; None means the user cancelled (EOF/Interrupt)."""
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        return None


def _confirm_continue(message: str) -> bool:
    """True when the user pressed Enter to proceed; False when they cancelled
    (EOF/Interrupt) or typed anything to abort. Shared by the save-confirm and
    wizard step prompts that follow the "Enter continues, text cancels" idiom."""
    answer = _prompt(message)
    return not (answer is None or answer)


def _confirm_and_save_remote(config: PaperConfig, info: GitRemoteInfo) -> PaperConfig | None:
    """Preview, confirm, handle a mismatched origin, save, and bind the managed origin.

    Returns the updated config, or None if the user cancelled at any step —
    nothing is changed in that case. Shared by the wizard, the manage entry,
    and the direct address-input flow.
    """
    origin = _managed_origin(config)
    print("\n请确认以下信息：")
    print(f"  仓库所有者：{info.owner}")
    print(f"  仓库名称：{info.repo}")
    print(f"  Remote URL：{info.ssh_url}")
    print(f"  预期 Pages URL：{info.pages_url}")
    if origin and origin != info.ssh_url:
        print(f"  ⚠️ 托管仓库当前 origin：{origin}（与将要保存的不一致）")
    if not _confirm_continue("\n按 Enter 确认保存（输入任意内容取消）："):
        print("已取消。")
        return None
    if origin and origin != info.ssh_url:
        answer = _prompt("origin 不一致，输入 YES 替换托管仓库 origin（其他内容取消）：")
        if answer != "YES":
            print("已取消，未修改任何配置。")
            return None
    saved = save_config(config, git_remote=info.ssh_url)
    _, message = _bind_managed_origin(saved, info.ssh_url)
    if message:
        print(f"⚠️ {message}")
    print(f"✅ 已保存 GitHub 远程：{info.ssh_url}")
    print(f"   预期站点：{info.pages_url}")
    return saved


def cmd_remote_entry(config: PaperConfig) -> PaperConfig:
    """The 远程 option always runs the guided wizard — first-time setup and
    re-binding both flow through it. The wizard is state-aware: an existing
    binding is shown up front, the create-repo step is skipped, and pasting a
    new address re-binds (replacing the origin when it differs).
    """

    _clear_screen()
    return cmd_remote_wizard(config)


def cmd_remote_wizard(config: PaperConfig) -> PaperConfig:
    """Guided 4-step flow: create repo, paste address, confirm, publish + enable Pages.

    Runs for first-time setup and re-binding alike. When a remote is already
    bound it is shown up front and the create-repo step is skipped; pasting a
    new address re-binds through the same confirm/save path.
    """

    if shutil.which("git") is None:
        _error("未找到 Git。请先安装 Git（macOS：brew install git），再来配置 GitHub 远程。", 1)
        _pause()
        return config
    existing = normalize_git_remote(config.git_remote)
    print("🧭 GitHub Pages 发布向导（4 步）\n")
    if existing:
        print(f"  当前已绑定：{existing.owner}/{existing.repo} · {existing.pages_url}")
        print("  要更换绑定，直接在第 2 步粘贴新地址；要保留当前绑定，留空退出。\n")
    print("第 1 步 / 共 4 步：创建仓库")
    if existing:
        print("  已绑定仓库，无需新建 —— 直接到第 2 步粘贴要绑定的地址。")
    else:
        opened = _open_browser("https://github.com/new")
        print(f"  {'已为你打开' if opened else '未能自动打开'} https://github.com/new —— 没有反应就复制这条网址手动打开。")
        print("  · 仓库名决定博客地址：你的用户名.github.io → 根路径；其它名字 → /仓库名 子路径")
        print("  · 已有仓库可跳过本步，直接到下一步粘贴地址")
        if not _confirm_continue("创建好仓库并复制地址后，按 Enter 继续（输入任意内容取消）："):
            print("已取消。")
            return config
    print("第 2 步 / 共 4 步：粘贴仓库地址")
    while True:
        raw = _prompt("  仓库地址（SSH / HTTPS / owner/repo 简写；留空取消）：")
        if raw is None or not raw:
            return config
        info = normalize_git_remote(raw)
        if info is None:
            _error("无法识别的 GitHub 仓库地址，请粘贴完整地址或 owner/repo 简写", 1)
            _pause()
            continue
        break
    print("第 3 步 / 共 4 步：核对并保存")
    result = _confirm_and_save_remote(config, info)
    if result is None:
        return config
    config = result
    print("\n第 4 步 / 共 4 步：发布并开启 GitHub Pages")
    print("  gh-pages 分支要等你发布之后才存在。现在可以直接发布，不用退出配置。")
    choice = _prompt("\n  现在发布并推送 gh-pages 吗？按 Enter 发布（会先勾选草稿）· 输入 skip 稍后自己发布：")
    if choice is None or choice.lower() == "skip":
        print("  已跳过发布。之后执行 paper publish，推送 gh-pages 后再来开启 Pages。")
    else:
        cmd_publish(all_posts=False, slugs=[])
        if _gh_pages_pushed(config):
            print("  ✅ 已推送 gh-pages —— 设置页里现在可以选到它了。")
        else:
            print("  ⚠️ 尚未推送 gh-pages（刚才可能没有勾选草稿）。")
            retry = _prompt("  要把当前站点（首页 + 已发布内容）先推上去吗？按 Enter 推送 · 输入 skip 稍后自己处理：")
            if not (retry is None or retry.lower() == "skip"):
                try:
                    build_site(config)
                    pushed = cmd_deploy() == 0
                except Exception:
                    pushed = False
                print("  ✅ 已推送 gh-pages。" if pushed else "  ⚠️ 推送未成功，稍后执行 paper publish 重试。")
    print(f"\n  设置页：{info.pages_settings_url}")
    open_choice = _prompt("  现在打开设置页选 gh-pages 吗？按 Enter 打开 · 输入 skip 稍后自己打开：")
    if open_choice is None or open_choice.lower() == "skip":
        print("  已跳过。发布后打开上面的设置页，在「Deploy from a branch」选 gh-pages 并保存。")
    else:
        opened = _open_browser(info.pages_settings_url)
        print(f"  {'已为你打开' if opened else '未能自动打开'}设置页。")
        print("  ⚠️ 若下拉框里没有 gh-pages，说明还没推送成功 —— 稍后执行 paper publish 再回来刷新。")
    _pause()
    return config


def cmd_pages_url(config: PaperConfig) -> PaperConfig:
    info = normalize_git_remote(config.git_remote) if config.git_remote else None
    derived = info.pages_url if info else "（需先配置 GitHub 远程）"
    print(f"推导的 Pages 地址：{derived}")
    print(f"当前站点地址（siteUrl）：{config.site_url or '未设置 —— 构建时自动使用推导值'}")
    try:
        raw = input("自定义站点地址（留空清除自定义，恢复自动推导）：").strip()
    except (EOFError, KeyboardInterrupt):
        print("已取消。")
        return config
    return save_config(config, site_url=raw)


def cmd_test_connection(config: PaperConfig) -> int:
    if shutil.which("git") is None:
        return _error("系统未找到 Git。")
    info = normalize_git_remote(config.git_remote) if config.git_remote else None
    if info is None:
        return _error("尚未配置有效的 GitHub 远程，请先在「GitHub 远程」设置。")
    print(f"测试远程：{info.ssh_url}")
    try:
        result = subprocess.run(
            ["git", "ls-remote", info.ssh_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return _error("连接超时（>10 秒）。请检查网络与 SSH 认证。")
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return _error("远程不可达或认证失败。")
    print("✅ Git 可用，远程仓库可达。")
    return 0


def cmd_link(path_arg: str | None) -> int:
    target = Path(path_arg).expanduser().resolve() if path_arg else _folder_picker()
    if target is None and not sys.stdin.isatty():
        return _error("非交互环境必须传入文章目录，例如 paper link ~/Documents/Paper/posts")
    if target is None:
        try:
            answer = input("文章目录绝对路径（留空取消）：").strip()
        except (EOFError, KeyboardInterrupt):
            return _error("已取消关联", 1)
        if not answer:
            return _error("已取消关联", 1)
        target = Path(answer).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    try:
        config = load_config()
    except ConfigError as exc:
        return _error(str(exc))
    save_config(config, posts_dir=target)
    print(f"✅ 已关联文章目录：{target}")
    return 0


def cmd_init() -> int:
    DEFAULT_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    return cmd_link(str(DEFAULT_POSTS_DIR))


def _slug(title: str) -> str:
    import re

    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", title.lower(), flags=re.UNICODE).strip("-")
    return value or f"post-{int(time.time())}"


def _open_editor(path: Path, config: PaperConfig) -> None:
    editor = config.editor.strip().lower()
    if editor == "none" or not sys.stdin.isatty():
        return
    try:
        if editor in {"default", "system", "open"} and sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif editor in {"vscode", "code"}:
            subprocess.Popen(["code", str(path)])
        elif editor == "cursor":
            subprocess.Popen(["cursor", str(path)])
        elif editor in {"typora", "obsidian", "iawriter", "macdown"} and sys.platform == "darwin":
            app_names = {"typora": "Typora", "obsidian": "Obsidian", "iawriter": "iA Writer", "macdown": "MacDown"}
            subprocess.Popen(["open", "-a", app_names[editor], str(path)])
        elif editor:
            subprocess.Popen([editor, str(path)])
    except OSError as exc:
        print(f"⚠️ 无法打开编辑器，文章已创建：{exc}")


def cmd_new(title: str | None) -> int:
    config = _require_linked()
    if config is None:
        return 2
    if not title:
        if not sys.stdin.isatty():
            return _error("非交互环境必须传入标题，例如 paper new 'Hello Paper'")
        try:
            title = input("文章标题：").strip()
        except (EOFError, KeyboardInterrupt):
            return _error("已取消新建", 1)
    if not title:
        return _error("标题不能为空", 1)
    if any(character in title for character in "\r\n"):
        return _error("标题不能包含换行", 1)
    target = config.posts_dir / f"{_slug(title)}.md"
    if target.exists():
        return _error(f"文章已存在：{target.name}", 1)
    today = dt.date.today().isoformat()
    target.parent.mkdir(parents=True, exist_ok=True)
    escaped_title = title.replace('"', '\\"')
    target.write_text(
        f'---\ntitle: "{escaped_title}"\ndate: {today}\npublished: false\n---\n\n写下你的随想……\n',
        encoding="utf-8",
    )
    _open_editor(target, config)
    print(f"✅ 已创建草稿：{target}")
    return 0


def _list_items(config: PaperConfig) -> list[Post]:
    """Return the fixed homepage followed by articles ordered by modification time."""

    index_path = config.posts_dir / "index.md"
    if index_path.exists():
        metadata, body = parse_frontmatter(index_path.read_text(encoding="utf-8"))
        modified_time = index_path.stat().st_mtime
        modified_date = dt.date.fromtimestamp(modified_time).isoformat()
        title = str(metadata.get("title") or config.site_name)
    else:
        body = DEFAULT_INDEX
        modified_time = 0.0
        modified_date = "—"
        title = config.site_name
    homepage = Post(
        slug="__home__",
        title=title,
        date=modified_date,
        published=True,
        description="",
        content=body,
        source_path=index_path,
        modified_time=modified_time,
        modified_date=modified_date,
    )
    return [homepage, *discover_posts(config.posts_dir)]


def cmd_list() -> int:
    config = _require_linked()
    if config is None:
        return 2
    posts = _list_items(config)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        for post in posts:
            marker = "🟢" if post.published else "⚪"
            homepage = "（首页）" if post.slug == "__home__" else ""
            print(f"{marker}  {post.modified_date}  {post.title}{homepage}")
        return 0

    while True:
        posts = _list_items(config)
        options = [
            (
                post.slug,
                f"{'🟢' if post.published else '⚪'} {post.modified_date}",
                f"{post.title}{'（首页）' if post.slug == '__home__' else ''}",
            )
            for post in posts
        ] + [("back", "返回", "返回主菜单")]
        selected = _terminal_menu("📄 Paper 文章控制台（🟢 已上线　⚪ 草稿或已下线）", options)
        if selected in {None, "back"}:
            return 0
        post = next((item for item in posts if item.slug == selected), None)
        if post is None:
            continue
        if post.slug == "__home__":
            action = _terminal_menu(
                f"首页操作：{post.title}",
                [
                    ("edit", "编辑首页", "使用默认编辑器打开 index.md"),
                    ("back", "返回", "返回文章列表"),
                ],
            )
            if action == "edit":
                if not post.source_path.exists():
                    post.source_path.write_text(DEFAULT_INDEX, encoding="utf-8")
                _open_editor(post.source_path, config)
            continue
        action = _terminal_menu(
            f"文章操作：{post.title}",
            [
                ("edit", "编辑", "使用默认编辑器打开 Markdown"),
                ("archive" if post.published else "publish", "下架" if post.published else "发布", "重新构建站点"),
                ("delete", "删除", "移动到废纸篓，可恢复"),
                ("back", "返回", "返回文章列表"),
            ],
        )
        if action == "edit":
            _open_editor(post.source_path, config)
        elif action == "publish":
            cmd_publish(False, [post.slug])
            _pause()
        elif action == "archive":
            set_post_published(post.source_path, False)
            build_site(config)
            print(f"✅ 已下架：{post.title}")
            _pause()
        elif action == "delete":
            confirmation = input(f"将《{post.title}》移动到废纸篓？按 Enter 确认删除（输入任意内容取消）：").strip()
            if confirmation:
                continue
            trash_dir = Path.home() / ".Trash" if sys.platform == "darwin" else config.site_dir / ".trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            target = trash_dir / post.source_path.name
            counter = 1
            while target.exists():
                target = trash_dir / f"{post.source_path.stem}-{counter}{post.source_path.suffix}"
                counter += 1
            shutil.move(str(post.source_path), str(target))
            build_site(config)
            print(f"✅ 已移动到废纸篓：{target}")
            _pause()


def cmd_build(preview: bool = False) -> int:
    config = _require_linked()
    if config is None:
        return 2
    output = build_site(config, include_drafts=preview)
    print(f"✅ 已生成静态站点：{output}")
    return 0


class _PreviewHandler(http.server.SimpleHTTPRequestHandler):
    preview_state: _PreviewState | None = None

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/.paper-revision":
            revision = self.preview_state.revision if self.preview_state else 0
            payload = str(revision).encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


class _PreviewServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url))
    except webbrowser.Error:
        return False


def cmd_serve(port: int) -> int:
    config = _require_linked()
    if config is None:
        return 2
    preview_config = replace(config, site_dir=config.site_dir / ".preview")
    output = build_site(preview_config, include_drafts=True, live_reload=True)
    preview_state = _PreviewState()
    _PreviewHandler.preview_state = preview_state
    stop_watcher = threading.Event()
    watcher = threading.Thread(
        target=_watch_preview,
        args=(preview_config, preview_state, stop_watcher),
        name="paper-preview-watcher",
        daemon=True,
    )
    watcher.start()
    handler = partial(_PreviewHandler, directory=str(output))
    try:
        try:
            server = _PreviewServer(("127.0.0.1", port), handler)
        except OSError:
            server = _PreviewServer(("127.0.0.1", 0), handler)
            print(f"⚠️ 端口 {port} 已被占用，已改用随机端口。")
        with server:
            actual_port = server.server_address[1]
            preview_url = f"http://127.0.0.1:{actual_port}"
            print(f"🌐 Paper 预览（包含草稿，仅本机可访问）：{preview_url}")
            opened = _open_browser(preview_url)
            print("已在默认浏览器中打开。" if opened else "未能自动打开浏览器，请复制上方地址。")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("\n已停止预览。")
    finally:
        stop_watcher.set()
        watcher.join(timeout=1)
        shutil.rmtree(preview_config.site_dir, ignore_errors=True)
    return 0


def _git(config: PaperConfig, *args: str, capture: bool = False, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(config.site_dir), *args],
        check=False,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def _run_with_spinner(message: str, argv: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[str] | None:
    """Run a blocking subprocess, animating a loading spinner on a TTY while it works.

    Returns the CompletedProcess, or None if it timed out. On non-TTY output the
    spinner is skipped (tests and pipes stay deterministic) and the process just
    runs quietly, captured.
    """
    if not (sys.stdout.isatty() and sys.stderr.isatty()):
        try:
            return subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop = threading.Event()
    result: dict[str, object] = {}

    def _run() -> None:
        try:
            result["cp"] = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timeout"] = True
        finally:
            stop.set()

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    index = 0
    label = f"  {message} "
    while not stop.is_set():
        sys.stdout.write("\r" + label + frames[index % len(frames)])
        sys.stdout.flush()
        index += 1
        time.sleep(0.08)
    worker.join()
    sys.stdout.write("\r" + " " * (len(label) + 1) + "\r")
    sys.stdout.flush()
    if "timeout" in result:
        return None
    return result.get("cp")  # type: ignore[return-value]


def _managed_origin(config: PaperConfig) -> str | None:
    """Return the managed repository's current origin, or None."""
    if not (config.site_dir / ".git").exists():
        return None
    result = _git(config, "remote", "get-url", "origin", capture=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def _bind_managed_origin(config: PaperConfig, url: str) -> tuple[bool, str | None]:
    """Bind the managed repository's origin to a canonical remote, locally only."""
    if shutil.which("git") is None:
        return False, "未找到 Git，托管仓库 origin 未绑定（配置已保存）。"
    config.site_dir.mkdir(parents=True, exist_ok=True)
    if not (config.site_dir / ".git").exists() and _git(config, "init").returncode != 0:
        return False, "无法初始化托管仓库。"
    current = _managed_origin(config)
    if current == url:
        return True, None
    if current is None:
        ok = _git(config, "remote", "add", "origin", url).returncode == 0
    else:
        ok = _git(config, "remote", "set-url", "origin", url).returncode == 0
    if not ok:
        return False, "无法绑定托管仓库 origin。"
    return True, None


def cmd_deploy() -> int:
    config = _require_linked()
    if config is None:
        return 2
    if not config.git_remote:
        return _error("尚未配置 GitHub remote。请先在 ~/.paper/config.json 设置 gitRemote。")
    if shutil.which("git") is None:
        return _error("系统未找到 Git，已保留本地静态输出。")
    config.site_dir.mkdir(parents=True, exist_ok=True)
    if not (config.site_dir / ".git").exists() and _git(config, "init").returncode != 0:
        return _error("无法初始化 Paper 托管仓库")
    remotes = _git(config, "remote", capture=True)
    if not remotes.stdout.strip() and _git(config, "remote", "add", "origin", config.git_remote).returncode != 0:
        return _error("无法绑定 GitHub remote")
    if remotes.stdout.strip():
        current_remote = _git(config, "remote", "get-url", "origin", capture=True)
        if current_remote.returncode != 0 or current_remote.stdout.strip() != config.git_remote:
            return _error("托管仓库的 origin 与 Paper 配置不一致，请先确认 remote，避免推送到错误仓库。")
    print("  · 暂存并提交站点更新……")
    if _git(config, "add", "out", capture=True).returncode != 0:
        return _error("无法暂存静态输出")
    committed = _git(config, "commit", "-m", "paper: update site", "--allow-empty", capture=True)
    if committed.returncode != 0:
        return _error("Git commit 失败，请检查 user.name、user.email 或 hooks。")
    print(f"  · 正在推送 gh-pages 到 {config.git_remote} ……")
    print("    （这一步需要联网上传，首次或网络较慢时可能要等几十秒到几分钟）")
    pushed = _run_with_spinner(
        "正在上传到 GitHub ……",
        ["git", "-C", str(config.site_dir), "subtree", "push", "--prefix", "out", "origin", "gh-pages"],
        timeout=600,
    )
    if pushed is None:
        print("❌ 推送超时（10 分钟仍未完成）——通常是网络无法稳定连接 GitHub。", file=sys.stderr)
        print("   建议：在配置面板「GitHub 远程 → 测试连接」检查连通性，网络恢复后执行 paper deploy 重试。", file=sys.stderr)
        return 1
    if pushed.returncode != 0:
        print("❌ GitHub Pages 推送失败；本地状态保留，可稍后执行 paper deploy 重试。", file=sys.stderr)
        if pushed.stderr:
            print(pushed.stderr.strip(), file=sys.stderr)
        print("   常见原因：网络连不上 GitHub、SSH 密钥 / 个人访问令牌未配置或已失效、仓库地址填错。", file=sys.stderr)
        print("   建议：配置面板「GitHub 远程 → 测试连接」检查连通性，或 ssh -T git@github.com 验证认证。", file=sys.stderr)
        return 1
    print("✅ 已推送 gh-pages；GitHub Pages 可能仍需数分钟完成构建。")
    return 0


def cmd_publish(all_posts: bool, slugs: list[str]) -> int:
    config = _require_linked()
    if config is None:
        return 2
    drafts = [post for post in discover_posts(config.posts_dir) if not post.published]
    if not all_posts and not slugs and sys.stdin.isatty() and sys.stdout.isatty():
        if not drafts:
            print("没有待发布的草稿。先 paper new 创建文章，之后再发布。")
            return 0
        slugs = _terminal_multiselect(
            "🚀 勾选要发布的草稿：",
            [(post.slug, post.title, post.date) for post in drafts],
        )
        if not slugs:
            print("未勾选任何草稿，已跳过发布。")
            return 0
    wanted = set(slugs)
    targets = drafts if all_posts else [post for post in drafts if post.slug in wanted]
    if not targets:
        if all_posts:
            return _error("没有待发布的草稿。先 paper new 创建文章。", 1)
        available = ", ".join(post.slug for post in drafts)
        if not slugs:
            return _error("未指定要发布的文章。用 paper publish <slug> 或 paper publish --all 指定。", 1)
        return _error(f"没有匹配的草稿：{', '.join(slugs)}。可用草稿：{available or '无'}", 1)
    originals = {post.source_path: post.source_path.read_text(encoding="utf-8") for post in targets}
    for post in targets:
        set_post_published(post.source_path, True)
    try:
        build_site(config)
    except Exception as exc:
        for source_path, original in originals.items():
            source_path.write_text(original, encoding="utf-8")
        return _error(f"构建失败，已恢复原稿状态：{exc}", 1)
    print(f"已将 {len(targets)} 篇文章标记为已发布，开始同步 GitHub Pages……")
    return cmd_deploy()


def cmd_status() -> int:
    config = _require_linked()
    if config is None:
        return 2
    posts = discover_posts(config.posts_dir)
    print(f"文章目录：{config.posts_dir}")
    print(f"托管目录：{config.site_dir}")
    print(f"文章数量：{len(posts)}（已发布 {sum(post.published for post in posts)}）")
    print(f"Git remote：{config.git_remote or '未配置'}")
    if config.git_remote:
        info = normalize_git_remote(config.git_remote)
        if info:
            print(f"Pages 地址：{info.pages_url}")
    print(f"静态输出：{'存在' if config.output_dir.exists() else '未构建'}")
    state, label = _deployment_readiness(config)
    print(f"部署就绪：{label}")
    if state == "pushed":
        _refine_pushed_state(config)
    return 0


def _refine_pushed_state(config: PaperConfig) -> None:
    """Distinguish ``pushed awaiting Pages`` from a failed push via one probe."""
    local = _git(config, "rev-parse", "--verify", "--quiet", "refs/heads/gh-pages", capture=True)
    if local.returncode != 0:
        return
    local_sha = local.stdout.strip()
    try:
        remote = subprocess.run(
            ["git", "-C", str(config.site_dir), "ls-remote", "origin", "refs/heads/gh-pages"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        print("  无法确认远程状态（可运行「测试连接」排查）。")
        return
    if remote.returncode != 0 or not remote.stdout.strip():
        print("  本地 gh-pages 领先远程，上次推送可能失败，可执行 paper deploy 重试。")
        return
    remote_sha = remote.stdout.strip().split()[0]
    if remote_sha == local_sha:
        print("  已推送，等待 GitHub Pages 构建（通常需数分钟）。")
    else:
        print("  本地 gh-pages 领先远程，上次推送可能失败，可执行 paper deploy 重试。")


def cmd_doctor() -> int:
    checks = []
    try:
        import markdown_it  # noqa: F401
        import pygments  # noqa: F401
        checks.append((True, "Markdown/Pygments 运行依赖"))
    except ImportError:
        checks.append((False, "Markdown/Pygments 运行依赖"))
    checks.append((sys.version_info >= (3, 11), f"Python >= 3.11（当前 {sys.version.split()[0]}）"))
    checks.append((shutil.which("git") is not None, "Git（仅发布需要）"))
    checks.append((_has_config(), f"Paper 配置（{config_path()}）"))
    for ok, name in checks:
        print(f"{'✅' if ok else '❌'} {name}")
    return 0 if all(ok for ok, _ in checks[:2]) else 1


def cmd_uninstall(clean: bool) -> int:
    print("Paper 程序由 Homebrew 管理，请使用：brew uninstall paper")
    if clean:
        answer = input("确认清理 ~/.paper（不会删除文章原稿）？输入 CLEAN：") if sys.stdin.isatty() else ""
        if answer == "CLEAN":
            shutil.rmtree(Path(os.environ.get("PAPER_HOME", Path.home() / ".paper")), ignore_errors=True)
            print("✅ 已清理 Paper 配置与托管站点。原稿目录未修改。")
        else:
            print("已取消清理。")
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper", description="极简 Python SSG 与写作 CLI")
    parser.add_argument("--version", action="version", version=f"paper {VERSION}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init", help="创建标准文章目录并关联")
    link = commands.add_parser("link", help="关联已有 Markdown 文章目录")
    link.add_argument("path", nargs="?")
    new = commands.add_parser("new", help="创建草稿")
    new.add_argument("title", nargs="?")
    commands.add_parser("list", aliases=["posts"], help="列出文章")
    commands.add_parser("build", help="生成生产静态站点")
    serve = commands.add_parser("serve", help="启动本地草稿预览")
    serve.add_argument("--port", type=int, default=8000)
    publish = commands.add_parser("publish", help="发布草稿并同步 GitHub Pages")
    publish.add_argument("slugs", nargs="*")
    publish.add_argument("--all", action="store_true")
    commands.add_parser("deploy", help="重试 GitHub Pages 部署")
    commands.add_parser("status", help="显示站点状态")
    commands.add_parser("config", help="打开方向键配置控制台")
    commands.add_parser("doctor", help="检查安装和运行环境")
    uninstall = commands.add_parser("uninstall", help="显示卸载指引，可选清理 Paper 数据")
    uninstall.add_argument("--clean", action="store_true")
    return parser


def run_dashboard() -> int:
    exit_armed = False
    enter_alt_screen()
    try:
        while True:
            action = _terminal_menu(
                "请使用方向键导航，Enter 或数字键选择对应的功能：",
                [
                    ("list", "list", "管理文章"),
                    ("new", "new", "新建文章并打开编辑器"),
                    ("config", "config", "设置路径、编辑器与品牌"),
                    ("publish", "publish", "选择草稿并发布"),
                    ("serve", "serve", "启动本地热更新预览"),
                    ("uninstall", "uninstall", "卸载与清理配置，保留原稿"),
                    ("quit", "quit", "退出 Paper"),
                ],
                footer_message="再按一次 Esc 或 Q 退出 Paper" if exit_armed else "",
            )
            if action is None:
                if exit_armed:
                    _clear_screen()
                    print("\n已退出 Paper。再见！\n")
                    return 0
                exit_armed = True
                continue
            exit_armed = False
            if action == "quit":
                _clear_screen()
                print("\n已退出 Paper。再见！\n")
                return 0
            if action == "list":
                cmd_list()
            elif action == "new":
                cmd_new(None)
                _pause()
            elif action == "config":
                cmd_config()
            elif action == "publish":
                cmd_publish(False, [])
                _pause()
            elif action == "serve":
                cmd_serve(8000)
            elif action == "uninstall":
                cmd_uninstall(True)
                _pause()
    finally:
        leave_alt_screen()


def _main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    if not raw_argv and sys.stdin.isatty():
        return run_dashboard()
    args = make_parser().parse_args(raw_argv)
    command = args.command
    if command == "init": return cmd_init()
    if command == "link": return cmd_link(args.path)
    if command == "new": return cmd_new(args.title)
    if command in {"list", "posts"}: return cmd_list()
    if command == "build": return cmd_build()
    if command == "serve": return cmd_serve(args.port)
    if command == "publish": return cmd_publish(args.all, args.slugs)
    if command == "deploy": return cmd_deploy()
    if command == "status": return cmd_status()
    if command == "config": return cmd_config()
    if command == "doctor": return cmd_doctor()
    if command == "uninstall": return cmd_uninstall(args.clean)
    make_parser().print_help()
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print("\n已退出 Paper。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
