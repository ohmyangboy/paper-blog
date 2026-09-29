"""Tests for the folder-bound background preview used by the console."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.error import URLError
from urllib.request import urlopen

from paper_runtime import preview as preview_runtime
from paper_runtime.core import load_local_config
from paper_runtime.preview import (
    PreviewHandle,
    _server_file,
    acquire_preview,
    preview_url,
    project_key,
    release_preview,
    restart_preview,
)


def _make_project(root: Path) -> Path:
    project = root / "blog"
    (project / "posts").mkdir(parents=True)
    (project / "posts" / "hello.md").write_text(
        "---\ntitle: Hello\npublished: true\n---\n\nHello preview body\n",
        encoding="utf-8",
    )
    return project


class PreviewRegistryUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="paper-preview-unit-"))
        self._old_home = os.environ.get("PAPER_HOME")
        os.environ["PAPER_HOME"] = str(self.temp_dir / ".paper")
        self.project = _make_project(self.temp_dir)
        self.config = load_local_config(self.project)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = self._old_home
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_project_key_is_stable_and_folder_specific(self) -> None:
        self.assertEqual(project_key(self.config), project_key(self.config))
        sibling = self.temp_dir / "other"
        (sibling / "posts").mkdir(parents=True)
        self.assertNotEqual(project_key(self.config), project_key(load_local_config(sibling)))

    def test_preview_url_includes_pages_base_path(self) -> None:
        self.assertEqual(preview_url(self.config, 8123), "http://127.0.0.1:8123/")
        with_remote = replace(self.config, git_remote="git@github.com:me/blog.git")
        self.assertEqual(preview_url(with_remote, 8123), "http://127.0.0.1:8123/blog/")

    def test_acquire_reuses_a_live_server(self) -> None:
        key = project_key(self.config)
        info = {"key": key, "port": 8123, "pid": os.getpid(), "dir": str(self.project)}
        with mock.patch.object(preview_runtime, "_live_server", return_value=info), mock.patch.object(
            preview_runtime, "_spawn_daemon"
        ) as spawn:
            handle = preview_runtime.acquire_preview(self.config, local=True, local_dir=self.project)
        self.assertIsNotNone(handle)
        self.assertTrue(handle.reused)
        self.assertEqual(handle.port, 8123)
        spawn.assert_not_called()

    def test_release_keeps_daemon_while_another_client_is_live(self) -> None:
        handle = PreviewHandle(url="http://127.0.0.1:8123/", port=8123, key="abc")
        with mock.patch.object(preview_runtime, "_live_client_pids", return_value=[os.getpid(), 4242]), mock.patch.object(
            preview_runtime, "_terminate_pid"
        ) as terminate:
            release_preview(handle)
        terminate.assert_not_called()

    def test_release_stops_daemon_after_the_last_client(self) -> None:
        handle = PreviewHandle(url="http://127.0.0.1:8123/", port=8123, key="abc")
        with mock.patch.object(preview_runtime, "_live_client_pids", return_value=[]), mock.patch.object(
            preview_runtime, "_read_server", return_value={"pid": 4242, "port": 8123}
        ), mock.patch.object(preview_runtime, "_terminate_pid") as terminate:
            release_preview(handle)
        terminate.assert_called_once_with(4242)


class PreviewDaemonIntegrationTests(unittest.TestCase):
    """Exercise a real detached daemon through the public helpers."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="paper-preview-int-"))
        self._old_home = os.environ.get("PAPER_HOME")
        os.environ["PAPER_HOME"] = str(self.temp_dir / ".paper")
        self.project = _make_project(self.temp_dir)
        self.config = load_local_config(self.project)
        self.key = project_key(self.config)
        self.handle: PreviewHandle | None = None

    def tearDown(self) -> None:
        if self.handle is not None:
            release_preview(self.handle)
        try:
            info = json.loads(_server_file(self.key).read_text(encoding="utf-8"))
            preview_runtime._terminate_pid(int(info.get("pid") or 0))
        except (OSError, json.JSONDecodeError):
            pass
        if self._old_home is None:
            os.environ.pop("PAPER_HOME", None)
        else:
            os.environ["PAPER_HOME"] = self._old_home
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _reachable(self, url: str, timeout: float = 2.0) -> bool:
        try:
            with urlopen(url, timeout=timeout) as response:
                return response.status == 200
        except (URLError, OSError):
            return False

    def _wait_until(self, predicate, timeout: float = 12.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.25)
        return predicate()

    def test_multiple_consoles_share_one_daemon_and_last_release_stops_it(self) -> None:
        self.handle = acquire_preview(self.config, local=True, local_dir=self.project)
        self.assertIsNotNone(self.handle)
        self.assertTrue(self._reachable(self.handle.url))
        post_url = f"{self.handle.url.rstrip('/')}/posts/hello/"
        with urlopen(post_url, timeout=3) as response:
            self.assertIn("Hello preview body", response.read().decode("utf-8"))

        # A second console opening the same folder reuses the running daemon
        # instead of building a duplicate server on another port.
        second = acquire_preview(self.config, local=True, local_dir=self.project)
        self.assertIsNotNone(second)
        self.assertTrue(second.reused)
        self.assertEqual(second.port, self.handle.port)

        # Both leases come from this test process, so dropping them stops the daemon.
        url = self.handle.url
        release_preview(second)
        self.assertTrue(self._wait_until(lambda: not self._reachable(url)), "last release must stop the daemon")
        release_preview(self.handle)
        self.handle = None

    def test_restart_replaces_daemon_and_keeps_the_same_port(self) -> None:
        first = acquire_preview(self.config, local=True, local_dir=self.project)
        self.assertIsNotNone(first)
        initial_pid = json.loads(_server_file(self.key).read_text(encoding="utf-8"))["pid"]

        self.handle = restart_preview(self.config, local=True, local_dir=self.project)
        self.assertIsNotNone(self.handle)
        restarted_pid = json.loads(_server_file(self.key).read_text(encoding="utf-8"))["pid"]
        self.assertNotEqual(initial_pid, restarted_pid)
        self.assertEqual(self.handle.port, first.port)
        self.assertTrue(self._reachable(self.handle.url))


if __name__ == "__main__":
    unittest.main()
