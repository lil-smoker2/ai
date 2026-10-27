from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Page


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    predicted_category: str | None
    predicted_item_type: str | None
    confidence: float
    attributes: dict | None
    source: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    category: str
    format: str
    width: int
    height: int
    size_bytes: int
    status: str
    duplicate_of: str | None
    attribution: str | None
    license: str | None
    last_seen_at: datetime
    analysis: AnalysisOut | None = None


class AssetPage(BaseModel):
    assets: list[AssetOut]
    page: Page


class ScanRequest(BaseModel):
    """Optional rescan control. force_full regenerates thumbnails for all."""

    force_full: bool = False


class ScanStatus(BaseModel):
    state: str  # idle | running | completed | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    files_seen: int = 0
    new: int = 0
    updated: int = 0
    duplicates: int = 0
    corrupted: int = 0
    removed: int = 0
    error: str | None = None
