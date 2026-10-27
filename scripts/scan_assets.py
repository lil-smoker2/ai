#!/usr/bin/env python
"""Manual asset scan: discover, index, analyze and thumbnail images.

Usage (from the repository root, using the backend venv):
    apps/api/.venv/bin/python scripts/scan_assets.py [--force-full]

New image files placed anywhere under assets/ are discovered automatically;
filenames are never changed and new category folders are detected on the fly.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services.asset_scanner import scan_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan the LifeSmart asset library")
    parser.add_argument("--force-full", action="store_true",
                        help="re-analyze and regenerate all thumbnails")
    args = parser.parse_args()

    with SessionLocal() as db:
        summary = scan_assets(db, get_settings(), force_full=args.force_full)

    print(
        f"scanned={summary.files_seen} new={summary.new} updated={summary.updated} "
        f"unchanged={summary.unchanged} duplicates={summary.duplicates} "
        f"corrupted={summary.corrupted} removed={summary.removed}"
    )
    for err in summary.errors:
        print(f"  warning: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
