#!/usr/bin/env python
"""Development filesystem watcher: rescans assets when files change.

Usage:
    apps/api/.venv/bin/python scripts/watch_assets.py

Uses a short debounce; each batch triggers one incremental scan. In production
use POST /api/assets/scan (manual or scheduled) instead.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from watchdog.events import FileSystemEventHandler  # noqa: E402
from watchdog.observers import Observer  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services.asset_scanner import scan_assets  # noqa: E402

DEBOUNCE_SECONDS = 2.0


class _RescanHandler(FileSystemEventHandler):
    def __init__(self, root: Path):
        self.root = root
        self.dirty = False

    def on_any_event(self, event):
        if event.is_directory:
            return
        # Thumbnail output changes do not require a new scan.
        if f"{Path(event.src_path).name}" == ".gitkeep":
            return
        if self.root.name in Path(event.src_path).parts and \
                ".thumbnails" not in Path(event.src_path).parts:
            self.dirty = True


def main() -> int:
    settings = get_settings()
    root = settings.assets_root_path
    root.mkdir(parents=True, exist_ok=True)

    handler = _RescanHandler(root)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    print(f"watching {root} - Ctrl+C to stop")

    try:
        while True:
            time.sleep(1.0)
            if handler.dirty:
                time.sleep(DEBOUNCE_SECONDS)  # let writes settle
                handler.dirty = False
                with SessionLocal() as db:
                    summary = scan_assets(db, settings)
                print(
                    f"rescan: seen={summary.files_seen} new={summary.new} "
                    f"updated={summary.updated} removed={summary.removed} "
                    f"corrupted={summary.corrupted}"
                )
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
