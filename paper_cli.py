#!/usr/bin/env python3
"""The user-facing Paper command."""

from __future__ import annotations

import argparse
import atexit
import datetime as dt
import http.server
import json
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
import unicodedata
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from paper_runtime.core import (
    ConfigError,
    DEFAULT_COLOR,
    DEFAULT_ICON,
    DEFAULT_INDEX,
    GitRemoteInfo,
    PaperConfig,
    Post,
    _base_path,
    _has_github_pages_actions,
    build_site,
    config_path,
    discover_posts,
    load_config,
    load_local_config,
    normalize_git_remote,
    parse_frontmatter,
    save_config,
    set_post_published,
)
from paper_runtime.i18n import (
    LANGUAGE_LABELS,
    SUPPORTED_LANGUAGES,
    get_current_language,
    normalize_locale,
    resolve_language,
    set_current_language,
    t,
)

VERSION = "0.1.3-beta.2"
DEFAULT_POSTS_DIR = Path.home() / "Documents" / "Paper" / "posts"
TERRACOTTA = "\033[38;2;217;119;87m"
GREEN = "\033[32m"
BOLD = "\033[1m"
GRAY = "\033[90m"
RESET = "\033[0m"
PAPER_BANNER = f"  {TERRACOTTA}Paper{RESET} {BOLD}Blog{RESET}"
PREVIEW_POLL_SECONDS = 0.5
PREVIEW_DEBOUNCE_SECONDS = 2.0
UPDATE_CHECK_TTL_SECONDS = 6 * 60 * 60
UPDATE_FORMULA_RAW_URL = "https://raw.githubusercontent.com/ohmyangboy/homebrew-tap/main/Formula/paper.rb"
UPDATE_RELEASES_URL = "https://api.github.com/repos/ohmyangboy/paper-blog/releases?per_page=10"
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
    refresh_requested: threading.Event = field(default_factory=threading.Event, repr=False)
    refresh_completed: threading.Event = field(default_factory=threading.Event, repr=False)
    watcher_ready: threading.Event = field(default_factory=threading.Event, repr=False)

    def bump(self) -> None:
        self.revision += 1
        self.error = ""

    def request_refresh(self, *, timeout: float = 5.0) -> bool:
        """Ask the watcher to process pending changes before serving a document."""

        self.refresh_completed.clear()
        self.refresh_requested.set()
        return self.refresh_completed.wait(timeout)

    def finish_refresh(self) -> None:
        self.refresh_requested.clear()
        self.refresh_completed.set()


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
    """Poll sources and batch rebuilds after the current editing burst settles."""

    previous = _source_snapshot(config.posts_dir)
    state.watcher_ready.set()
    pending_since: float | None = None
    while not stop.is_set():
        refresh_now = state.refresh_requested.wait(PREVIEW_POLL_SECONDS)
        if stop.is_set():
            break
        current = _source_snapshot(config.posts_dir)
        if current != previous:
            previous = current
            pending_since = time.monotonic()
        should_rebuild = pending_since is not None and (
            refresh_now or time.monotonic() - pending_since >= PREVIEW_DEBOUNCE_SECONDS
        )
        if not should_rebuild:
            if refresh_now:
                state.finish_refresh()
            continue
        try:
            build_site(config, include_drafts=True, live_reload=True)
        except Exception as exc:  # keep serving the last good output
            state.error = str(exc)
            print(t("serve_rebuild_failed", exc=exc), file=sys.stderr)
        else:
            state.bump()
            print(t("serve_reloaded"))
        finally:
            pending_since = None
            if refresh_now:
                state.finish_refresh()


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
            print(f"\n  {title}\n")
            start, end = _menu_window(len(options), selected, reserved_lines=7 + title.count("\n") + bool(footer_message))
            if start:
                print(f"{GRAY}{t('menu_more_above', count=start)}{RESET}")
            for index in range(start, end):
                _key, label, description = options[index]
                active = index == selected
                prefix = f"{TERRACOTTA}> {index + 1}.{RESET}" if active else f"  {index + 1}."
                label_cell = f"{label:<11}"
                rendered_label = f"{TERRACOTTA}{label_cell}{RESET}" if active else label_cell
                rendered_desc = f"{TERRACOTTA}{description}{RESET}" if active else f"{GRAY}{description}{RESET}"
                print(f"{prefix}  {rendered_label}  {rendered_desc}")
            if end < len(options):
                print(f"{GRAY}{t('menu_more_below', count=len(options) - end)}{RESET}")
            print(f"\n  {GRAY}{t('menu_controls_hint')}{RESET}")
            if footer_message:
                print(f"  {TERRACOTTA}{footer_message}{RESET}")
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


def _terminal_multiselect(title: str, options: list[tuple[str, str, str]]) -> list[str] | None:
    """Pick a subset of options on a TTY.

    Returns the selected keys on Enter (possibly an empty list, meaning
    "continue without selecting"), or None on Esc/Q/Ctrl+C (meaning "cancel
    the whole operation"). Off-TTY and empty options return an empty list so
    callers treat them as "nothing selected, keep going".
    """
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
            print(f"\n  {title}\n")
            start, end = _menu_window(len(options), selected_index, reserved_lines=7 + title.count("\n"))
            if start:
                print(f"{GRAY}{t('menu_more_above', count=start)}{RESET}")
            for index in range(start, end):
                key, label, description = options[index]
                active = index == selected_index
                mark = "[x]" if key in checked else "[ ]"
                prefix = f"{TERRACOTTA}> {mark}{RESET}" if active else f"  {mark}"
                rendered = f"{TERRACOTTA}{label}{RESET}" if active else label
                print(f"{prefix} {rendered}  {GRAY}{description}{RESET}")
            if end < len(options):
                print(f"{GRAY}{t('menu_more_below', count=len(options) - end)}{RESET}")
            print(f"\n  {GRAY}{t('menu_multiselect_controls')}{RESET}")
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
                return None
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        leave_alt_screen()


def _pause() -> None:
    if not sys.stdin.isatty():
        return
    input(t("pause_prompt"))


def _has_config() -> bool:
    return config_path().exists()


