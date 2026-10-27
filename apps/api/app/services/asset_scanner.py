"""Dynamic asset discovery pipeline.

Scans ASSETS_ROOT recursively, preserves original filenames, computes content
hashes for duplicate detection, validates real image content (never trusts
extensions), generates thumbnails in a separate directory and indexes metadata
in the database. New category folders are detected automatically.
"""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.asset import Asset, AssetAnalysis
from app.services import analysis

THUMBNAIL_DIRNAME = ".thumbnails"
THUMBNAIL_MAX_SIZE = (320, 320)
IGNORED_FILENAMES = {".gitkeep", "thumbs.db", "desktop.ini"}


@dataclass
class ScanSummary:
    files_seen: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates: int = 0
    corrupted: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_category(rel_path: Path) -> str:
    """Category from folder path under assets root, e.g. clothing/trousers."""
    parts = rel_path.parent.parts
    return "/".join(parts) if parts else "uncategorized"


def category_match(category: str):
    """SQL clause matching a category label at any depth, case-insensitively.

    Callers pass a short label - the inventory UI sends an item's category
    ("trousers") - while assets are filed by folder path ("clothing/trousers").
    Matching only the head of the path left every nested wardrobe image unseen,
    so a label resolves as an exact path, a path prefix, a final segment or a
    middle segment. LIKE wildcards inside the label are escaped. Returns None
    for a blank label, which callers treat as "no filter".
    """
    like = (category or "").strip().replace("\\", "\\\\").replace("%", "\\%")
    like = like.replace("_", "\\_")
    if not like:
        return None
    return or_(
        Asset.category.ilike(like, escape="\\"),            # clothing/trousers
        Asset.category.ilike(f"{like}/%", escape="\\"),     # a top-level folder's subtree
        Asset.category.ilike(f"%/{like}", escape="\\"),     # .../trousers (leaf)
        Asset.category.ilike(f"%/{like}/%", escape="\\"),   # .../trousers/...
    )


def _read_image_metadata(path: Path, supported: set[str]) -> tuple[str, int, int]:
    """Validate actual content; raise on non-image/corrupted/unsupported files."""
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        if (img.format or "").upper() not in supported:
            raise ValueError(f"unsupported format {img.format}")
        return img.format.upper(), img.width, img.height


def _generate_thumbnail(source: Path, thumb_path: Path) -> None:
    with Image.open(source) as img:
        if img.mode == "P":
            img = img.convert("RGB")
        img.thumbnail(THUMBNAIL_MAX_SIZE)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(thumb_path, "WEBP", quality=80)


def scan_assets(db: Session, settings: Settings, force_full: bool = False) -> ScanSummary:
    root = settings.assets_root_path
    summary = ScanSummary()
    if not root.is_dir():
        summary.errors.append(f"assets root missing: {root}")
        return summary

    supported = settings.supported_formats
    thumb_root = root / THUMBNAIL_DIRNAME
    seen_rel_paths: set[str] = set()

    existing = {a.rel_path: a for a in db.scalars(select(Asset))}
    first_by_hash: dict[str, Asset] = {}
    for asset in existing.values():
        if asset.status == "active":
            first_by_hash.setdefault(asset.sha256, asset)

    now = datetime.now(timezone.utc)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == THUMBNAIL_DIRNAME:
            continue
        if path.name.lower() in IGNORED_FILENAMES:
            continue

        summary.files_seen += 1
        rel_str = rel.as_posix()
        seen_rel_paths.add(rel_str)

        size = path.stat().st_size
        if size > settings.max_image_bytes:
            summary.corrupted += 1
            summary.errors.append(f"{rel_str}: exceeds size limit")
            continue

        try:
            fmt, width, height = _read_image_metadata(path, supported)
        except (UnidentifiedImageError, ValueError, OSError) as exc:
            summary.corrupted += 1
            summary.errors.append(f"{rel_str}: {exc}")
            # Record rejected files so rescans can report them consistently.
            known = existing.get(rel_str)
            if known is not None and known.status != "corrupted":
                known.status = "corrupted"
                known.last_seen_at = now
            continue

        file_hash = _sha256(path)
        # Naive UTC: SQLite strips tz info on round-trip; keep both sides equal.
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(
            tzinfo=None
        )
        category = _infer_category(rel)
        asset = existing.get(rel_str)
        dup_of = first_by_hash.get(file_hash)
        is_duplicate = dup_of is not None and dup_of.rel_path != rel_str

        if asset is None:
            changed = True
            asset = Asset(
                id=str(uuid.uuid4()),
                rel_path=rel_str,
                original_filename=path.name,
                category=category,
                sha256=file_hash,
                size_bytes=size,
                format=fmt,
                width=width,
                height=height,
                file_modified_at=mtime,
                status="duplicate" if is_duplicate else "active",
                duplicate_of=dup_of.id if is_duplicate else None,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(asset)
            db.flush()
            summary.new += 1
            if is_duplicate:
                summary.duplicates += 1
        else:
            changed = asset.sha256 != file_hash or asset.file_modified_at != mtime
            asset.original_filename = path.name
            asset.category = category
            asset.size_bytes = size
            asset.format = fmt
            asset.width = width
            asset.height = height
            asset.file_modified_at = mtime
            asset.last_seen_at = now
            if changed:
                asset.sha256 = file_hash
                asset.status = "duplicate" if is_duplicate else "active"
                asset.duplicate_of = dup_of.id if is_duplicate else None
                summary.updated += 1
            else:
                summary.unchanged += 1
            if is_duplicate:
                asset.status = "duplicate"
                asset.duplicate_of = dup_of.id
                summary.duplicates += 1

        if asset.status != "duplicate":
            if not is_duplicate:
                first_by_hash.setdefault(file_hash, asset)
            thumb_path = thumb_root / f"{asset.id}.webp"
            if force_full or changed or asset.thumbnail_rel_path is None:
                try:
                    _generate_thumbnail(path, thumb_path)
                    asset.thumbnail_rel_path = f"{THUMBNAIL_DIRNAME}/{asset.id}.webp"
                except Exception as exc:  # thumbnail failure is non-fatal
                    summary.errors.append(f"{rel_str}: thumbnail {exc}")

        # Store analysis metadata once per stable asset/hash (or on rescan force).
        has_analysis = db.scalars(
            select(AssetAnalysis).where(
                AssetAnalysis.asset_id == asset.id,
                AssetAnalysis.source == "folder",
            )
        ).first()
        if has_analysis is None or force_full:
            result = analysis.analyze_image(path, category)
            if result is not None:
                if has_analysis is not None:
                    db.delete(has_analysis)
                db.add(
                    AssetAnalysis(
                        asset_id=asset.id,
                        predicted_category=result.get("predicted_category"),
                        predicted_item_type=result.get("predicted_item_type"),
                        confidence=float(result.get("confidence", 0.0)),
                        attributes=result.get("attributes"),
                        source=result.get("source", "folder"),
                    )
                )

    # Files removed from disk since the last scan.
    for rel_str, asset in existing.items():
        if rel_str not in seen_rel_paths and asset.status != "missing":
            asset.status = "missing"
            summary.removed += 1

    db.commit()
    return summary
