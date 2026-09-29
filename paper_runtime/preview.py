#!/usr/bin/env python3
"""Folder-bound background preview used by the Paper console.

The console should never ask the user to run ``paper serve`` by hand, and it
should never start a second server for a folder that already has one. This
module keeps a small registry under ``$PAPER_HOME/preview`` that maps a project
folder to its live preview daemon:

* one detached daemon process per project folder, reachable over HTTP;
* every console registers itself as a client while it is open;
* the daemon (and its local URL) is reused by every other console opened on the
  same folder;
* the daemon is torn down when the last client exits, or immediately by the
  last console that releases the folder.

The serving primitives (``_PreviewState``, ``_watch_preview``,
``_PreviewHandler`` ...) live here and are re-exported by ``paper_cli`` so the
CLI and the tests keep a single implementation.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import http.server
import json
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field, replace
from functools import partial
from pathlib import Path
from urllib.request import urlopen

from paper_runtime.core import (
    PaperConfig,
    _base_path,
    build_site,
    load_config,
    load_local_config,
    paper_home,
)
from paper_runtime.i18n import t

PREVIEW_POLL_SECONDS = 0.5
PREVIEW_DEBOUNCE_SECONDS = 2.0
PREVIEW_SWAP_RETRIES = 6
PREVIEW_SWAP_RETRY_SECONDS = 0.05
PREVIEW_CLIENT_POLL_SECONDS = 2.0
PREVIEW_IDLE_GRACE_SECONDS = 4.0
PREVIEW_START_TIMEOUT_SECONDS = 20.0
DEFAULT_PREVIEW_PORT = 8000
REVISION_PATH = "/.paper-revision"
_PREVIEW_SUBDIR = ".preview"
_DAEMON_PROCESSES: list[subprocess.Popen[bytes]] = []


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
        if request_path == REVISION_PATH:
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
        self._wait_for_output()
        super().do_GET()

    def _wait_for_output(self) -> None:
        """Rebuilds swap the output directory; wait out the gap instead of answering 404.

        The swap renames `out` away before the fresh tree takes its place, so a request
        landing in that window would see a missing path even though the site is fine.
        """

        for attempt in range(PREVIEW_SWAP_RETRIES):
            if os.path.exists(self.translate_path(self.path)):
                return
            if attempt < PREVIEW_SWAP_RETRIES - 1:
                time.sleep(PREVIEW_SWAP_RETRY_SECONDS)

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


# ── Registry ─────────────────────────────────────────────────────────────────


@dataclass
class PreviewHandle:
    """A console's lease on a folder's preview daemon."""

    url: str
    port: int
    key: str
    reused: bool = False


def registry_root() -> Path:
    return paper_home() / "preview"


def project_key(config: PaperConfig) -> str:
    """Stable identity for a project folder, independent of process or port."""

    target = str(Path(config.site_dir).expanduser().resolve())
    return hashlib.sha1(target.encode("utf-8")).hexdigest()[:16]


def preview_url(config: PaperConfig, port: int) -> str:
    base_path = _base_path(replace(config, site_dir=config.site_dir / _PREVIEW_SUBDIR))
    path = f"{base_path}/" if base_path else "/"
    return f"http://127.0.0.1:{port}{path}"


def _server_file(key: str) -> Path:
    return registry_root() / f"{key}.json"


def _clients_dir(key: str) -> Path:
    return registry_root() / f"{key}.clients"


def _lock_file(key: str) -> Path:
    return registry_root() / f"{key}.lock"


def _log_file(key: str) -> Path:
    return registry_root() / f"{key}.log"


def _read_server(key: str) -> dict[str, object] | None:
    try:
        return json.loads(_server_file(key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_server(key: str, payload: dict[str, object]) -> None:
    target = _server_file(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temp, target)


def _remove_server(key: str) -> None:
    try:
        _server_file(key).unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def _probe(port: int, timeout: float = 1.5) -> bool:
    if port <= 0:
        return False
    try:
        with urlopen(f"http://127.0.0.1:{port}{REVISION_PATH}", timeout=timeout) as response:
            return int(response.status) == 200
    except Exception:
        return False


def _live_server(key: str) -> dict[str, object] | None:
    """Return the running daemon record for this folder, or None when absent."""

    info = _read_server(key)
    if not info:
        return None
    pid = int(info.get("pid") or 0)
    port = int(info.get("port") or 0)
    if _pid_alive(pid) and _probe(port):
        return info
    return None


def _register_client(key: str, pid: int) -> None:
    directory = _clients_dir(key)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / str(pid)).write_text(str(time.time()), encoding="utf-8")


def _unregister_client(key: str, pid: int) -> None:
    try:
        (_clients_dir(key) / str(pid)).unlink()
    except OSError:
        pass


def _live_client_pids(key: str) -> list[int]:
    directory = _clients_dir(key)
    if not directory.is_dir():
        return []
    pids: list[int] = []
    for entry in directory.iterdir():
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        if _pid_alive(pid):
            pids.append(pid)
        else:
            try:
                entry.unlink()
            except OSError:
                pass
    return pids


def _terminate_pid(pid: int, timeout: float = 5.0) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


class _RegistryLock:
    """Serialize registry reads/writes across console processes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle = None

    def __enter__(self) -> "_RegistryLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self._path, "a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def _pythonpath_with_package() -> str:
    """Make ``paper_runtime`` importable by the detached daemon interpreter."""

    package_parent = str(Path(__file__).resolve().parent.parent)
    existing = os.environ.get("PYTHONPATH", "")
    return package_parent + (os.pathsep + existing if existing else "")


