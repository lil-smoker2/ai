"""Near-duplicate image detection - a deterministic, offline perceptual hash.

The asset pipeline already rejects byte-for-byte copies by content hash (see
``asset_scanner``). This service answers the harder, neighbouring question:
which *different* files look alike - the same picture re-saved, resized or
lightly edited. It computes a perceptual "image hash" (a 64-bit DCT fingerprint)
for each active asset straight from the file on disk and groups images whose
hashes sit within a small Hamming distance.

Everything is arithmetic over Pillow pixels: no model, no dependency and no
network. Recomputing from the files on every call keeps the result honest with
what is actually present; the library is small and this endpoint is on-demand,
so nothing is cached. A picture with no near-duplicate is simply not reported.
"""
import math
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.asset import Asset

HASH_SIZE = 8            # fingerprint is HASH_SIZE * HASH_SIZE bits
DCT_INPUT = 32           # image is reduced to this square before the transform
# Hamming radius (of 64 bits) counted as "looks alike". Real re-saves of one
# photo (re-encode, resize, light edit) sit near zero; unrelated photos land
# far above this. Deliberately conservative so the tool over-merges nothing.
MAX_DISTANCE = 10


def _dct_matrix(n: int) -> list[list[float]]:
    """Orthonormal Type-II DCT basis, so ``C · pixeldata · Cᵀ`` is the 2D DCT."""
    factor = math.pi / n
    matrix = []
    for u in range(n):
        cu = 1.0 / math.sqrt(2.0) if u == 0 else 1.0
        matrix.append([cu * math.cos((2 * x + 1) * u * factor) for x in range(n)])
    return matrix


def _hamming(a: str, b: str) -> int:
    """Bits that differ between two equal-length binary strings."""
    if len(a) != len(b):
        raise ValueError("perceptual hashes must be the same length")
    return sum(bit_a != bit_b for bit_a, bit_b in zip(a, b))


def _load_pixels(path: Path) -> list[list[float]] | None:
    """Grayscale, resized to DCT_INPUT square, as a row-major float grid."""
    try:
        with Image.open(path) as img:
            img = img.convert("L").resize(
                (DCT_INPUT, DCT_INPUT), Image.BILINEAR
            )
            data = list(img.getdata())  # row-major: [rows][cols]
            return [
                [float(v) for v in data[row * DCT_INPUT:(row + 1) * DCT_INPUT]]
                for row in range(DCT_INPUT)
            ]
    except (OSError, ValueError):
        return None


def phash_from_file(path: Path) -> str | None:
    """64-bit perceptual fingerprint as a binary string, or None if unreadable.

    The image is reduced to a square and taken through the DCT; the low-frequency
    (structural) 8x8 block is kept and each coefficient is compared against the
    median of the *other* coefficients - a shape code robust to resize, format and
    light compression. The median is taken with the DC (average-brightness) term
    excluded, so a darker or lighter copy of the same picture still matches while
    the DC bit itself stays in the code. Coefficients are rounded first so a flat,
    featureless picture hashes deterministically.
    """
    pixels = _load_pixels(path)
    if pixels is None:
        return None

    n = DCT_INPUT
    matrix = _dct_matrix(n)
    tmp = [
        [sum(matrix[u][i] * pixels[i][j] for i in range(n)) for j in range(n)]
        for u in range(n)
    ]
    coeffs = [
        [sum(tmp[u][k] * matrix[v][k] for k in range(n)) for v in range(n)]
        for u in range(n)
    ]

    block = [
        (round(coeffs[u][v]), u == 0 and v == 0)
        for u in range(HASH_SIZE)
        for v in range(HASH_SIZE)
    ]
    ac = sorted(value for value, is_dc in block if not is_dc)
    length = len(ac)
    median = float(ac[length // 2]) if length % 2 else (
        ac[length // 2 - 1] + ac[length // 2]
    ) / 2.0
    return "".join("1" if value > median else "0" for value, _ in block)


def _clusters(items: list[dict]) -> list[list[dict]]:
    """Group items so any two within MAX_DISTANCE land in one cluster.

    Single-linkage over the "looks alike" relation: union the endpoints of every
    close pair, then collect by root. Pairwise in the library size, which for one
    person's image folder stays well under any practical limit.
    """
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if _hamming(items[i]["hash"], items[j]["hash"]) <= MAX_DISTANCE:
                root_i, root_j = find(i), find(j)
                if root_i != root_j:
                    parent[root_j] = root_i

    groups: dict[int, list[dict]] = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return list(groups.values())


def find_similar_assets(db: Session, settings: Settings) -> dict:
    """Cluster the active library into groups of near-duplicate pictures.

    Only ``active`` assets are considered - byte-identical files were already
    reduced to a single ``active`` copy by the content-hash scan. A group is
    reported only when two or more genuinely different files look alike.
    """
    root = settings.assets_root_path
    assets = db.scalars(
        select(Asset).where(Asset.status == "active").order_by(Asset.rel_path)
    ).all()

    items: list[dict] = []
    for asset in assets:
        digest = phash_from_file(root / asset.rel_path)
        if digest is None:
            continue  # file moved or corrupted since the scan; not claimed
        items.append(
            {
                "id": asset.id,
                "original_filename": asset.original_filename,
                "category": asset.category,
                "rel_path": asset.rel_path,
                "hash": digest,
            }
        )

    groups = [
        sorted(cluster, key=lambda item: item["rel_path"])
        for cluster in _clusters(items)
        if len(cluster) > 1
    ]
    groups.sort(key=lambda members: members[0]["rel_path"])
    return {
        "threshold": MAX_DISTANCE,
        "hash_bits": HASH_SIZE * HASH_SIZE,
        "groups": [
            {
                "members": [
                    {
                        "id": member["id"],
                        "original_filename": member["original_filename"],
                        "category": member["category"],
                    }
                    for member in cluster
                ]
            }
            for cluster in groups
        ],
    }
