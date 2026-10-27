"""LifeSmart desktop launcher.

This is the entrypoint frozen by PyInstaller into a single `lifesmart`
executable. It initialises the local database, serves the API + bundled UI
on a loopback port, and opens a native window. Everything runs per-user with
data in ~/.local/share/lifesmart - no server, no sudo, no external database.
"""
import os
import asyncio
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from app.core.config import data_home, get_settings
from app.core.database import Base, engine


def _ensure_schema() -> None:
    """Create tables on first run (idempotent). Keeps the desktop app
    self-contained; Alembic remains the path for hosted/production deploys."""
    import app.models  # noqa: F401  register all mappers on Base.metadata

    Base.metadata.create_all(bind=engine)


def _free_port(preferred: int = 8756) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No available loopback port")


class _NoSignalServer(uvicorn.Server):
    """uvicorn installs SIGINT/SIGTERM handlers, which raise when the server
    runs in a worker thread. We drive shutdown via should_exit from the main
    thread instead, so skip that setup."""

    def install_signal_handlers(self) -> None:  # pragma: no cover - override
        pass


class _Server:
    def __init__(self, app, host: str, port: int) -> None:
        self.config = uvicorn.Config(
            app, host=host, port=port, log_level="warning", lifespan="on"
        )
        self.server = _NoSignalServer(self.config)

    def run(self) -> None:
        asyncio.run(self.server.serve())

    def stop(self) -> None:
        self.server.should_exit = True


def _wait_until_ready(url: str, timeout: float = 15.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _open_window(url: str) -> None:
    """Prefer a chromeless app window; fall back gracefully.

    Chromium-family browsers support --app (no address bar -> feels native).
    Otherwise the default browser opens the URL. pywebview is optional.
    """
    if os.environ.get("LIFESMART_NO_WINDOW"):
        return

    for exe, flag in (
        ("chromium", "--app={u}"),
        ("chromium-browser", "--app={u}"),
        ("google-chrome", "--app={u}"),
        ("google-chrome-stable", "--app={u}"),
        ("brave", "--app={u}"),
        ("microsoft-edge-stable", "--app={u}"),
        ("vivaldi-stable", "--app={u}"),
    ):
        path = shutil.which(exe)
        if path:
            subprocess.Popen(  # noqa: S603 (trusted fixed argv)
                [path, flag.format(u=url), "--user-data-dir=" + str(data_home() / "browser")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    webbrowser.open(url)


def _bundle_path(rel: str) -> Path:
    """Resolve a file bundled into the frozen binary (or beside desktop.py)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / rel
    return Path(__file__).resolve().parent / rel


def _system_python() -> str | None:
    """The distro interpreter that carries the GTK bindings.

    Never the frozen binary and not a bare venv (which lacks ``gi``), so we
    probe the known system paths first.
    """
    for cand in ("/usr/bin/python3", "/usr/bin/python"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("python3")


def _gui_available(py: str) -> bool:
    """True if this interpreter can load GTK + WebKit2 (native window path)."""
    probe = (
        "import gi;"
        "gi.require_version('Gtk','3.0');"
        "gi.require_version('WebKit2','4.1');"
        "from gi.repository import Gtk, WebKit2"
    )
    try:
        r = subprocess.run(
            [py, "-c", probe],
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return r.returncode == 0
    except Exception:
        return False


def _open_native_window(py: str, opener: str, url: str) -> int:
    """Launch the native GTK window (blocking until it is closed)."""
    env = dict(os.environ)
    env.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    try:
        return subprocess.run([py, opener, url], env=env).returncode
    except KeyboardInterrupt:
        return 130


def _run_until_interrupt(srv: "_Server") -> int:
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.stop()
    return 0


def main() -> int:
    from app.main import create_app

    get_settings()  # ensures the data dir + secret exist
    _ensure_schema()

    host = "127.0.0.1"
    port = _free_port()
    url = f"http://{host}:{port}"

    srv = _Server(create_app(), host, port)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()

    if not _wait_until_ready(url):
        print(
            "LifeSmart failed to start. Check permissions in:",
            data_home(),
            file=sys.stderr,
            flush=True,
        )
        return 1

    print(f"LifeSmart is running at {url}  (data: {data_home()})", flush=True)

    # Headless (tests / no display): keep the server up until Ctrl-C.
    if os.environ.get("LIFESMART_NO_WINDOW"):
        return _run_until_interrupt(srv)

    # Preferred: a real native GTK/WebKit window via the system python, which
    # already ships PyGObject + webkit2gtk on GNOME desktops. This blocks until
    # the window is closed, then we shut the server down so the app exits.
    py = _system_python()
    opener = _bundle_path("packaging/window_opener.py")
    if py and opener.is_file() and _gui_available(py):
        print("Opening the LifeSmart window\u2026", flush=True)
        _open_native_window(py, str(opener), url)
        srv.stop()
        return 0

    # Fallback: standalone Chromium app window (or the default browser).
    print("Native window toolkit unavailable; opening a standalone app window.",
          flush=True)
    _open_window(url)
    return _run_until_interrupt(srv)


if __name__ == "__main__":
    sys.exit(main())