def _spawn_daemon(
    config: PaperConfig,
    key: str,
    *,
    port: int,
    mode: str,
    config_dir: str | None,
) -> dict[str, object] | None:
    root = registry_root()
    root.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "paper_runtime.preview",
        "daemon",
        "--key",
        key,
        "--port",
        str(port),
        "--mode",
        mode,
    ]
    if config_dir:
        argv += ["--config-dir", config_dir]
    env = dict(os.environ)
    env["PYTHONPATH"] = _pythonpath_with_package()
    try:
        with open(_log_file(key), "wb") as log:
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env=env,
                start_new_session=True,
                close_fds=True,
            )
    except OSError:
        return None
    # Keep a handle to the detached daemon so Python does not warn about a
    # still-running child when the Popen object is collected.
    _DAEMON_PROCESSES[:] = [proc for proc in _DAEMON_PROCESSES if proc.poll() is None]
    _DAEMON_PROCESSES.append(process)
    deadline = time.monotonic() + PREVIEW_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        info = _live_server(key)
        if info:
            return info
        time.sleep(0.2)
    return None


def _teardown_dead_server(key: str) -> None:
    """Drop a stale record and stop a hung daemon that no longer answers HTTP."""

    info = _read_server(key)
    if info:
        _terminate_pid(int(info.get("pid") or 0))
    _remove_server(key)


def _acquire_locked(
    config: PaperConfig,
    key: str,
    *,
    port: int,
    mode: str,
    config_dir: str | None,
) -> PreviewHandle | None:
    pid = os.getpid()
    info = _live_server(key)
    if info:
        _register_client(key, pid)
        actual_port = int(info.get("port") or port)
        return PreviewHandle(url=preview_url(config, actual_port), port=actual_port, key=key, reused=True)
    _teardown_dead_server(key)
    _register_client(key, pid)
    info = _spawn_daemon(config, key, port=port, mode=mode, config_dir=config_dir)
    if info is None:
        return None
    actual_port = int(info.get("port") or port)
    return PreviewHandle(url=preview_url(config, actual_port), port=actual_port, key=key, reused=False)


def acquire_preview(
    config: PaperConfig,
    *,
    local: bool = False,
    local_dir: Path | str | None = None,
    port: int = DEFAULT_PREVIEW_PORT,
) -> PreviewHandle | None:
    """Reuse this folder's running preview, or start one bound to the folder."""

    key = project_key(config)
    mode = "local" if (local or local_dir is not None) else "global"
    config_dir = str(Path(local_dir or ".").expanduser().resolve()) if mode == "local" else None
    with _RegistryLock(_lock_file(key)):
        return _acquire_locked(config, key, port=port, mode=mode, config_dir=config_dir)


def release_preview(handle: PreviewHandle | None) -> None:
    """Drop this console's lease; stop the daemon when it was the last client."""

    if handle is None:
        return
    key = handle.key
    pid = os.getpid()
    with _RegistryLock(_lock_file(key)):
        _unregister_client(key, pid)
        if _live_client_pids(key):
            return
        info = _read_server(key)
        if info:
            _terminate_pid(int(info.get("pid") or 0))
        _remove_server(key)


