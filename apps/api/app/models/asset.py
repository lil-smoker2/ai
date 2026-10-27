from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow

ASSET_STATUSES = ("active", "duplicate", "corrupted", "missing")
ANALYSIS_SOURCES = ("folder", "vision", "manual")


class Asset(Base):
    """A discovered image file. Original filenames are never changed or required
    by the UI; internal ids and hashes identify assets."""

    __tablename__ = "assets"

    # Stable uuid assigned at first discovery, preserved across rescans.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Path relative to ASSETS_ROOT; never exposed outside sanitized form.
    rel_path: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    # Folder-inferred category, e.g. "clothing/trousers". Configurable and
    # extended automatically when new category folders are added.
    category: Mapped[str] = mapped_column(String(255), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    format: Mapped[str] = mapped_column(String(20))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    file_modified_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(
        Enum(*ASSET_STATUSES, name="asset_status"), default="active"
    )
    duplicate_of: Mapped[str | None] = mapped_column(
        ForeignKey("assets.id"), default=None
    )
    thumbnail_rel_path: Mapped[str | None] = mapped_column(
        String(512), default=None
    )
    attribution: Mapped[str | None] = mapped_column(String(255), default=None)
    license: Mapped[str | None] = mapped_column(String(120), default=None)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AssetAnalysis(Base):
    """Structured analysis result for an asset. Folder-based classification is
    the fallback; vision adapters plug in without changing the schema."""

    __tablename__ = "asset_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    predicted_category: Mapped[str | None] = mapped_column(String(255), default=None)
    predicted_item_type: Mapped[str | None] = mapped_column(String(120), default=None)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    attributes: Mapped[dict | None] = mapped_column(JSON, default=None)
    source: Mapped[str] = mapped_column(
        Enum(*ANALYSIS_SOURCES, name="analysis_source"), default="folder"
    )
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
