import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import webbrowser
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import paper_cli
from paper_cli import (
    _ALT_SCREEN_ENTER,
    _ALT_SCREEN_LEAVE,
    _PreviewState,
    _app_picker,
    _choose_editor,
    _deployment_readiness,
    _list_items,
    _menu_window,
    _open_browser,
    _open_editor,
    _pick_custom_editor,
    _read_terminal_key,
    _terminal_menu,
    _latest_available_version,
    _startup_update_notice,
    _version_key,
    _watch_preview,
    _with_spinner,
    cmd_config,
    cmd_test_connection,
    main,
    make_parser,
    run_dashboard,
)
from paper_runtime.core import PaperConfig, build_site


def _init_with_origin(site_dir: Path, remote: str, gh_pages: bool = False) -> None:
    """Create a disposable local managed repo with a bound origin (no network)."""
    site_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(site_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(site_dir), "remote", "add", "origin", remote], check=True, capture_output=True)
    if gh_pages:
        subprocess.run(["git", "-C", str(site_dir), "config", "user.email", "test@example.test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(site_dir), "config", "user.name", "test"], check=True, capture_output=True)
        (site_dir / "seed.txt").write_text("seed", encoding="utf-8")
        subprocess.run(["git", "-C", str(site_dir), "add", "seed.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(site_dir), "commit", "-m", "seed"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(site_dir), "branch", "gh-pages"], check=True, capture_output=True)


class PaperCliTests(unittest.TestCase):
    def _set_paper_home(self, root: Path):
        old_home = os.environ.get("PAPER_HOME")
        os.environ["PAPER_HOME"] = str(root / ".paper")
        return old_home

    def _restore_paper_home(self, old_home):
        if old_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = old_home

    def test_no_argument_interactive_run_opens_dashboard(self):
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "paper_cli._startup_update_notice", return_value="new version"
        ), mock.patch(
            "paper_cli.run_dashboard", return_value=0, create=True
        ) as dashboard:
            self.assertEqual(main([]), 0)
            dashboard.assert_called_once_with("new version", local=False, local_dir=None)

    def test_terminal_reader_keeps_arrow_escape_sequence_together(self):
        with mock.patch("sys.stdin.fileno", return_value=7), mock.patch(
            "paper_cli.os.read", side_effect=[b"\x1b", b"[", b"B"]
        ), mock.patch("paper_cli.select.select", return_value=([7], [], [])):
            self.assertEqual(_read_terminal_key(), "\x1b[B")

    def test_menu_uses_alternate_screen_and_restores_it(self):
        output = io.StringIO()
        paper_cli._alt_screen_depth = 0
        with contextlib.redirect_stdout(output), mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
            "sys.stdout.isatty", return_value=True
        ), mock.patch("sys.stdin.fileno", return_value=7), mock.patch(
            "paper_cli.termios.tcgetattr", return_value=[]
        ), mock.patch("paper_cli.termios.tcsetattr"), mock.patch("paper_cli.tty.setcbreak"), mock.patch(
            "paper_cli._read_terminal_key", return_value="q"
        ):
            self.assertIsNone(_terminal_menu("Menu", [("one", "one", "description")]))
        rendered = output.getvalue()
        self.assertIn(_ALT_SCREEN_ENTER, rendered)
        self.assertIn(_ALT_SCREEN_LEAVE, rendered)
        self.assertEqual(paper_cli._alt_screen_depth, 0)

    def test_menu_window_respects_terminal_height(self):
        with mock.patch("paper_cli.shutil.get_terminal_size", return_value=os.terminal_size((80, 12))):
            start, end = _menu_window(30, 15, reserved_lines=7)
        self.assertLessEqual(end - start, 5)
        self.assertLessEqual(start, 15)
        self.assertGreater(end, 15)

    def test_dashboard_requires_escape_or_q_twice(self):
        paper_cli._alt_screen_depth = 0
        with mock.patch("paper_cli._terminal_menu", side_effect=[None, None]) as menu, mock.patch(
            "sys.stdout.isatty", return_value=False
        ):
            self.assertEqual(run_dashboard(), 0)
        self.assertEqual(menu.call_count, 2)
        self.assertEqual(menu.call_args_list[0].kwargs["footer_message"], "")
        self.assertIn("再按一次", menu.call_args_list[1].kwargs["footer_message"])

    def test_dashboard_prints_update_notice_above_menu(self):
        paper_cli._alt_screen_depth = 0
        with mock.patch("paper_cli._terminal_menu", return_value="quit") as menu, mock.patch(
            "sys.stdout.isatty", return_value=False
        ):
            self.assertEqual(run_dashboard("🆕 Paper 9.9.9 新版本可用"), 0)
        self.assertIn("Paper 9.9.9 新版本可用", menu.call_args.args[0])

    def test_ctrl_c_exits_without_traceback(self):
        output = io.StringIO()
        with mock.patch("paper_cli._main", side_effect=KeyboardInterrupt), contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 130)
        self.assertIn("已退出 Paper", output.getvalue())

    def test_open_browser_invokes_webbrowser(self):
        with mock.patch("paper_cli.webbrowser.open", return_value=True) as browser:
            self.assertTrue(_open_browser("http://127.0.0.1:8000"))
            browser.assert_called_once_with("http://127.0.0.1:8000")

    def test_open_browser_reports_failure_on_webbrowser_error(self):
        with mock.patch(
            "paper_cli.webbrowser.open", side_effect=webbrowser.Error
        ):
            self.assertFalse(_open_browser("http://127.0.0.1:8000"))

    def test_open_editor_anchors_obsidian_note_inside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "My Vault"
            note = vault / "paper blog" / "你好 世界.md"
            (vault / ".obsidian").mkdir(parents=True)
            note.parent.mkdir()
            note.write_text("# Note", encoding="utf-8")
            config = PaperConfig(posts_dir=note.parent, site_dir=vault / ".paper", editor="obsidian")
            with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                "paper_cli.sys.platform", "darwin"
            ), mock.patch("paper_cli.subprocess.Popen") as popen:
                _open_editor(note, config)
            popen.assert_called_once_with([
                "open",
                "obsidian://open?path=" + quote(str(note.resolve()), safe=""),
            ])

    def test_open_editor_falls_back_when_obsidian_uri_cannot_launch(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "vault"
            note = vault / "note.md"
            (vault / ".obsidian").mkdir(parents=True)
            note.write_text("# Note", encoding="utf-8")
            config = PaperConfig(posts_dir=vault, site_dir=vault / ".paper", editor="obsidian")
            with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                "paper_cli.sys.platform", "darwin"
            ), mock.patch(
                "paper_cli.subprocess.Popen", side_effect=[OSError("URI unavailable"), mock.DEFAULT]
            ) as popen:
                _open_editor(note, config)
            self.assertEqual(popen.call_count, 2)
            popen.assert_called_with(["open", "-a", "Obsidian", str(note)])

    def test_open_editor_uses_regular_obsidian_open_outside_vault(self):
        with tempfile.TemporaryDirectory() as root:
            note = Path(root) / "note.md"
            note.write_text("# Note", encoding="utf-8")
            config = PaperConfig(posts_dir=note.parent, site_dir=note.parent / ".paper", editor="obsidian")
            with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                "paper_cli.sys.platform", "darwin"
            ), mock.patch("paper_cli.subprocess.Popen") as popen:
                _open_editor(note, config)
            popen.assert_called_once_with(["open", "-a", "Obsidian", str(note)])

    def test_open_editor_uses_custom_app_bundle(self):
        with tempfile.TemporaryDirectory() as root:
            note = Path(root) / "note.md"
            note.write_text("# Note", encoding="utf-8")
            config = PaperConfig(posts_dir=note.parent, site_dir=note.parent / ".paper", editor="/Applications/Zed.app")
            with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                "paper_cli.sys.platform", "darwin"
            ), mock.patch("paper_cli.subprocess.Popen") as popen:
                _open_editor(note, config)
            popen.assert_called_once_with(["open", "-a", "/Applications/Zed.app", str(note)])

    def test_open_editor_uses_custom_cli_command(self):
        with tempfile.TemporaryDirectory() as root:
            note = Path(root) / "note.md"
            note.write_text("# Note", encoding="utf-8")
            config = PaperConfig(posts_dir=note.parent, site_dir=note.parent / ".paper", editor="myeditor")
            with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                "paper_cli.sys.platform", "linux"
            ), mock.patch("paper_cli.subprocess.Popen") as popen:
                _open_editor(note, config)
            popen.assert_called_once_with(["myeditor", str(note)])

    def test_app_picker_success(self):
        with mock.patch("paper_cli.sys.platform", "darwin"), mock.patch(
            "paper_cli.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="/Applications/Visual Studio Code.app\n"),
        ):
            picked = _app_picker()
            self.assertEqual(picked, Path("/Applications/Visual Studio Code.app").resolve())

    def test_app_picker_failure_or_cancel(self):
        with mock.patch("paper_cli.sys.platform", "darwin"), mock.patch(
            "paper_cli.subprocess.run",
            return_value=mock.Mock(returncode=1, stdout=""),
        ):
            self.assertIsNone(_app_picker())

    def test_app_picker_non_darwin(self):
        with mock.patch("paper_cli.sys.platform", "linux"):
            self.assertIsNone(_app_picker())

    def test_pick_custom_editor_with_app_picker(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                config = PaperConfig(posts_dir=root_path / "posts", site_dir=root_path / "site")
                with mock.patch(
                    "paper_cli._app_picker",
                    return_value=Path("/Applications/Zed.app"),
                ):
                    updated = _pick_custom_editor(config)
                    self.assertEqual(updated.editor, "/Applications/Zed.app")
            finally:
                self._restore_paper_home(old_home)

    def test_pick_custom_editor_fallback_prompt(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                config = PaperConfig(posts_dir=root_path / "posts", site_dir=root_path / "site")
                with mock.patch("paper_cli._app_picker", return_value=None), mock.patch(
                    "paper_cli._prompt", return_value="zed"
                ):
                    updated = _pick_custom_editor(config)
                    self.assertEqual(updated.editor, "zed")
            finally:
                self._restore_paper_home(old_home)

    def test_choose_editor_custom_selection(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                config = PaperConfig(posts_dir=root_path / "posts", site_dir=root_path / "site")
                with mock.patch("paper_cli._terminal_menu", return_value="custom"), mock.patch(
                    "paper_cli._pick_custom_editor",
                    return_value=PaperConfig(posts_dir=config.posts_dir, site_dir=config.site_dir, editor="/Applications/Zed.app"),
                ) as pick_mock:
                    updated = _choose_editor(config)
                    pick_mock.assert_called_once_with(config)
                    self.assertEqual(updated.editor, "/Applications/Zed.app")
            finally:
                self._restore_paper_home(old_home)

    def test_config_editor_cli_argument(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                self.assertEqual(main(["config", "editor", "/Applications/Zed.app"]), 0)
                config_file = root_path / ".paper" / "config.json"
                self.assertEqual(json.loads(config_file.read_text(encoding="utf-8"))["editor"], "/Applications/Zed.app")
            finally:
                self._restore_paper_home(old_home)


    def test_preview_watcher_rebuilds_after_markdown_changes(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts = root_path / "posts"
            posts.mkdir()
            source = posts / "draft.md"
            source.write_text("---\ntitle: Draft\n---\n\nBefore", encoding="utf-8")
            config = PaperConfig(posts_dir=posts, site_dir=root_path / "preview")
            build_site(config, include_drafts=True, live_reload=True)
            state = _PreviewState()
            stop = threading.Event()
            watcher = threading.Thread(target=_watch_preview, args=(config, state, stop), daemon=True)
            watcher.start()
            try:
                self.assertTrue(state.watcher_ready.wait(timeout=1))
                source.write_text("---\ntitle: Draft\n---\n\nAfter", encoding="utf-8")
                deadline = time.monotonic() + 5
                output = config.output_dir / "posts" / "draft" / "index.html"
                while time.monotonic() < deadline and "After" not in output.read_text(encoding="utf-8"):
                    time.sleep(0.05)
                self.assertIn("After", output.read_text(encoding="utf-8"))
                self.assertGreater(state.revision, 0)
            finally:
                stop.set()
                watcher.join(timeout=1)

    def test_preview_watcher_batches_a_burst_of_changes(self):
        self.assertEqual(paper_cli.PREVIEW_DEBOUNCE_SECONDS, 2.0)
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts = root_path / "posts"
            posts.mkdir()
            source = posts / "draft.md"
            source.write_text("Before", encoding="utf-8")
            config = PaperConfig(posts_dir=posts, site_dir=root_path / "preview")
            state = _PreviewState()
            stop = threading.Event()
            with mock.patch("paper_cli.PREVIEW_POLL_SECONDS", 0.02, create=True), mock.patch(
                "paper_cli.PREVIEW_DEBOUNCE_SECONDS", 0.4, create=True
            ), mock.patch("paper_cli.build_site") as rebuild:
                watcher = threading.Thread(target=_watch_preview, args=(config, state, stop), daemon=True)
                watcher.start()
                try:
                    self.assertTrue(state.watcher_ready.wait(timeout=1))
                    rebuild.reset_mock()
                    changes = ("First", "Second", "Third")
                    for index, content in enumerate(changes):
                        source.write_text(content, encoding="utf-8")
                        if index < len(changes) - 1:
                            time.sleep(0.3)
                    time.sleep(0.15)
                    self.assertEqual(rebuild.call_count, 0)
                    deadline = time.monotonic() + 1
                    while time.monotonic() < deadline and rebuild.call_count == 0:
                        time.sleep(0.02)
                    self.assertEqual(rebuild.call_count, 1)
                finally:
                    stop.set()
                    watcher.join(timeout=1)

    def test_preview_manual_refresh_rebuilds_pending_changes_immediately(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts = root_path / "posts"
            posts.mkdir()
            source = posts / "draft.md"
            source.write_text("Before", encoding="utf-8")
            config = PaperConfig(posts_dir=posts, site_dir=root_path / "preview")
            state = _PreviewState()
            stop = threading.Event()
            with mock.patch("paper_cli.PREVIEW_POLL_SECONDS", 0.02, create=True), mock.patch(
                "paper_cli.PREVIEW_DEBOUNCE_SECONDS", 10.0, create=True
            ), mock.patch("paper_cli.build_site") as rebuild:
                watcher = threading.Thread(target=_watch_preview, args=(config, state, stop), daemon=True)
                watcher.start()
                try:
                    self.assertTrue(state.watcher_ready.wait(timeout=1))
                    rebuild.reset_mock()
                    source.write_text("After", encoding="utf-8")
                    state.request_refresh(timeout=1)
                    self.assertEqual(rebuild.call_count, 1)
                finally:
                    stop.set()
                    watcher.join(timeout=1)

    def test_preview_document_request_triggers_immediate_refresh_only_for_html(self):
        handler = object.__new__(paper_cli._PreviewHandler)
        handler.preview_state = mock.Mock()
        with mock.patch.object(paper_cli.http.server.SimpleHTTPRequestHandler, "do_GET"):
            handler.path = "/posts/draft/"
            handler.do_GET()
            handler.preview_state.request_refresh.assert_called_once_with()

            handler.preview_state.request_refresh.reset_mock()
            handler.path = "/assets/image.png"
            handler.do_GET()
            handler.preview_state.request_refresh.assert_not_called()

    def test_preview_maps_github_pages_base_path_to_generated_articles_and_assets(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "out"
            article = output / "posts" / "你好-世界" / "index.html"
            image = output / "assets" / "封面.png"
            article.parent.mkdir(parents=True)
            image.parent.mkdir(parents=True)
            article.write_text("article", encoding="utf-8")
            image.write_bytes(b"image")

            handler = object.__new__(paper_cli._PreviewHandler)
            handler.directory = str(output)
            handler.preview_base_path = "/blog"

            encoded_article = "/blog/posts/%E4%BD%A0%E5%A5%BD-%E4%B8%96%E7%95%8C/"
            encoded_image = "/blog/assets/%E5%B0%81%E9%9D%A2.png"
            self.assertEqual(Path(handler.translate_path(encoded_article)), article.parent)
            self.assertEqual(Path(handler.translate_path(encoded_image)), image)
            self.assertEqual(Path(handler.translate_path("/blog/")), output)
            self.assertEqual(
                Path(handler.translate_path("/blogger/posts/example/")),
                output / "blogger" / "posts" / "example",
            )

    def test_article_console_keeps_homepage_first_and_uses_status_lights(self):
        with tempfile.TemporaryDirectory() as root:
            posts = Path(root)
            (posts / "index.md").write_text("---\ntitle: My Home\n---\n\nWelcome", encoding="utf-8")
            (posts / "draft.md").write_text("---\ntitle: Draft\n---\n\nBody", encoding="utf-8")
            (posts / "live.md").write_text("---\ntitle: Live\npublished: true\n---\n\nBody", encoding="utf-8")
            os.utime(posts / "draft.md", (300, 300))
            os.utime(posts / "live.md", (200, 200))
            items = _list_items(PaperConfig(posts_dir=posts, site_dir=posts / ".site"))
            self.assertEqual(items[0].slug, "__home__")
            self.assertEqual(items[0].title, "My Home")
            self.assertEqual([item.slug for item in items[1:]], ["draft", "live"])
            self.assertTrue(items[0].published)
            self.assertFalse(items[1].published)

    def test_first_run_requires_link_before_new(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            os.environ["PAPER_HOME"] = str(Path(root) / ".paper")
            try:
                output = io.StringIO()
                with contextlib.redirect_stderr(output):
                    code = main(["new", "Private"])
                self.assertEqual(code, 2)
                self.assertIn("paper link", output.getvalue())
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_link_new_and_build_are_one_local_writing_slice(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            paper_home = Path(root) / ".paper"
            posts = Path(root) / "notes"
            os.environ["PAPER_HOME"] = str(paper_home)
            try:
                self.assertEqual(main(["link", str(posts)]), 0)
                self.assertEqual(main(["new", "Hello Paper"]), 0)
                draft = posts / "hello-paper.md"
                self.assertTrue(draft.exists())
                self.assertEqual(main(["build"]), 0)
                output = paper_home / "site" / "out"
                self.assertTrue((output / "index.html").exists())
                self.assertFalse((output / "posts" / "hello-paper" / "index.html").exists())
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_new_writes_no_frontmatter_title_and_falls_back_to_filename(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            paper_home = Path(root) / ".paper"
            posts = Path(root) / "notes"
            os.environ["PAPER_HOME"] = str(paper_home)
            try:
                self.assertEqual(main(["link", str(posts)]), 0)
                self.assertEqual(main(["new", "Hello Paper"]), 0)
                draft = posts / "hello-paper.md"
                content = draft.read_text(encoding="utf-8")
                self.assertNotIn("title:", content)
                self.assertIn("published: false", content)
                draft.write_text(
                    content.replace("published: false", "published: true"),
                    encoding="utf-8",
                )
                self.assertEqual(main(["build"]), 0)
                index_html = (paper_home / "site" / "out" / "index.html").read_text(encoding="utf-8")
                self.assertIn('href="/posts/hello-paper/"', index_html)
                self.assertIn(">hello-paper<", index_html)
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_version_key_orders_stable_above_prerelease(self):
        self.assertGreater(_version_key("0.1.1"), _version_key("0.1.1-beta.1"))
        self.assertGreater(_version_key("0.1.1-beta.2"), _version_key("0.1.1-beta.1"))
        self.assertGreater(_version_key("0.1.1-beta.1"), _version_key("0.1.0"))
        self.assertEqual(_version_key("0.1.1-beta.1"), _version_key("0.1.1-beta.1"))

    def test_startup_update_notice_reports_newer_release(self):
        with mock.patch("paper_cli._latest_available_version", return_value="0.1.2"):
            self.assertIn("paper update", _startup_update_notice())
        with mock.patch("paper_cli._latest_available_version", return_value=paper_cli.VERSION):
            self.assertEqual(_startup_update_notice(), "")

    def test_latest_version_check_uses_six_hour_cache(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            os.environ["PAPER_HOME"] = str(Path(root) / ".paper")
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = (
                b'[{"tag_name":"v0.1.2","draft":false},{"tag_name":"v0.1.1-beta.4","draft":false}]'
            )
            try:
                with mock.patch("paper_cli.urlopen", return_value=response) as open_url:
                    self.assertEqual(_latest_available_version(), "0.1.2")
                    self.assertEqual(_latest_available_version(), "0.1.2")
                open_url.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_keeps_published_state_when_deploy_cannot_run(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                draft = root_path / "notes" / "draft.md"
                draft.write_text(
                    "---\ntitle: Draft\npublished: false\n---\n\nBody\n",
                    encoding="utf-8",
                )
                config_path = Path(os.environ["PAPER_HOME"]) / "config.json"
                config = config_path.read_text(encoding="utf-8").replace(
                    '"gitRemote": ""', '"gitRemote": "https://example.invalid/paper.git"'
                )
                config_path.write_text(config, encoding="utf-8")
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    code = main(["publish", "draft"])
                self.assertEqual(code, 1)
                self.assertIn("git", output.getvalue().lower())
                self.assertIn("published: true", draft.read_text(encoding="utf-8"))
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_without_drafts_still_builds_and_deploys(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                output = io.StringIO()
                with contextlib.redirect_stdout(output), mock.patch(
                    "sys.stdin.isatty", return_value=True
                ), mock.patch("sys.stdout.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_multiselect", return_value=[]
                ) as multiselect, mock.patch("paper_cli.cmd_deploy", return_value=0) as deploy:
                    code = main(["publish"])
                self.assertEqual(code, 0)
                self.assertIn("没有需要首次发布的草稿", output.getvalue())
                multiselect.assert_not_called()
                deploy.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_empty_selection_syncs_site_and_keeps_draft(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                draft = root_path / "notes" / "draft.md"
                draft.write_text(
                    "---\ntitle: Draft\npublished: false\n---\n\nBody\n",
                    encoding="utf-8",
                )
                output = io.StringIO()
                with contextlib.redirect_stdout(output), mock.patch(
                    "sys.stdin.isatty", return_value=True
                ), mock.patch("sys.stdout.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_multiselect", return_value=[]
                ), mock.patch("paper_cli.cmd_deploy", return_value=0) as deploy:
                    code = main(["publish"])
                self.assertEqual(code, 0)
                self.assertIn("没有需要首次发布的草稿", output.getvalue())
                self.assertIn("published: false", draft.read_text(encoding="utf-8"))
                deploy.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_published_slug_rebuilds_without_touching_frontmatter(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                live = root_path / "notes" / "live.md"
                live.write_text(
                    "---\ntitle: Live\npublished: true\n---\n\nOld body\n",
                    encoding="utf-8",
                )
                self.assertEqual(main(["build"]), 0)
                live.write_text(
                    "---\ntitle: Live\npublished: true\n---\n\nNew body\n",
                    encoding="utf-8",
                )
                with mock.patch("paper_cli.cmd_deploy", return_value=0) as deploy:
                    code = main(["publish", "live"])
                self.assertEqual(code, 0)
                self.assertIn("published: true", live.read_text(encoding="utf-8"))
                rendered = (
                    root_path / ".paper" / "site" / "out" / "posts" / "live" / "index.html"
                ).read_text(encoding="utf-8")
                self.assertIn("New body", rendered)
                self.assertNotIn("Old body", rendered)
                deploy.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_slug_draft_sets_published_true(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                draft = root_path / "notes" / "draft.md"
                draft.write_text(
                    "---\ntitle: Draft\npublished: false\n---\n\nBody\n",
                    encoding="utf-8",
                )
                with mock.patch("paper_cli.cmd_deploy", return_value=0):
                    code = main(["publish", "draft"])
                self.assertEqual(code, 0)
                self.assertIn("published: true", draft.read_text(encoding="utf-8"))
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_all_without_drafts_still_syncs(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                (root_path / "notes" / "live.md").write_text(
                    "---\ntitle: Live\npublished: true\n---\n\nBody\n",
                    encoding="utf-8",
                )
                output = io.StringIO()
                with contextlib.redirect_stdout(output), mock.patch(
                    "paper_cli.cmd_deploy", return_value=0
                ) as deploy:
                    code = main(["publish", "--all"])
                self.assertEqual(code, 0)
                self.assertIn("没有需要首次发布的草稿", output.getvalue())
                deploy.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_publish_build_failure_rolls_back_only_newly_published(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                self.assertEqual(main(["link", str(root_path / "notes")]), 0)
                draft = root_path / "notes" / "draft.md"
                draft.write_text(
                    "---\ntitle: Draft\npublished: false\n---\n\nBody\n",
                    encoding="utf-8",
                )
                live = root_path / "notes" / "live.md"
                live.write_text(
                    "---\ntitle: Live\npublished: true\n---\n\nBody\n",
                    encoding="utf-8",
                )
                with mock.patch("paper_cli.build_site", side_effect=RuntimeError("boom")):
                    code = main(["publish", "draft", "live"])
                self.assertEqual(code, 1)
                self.assertIn("published: false", draft.read_text(encoding="utf-8"))
                self.assertIn("published: true", live.read_text(encoding="utf-8"))
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def _deploy_env(self, root_path: Path) -> Path:
        """Set up a linked site with a local managed repo and origin, no network."""
        self.assertEqual(main(["link", str(root_path / "notes")]), 0)
        config_path = root_path / ".paper" / "config.json"
        text = config_path.read_text(encoding="utf-8").replace(
            '"gitRemote": ""', '"gitRemote": "https://example.invalid/paper.git"'
        )
        config_path.write_text(text, encoding="utf-8")
        site_dir = root_path / ".paper" / "site"
        _init_with_origin(site_dir, "https://example.invalid/paper.git", gh_pages=True)
        (root_path / "notes" / "live.md").write_text(
            "---\ntitle: Live\npublished: true\n---\n\nBody\n",
            encoding="utf-8",
        )
        return site_dir

    @staticmethod
    def _fake_push_success():
        return subprocess.CompletedProcess(["git"], 0, "", "")

    def test_deploy_commits_when_diff_and_never_uses_allow_empty(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                site_dir = self._deploy_env(root_path)
                self.assertEqual(main(["build"]), 0)
                real_git = paper_cli._git
                calls: list[tuple[str, ...]] = []

                def spy(config, *args, **kwargs):
                    calls.append(tuple(args))
                    return real_git(config, *args, **kwargs)

                with mock.patch("paper_cli._git", side_effect=spy), mock.patch(
                    "paper_cli._run_with_spinner", return_value=self._fake_push_success()
                ) as push:
                    code = main(["deploy"])
                self.assertEqual(code, 0)
                log = subprocess.run(
                    ["git", "-C", str(site_dir), "log", "--oneline", "-1"],
                    capture_output=True,
                    text=True,
                ).stdout
                self.assertIn("paper: update site", log)
                self.assertFalse(
                    any("--allow-empty" in args for args in calls),
                    f"--allow-empty should never be used, got {calls}",
                )
                push.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_deploy_without_diff_skips_commit_but_pushes(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                site_dir = self._deploy_env(root_path)
                self.assertEqual(main(["build"]), 0)
                with mock.patch(
                    "paper_cli._run_with_spinner", return_value=self._fake_push_success()
                ):
                    self.assertEqual(main(["deploy"]), 0)
                count_before = subprocess.run(
                    ["git", "-C", str(site_dir), "rev-list", "--count", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                with mock.patch(
                    "paper_cli._run_with_spinner", return_value=self._fake_push_success()
                ) as push:
                    code = main(["deploy"])
                self.assertEqual(code, 0)
                count_after = subprocess.run(
                    ["git", "-C", str(site_dir), "rev-list", "--count", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self.assertEqual(count_before, count_after)
                push.assert_called_once()
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home

    def test_rebuild_same_input_produces_no_git_diff(self):
        with tempfile.TemporaryDirectory() as root:
            old_home = os.environ.get("PAPER_HOME")
            root_path = Path(root)
            os.environ["PAPER_HOME"] = str(root_path / ".paper")
            try:
                site_dir = self._deploy_env(root_path)
                self.assertEqual(main(["build"]), 0)
                subprocess.run(
                    ["git", "-C", str(site_dir), "add", "out"], check=True, capture_output=True
                )
                subprocess.run(
                    ["git", "-C", str(site_dir), "commit", "-m", "first build"],
                    check=True,
                    capture_output=True,
                )
                self.assertEqual(main(["build"]), 0)
                diff = subprocess.run(
                    ["git", "-C", str(site_dir), "diff", "HEAD", "--", "out"],
                    capture_output=True,
                    text=True,
                ).stdout
                self.assertEqual(diff, "")
            finally:
                if old_home is None:
                    os.environ.pop("PAPER_HOME", None)
                else:
                    os.environ["PAPER_HOME"] = old_home


class GitHubRemoteConfigTests(unittest.TestCase):
    def _set_paper_home(self, root: Path):
        old_home = os.environ.get("PAPER_HOME")
        os.environ["PAPER_HOME"] = str(root / ".paper")
        return old_home

    def test_config_sets_github_remote_end_to_end(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input", side_effect=["octocat/Hello-World", ""]
                ), mock.patch("paper_cli.webbrowser.open", return_value=True), mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True, True, True, True]
                ), mock.patch(
                    "paper_cli.cmd_publish", return_value=0
                ), mock.patch("paper_cli._gh_pages_pushed", return_value=True):
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads((root_path / ".paper" / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/Hello-World.git")
                if shutil.which("git") is not None:
                    origin = subprocess.run(
                        ["git", "-C", str(root_path / ".paper" / "site"), "remote", "get-url", "origin"],
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    self.assertEqual(origin, "git@github.com:octocat/Hello-World.git")
            finally:
                self._restore_paper_home(old_home)

    def test_wizard_opens_repo_creation_and_pages_settings(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input", side_effect=["octocat/Hello-World", ""]
                ), mock.patch("paper_cli.webbrowser.open", return_value=True) as browser, mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True, True, True, True]
                ), mock.patch(
                    "paper_cli.cmd_publish", return_value=0
                ), mock.patch("paper_cli._gh_pages_pushed", return_value=True):
                    self.assertEqual(cmd_config(), 0)
                self.assertEqual(
                    browser.call_args_list,
                    [
                        mock.call("https://github.com/new"),
                        mock.call("https://github.com/octocat/Hello-World/settings/pages"),
                    ],
                )
            finally:
                self._restore_paper_home(old_home)

    def test_wizard_reports_missing_git_without_changes(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch("paper_cli.shutil.which", return_value=None), mock.patch(
                    "builtins.input", side_effect=[""]
                ):
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads((root_path / ".paper" / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "")
            finally:
                self._restore_paper_home(old_home)

    def test_wizard_retries_invalid_address_then_saves(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input",
                    side_effect=["not-an-address", "", "octocat/Hello-World", ""],
                ), mock.patch("paper_cli.webbrowser.open", return_value=True), mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True, True, True, True]
                ), mock.patch(
                    "paper_cli.cmd_publish", return_value=0
                ), mock.patch("paper_cli._gh_pages_pushed", return_value=True):
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads((root_path / ".paper" / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/Hello-World.git")
            finally:
                self._restore_paper_home(old_home)

    def test_wizard_skip_keeps_settings_page_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input", side_effect=["octocat/Hello-World", ""]
                ), mock.patch("paper_cli._confirm_or_skip", side_effect=[True, True, False, False]), mock.patch(
                    "paper_cli.webbrowser.open", return_value=True
                ) as browser:
                    self.assertEqual(cmd_config(), 0)
                self.assertEqual(browser.call_args_list, [mock.call("https://github.com/new")])
                saved = json.loads((root_path / ".paper" / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/Hello-World.git")
            finally:
                self._restore_paper_home(old_home)

    def test_configured_remote_rebind_skips_repo_creation(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                config_file = root_path / ".paper" / "config.json"
                config_file.write_text(
                    config_file.read_text(encoding="utf-8").replace(
                        '"gitRemote": ""', '"gitRemote": "git@github.com:octocat/Hello-World.git"'
                    ),
                    encoding="utf-8",
                )
                site = root_path / ".paper" / "site"
                _init_with_origin(site, "git@github.com:octocat/Hello-World.git")
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch("builtins.input", side_effect=["octocat/New-Repo", "YES", ""]), mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True, True, True]
                ), mock.patch(
                    "paper_cli.webbrowser.open", return_value=True
                ) as browser, mock.patch("paper_cli.cmd_publish", return_value=0), mock.patch(
                    "paper_cli._gh_pages_pushed", return_value=True
                ):
                    self.assertEqual(cmd_config(), 0)
                # Re-binding still runs the wizard, but skips the create-repo step:
                # no github.com/new, only the new repo's Pages settings.
                self.assertEqual(
                    browser.call_args_list,
                    [mock.call("https://github.com/octocat/New-Repo/settings/pages")],
                )
                saved = json.loads(config_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/New-Repo.git")
                origin = subprocess.run(
                    ["git", "-C", str(site), "remote", "get-url", "origin"], capture_output=True, text=True
                ).stdout.strip()
                self.assertEqual(origin, "git@github.com:octocat/New-Repo.git")
            finally:
                self._restore_paper_home(old_home)

    def test_configured_remote_wizard_cancel_keeps_binding(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                config_file = root_path / ".paper" / "config.json"
                config_file.write_text(
                    config_file.read_text(encoding="utf-8").replace(
                        '"gitRemote": ""', '"gitRemote": "git@github.com:octocat/Hello-World.git"'
                    ),
                    encoding="utf-8",
                )
                site = root_path / ".paper" / "site"
                _init_with_origin(site, "git@github.com:octocat/Hello-World.git")
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch("builtins.input", side_effect=[""]), mock.patch(
                    "paper_cli.webbrowser.open", return_value=True
                ) as browser:
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads(config_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/Hello-World.git")
                browser.assert_not_called()
            finally:
                self._restore_paper_home(old_home)

    def test_config_remote_mismatch_requires_yes_to_retarget(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                config_file = root_path / ".paper" / "config.json"
                config_file.write_text(
                    config_file.read_text(encoding="utf-8").replace(
                        '"gitRemote": ""', '"gitRemote": "git@github.com:old/old.git"'
                    ),
                    encoding="utf-8",
                )
                site = root_path / ".paper" / "site"
                _init_with_origin(site, "git@github.com:old/old.git")
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input", side_effect=["octocat/Hello-World", "YES", ""]
                ), mock.patch("paper_cli._confirm_or_skip", side_effect=[True, True, True]), mock.patch(
                    "paper_cli.webbrowser.open", return_value=True
                ), mock.patch(
                    "paper_cli.cmd_publish", return_value=0
                ), mock.patch("paper_cli._gh_pages_pushed", return_value=True):
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads(config_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:octocat/Hello-World.git")
                origin = subprocess.run(
                    ["git", "-C", str(site), "remote", "get-url", "origin"], capture_output=True, text=True
                ).stdout.strip()
                self.assertEqual(origin, "git@github.com:octocat/Hello-World.git")
            finally:
                self._restore_paper_home(old_home)

    def test_config_remote_mismatch_decline_changes_nothing(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                config_file = root_path / ".paper" / "config.json"
                config_file.write_text(
                    config_file.read_text(encoding="utf-8").replace(
                        '"gitRemote": ""', '"gitRemote": "git@github.com:old/old.git"'
                    ),
                    encoding="utf-8",
                )
                site = root_path / ".paper" / "site"
                _init_with_origin(site, "git@github.com:old/old.git")
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch("builtins.input", side_effect=["octocat/Hello-World", "no"]), mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True]
                ):
                    self.assertEqual(cmd_config(), 0)
                saved = json.loads(config_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["gitRemote"], "git@github.com:old/old.git")
                origin = subprocess.run(
                    ["git", "-C", str(site), "remote", "get-url", "origin"], capture_output=True, text=True
                ).stdout.strip()
                self.assertEqual(origin, "git@github.com:old/old.git")
            finally:
                self._restore_paper_home(old_home)

    def test_wizard_prints_step_tracker_and_guidance(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                buffer = io.StringIO()
                with mock.patch("sys.stdin.isatty", return_value=True), mock.patch(
                    "paper_cli._terminal_menu", side_effect=["remote", None]
                ), mock.patch(
                    "builtins.input", side_effect=["octocat/Hello-World", ""]
                ), mock.patch("paper_cli.webbrowser.open", return_value=True), mock.patch(
                    "paper_cli._confirm_or_skip", side_effect=[True, True, True, True]
                ), mock.patch("paper_cli.cmd_publish", return_value=0), mock.patch(
                    "paper_cli._gh_pages_pushed", return_value=True
                ), contextlib.redirect_stdout(buffer):
                    self.assertEqual(cmd_config(), 0)
                output = re.sub(r"\x1b\[[0-9;]*m", "", buffer.getvalue())
                self.assertIn("● 1 创建仓库", output)  # active step marker
                self.assertIn("✓ 1 创建仓库", output)  # completed step marker
                self.assertIn("● 4 发布开启", output)
                self.assertIn("已为你打开 GitHub 新建仓库页", output)
                self.assertIn("git@github.com:用户名/仓库.git", output)
                self.assertIn("┌", output)  # content panel border
            finally:
                self._restore_paper_home(old_home)

    def test_config_subcommand_parser_routes_nested(self):
        args = make_parser().parse_args(["config", "home", "color"])
        self.assertEqual(args.command, "config")
        self.assertEqual(args.config_cmd, "home")
        self.assertEqual(args.home_cmd, "color")

        args = make_parser().parse_args(["config", "home"])
        self.assertEqual(args.config_cmd, "home")
        self.assertEqual(getattr(args, "home_cmd", None), None)

        args = make_parser().parse_args(["config", "remote"])
        self.assertEqual(args.config_cmd, "remote")
        self.assertEqual(getattr(args, "home_cmd", None), None)

        args = make_parser().parse_args(["config", "compress", "off"])
        self.assertEqual(args.config_cmd, "compress")
        self.assertEqual(args.compress_cmd, "off")

    def test_config_compress_defaults_on_and_can_be_toggled_directly(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            old_home = self._set_paper_home(root_path)
            try:
                self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                config_file = root_path / ".paper" / "config.json"
                self.assertTrue(json.loads(config_file.read_text(encoding="utf-8"))["compress"])

                self.assertEqual(main(["config", "compress", "off"]), 0)
                self.assertFalse(json.loads(config_file.read_text(encoding="utf-8"))["compress"])

                self.assertEqual(main(["config", "compress", "on"]), 0)
                self.assertTrue(json.loads(config_file.read_text(encoding="utf-8"))["compress"])
            finally:
                self._restore_paper_home(old_home)

    def test_config_subcommand_dispatches_to_leaf(self):
        cases = [
            (["home", "color"], "paper_cli._set_highlight_color"),
            (["home", "icon"], "paper_cli._set_icon"),
            (["home"], "paper_cli.cmd_brand_config"),
            (["editor"], "paper_cli._choose_editor"),
            (["remote"], "paper_cli.cmd_remote_entry"),
            (["status"], "paper_cli.cmd_status"),
            (["test"], "paper_cli.cmd_test_connection"),
        ]
        for subargs, target in cases:
            with self.subTest(subargs=subargs):
                with tempfile.TemporaryDirectory() as root:
                    root_path = Path(root)
                    old_home = self._set_paper_home(root_path)
                    try:
                        self.assertEqual(main(["link", str(root_path / "posts")]), 0)
                        with mock.patch(target) as leaf:
                            main(["config", *subargs])
                        leaf.assert_called_once()
                    finally:
                        self._restore_paper_home(old_home)

    def test_deployment_readiness_states(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            posts = root_path / "posts"
            base = PaperConfig(posts_dir=posts, site_dir=root_path / "site")
            self.assertEqual(_deployment_readiness(base)[0], "not-configured")

            configured = PaperConfig(posts_dir=posts, site_dir=root_path / "site2", git_remote="git@github.com:o/r.git")
            self.assertEqual(_deployment_readiness(configured)[0], "unverified")

            site_ready = root_path / "site3"
            _init_with_origin(site_ready, "git@github.com:o/r.git")
            ready = PaperConfig(posts_dir=posts, site_dir=site_ready, git_remote="git@github.com:o/r.git")
            self.assertEqual(_deployment_readiness(ready)[0], "ready")

            site_pushed = root_path / "site4"
            _init_with_origin(site_pushed, "git@github.com:o/r.git", gh_pages=True)
            pushed = PaperConfig(posts_dir=posts, site_dir=site_pushed, git_remote="git@github.com:o/r.git")
            self.assertEqual(_deployment_readiness(pushed)[0], "pushed")

            site_mismatch = root_path / "site5"
            _init_with_origin(site_mismatch, "git@github.com:other/other.git")
            mismatched = PaperConfig(posts_dir=posts, site_dir=site_mismatch, git_remote="git@github.com:o/r.git")
            self.assertEqual(_deployment_readiness(mismatched)[0], "unverified")

    def test_test_connection_reports_git_missing(self):
        cfg = PaperConfig(posts_dir=Path("/unused/posts"), site_dir=Path("/unused/site"), git_remote="git@github.com:o/r.git")
        with mock.patch("paper_cli.shutil.which", return_value=None):
            self.assertNotEqual(cmd_test_connection(cfg), 0)

    def test_test_connection_success_failure_and_timeout(self):
        cfg = PaperConfig(posts_dir=Path("/unused/posts"), site_dir=Path("/unused/site"), git_remote="git@github.com:o/r.git")
        with mock.patch("paper_cli.subprocess.run", return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            self.assertEqual(cmd_test_connection(cfg), 0)
            self.assertEqual(run.call_args.args[0][:2], ["git", "ls-remote"])
        with mock.patch(
            "paper_cli.subprocess.run",
            return_value=mock.Mock(returncode=128, stdout="", stderr="Permission denied (publickey)"),
        ):
            self.assertNotEqual(cmd_test_connection(cfg), 0)
        with mock.patch(
            "paper_cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git ls-remote", timeout=10),
        ):
            self.assertNotEqual(cmd_test_connection(cfg), 0)

    def test_with_spinner_runs_callable_off_tty(self):
        calls = []

        def probe():
            calls.append(1)
            return "done"

        self.assertEqual(_with_spinner("working", probe), "done")
        self.assertEqual(calls, [1])  # ran synchronously, once

    def test_with_spinner_propagates_exception_off_tty(self):
        def boom():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            _with_spinner("working", boom)

    def test_with_spinner_propagates_exception_on_tty(self):
        with mock.patch("paper_cli.sys.stdout.isatty", return_value=True), mock.patch(
            "paper_cli.sys.stderr.isatty", return_value=True
        ), mock.patch("paper_cli.time.sleep"):

            def boom():
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                _with_spinner("working", boom)

    def _restore_paper_home(self, old_home):
        if old_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = old_home


if __name__ == "__main__":
    unittest.main()
