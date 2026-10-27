"""Dynamic asset API: discovery scan, listing, metadata and thumbnails.

Images reach the frontend only through these endpoints - never through
hardcoded filenames or URLs. Management endpoints require authentication.
Server filesystem paths are never exposed; only asset ids and sanitized
category paths are returned.
"""
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.core.database import SessionLocal, get_db
from app.models.asset import Asset, AssetAnalysis
from app.models.user import User
from app.schemas.assets import AnalysisOut, AssetOut, AssetPage, ScanRequest, ScanStatus
from app.schemas.common import Page
from app.services.asset_scanner import category_match, scan_assets

router = APIRouter(prefix="/api/assets", tags=["assets"])

# In-process scan state; a task queue replaces this only when scale requires it.
_scan_lock = threading.Lock()
_scan_state = ScanStatus(state="idle")


def _run_scan(force_full: bool) -> None:
    global _scan_state
    db = SessionLocal()
    try:
        summary = scan_assets(db, get_settings(), force_full=force_full)
        _scan_state = ScanStatus(
            state="completed",
            started_at=_scan_state.started_at,
            finished_at=datetime.now(timezone.utc),
            files_seen=summary.files_seen,
            new=summary.new,
            updated=summary.updated,
            duplicates=summary.duplicates,
            corrupted=summary.corrupted,
            removed=summary.removed,
            error="; ".join(summary.errors[:5]) or None,
        )
    except Exception as exc:
        _scan_state = ScanStatus(state="failed", error=str(exc))
    finally:
        db.close()
        _scan_lock.release()


@router.post("/scan", response_model=ScanStatus, status_code=202)
def trigger_scan(body: ScanRequest = ScanRequest(),
                 background: BackgroundTasks = None,
                 user: User = Depends(get_current_user)):
    global _scan_state
    if not _scan_lock.acquire(blocking=False):
        return _scan_state  # a scan is already running
    _scan_state = ScanStatus(state="running", started_at=datetime.now(timezone.utc))
    background.add_task(_run_scan, body.force_full)
    return _scan_state


@router.get("/scan/status", response_model=ScanStatus)
def scan_status(user: User = Depends(get_current_user)):
    return _scan_state


@router.get("", response_model=AssetPage)
def list_assets(
    category: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status",
                                      pattern="^(active|duplicate|corrupted|missing)$"),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Asset)
    # Nested folder labels ("clothing/trousers" for a "Trousers" item) resolve
    # through the shared matcher, the same one the net-worth page uses.
    match = category_match(category) if category else None
    if match is not None:
        query = query.where(match)
    if status_filter:
        query = query.where(Asset.status == status_filter)
    else:
        query = query.where(Asset.status == "active")

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Asset.rel_path)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    assets = []
    for asset in rows:
        analysis = db.scalars(
            select(AssetAnalysis)
            .where(AssetAnalysis.asset_id == asset.id)
            .order_by(AssetAnalysis.analyzed_at.desc())
        ).first()
        out = AssetOut.model_validate(asset)
        out.analysis = AnalysisOut.model_validate(analysis) if analysis else None
        if min_confidence is not None and (
            out.analysis is None or out.analysis.confidence < min_confidence
        ):
            continue
        assets.append(out)

    return AssetPage(assets=assets,
                     page=Page(total=total, page=page, page_size=page_size))


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """All categories currently present in the indexed library. New folders
    appear here after a scan without any code change."""
    rows = db.scalars(
        select(Asset.category).where(Asset.status == "active").distinct()
    ).all()
    return sorted(rows)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    out = AssetOut.model_validate(asset)
    analysis = db.scalars(
        select(AssetAnalysis)
        .where(AssetAnalysis.asset_id == asset.id)
        .order_by(AssetAnalysis.analyzed_at.desc())
    ).first()
    out.analysis = AnalysisOut.model_validate(analysis) if analysis else None
    return out


@router.get("/{asset_id}/thumbnail")
def get_thumbnail(asset_id: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id)
    if asset is None or asset.thumbnail_rel_path is None:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    settings = get_settings()
    root = settings.assets_root_path.resolve()
    path = (root / asset.thumbnail_rel_path).resolve()
    # Path traversal guard: thumbnail must remain inside the assets root.
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return FileResponse(path, media_type="image/webp")