def restart_preview(
    config: PaperConfig,
    *,
    local: bool = False,
    local_dir: Path | str | None = None,
    port: int = DEFAULT_PREVIEW_PORT,
) -> PreviewHandle | None:
    """Rebuild this folder's preview from scratch, keeping other consoles served."""

    key = project_key(config)
    mode = "local" if (local or local_dir is not None) else "global"
    config_dir = str(Path(local_dir or ".").expanduser().resolve()) if mode == "local" else None
    pid = os.getpid()
    with _RegistryLock(_lock_file(key)):
        _register_client(key, pid)
        info = _read_server(key)
        previous_port = int(info.get("port") or 0) if info else 0
        if info:
            _terminate_pid(int(info.get("pid") or 0))
        _remove_server(key)
        fresh = _spawn_daemon(
            config,
            key,
            port=previous_port or port,
            mode=mode,
            config_dir=config_dir,
        )
        if fresh is None:
            return None
        actual_port = int(fresh.get("port") or port)
        return PreviewHandle(url=preview_url(config, actual_port), port=actual_port, key=key, reused=False)


# ── Daemon ───────────────────────────────────────────────────────────────────


def _monitor_clients(key: str, stop_event: threading.Event, server: socketserver.BaseServer) -> None:
    empty_since: float | None = None
    while not stop_event.is_set():
        if _live_client_pids(key):
            empty_since = None
        else:
            now = time.monotonic()
            if empty_since is None:
                empty_since = now
            elif now - empty_since >= PREVIEW_IDLE_GRACE_SECONDS:
                break
        stop_event.wait(PREVIEW_CLIENT_POLL_SECONDS)
    server.shutdown()


def _run_daemon(key: str, port: int, mode: str, config_dir: str) -> int:
    config = (
        load_local_config(Path(config_dir).expanduser().resolve())
        if mode == "local" and config_dir
        else load_config()
    )
    preview_config = replace(config, site_dir=config.site_dir / _PREVIEW_SUBDIR)
    build_site(preview_config, include_drafts=True, live_reload=True)

    state = _PreviewState()
    _PreviewHandler.preview_state = state
    stop_watcher = threading.Event()
    watcher = threading.Thread(
        target=_watch_preview,
        args=(preview_config, state, stop_watcher),
        name="paper-preview-watcher",
        daemon=True,
    )
    watcher.start()
    state.watcher_ready.wait()

    base_path = _base_path(preview_config)
    handler = partial(_PreviewHandler, directory=str(preview_config.output_dir), base_path=base_path)
    try:
        try:
            server = _PreviewServer(("127.0.0.1", port), handler)
        except OSError:
            server = _PreviewServer(("127.0.0.1", 0), handler)
        with server:
            actual_port = int(server.server_address[1])
            _write_server(
                key,
                {
                    "key": key,
                    "dir": str(config.site_dir),
                    "port": actual_port,
                    "pid": os.getpid(),
                    "started": time.time(),
                },
            )
            stop_event = threading.Event()

            def _handle_signal(_signum: int, _frame: object) -> None:
                stop_event.set()

            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    signal.signal(sig, _handle_signal)
                except (ValueError, OSError):
                    pass
            monitor = threading.Thread(
                target=_monitor_clients,
                args=(key, stop_event, server),
                name="paper-preview-monitor",
                daemon=True,
            )
            monitor.start()
            try:
                server.serve_forever(poll_interval=PREVIEW_POLL_SECONDS)
            finally:
                _remove_server(key)
    finally:
        stop_watcher.set()
        state.refresh_requested.set()
        watcher.join(timeout=1)
        shutil.rmtree(preview_config.site_dir, ignore_errors=True)
    return 0


def daemon_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paper-preview")
    subparsers = parser.add_subparsers(dest="command")
    daemon = subparsers.add_parser("daemon")
    daemon.add_argument("--key", required=True)
    daemon.add_argument("--port", type=int, default=DEFAULT_PREVIEW_PORT)
    daemon.add_argument("--mode", choices=["local", "global"], default="global")
    daemon.add_argument("--config-dir", default="")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "daemon":
        parser.print_help()
        return 2
    return _run_daemon(args.key, args.port, args.mode, args.config_dir)


if __name__ == "__main__":
    raise SystemExit(daemon_main())