def _require_linked(local: bool = False, local_dir: Path | str | None = None) -> PaperConfig | None:
    if local or local_dir is not None:
        target_dir = Path(local_dir or ".").expanduser().resolve()
        try:
            return load_local_config(target_dir)
        except ConfigError as exc:
            _error(str(exc))
            return None
    if not _has_config():
        _error(t("error_not_linked"))
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
        prompt_str = t("choose_posts_folder_prompt").replace('"', '\\"')
        result = subprocess.run(
            ["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt_str}")'],
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
        prompt_str = t("choose_favicon_prompt").replace('"', '\\"')
        result = subprocess.run(
            ["osascript", "-e", f'POSIX path of (choose file with prompt "{prompt_str}")'],
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
        _error(t("favicon_invalid_format"), 1)
        return None
    assets = config.posts_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / f"favicon{suffix}"
    shutil.copy2(source, target)
    return save_config(config, icon=f"assets/{target.name}")


def _app_picker() -> Path | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose file with prompt "选择用于打开 Markdown 文章的编辑器应用" default location (path to applications folder))',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    return Path(result.stdout.strip()).expanduser().resolve() if result.returncode == 0 and result.stdout.strip() else None


def _pick_custom_editor(config: PaperConfig) -> PaperConfig:
    source = _app_picker()
    if source is None:
        raw_path = _prompt(t("editor_custom_input"))
        if not raw_path:
            return config
        raw_path = raw_path.strip()
        if "/" in raw_path or raw_path.startswith("~") or Path(raw_path).exists():
            source_str = str(Path(raw_path).expanduser().resolve())
        else:
            source_str = raw_path
    else:
        source_str = str(source)

    if source_str:
        saved = save_config(config, editor=source_str)
        print(t("editor_set", editor=source_str))
        return saved
    return config


def _editor_installed(command: str, app_name: str) -> bool:
    if shutil.which(command) is not None:
        return True
    if sys.platform == "darwin":
        app_paths = [
            Path("/Applications") / f"{app_name}.app",
            Path.home() / "Applications" / f"{app_name}.app",
            Path("/System/Applications") / f"{app_name}.app",
        ]
        return any(p.exists() for p in app_paths)
    return False


def _set_highlight_color(config: PaperConfig) -> PaperConfig:
    value = _prompt(t("brand_color_prompt", color=config.color))
    if value is None:
        return config
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        _error(t("brand_color_hex_error"), 1)
        _pause()
        return config
    return save_config(config, color=value.upper())


def _set_icon(config: PaperConfig) -> PaperConfig:
    icon_action = _terminal_menu(
        t("brand_icon_source_title"),
        [
            ("default", "default", t("brand_icon_opt_default")),
            ("file", "file", t("brand_icon_opt_file")),
            ("paste", "paste", t("brand_icon_opt_paste")),
            ("back", "back", t("brand_icon_opt_back")),
        ],
    )
    if icon_action == "default":
        return save_config(config, icon=DEFAULT_ICON)
    if icon_action == "file":
        source = _file_picker()
        if source is None:
            raw_path = _prompt(t("brand_icon_file_prompt"))
            source = Path(raw_path).expanduser().resolve() if raw_path else None
        if source is not None:
            return _install_favicon_file(config, source) or config
    elif icon_action == "paste":
        value = _prompt(t("brand_icon_paste_prompt"))
        if value and ("<svg" in value.lower() or value.startswith(("data:image/", "http://", "https://", "assets/"))):
            return save_config(config, icon=value)
        if value:
            _error(t("brand_icon_unrecognized"), 1)
            _pause()
    return config


def _choose_editor(config: PaperConfig) -> PaperConfig:
    candidates = [
        ("default", "default", t("editor_default_system")),
        ("code", "code", t("editor_installed") if _editor_installed("code", "Visual Studio Code") else t("editor_not_detected")),
        ("cursor", "cursor", t("editor_installed") if _editor_installed("cursor", "Cursor") else t("editor_not_detected")),
        ("typora", "typora", t("editor_installed") if _editor_installed("typora", "Typora") else t("editor_not_detected")),
        ("obsidian", "obsidian", t("editor_installed") if _editor_installed("obsidian", "Obsidian") else t("editor_not_detected")),
        ("custom", "custom", t("editor_custom_option")),
        ("back", "back", t("brand_icon_opt_back")),
    ]
    editor = _terminal_menu(t("editor_picker_title"), candidates)
    if editor == "custom":
        return _pick_custom_editor(config)
    if editor not in {None, "back"}:
        saved = save_config(config, editor=editor)
        print(t("editor_set", editor=editor))
        return saved
    return config


def _set_image_compression(config: PaperConfig, state: str | None = None) -> PaperConfig:
    if state is None:
        state = _terminal_menu(
            t("compress_menu_title"),
            [
                ("on", "on", t("compress_opt_on")),
                ("off", "off", t("compress_opt_off")),
                ("back", "back", t("brand_icon_opt_back")),
            ],
        )
    if state in {None, "back"}:
        return config
    enabled = state == "on"
    saved = save_config(config, compress=enabled)
    state_label = t("state_on") if enabled else t("state_off")
    print(t("compress_feedback", state=state_label))
    return saved


def _set_language(config: PaperConfig, lang_code: str | None = None) -> PaperConfig:
    if lang_code is None:
        lang_code = _terminal_menu(
            t("lang_menu_title"),
            [
                ("zh_CN", "zh_CN", t("lang_option_zh")),
                ("en_US", "en_US", t("lang_option_en")),
                ("auto", "auto", t("lang_option_auto")),
                ("back", "back", t("cancel")),
            ],
        )
    if lang_code in {None, "back"}:
        return config
    norm = "auto" if lang_code.strip().lower() in {"auto", "system", "default"} else normalize_locale(lang_code)
    saved = save_config(config, language=norm)
    set_current_language(resolve_language(config_lang=norm))
    display_label = t("lang_option_auto") if norm == "auto" else LANGUAGE_LABELS.get(norm, norm)
    print(t("lang_set", lang=display_label))
    return saved


def cmd_brand_config(config: PaperConfig) -> int:
    while True:
        icon_label = t("brand_icon_zine") if config.icon.strip() == DEFAULT_ICON else t("brand_icon_customized")
        action = _terminal_menu(
            t("brand_menu_title"),
            [
                ("color", "color", t("brand_current_color", color=config.color)),
                ("icon", "icon", t("brand_icon_desc", icon_label=icon_label)),
                ("back", "back", t("brand_back_to_config")),
            ],
        )
        if action in {None, "back"}:
            return 0
        if action == "color":
            config = _set_highlight_color(config)
        elif action == "icon":
            config = _set_icon(config)


def cmd_config(
    config_cmd: str | None = None,
    home_cmd: str | None = None,
    compress_cmd: str | None = None,
    editor_name: str | None = None,
    lang_code: str | None = None,
    local: bool = False,
    local_dir: Path | str | None = None,
) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    if config_cmd is not None:
        return _run_config_leaf(config, config_cmd, home_cmd, compress_cmd, editor_name, lang_code)
    if not sys.stdin.isatty():
        pages = t("pages_need_remote")
        if config.git_remote:
            info = normalize_git_remote(config.git_remote)
            if info:
                pages = info.pages_url
        print(
            f"{t('status_posts_dir', path=config.posts_dir)}\n"
            f"{t('config_item_editor')}：{config.editor}\n"
            f"{t('brand_item_color')}：{config.color}\n"
            f"{t('brand_item_icon')}：{t('status_out_exists') if config.icon else t('status_not_set')}\n"
            f"{t('config_item_compress')}：{t('state_on') if config.compress else t('state_off')}\n"
            f"{t('config_item_language')}：{config.language}\n"
            f"{t('status_remote', remote=config.git_remote or t('status_not_set'))}\n"
            f"{t('status_pages_url', url=pages)}"
        )
        return 0
    while True:
        _state, readiness_label = _deployment_readiness(config)
        remote_info = normalize_git_remote(config.git_remote)
        title_prefix = t("config_menu_title") + (t("config_mode_prefix", dir_name=Path(local_dir or '.').resolve().name) if (local or local_dir is not None) else "")
        lang_display = t("lang_option_auto") if config.language == "auto" else LANGUAGE_LABELS.get(normalize_locale(config.language), config.language)
        action = _terminal_menu(
            title_prefix,
            [
                ("home", "home", t("config_item_brand_desc")),
                ("compress", "compress", f"{t('config_item_compress')} · {t('state_on') if config.compress else t('state_off')}"),
                ("editor", "editor", t("config_current_editor", editor=config.editor)),
                ("language", "language", t("config_current_language", lang=lang_display)),
                ("link", "link", str(config.posts_dir)),
                ("remote", "remote", t("config_remote_bound", owner=remote_info.owner, repo=remote_info.repo) if remote_info else t("config_remote_not_configured")),
                ("pages", "pages", t("config_item_pages_desc")),
                ("test", "test", t("config_item_test_desc")),
                ("status", "status", t("config_item_status_desc", readiness=readiness_label)),
                ("back", "back", t("config_item_back")),
            ],
        )
        if action in {None, "back"}:
            return 0
        if action == "home":
            cmd_brand_config(config)
            config = _require_linked(local=local, local_dir=local_dir) or config
        elif action == "compress":
            config = _set_image_compression(config)
        elif action == "editor":
            config = _choose_editor(config)
        elif action == "language":
            config = _set_language(config)
        elif action == "link":
            cmd_link(None)
            config = _require_linked(local=local, local_dir=local_dir) or config
        elif action == "remote":
            config = cmd_remote_entry(config)
        elif action == "pages":
            config = cmd_pages_url(config)
            _pause()
        elif action == "test":
            _clear_screen()
            cmd_test_connection(config)
            _pause()
        elif action == "status":
            _clear_screen()
            cmd_status(local=local, local_dir=local_dir)
            _pause()


def _run_config_leaf(
    config: PaperConfig,
    config_cmd: str,
    home_cmd: str | None,
    compress_cmd: str | None,
    editor_name: str | None = None,
    lang_code: str | None = None,
) -> int:
    """Run one config subcommand directly (paper config <cmd> [<sub>]) without the menu."""
    if config_cmd == "home":
        if home_cmd == "color":
            _set_highlight_color(config)
            return 0
        if home_cmd == "icon":
            _set_icon(config)
            return 0
        return cmd_brand_config(config)
    if config_cmd == "editor":
        if editor_name:
            if editor_name.lower() in {"custom", "picker", "browse"}:
                _pick_custom_editor(config)
            else:
                save_config(config, editor=editor_name)
                print(t("editor_set", editor=editor_name))
            return 0
        _choose_editor(config)
        return 0
    if config_cmd in {"lang", "language"}:
        _set_language(config, lang_code or editor_name)
        return 0
    if config_cmd == "compress":
        _set_image_compression(config, compress_cmd)
        return 0
    if config_cmd == "link":
        return cmd_link(None)
    if config_cmd == "remote":
        cmd_remote_entry(config)
        return 0
    if config_cmd == "pages":
        cmd_pages_url(config)
        _pause()
        return 0
    if config_cmd == "test":
        _clear_screen()
        return cmd_test_connection(config)
    if config_cmd == "status":
        _clear_screen()
        return cmd_status()
    return _error(t("config_unknown_subcmd", cmd=config_cmd), 1)


def _deployment_readiness(config: PaperConfig) -> tuple[str, str]:
    """Local-only deployment readiness, used for the dashboard menu label.

    Never touches the network; the ambiguous ``pushed`` state is refined in
    cmd_status with a single short ls-remote probe.
    """

    if _has_github_pages_actions(config.site_dir):
        return "actions", t("readiness_actions")
    if not config.git_remote:
        return "not-configured", t("readiness_not_configured")
    info = normalize_git_remote(config.git_remote)
    if info is None or shutil.which("git") is None:
        return "unverified", t("readiness_unverified")
    if not (config.site_dir / ".git").exists():
        return "unverified", t("readiness_unverified")
    origin = _managed_origin(config)
    if origin is None or origin != info.ssh_url:
        return "unverified", t("readiness_unverified")
    local = _git(config, "rev-parse", "--verify", "--quiet", "refs/heads/gh-pages", capture=True)
    if local.returncode == 0:
        return "pushed", t("readiness_pushed")
    return "ready", t("readiness_ready")


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


def _confirm_or_skip(message: str) -> bool:
    """Single-key confirmation: Enter = continue (True), any other key = cancel/skip (False).

    Shared by confirm-or-skip prompts across Paper. Reads a raw key on a TTY;
    falls back to line input off-TTY (Enter / empty line continues, anything else skips).
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        try:
            return not input(message).strip()
        except (EOFError, KeyboardInterrupt):
            return False
    sys.stdout.write(message)
    sys.stdout.flush()
    key = _read_terminal_key()
    sys.stdout.write("\n")
    sys.stdout.flush()
    return key in {"\r", "\n"}


def _wizard_steps() -> list[str]:
    return [t("wizard_step1_name"), t("wizard_step2_name"), t("wizard_step3_name"), t("wizard_step4_name")]


def _strip_ansi(text: str) -> str:
    """Remove ANSI SGR escape sequences so visible width can be measured."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _display_width(text: str) -> int:
    """Visible column width, counting CJK/wide glyphs as two columns."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def _wizard_header(current: int) -> None:
    """Top numbered stepper, Claude-settings style: the four steps as 1 2 3 4
    with the active number highlighted. Only the active marker moves between
    steps — the screen is redrawn in place, never appended downward."""
    parts = []
    steps = _wizard_steps()
    for index, name in enumerate(steps, start=1):
        if index < current:
            parts.append(f"{GREEN}✓ {index} {name}{RESET}")
        elif index == current:
            parts.append(f"{TERRACOTTA}{BOLD}● {index} {name}{RESET}")
        else:
            parts.append(f"{GRAY}{index} {name}{RESET}")
    print("  " + "    ".join(parts))


def _wizard_panel(title: str, body: list[tuple[str, str]]) -> None:
    """Render a bordered content panel.

    ``body`` rows are ``(kind, text)`` where ``kind`` is ``"hint"`` (dim gray
    instruction) or ``"content"`` (bold primary text) — the visual separation
    the wizard needs between guidance and the actual value to act on.
    """
    rows = [(kind, text) for kind, text in body]
    widths = [_display_width(title)] + [_display_width(text) for _, text in rows]
    width = max(widths)
    bar = "─" * (width + 2)
    print(f"  {GRAY}┌{bar}┐{RESET}")
    print(f"  {GRAY}│{RESET} {TERRACOTTA}{BOLD}{title}{RESET}" + " " * (width - _display_width(title)) + f" {GRAY}│{RESET}")
    for kind, text in rows:
        color = GRAY if kind == "hint" else BOLD
        print(f"  {GRAY}│{RESET} {color}{text}{RESET}" + " " * (width - _display_width(text)) + f" {GRAY}│{RESET}")
    print(f"  {GRAY}└{bar}┘{RESET}")


def _wizard_screen(current: int, title: str, body: list[tuple[str, str]]) -> None:
    """Clear and redraw the wizard for one step: numbered header on top, content
    panel below. Redrawing (not appending) makes advancing switch the header's
    active marker and swap the panel in place — the settings-style transition
    the wizard needs."""
    _clear_screen()
    _wizard_header(current)
    print()
    _wizard_panel(title, body)


def _confirm_and_save_remote(config: PaperConfig, info: GitRemoteInfo) -> PaperConfig | None:
    """Preview, confirm, handle a mismatched origin, save, and bind the managed origin.

    Returns the updated config, or None if the user cancelled at any step —
    nothing is changed in that case. Shared by the wizard, the manage entry,
    and the direct address-input flow.
    """
    origin = _managed_origin(config)
    body: list[tuple[str, str]] = [
        ("hint", t("wizard_verify_hint")),
        ("content", t("wizard_verify_owner", owner=info.owner)),
        ("content", t("wizard_verify_repo", repo=info.repo)),
        ("content", t("wizard_verify_remote", url=info.ssh_url)),
        ("content", t("wizard_verify_pages", pages_url=info.pages_url)),
    ]
    if origin and origin != info.ssh_url:
        body.append(("hint", t("wizard_origin_mismatch_warning", origin=origin)))
    _wizard_screen(3, t("wizard_step3_name"), body)
    if not _confirm_or_skip(t("wizard_confirm_save_prompt")):
        print(t("wizard_save_skipped"))
        return None
    if origin and origin != info.ssh_url:
        answer = _prompt(t("wizard_replace_origin_prompt"))
        if answer != "YES":
            print(t("wizard_save_cancelled"))
            return None
    saved = save_config(config, git_remote=info.ssh_url)
    result = _with_spinner(t("wizard_binding_origin_spinner"), _bind_managed_origin, saved, info.ssh_url)
    _, message = result if isinstance(result, tuple) else (False, t("wizard_bind_origin_failed"))
    if message:
        print(f"⚠️ {message}")
    print(t("remote_saved", remote=info.ssh_url, site_url=info.pages_url))
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

    Each step redraws the screen (``_wizard_screen``): a numbered header on top
    whose active marker switches in place, and a content panel below that swaps
    with it — the settings-style transition, never appended downward. Slow
    operations (binding the origin, building, pushing gh-pages) show a spinner.
    """

    if shutil.which("git") is None:
        _error(t("wizard_git_missing_error"), 1)
        _pause()
        return config
    existing = normalize_git_remote(config.git_remote)

    if existing:
        _wizard_screen(1, t("wizard_step1_name"), [
            ("content", t("wizard_step1_bound", owner=existing.owner, repo=existing.repo)),
            ("hint", t("wizard_step1_bound_hint")),
        ])
    else:
        opened = _open_browser("https://github.com/new")
        open_hint = (
            t("wizard_step1_open_success")
            if opened
            else t("wizard_step1_open_fail")
        )
        _wizard_screen(1, t("wizard_step1_name"), [
            ("hint", open_hint),
            ("hint", t("wizard_step1_hint_subpath")),
            ("hint", t("wizard_step1_hint_public")),
        ])
        _confirm_or_skip(t("wizard_step1_continue_prompt"))

    _wizard_screen(2, t("wizard_step2_name"), [
        ("hint", t("wizard_step2_formats_hint")),
        ("content", "git@github.com:用户名/仓库.git"),
        ("content", "https://github.com/用户名/仓库"),
        ("content", "用户名/仓库"),
    ])
    while True:
        raw = _prompt(t("wizard_enter_remote_prompt"))
        if raw is None or not raw:
            return config
        info = normalize_git_remote(raw)
        if info is None:
            _error(t("wizard_remote_invalid"), 1)
            _pause()
            continue
        break

    result = _confirm_and_save_remote(config, info)
    if result is None:
        return config
    config = result

    _wizard_screen(4, t("wizard_step4_name"), [
        ("hint", t("wizard_step4_desc")),
    ])
    if _confirm_or_skip(t("wizard_step4_publish_prompt")):
        cmd_publish(all_posts=False, slugs=[])
        if _gh_pages_pushed(config):
            print(f"  {t('wizard_pushed_gh_pages')}")
        else:
            print(t("wizard_step4_not_pushed_yet"))
            if _confirm_or_skip(t("wizard_step4_push_all_prompt")):
                try:
                    _with_spinner(t("publish_rebuilding"), build_site, config)
                    pushed = cmd_deploy() == 0
                except Exception:
                    pushed = False
                print(t("wizard_step4_pushed_ok") if pushed else t("wizard_step4_push_failed"))
    else:
        print(t("wizard_skipped_publish"))
    print(f"\n  设置页：{info.pages_settings_url}")
    if _confirm_or_skip(t("wizard_step4_open_settings_prompt")):
        opened = _open_browser(info.pages_settings_url)
        print(f"  {t('wizard_settings_opened') if opened else t('wizard_settings_open_fail')}")
        print(t("wizard_step4_settings_warning"))
    else:
        print(f"  ⏭ {t('wizard_settings_skipped', url=info.pages_settings_url)}")
    print(f"\n  {t('wizard_done')}")
    _pause()
    return config


def cmd_pages_url(config: PaperConfig) -> PaperConfig:
    info = normalize_git_remote(config.git_remote) if config.git_remote else None
    derived = info.pages_url if info else t("pages_need_remote")
    print(t("pages_derived_url", url=derived))
    print(t("pages_current_site_url", url=config.site_url or t("pages_site_url_unset")))
    try:
        raw = input(t("pages_custom_prompt")).strip()
    except (EOFError, KeyboardInterrupt):
        print(t("pages_cancelled"))
        return config
    return save_config(config, site_url=raw)


def cmd_test_connection(config: PaperConfig) -> int:
    if shutil.which("git") is None:
        return _error(t("test_git_missing"))
    info = normalize_git_remote(config.git_remote) if config.git_remote else None
    if info is None:
        return _error(t("test_remote_unconfigured"))
    print(t("test_testing_remote_prefix", remote=info.ssh_url))
    result = _run_with_spinner(
        t("test_connecting_spinner"),
        ["git", "ls-remote", info.ssh_url, "HEAD"],
        timeout=10,
    )
    if result is None:
        return _error(t("test_timeout_error"))
    if result.returncode != 0:
        if result.stderr.strip():
          print(result.stderr.strip(), file=sys.stderr)
        return _error(t("test_remote_unreachable_error"))
    print(t("test_connection_ok"))
    return 0


def cmd_link(path_arg: str | None) -> int:
    target = Path(path_arg).expanduser().resolve() if path_arg else _folder_picker()
    if target is None and not sys.stdin.isatty():
        return _error(t("link_noninteractive_error"))
    if target is None:
        try:
            answer = input(t("link_prompt")).strip()
        except (EOFError, KeyboardInterrupt):
            return _error(t("link_cancelled"), 1)
        if not answer:
            return _error(t("link_cancelled"), 1)
        target = Path(answer).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    try:
        config = load_config()
    except ConfigError as exc:
        return _error(str(exc))
    save_config(config, posts_dir=target)
    print(t("link_linked", path=target))
    return 0


def _seed_initial_posts(posts_dir: Path, site_name: str = "Paper Blog") -> None:
    """Create initial index.md and welcome post if directory is empty."""
    posts_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = posts_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    today = dt.date.today().isoformat()
    index_file = posts_dir / "index.md"
    if not index_file.exists():
        index_file.write_text(
            f"---\ntitle: {site_name}\ndate: {today}\npublished: true\n---\n\n"
            f"# {site_name}\n\n写简单的文字，做干净的博客。\n",
            encoding="utf-8",
        )

    has_other_posts = any(p for p in posts_dir.glob("*.md") if p.name != "index.md")
    if not has_other_posts:
        welcome_file = posts_dir / "hello-paper.md"
        if not welcome_file.exists():
            welcome_file.write_text(
                f"---\ntitle: 欢迎使用 {site_name}\ndate: {today}\npublished: true\n---\n\n"
                f"# 欢迎使用 {site_name}\n\n"
                f"恭喜你！Paper 博客已初始化完成。\n\n"
                f"- ✍️ **纯粹写作**：Markdown 即一切，无杂质极速阅读。\n"
                f"- 🎨 **自由排版**：原生支持 Obsidian / Typora 尺寸与对齐语法（如 `![[image.png|300|center]]`）。\n"
                f"- 🚀 **即时发布**：支持一键发布同步到 GitHub Pages。\n\n"
                f"你可以在当前文章目录中直接创建或编辑 Markdown 文档，开始你的写作之旅！\n",
                encoding="utf-8",
            )


def _is_already_initialized(is_local: bool, target_dir: Path | None) -> tuple[bool, PaperConfig | None]:
    """Check if the target environment (local project or global setup) is already initialized."""
    if is_local:
        base = (target_dir or Path.cwd()).resolve()
        cfg_candidates = [
            base / ".paper-config.json",
            base / "paper-config.json",
            base / "paper.config.json",
            base / ".paper" / "config.json",
        ]
        has_cfg = any(c.is_file() for c in cfg_candidates)
        has_posts = (base / "posts").is_dir() and any((base / "posts").glob("*.md"))
        if has_cfg or has_posts:
            try:
                cfg = load_local_config(base)
                return True, cfg
            except Exception:
                pass
        return False, None
    else:
        cfg_file = config_path()
        if cfg_file.is_file():
            try:
                cfg = load_config()
                if cfg.posts_dir.is_dir():
                    return True, cfg
            except Exception:
                pass
        return False, None


def cmd_init(local: bool = False, local_dir: Path | str | None = None) -> int:
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()

    # 1. 模式判断与选择（若未显式指定 -l 且在交互 TTY 下）
    mode = "local" if (local or local_dir is not None) else None
    if mode is None:
        if is_tty:
            print(f"\n{TERRACOTTA}{BOLD}{t('init_welcome_header')}{RESET}\n")
            chosen_mode = _terminal_menu(
                t("init_mode_choose"),
                [
                    ("global", "global", t("init_mode_global")),
                    ("local", "local", t("init_mode_local")),
                ],
            )
            if chosen_mode is None:
                print(t("init_cancelled"))
                return 0
            mode = chosen_mode
        else:
            mode = "global"

    is_local = (mode == "local")
    target_dir = Path(local_dir or ".").resolve() if is_local else None

    # 2. 检查是否已经初始化过
    already_init, existing_cfg = _is_already_initialized(is_local, target_dir)
    if already_init and existing_cfg:
        posts = discover_posts(existing_cfg.posts_dir)
        print(f"\n💡 {t('init_detected_existing')}")
        mode_str = t("init_mode_label_local") if is_local else t("init_mode_label_global")
        print(f"  · {t('cli_description')}：{mode_str}")
        print(f"  · {t('status_posts_dir', path=existing_cfg.posts_dir)}（{t('init_posts_count', count=len(posts))}）")
        print(f"  · {t('status_site_dir', path=existing_cfg.site_dir)}")
        if existing_cfg.git_remote:
            print(f"  · {t('status_remote', remote=existing_cfg.git_remote)}")
        print(f"  · {t('status_static_out', status=t('status_out_exists') if existing_cfg.output_dir.exists() else t('status_out_not_built'))}\n")

        if not is_tty:
            return 0

        action = _terminal_menu(
            t("init_action_choose"),
            [
                ("serve", "serve", t("init_op_serve")),
                ("new", "new", t("init_op_new")),
                ("reinit", "reinit", t("init_op_reinit")),
                ("exit", "exit", t("init_op_exit")),
            ],
        )
        if action == "serve":
            return cmd_serve(8000, local=is_local, local_dir=target_dir)
        elif action == "new":
            return cmd_new(None, local=is_local, local_dir=target_dir)
        elif action in {"exit", None}:
            print(t("init_exited"))
            return 0
        # 选择 reinit 则继续向下执行向导重设

    # 3. 确定配置与文章目录
    if is_local:
        config = load_local_config(target_dir or ".")
        posts_dir = config.posts_dir
        print(f"\n📁 【{t('init_mode_label_local')}】{t('status_site_dir', path=config.site_dir)}")
        print(f"📁 {t('status_posts_dir', path=posts_dir)}")
    else:
        try:
            config = load_config()
        except ConfigError:
            config = _default_config()

        default_dir_str = str(config.posts_dir or DEFAULT_POSTS_DIR)
        if is_tty:
            ans = _prompt(t("init_confirm_path_prompt", path=default_dir_str))
            posts_dir = Path(ans).expanduser().resolve() if ans else Path(default_dir_str).expanduser().resolve()
        else:
            posts_dir = Path(default_dir_str).expanduser().resolve()
        config = save_config(config, posts_dir=posts_dir)

    # 4. 初始文章脚手架
    _seed_initial_posts(posts_dir, site_name=config.site_name)
    print(t("init_posts_ready", path=posts_dir))

    # 5. 编辑器偏好设置（交互模式）
    if is_tty:
        editor_choice = _terminal_menu(
            t("init_choose_editor", editor=config.editor),
            [
                ("obsidian", "obsidian", "Obsidian"),
                ("typora", "typora", "Typora"),
                ("vscode", "vscode", "Visual Studio Code"),
                ("cursor", "cursor", "Cursor"),
                ("default", "default", t("editor_default_system")),
                ("custom", "custom", t("editor_custom_option")),
            ],
        )
        if editor_choice == "custom":
            config = _pick_custom_editor(config)
        elif editor_choice:
            config = save_config(config, editor=editor_choice)

    # 6. GitHub 关联引导
    if is_local and config.git_remote:
        print(t("init_auto_linked_remote", remote=config.git_remote))
        info = normalize_git_remote(config.git_remote)
        if info:
            print(t("init_pages_url", url=info.pages_url))
    elif is_tty:
        ans_remote = _prompt(t("init_remote_prompt"))
        if ans_remote:
            info = normalize_git_remote(ans_remote)
            if info:
                config = save_config(config, git_remote=info.ssh_url)
                print(t("remote_saved", remote=info.ssh_url, site_url=info.pages_url))
                _bind_managed_origin(config, info.ssh_url)
            else:
                print(t("init_remote_invalid"))

    # 7. 首次静态构建
    try:
        _with_spinner(t("init_building_site"), build_site, config)
        print(t("init_build_done", path=config.output_dir))
    except Exception as exc:
        print(t("init_build_hint", error=exc))

    # 8. 完成向导与后续行动
    if is_tty:
        next_action = _terminal_menu(
            t("init_done_title"),
            [
                ("serve", "serve", t("init_done_serve")),
                ("publish", "publish", t("init_done_publish")),
                ("exit", "exit", t("init_done_exit")),
            ],
        )
        if next_action == "serve":
            return cmd_serve(8000, local=is_local, local_dir=target_dir)
        elif next_action == "publish":
            return cmd_publish(False, [], local=is_local, local_dir=target_dir)

    print(t("init_quick_start_title"))
    cmd_prefix = f"paper -l" if is_local else "paper"
    print(f"  · {cmd_prefix} new \"Title\"")
    print(f"  · {cmd_prefix} serve")
    print(f"  · {cmd_prefix} publish")
    print(f"  · {cmd_prefix}\n")
    return 0


def _slug(title: str) -> str:
    import re

    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", title.lower(), flags=re.UNICODE).strip("-")
    return value or f"post-{int(time.time())}"


def _open_editor(path: Path, config: PaperConfig) -> None:
    raw_editor = config.editor.strip()
    editor = raw_editor.lower()
    if editor in {"", "none"} or not sys.stdin.isatty():
        return
    try:
        if editor in {"default", "system", "open"} and sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif editor in {"vscode", "code"}:
            subprocess.Popen(["code", str(path)])
        elif editor == "cursor":
            subprocess.Popen(["cursor", str(path)])
        elif editor == "obsidian" and sys.platform == "darwin":
            resolved = path.resolve()
            if any((parent / ".obsidian").is_dir() for parent in resolved.parents):
                try:
                    subprocess.Popen(["open", "obsidian://open?path=" + quote(str(resolved), safe="")])
                    return
                except OSError:
                    pass
            subprocess.Popen(["open", "-a", "Obsidian", str(path)])
        elif editor in {"typora", "iawriter", "macdown"} and sys.platform == "darwin":
            app_names = {"typora": "Typora", "iawriter": "iA Writer", "macdown": "MacDown"}
            subprocess.Popen(["open", "-a", app_names[editor], str(path)])
        elif sys.platform == "darwin" and (
            raw_editor.endswith(".app")
            or ".app/" in raw_editor
            or (Path("/Applications") / f"{raw_editor}.app").exists()
            or (Path.home() / "Applications" / f"{raw_editor}.app").exists()
            or (Path("/System/Applications") / f"{raw_editor}.app").exists()
        ):
            subprocess.Popen(["open", "-a", raw_editor, str(path)])
        elif sys.platform == "darwin" and not shutil.which(raw_editor) and not Path(raw_editor).is_file():
            subprocess.Popen(["open", "-a", raw_editor, str(path)])
        elif raw_editor:
            subprocess.Popen([raw_editor, str(path)])
    except OSError as exc:
        print(f"⚠️ {exc}")


def cmd_new(title: str | None, local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    if not title:
        if not sys.stdin.isatty():
            return _error(t("new_post_noninteractive"))
        try:
            title = input(t("new_post_prompt")).strip()
        except (EOFError, KeyboardInterrupt):
            return _error(t("new_post_cancelled"), 1)
    if not title:
        return _error(t("new_post_title_empty"), 1)
    if any(character in title for character in "\r\n"):
        return _error(t("new_post_title_newline"), 1)
    target = config.posts_dir / f"{_slug(title)}.md"
    if target.exists():
        return _error(t("new_post_exists", filename=target.name), 1)
    today = dt.date.today().isoformat()
    target.parent.mkdir(parents=True, exist_ok=True)
    # 不写 title：默认用文件名作为展示标题；需要时再手动在 frontmatter 加 title。
    target.write_text(
        f'---\ndate: {today}\npublished: false\n---\n\n...\n',
        encoding="utf-8",
    )
    _open_editor(target, config)
    print(t("new_post_created", path=target))
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


def cmd_list(local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    posts = _list_items(config)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        for post in posts:
            marker = "🟢" if post.published else "⚪"
            homepage = t("list_home_tag") if post.slug == "__home__" else ""
            print(f"{marker}  {post.modified_date}  {post.title}{homepage}")
        return 0

    while True:
        posts = _list_items(config)
        options = [
            (
                post.slug,
                f"{'🟢' if post.published else '⚪'} {post.modified_date}",
                f"{post.title}{t('list_home_tag') if post.slug == '__home__' else ''}",
            )
            for post in posts
        ] + [("back", t("back"), t("config_item_back"))]
        header = t("list_console_header") + (t("config_mode_prefix", dir_name=Path(local_dir or '.').resolve().name) if (local or local_dir is not None) else "")
        selected = _terminal_menu(header, options)
        if selected in {None, "back"}:
            return 0
        post = next((item for item in posts if item.slug == selected), None)
        if post is None:
            continue
        if post.slug == "__home__":
            action = _terminal_menu(
                t("list_home_op_title", title=post.title),
                [
                    ("edit", t("list_home_op_edit"), t("list_home_op_edit_desc")),
                    ("back", t("back"), t("posts_title")),
                ],
            )
            if action == "edit":
                if not post.source_path.exists():
                    post.source_path.write_text(DEFAULT_INDEX, encoding="utf-8")
                _open_editor(post.source_path, config)
            continue
        action = _terminal_menu(
            t("post_operation_title", title=post.title),
            [
                ("edit", t("post_op_edit"), t("list_post_op_edit_desc")),
                ("archive" if post.published else "publish", t("list_post_op_archive") if post.published else t("list_post_op_publish"), t("list_post_op_rebuild_desc")),
                ("delete", t("post_op_delete"), t("list_post_op_delete_desc")),
                ("back", t("back"), t("posts_title")),
            ],
        )
        if action == "edit":
            _open_editor(post.source_path, config)
        elif action == "publish":
            cmd_publish(False, [post.slug], local=local, local_dir=local_dir)
            _pause()
        elif action == "archive":
            set_post_published(post.source_path, False)
            build_site(config)
            print(t("list_post_archived", title=post.title))
            _pause()
        elif action == "delete":
            confirmation = input(t("list_post_delete_confirm_prompt", title=post.title)).strip()
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
            print(t("list_post_trash_moved", target=target))
            _pause()


def cmd_build(preview: bool = False, local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    output = build_site(config, include_drafts=preview)
    print(t("build_generated", path=output))
    return 0


class _PreviewHandler(http.server.SimpleHTTPRequestHandler):
    preview_state: _PreviewState | None = None

    def __init__(self, *args: object, base_path: str = "", **kwargs: object) -> None:
        self.preview_base_path = base_path.rstrip("/")
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        """Mount generated output at its GitHub Pages base path during preview."""

        request_path, separator, query = path.partition("?")
        base_path = self.preview_base_path
        if base_path and (request_path == base_path or request_path.startswith(base_path + "/")):
            request_path = request_path[len(base_path):] or "/"
            path = request_path + (separator + query if separator else "")
        return super().translate_path(path)

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        request_path = self.path.split("?", 1)[0]
        if request_path == "/.paper-revision":
            revision = self.preview_state.revision if self.preview_state else 0
            payload = str(revision).encode("ascii")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.preview_state and (request_path.endswith("/") or request_path.endswith(".html")):
            self.preview_state.request_refresh()
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


def cmd_serve(port: int = 8000, local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
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
    preview_state.watcher_ready.wait()
    base_path = _base_path(preview_config)
    handler = partial(_PreviewHandler, directory=str(output), base_path=base_path)
    try:
        try:
            server = _PreviewServer(("127.0.0.1", port), handler)
        except OSError:
            server = _PreviewServer(("127.0.0.1", 0), handler)
            print(t("serve_port_occupied", port=port))
        with server:
            actual_port = server.server_address[1]
            preview_path = f"{base_path}/" if base_path else "/"
            preview_url = f"http://127.0.0.1:{actual_port}{preview_path}"
            print(t("serve_banner", url=preview_url))
            opened = _open_browser(preview_url)
            print(t("serve_browser_opened") if opened else t("serve_browser_failed"))
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print(t("serve_stopped_hint"))
    finally:
        stop_watcher.set()
        preview_state.refresh_requested.set()
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


def _with_spinner(message: str, fn: Callable[..., object], *args: object) -> object:
    """Run a blocking callable, animating a loading spinner on a TTY while it works.

    Returns fn's return value. On non-TTY output the spinner is skipped and the
    callable runs synchronously (tests and pipes stay deterministic). Exceptions
    raised by fn are re-raised on the calling thread in both modes.
    """
    if not (sys.stdout.isatty() and sys.stderr.isatty()):
        return fn(*args)
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    stop = threading.Event()
    result: dict[str, object] = {}

    def _run() -> None:
        try:
            result["value"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            result["error"] = exc
        finally:
            stop.set()

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    index = 0
    # Hide cursor during spinning
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    try:
        while not stop.is_set():
            cols = shutil.get_terminal_size((80, 20)).columns
            frame = frames[index % len(frames)]
            # Clean plain message without escape sequences for length calculation
            plain_label = re.sub(r"\033\[[0-9;]*m", "", message)
            display_label = message
            if len(plain_label) + 6 > cols:
                display_label = plain_label[: max(cols - 10, 10)] + "..."
            # \r\033[2K clears the entire line and moves cursor to column 1
            sys.stdout.write(f"\r\033[2K  {frame} {display_label}")
            sys.stdout.flush()
            index += 1
            time.sleep(0.08)
    finally:
        # Clear spinner and restore cursor
        sys.stdout.write("\r\033[2K\033[?25h")
        sys.stdout.flush()

    worker.join()
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result.get("value")


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
        return False, t("test_git_missing")
    config.site_dir.mkdir(parents=True, exist_ok=True)
    if not (config.site_dir / ".git").exists() and _git(config, "init").returncode != 0:
        return False, t("deploy_init_failed")
    current = _managed_origin(config)
    if current == url:
        return True, None
    if current is None:
        ok = _git(config, "remote", "add", "origin", url).returncode == 0
    else:
        ok = _git(config, "remote", "set-url", "origin", url).returncode == 0
    if not ok:
        return False, t("deploy_bind_remote_failed")
    return True, None


def cmd_deploy(local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    if _has_github_pages_actions(config.site_dir):
        print(t("deploy_actions_intro"))
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return 0
        confirmed = _confirm_or_skip(t("deploy_actions_confirm_prompt"))
        if not confirmed:
            print(t("deploy_actions_cancelled"))
            return 0
        if shutil.which("git") is None:
            return _error(t("deploy_git_missing"))
        print(t("deploy_staging_local"))
        if _git(config, "add", ".", capture=True).returncode != 0:
            return _error(t("deploy_stage_failed"))
        changed = _git(config, "diff", "--cached", "--quiet")
        if changed.returncode == 1:
            print(t("deploy_committing_changes"))
            committed = _git(config, "commit", "-m", "publish: update posts", capture=True)
            if committed.returncode != 0:
                return _error(t("deploy_commit_failed"))
        print(t("deploy_pushing_remote_spinner"))
        pushed = _run_with_spinner(
            t("deploy_pushing_remote_spinner"),
            ["git", "-C", str(config.site_dir), "push"],
            timeout=600,
        )
        if pushed is None:
            print(t("deploy_push_timeout"), file=sys.stderr)
            return 1
        if pushed.returncode != 0:
            print(t("deploy_push_failed"), file=sys.stderr)
            if pushed.stderr:
                print(pushed.stderr.strip(), file=sys.stderr)
            return 1
        print(t("deploy_actions_success"))
        return 0
    if not config.git_remote:
        return _error(t("deploy_remote_missing"))
    if shutil.which("git") is None:
        return _error(t("deploy_git_missing_keep_out"))
    config.site_dir.mkdir(parents=True, exist_ok=True)
    if not (config.site_dir / ".git").exists() and _git(config, "init").returncode != 0:
        return _error(t("deploy_init_failed"))
    remotes = _git(config, "remote", capture=True)
    if not remotes.stdout.strip() and _git(config, "remote", "add", "origin", config.git_remote).returncode != 0:
        return _error(t("deploy_bind_remote_failed"))
    if remotes.stdout.strip():
        current_remote = _git(config, "remote", "get-url", "origin", capture=True)
        if current_remote.returncode != 0 or current_remote.stdout.strip() != config.git_remote:
            return _error(t("deploy_origin_mismatch"))
    print(t("deploy_staging"))
    if _git(config, "add", "out", capture=True).returncode != 0:
        return _error(t("deploy_stage_out_failed"))
    changed = _git(config, "diff", "--cached", "--quiet", "--", "out")
    if changed.returncode == 1:
        print(t("deploy_committing"))
        committed = _git(config, "commit", "-m", "paper: update site", capture=True)
        if committed.returncode != 0:
            return _error(t("deploy_commit_site_failed"))
    elif changed.returncode != 0:
        return _error(t("deploy_diff_failed"))
    # returncode 0 = 没有新 diff → 不创建空提交；两种情况都继续推送，
    # 以支持「上次 commit 已生成但 push 失败、本地无新 diff」的重试场景。
    print(t("deploy_pushing", remote=config.git_remote))
    pushed = _run_with_spinner(
        t("deploy_pushing_remote_spinner"),
        ["git", "-C", str(config.site_dir), "subtree", "push", "--prefix", "out", "origin", "gh-pages"],
        timeout=600,
    )
    if pushed is None:
        print(t("deploy_push_timeout"), file=sys.stderr)
        print(t("deploy_push_advice_timeout"), file=sys.stderr)
        return 1
    if pushed.returncode != 0:
        print(t("deploy_push_failed_retry_hint"), file=sys.stderr)
        if pushed.stderr:
            print(pushed.stderr.strip(), file=sys.stderr)
        print(t("deploy_push_common_reasons"), file=sys.stderr)
        return 1
    print(t("deploy_success"))
    return 0


def cmd_publish(all_posts: bool, slugs: list[str], local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    posts = discover_posts(config.posts_dir)
    drafts = [post for post in posts if not post.published]
    if not all_posts and not slugs and sys.stdin.isatty() and sys.stdout.isatty():
        if drafts:
            chosen = _terminal_multiselect(
                t("publish_multiselect_title"),
                [(post.slug, post.title, post.date) for post in drafts],
            )
            if chosen is None:
                print(t("publish_cancelled"))
                return 0
            slugs = chosen
    if all_posts:
        targets = drafts
    elif slugs:
        by_slug = {post.slug: post for post in posts}
        missing = [slug for slug in slugs if slug not in by_slug]
        if missing:
            available = ", ".join(post.slug for post in posts)
            return _error(t("publish_missing_posts", missing=", ".join(missing), available=available or t("no")), 1)
        targets = [by_slug[slug] for slug in slugs]
    else:
        # 无参数非 TTY，或交互空选择：不发布草稿，仅同步当前站点
        targets = []
    new_drafts = [post for post in targets if not post.published]
    originals = {
        post.source_path: post.source_path.read_text(encoding="utf-8") for post in new_drafts
    }
    for post in new_drafts:
        set_post_published(post.source_path, True)
    try:
        _with_spinner(t("publish_rebuilding"), build_site, config)
    except Exception as exc:
        for source_path, original in originals.items():
            source_path.write_text(original, encoding="utf-8")
        return _error(t("publish_failed_reverted", error=exc), 1)
    if new_drafts:
        print(t("publish_marked_count", count=len(new_drafts)))
    else:
        print(t("publish_no_drafts"))
    return cmd_deploy(local=local, local_dir=local_dir)


def cmd_status(local: bool = False, local_dir: Path | str | None = None) -> int:
    config = _require_linked(local=local, local_dir=local_dir)
    if config is None:
        return 2
    posts = discover_posts(config.posts_dir)
    print(t("status_posts_dir", path=config.posts_dir))
    print(t("status_site_dir", path=config.site_dir))
    print(t("status_posts_count", total=len(posts), published=sum(post.published for post in posts)))
    print(t("status_remote", remote=config.git_remote or t("status_not_set")))
    if config.git_remote:
        info = normalize_git_remote(config.git_remote)
        if info:
            print(t("status_pages_url", url=info.pages_url))
    print(t("status_static_out", status=t("status_out_exists") if config.output_dir.exists() else t("status_out_not_built")))
    state, label = _deployment_readiness(config)
    print(t("status_readiness", status=label))
    if state == "actions":
        print(t("status_actions_tip"))
    elif state == "pushed":
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
        print(t("status_pushed_unable_confirm"))
        return
    if remote.returncode != 0 or not remote.stdout.strip():
        print(t("status_pushed_ahead_retry"))
        return
    remote_sha = remote.stdout.strip().split()[0]
    if remote_sha == local_sha:
        print(t("status_pushed_waiting_pages"))
    else:
        print(t("status_pushed_ahead_retry"))


def cmd_doctor() -> int:
    checks = []
    try:
        import markdown_it  # noqa: F401
        import pygments  # noqa: F401
        checks.append((True, t("doctor_dependencies")))
    except ImportError:
        checks.append((False, t("doctor_dependencies")))
    checks.append((sys.version_info >= (3, 11), t("doctor_python_req", ver=sys.version.split()[0])))
    checks.append((shutil.which("git") is not None, t("doctor_git_req")))
    checks.append((_has_config(), t("doctor_config_req", path=config_path())))

    latest = _latest_available_version()
    if latest:
        if _version_key(latest) > _version_key(VERSION):
            checks.append((True, t("doctor_version_outdated", current=VERSION, latest=latest)))
        else:
            checks.append((True, t("doctor_version_latest", current=VERSION)))
    else:
        checks.append((True, t("doctor_version_current", current=VERSION)))

    for ok, name in checks:
        print(f"{'✅' if ok else '❌'} {name}")
    return 0 if all(ok for ok, _ in checks[:2]) else 1


def _version_key(value: str) -> tuple[int, ...]:
    """Return a sortable key for versions like 0.1.0 or 0.1.1-beta.1."""
    release, _, pre = value.partition("-")
    parts = [int(part) for part in release.split(".") if part.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    if not pre:
        return tuple(parts + [9999])
    kind = re.sub(r"[^a-z]", "", pre.split(".")[0].lower())
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "pre": 1, "preview": 1, "rc": 2}.get(kind, 1)
    number = re.search(r"\d+$", pre)
    return tuple(parts + [rank * 1000 + (int(number.group(0)) if number else 0)])


def _latest_available_version() -> str | None:
    """Return the newest release version, using short-lived local cache and fast CDN."""

    cache_path = config_path().parent / "update-check.json"
    cached_version: str | None = None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_version = str(cached.get("latest") or "") or None
        checked_at = float(cached.get("checkedAt") or 0)
        if cached_version and time.time() - checked_at < UPDATE_CHECK_TTL_SECONDS:
            return cached_version
    except (OSError, TypeError, ValueError):
        pass

    latest = None
    # 1. Try fetching from Homebrew Tap CDN (Zero rate limit, fast & reliable)
    try:
        req = Request(UPDATE_FORMULA_RAW_URL, headers={"User-Agent": f"Paper/{VERSION}"})
        with urlopen(req, timeout=1.5) as resp:
            content = resp.read().decode("utf-8")
        match = re.search(r"tags/v?([0-9A-Za-z.-]+)\.tar\.gz", content)
        if match:
            latest = match.group(1)
    except Exception:
        pass

    # 2. Fallback to GitHub Releases API if CDN didn't return a version
    if not latest:
        try:
            request = Request(
                UPDATE_RELEASES_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": f"Paper/{VERSION}"},
            )
            with urlopen(request, timeout=1.5) as response:
                releases = json.loads(response.read().decode("utf-8"))
            versions = [
                str(release.get("tag_name") or "").strip().removeprefix("v")
                for release in releases
                if isinstance(release, dict) and not release.get("draft")
            ]
            versions = [version for version in versions if re.fullmatch(r"\d+(?:\.\d+)+(?:-[0-9A-Za-z.-]+)?", version)]
            if versions:
                latest = max(versions, key=_version_key)
        except Exception:
            pass

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"checkedAt": time.time(), "latest": latest or cached_version}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    return latest or cached_version


def _startup_update_notice() -> str:
    """Build the non-blocking update notice shown above the dashboard."""

    latest = _latest_available_version()
    if latest and _version_key(latest) > _version_key(VERSION):
        return t("update_notice_banner", latest=latest)
    return ""


def _check_and_auto_update() -> bool:
    """Silently check for updates on startup. If a newer version is available,
    prompt the user and automatically upgrade via Homebrew with an animated spinner.
    Returns True if an upgrade was performed and restarted/handled.
    """
    if os.environ.get("PAPER_NO_AUTO_UPDATE", "").lower() in ("1", "true", "yes"):
        return False

    latest = _latest_available_version()
    if not latest or _version_key(latest) <= _version_key(VERSION):
        return False

    if not _is_homebrew_install():
        print(f"{TERRACOTTA}🆕 {t('auto_update_found', current=VERSION, latest=latest)}{RESET}")
        print(f"{TERRACOTTA}{t('update_non_brew')}{RESET}\n")
        return False

    if shutil.which("brew") is None:
        print(f"{TERRACOTTA}🆕 {t('auto_update_found', current=VERSION, latest=latest)}{RESET}")
        print(f"{TERRACOTTA}⚠️ {t('update_brew_missing')}{RESET}\n")
        return False

    def _upgrade_task() -> int:
        subprocess.run(["brew", "update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = subprocess.run(
            ["brew", "upgrade", "ohmyangboy/tap/paper"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return res.returncode

    spinner_msg = f"{TERRACOTTA}🆕 {t('auto_update_spinner', latest=latest)}{RESET}"
    res_code = _with_spinner(spinner_msg, _upgrade_task)

    if res_code == 0:
        print(f"✅ {t('auto_update_success', latest=latest)}\n")
        try:
            os.execvp(sys.argv[0], sys.argv)
        except OSError:
            return True
        return True
    else:
        print(f"⚠️ {t('auto_update_failed')}\n")
        return False


def _is_homebrew_install() -> bool:
    try:
        return "/Cellar/paper/" in os.path.realpath(sys.argv[0])
    except OSError:
        return False


def cmd_update() -> int:
    """Self-update Paper when installed via the Homebrew tap."""
    if shutil.which("brew") is None:
        return _error(t("update_brew_missing"), 1)
    if not _is_homebrew_install():
        print(t("update_non_brew"))
        return 1
    print(t("update_current_ver", version=VERSION))

    def _refresh_tap() -> subprocess.CompletedProcess[str]:
        subprocess.run(["brew", "update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return subprocess.run(
            ["brew", "info", "--json=v2", "ohmyangboy/tap/paper"],
            capture_output=True,
            text=True,
        )

    info = _with_spinner(t("update_refreshing_tap"), _refresh_tap)
    try:
        latest = json.loads(info.stdout)["formulae"][0]["versions"]["stable"]
    except (KeyError, IndexError, ValueError, AttributeError):
        return _error(t("update_fetching_failed"), 1)
    print(t("update_latest_version", version=latest))
    if _version_key(latest) <= _version_key(VERSION):
        print(t("update_already_latest"))
        return 0

    def _run_upgrade() -> int:
        return subprocess.run(
            ["brew", "upgrade", "ohmyangboy/tap/paper"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode

    upgrade_msg = t("update_upgrading", current=VERSION, latest=latest)
    if _with_spinner(upgrade_msg, _run_upgrade) == 0:
        print(t("update_success"))
        return 0
    return _error(t("update_failed_brew_upgrade"), 1)


def cmd_uninstall(clean: bool) -> int:
    print(t("uninstall_guide"))
    if clean:
        answer = input(t("uninstall_prompt_clean")) if sys.stdin.isatty() else ""
        if answer == "CLEAN":
            shutil.rmtree(Path(os.environ.get("PAPER_HOME", Path.home() / ".paper")), ignore_errors=True)
            print(t("uninstall_cleaned_msg"))
        else:
            print(t("uninstall_clean_cancelled"))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper", description=t("cli_description"))
    parser.add_argument("--version", action="version", version=f"paper {VERSION}")
    parser.add_argument("-l", "--local", action="store_true", help=t("help_local"))
    parser.add_argument("-C", "--dir", type=str, default=None, help=t("help_dir"))
    parser.add_argument("--lang", "--language", type=str, default=None, choices=["zh", "en", "zh_CN", "en_US", "auto"], help=t("help_lang"))

    def _add_common_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("-l", "--local", action="store_true", default=argparse.SUPPRESS, help=t("help_local"))
        subparser.add_argument("-C", "--dir", type=str, default=argparse.SUPPRESS, help=t("help_dir"))
        subparser.add_argument("--lang", "--language", type=str, default=argparse.SUPPRESS, choices=["zh", "en", "zh_CN", "en_US", "auto"], help=t("help_lang"))

    commands = parser.add_subparsers(dest="command")
    init = commands.add_parser("init", help=t("help_cmd_init"))
    _add_common_options(init)

    link = commands.add_parser("link", help=t("help_cmd_link"))
    link.add_argument("path", nargs="?")
    _add_common_options(link)

    new = commands.add_parser("new", help=t("help_cmd_new"))
    new.add_argument("title", nargs="?")
    _add_common_options(new)

    list_p = commands.add_parser("list", aliases=["posts"], help=t("help_cmd_list"))
    _add_common_options(list_p)

    build = commands.add_parser("build", help=t("help_cmd_build"))
    _add_common_options(build)

    serve = commands.add_parser("serve", help=t("help_cmd_serve"))
    serve.add_argument("--port", type=int, default=8000)
    _add_common_options(serve)

    publish = commands.add_parser("publish", help=t("help_cmd_publish"))
    publish.add_argument("slugs", nargs="*")
    publish.add_argument("--all", action="store_true")
    _add_common_options(publish)

    deploy = commands.add_parser("deploy", help=t("help_cmd_deploy"))
    _add_common_options(deploy)

    status = commands.add_parser("status", help=t("help_cmd_status"))
    _add_common_options(status)

    config = commands.add_parser("config", help=t("help_cmd_config"))
    _add_common_options(config)
    config_sub = config.add_subparsers(dest="config_cmd")
    home = config_sub.add_parser("home", help=t("config_item_brand"))
    _add_common_options(home)
    home_sub = home.add_subparsers(dest="home_cmd")
    c_color = home_sub.add_parser("color", help=t("brand_item_color"))
    _add_common_options(c_color)
    c_icon = home_sub.add_parser("icon", help=t("brand_item_icon"))
    _add_common_options(c_icon)
    compress = config_sub.add_parser("compress", help=t("config_item_compress"))
    compress.add_argument("compress_cmd", nargs="?", choices=["on", "off"])
    _add_common_options(compress)
    c_lang = config_sub.add_parser("lang", aliases=["language"], help=t("config_item_language"))
    c_lang.add_argument("lang_code", nargs="?", choices=["zh", "en", "zh_CN", "en_US", "auto", "system"])
    _add_common_options(c_lang)
    c_editor = config_sub.add_parser("editor", help=t("config_item_editor"))
    c_editor.add_argument("editor_name", nargs="?", help="Editor name, command, or app path")
    _add_common_options(c_editor)
    c_link = config_sub.add_parser("link", help=t("config_item_link"))
    _add_common_options(c_link)
    c_remote = config_sub.add_parser("remote", help=t("config_item_remote"))
    _add_common_options(c_remote)
    c_pages = config_sub.add_parser("pages", help=t("config_item_pages"))
    _add_common_options(c_pages)
    c_test = config_sub.add_parser("test", help=t("config_item_test"))
    _add_common_options(c_test)
    c_status = config_sub.add_parser("status", help=t("config_item_status"))
    _add_common_options(c_status)

    commands.add_parser("doctor", help=t("help_cmd_doctor"))
    commands.add_parser("update", help=t("help_cmd_update"))
    uninstall = commands.add_parser("uninstall", help=t("help_cmd_uninstall"))
    uninstall.add_argument("--clean", action="store_true")
    return parser


def run_dashboard(startup_notice: str = "", local: bool = False, local_dir: Path | str | None = None) -> int:
    exit_armed = False
    enter_alt_screen()
    try:
        while True:
            mode_prefix = t("dashboard_mode_prefix", dir_name=Path(local_dir or '.').resolve().name) if (local or local_dir is not None) else ""
            prompt_header = f"{startup_notice}\n\n{mode_prefix}{t('dashboard_prompt')}" if startup_notice else f"{mode_prefix}{t('dashboard_prompt')}"
            action = _terminal_menu(
                prompt_header,
                [
                    ("list", "list", t("menu_list")),
                    ("new", "new", t("menu_new")),
                    ("config", "config", t("menu_config")),
                    ("publish", "publish", t("menu_publish")),
                    ("serve", "serve", t("menu_serve")),
                    ("uninstall", "uninstall", t("menu_uninstall")),
                    ("quit", "quit", t("menu_quit")),
                ],
                footer_message=t("press_esc_to_exit") if exit_armed else "",
            )
            if action is None:
                if exit_armed:
                    _clear_screen()
                    print(t("exit_goodbye"))
                    return 0
                exit_armed = True
                continue
            exit_armed = False
            if action == "quit":
                _clear_screen()
                print(t("exit_goodbye"))
                return 0
            if action == "list":
                cmd_list(local=local, local_dir=local_dir)
            elif action == "new":
                cmd_new(None, local=local, local_dir=local_dir)
                _pause()
            elif action == "config":
                cmd_config(local=local, local_dir=local_dir)
            elif action == "publish":
                cmd_publish(False, [], local=local, local_dir=local_dir)
                _pause()
            elif action == "serve":
                cmd_serve(8000, local=local, local_dir=local_dir)
            elif action == "uninstall":
                cmd_uninstall(True)
                _pause()
    finally:
        leave_alt_screen()


def _main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv

    cli_lang = None
    for idx, arg in enumerate(raw_argv):
        if arg in ("--lang", "--language"):
            if idx + 1 < len(raw_argv):
                cli_lang = raw_argv[idx + 1]
        elif arg.startswith("--lang=") or arg.startswith("--language="):
            cli_lang = arg.split("=", 1)[1]

    local = "-l" in raw_argv or "--local" in raw_argv
    dir_path = None
    for idx, arg in enumerate(raw_argv):
        if arg in ("-C", "--dir"):
            if idx + 1 < len(raw_argv):
                dir_path = raw_argv[idx + 1]
        elif arg.startswith("--dir="):
            dir_path = arg.split("=", 1)[1]

    cfg_lang = None
    try:
        if local or dir_path is not None:
            cfg = load_local_config(dir_path or ".")
        else:
            cfg = load_config()
        cfg_lang = cfg.language
    except Exception:
        pass

    effective_lang = resolve_language(config_lang=cfg_lang, cli_lang=cli_lang)
    set_current_language(effective_lang)

    args = make_parser().parse_args(raw_argv)
    
    local = bool(getattr(args, "local", False))
    dir_path = getattr(args, "dir", None)

    command = args.command
    if command not in ("update", "uninstall"):
        upgraded = _check_and_auto_update()
        if upgraded:
            return 0

    if not command and sys.stdin.isatty():
        return run_dashboard(_startup_update_notice(), local=local, local_dir=dir_path)

    if command == "init": return cmd_init(local=local, local_dir=dir_path)
    if command == "link": return cmd_link(args.path)
    if command == "new": return cmd_new(args.title, local=local, local_dir=dir_path)
    if command in {"list", "posts"}: return cmd_list(local=local, local_dir=dir_path)
    if command == "build": return cmd_build(local=local, local_dir=dir_path)
    if command == "serve": return cmd_serve(args.port, local=local, local_dir=dir_path)
    if command == "publish": return cmd_publish(args.all, args.slugs, local=local, local_dir=dir_path)
    if command == "deploy": return cmd_deploy(local=local, local_dir=dir_path)
    if command == "status": return cmd_status(local=local, local_dir=dir_path)
    if command == "config":
        return cmd_config(
            config_cmd=getattr(args, "config_cmd", None),
            home_cmd=getattr(args, "home_cmd", None),
            compress_cmd=getattr(args, "compress_cmd", None),
            editor_name=getattr(args, "editor_name", None),
            lang_code=getattr(args, "lang_code", None),
            local=local,
            local_dir=dir_path,
        )
    if command == "doctor": return cmd_doctor()
    if command == "update": return cmd_update()
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
