"""Pluggable image-analysis interface.

Folder-based categorization is the always-available fallback. Vision adapters
(local VLM, embeddings, authorized cloud APIs) can be registered without
changing the schema or the frontend.
"""
from pathlib import Path
from typing import Protocol

from PIL import Image


class AnalysisResult(dict):
    """predicted_category, predicted_item_type, confidence, attributes, source."""


class ImageAnalyzer(Protocol):
    name: str

    def analyze(self, image_path: Path, category: str) -> AnalysisResult | None:
        ...


class FolderFallbackAnalyzer:
    """Uses the user's folder placement as the classification signal.

    Confidence reflects explicit user organization, not visual proof; brand,
    price, quality and seller are never inferred from a photograph.
    """

    name = "folder"

    def analyze(self, image_path: Path, category: str) -> AnalysisResult | None:
        item_type = category.rsplit("/", 1)[-1] if "/" in category else category
        return AnalysisResult(
            predicted_category=category,
            predicted_item_type=item_type,
            confidence=0.9,
            attributes=None,
            source="folder",
        )


class DominantColorMixin:
    """Optional lightweight attribute extraction for adapters."""

    @staticmethod
    def dominant_color(image_path: Path) -> str | None:
        try:
            with Image.open(image_path) as img:
                small = img.convert("RGB").resize((32, 32))
                pixel = small.getpixel((16, 16))
                return "#{:02x}{:02x}{:02x}".format(*pixel)
        except Exception:
            return None


# Registered analyzers, tried in order; first non-None result wins.
_ANALYZERS: list[ImageAnalyzer] = [FolderFallbackAnalyzer()]


def register_analyzer(analyzer: ImageAnalyzer, prepend: bool = True) -> None:
    """Vision adapters call this at startup (prepend=True to take priority)."""
    if prepend:
        _ANALYZERS.insert(0, analyzer)
    else:
        _ANALYZERS.append(analyzer)


def analyze_image(image_path: Path, category: str) -> AnalysisResult | None:
    for analyzer in _ANALYZERS:
        result = analyzer.analyze(image_path, category)
        if result is not None:
            return result
    return None
