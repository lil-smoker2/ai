"""Perceptual near-duplicate detection: unit checks and the /api/assets/similar
endpoint. Exact copies are handled elsewhere by the content hash; these tests
cover the harder case - the same picture re-saved or resized under a different
filename must be grouped, while a genuinely different image must not be.

Nothing here invents a group: a lone picture reports nothing, and only files
that are actually present are claimed.
"""
from pathlib import Path

from PIL import Image

from app.services.perceptual import (
    MAX_DISTANCE,
    _hamming,
    phash_from_file,
)


def _gradient(size=120):
    img = Image.new("L", (size, size))
    for x in range(size):
        for y in range(size):
            img.putpixel((x, y), int(255 * x / (size - 1)))
    return img


def _blocks(size=120):
    img = Image.new("L", (size, size))
    for x in range(size):
        for y in range(size):
            img.putpixel((x, y), 255 if (x // 16 + y // 16) % 2 else 0)
    return img


def _save(directory: Path, name: str, img, fmt=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    img.save(path, fmt) if fmt else img.save(path)
    return path


def test_phash_is_64_bits_and_deterministic(tmp_path):
    path = _save(tmp_path, "grad.png", _gradient())
    first = phash_from_file(path)
    assert first is not None and len(first) == 64
    assert set(first) <= {"0", "1"}
    assert phash_from_file(path) == first  # same file, same code


def test_phash_returns_none_for_unreadable(tmp_path):
    bogus = tmp_path / "not-an-image.png"
    bogus.write_bytes(b"definitely not image bytes")
    assert phash_from_file(bogus) is None


def test_reencode_and_resize_stay_within_threshold(tmp_path):
    source = _gradient()
    png = phash_from_file(_save(tmp_path, "a.png", source))
    jpeg = phash_from_file(_save(tmp_path, "a.jpg", source, "JPEG"))
    big = phash_from_file(_save(tmp_path, "big.png", source.resize((300, 300))))
    assert _hamming(png, jpeg) <= MAX_DISTANCE
    assert _hamming(png, big) <= MAX_DISTANCE


def test_structurally_different_image_is_far(tmp_path):
    grad = phash_from_file(_save(tmp_path, "g.png", _gradient()))
    blocks = phash_from_file(_save(tmp_path, "b.png", _blocks()))
    assert _hamming(grad, blocks) > MAX_DISTANCE


def _write_library(root: Path):
    """Two near-duplicate families plus a one-off, under arbitrary filenames."""
    grad = _gradient()
    _save(root / "clothing" / "shirts", "IMG_0001.png", grad)
    _save(root / "clothing" / "shirts", "copy_re.saved.jpg", grad, "JPEG")
    _save(root / "clothing" / "shirts", "big_version.png", grad.resize((300, 300)))
    _save(root / "household" / "plates", "patternA.png", _blocks())
    _save(root / "household" / "plates", "patternB.png", _blocks().resize((240, 240)))
    _save(root / "food" / "fruits", "lonely.png", _gradient(90).transpose(
        Image.ROTATE_90))


def _scan(client, auth_headers):
    resp = client.post("/api/assets/scan", json={}, headers=auth_headers)
    assert resp.status_code == 202


def test_similar_endpoint_requires_auth(client):
    assert client.get("/api/assets/similar").status_code == 401


def test_similar_groups_near_duplicates(client, auth_headers, assets_root):
    _write_library(assets_root)
    _scan(client, auth_headers)

    body = client.get("/api/assets/similar", headers=auth_headers).json()
    assert body["hash_bits"] == 64
    assert body["threshold"] == MAX_DISTANCE

    groups = {
        tuple(sorted(m["original_filename"] for m in g["members"]))
        for g in body["groups"]
    }
    # The three re-saves of the gradient collapse into one group.
    assert ("IMG_0001.png", "big_version.png", "copy_re.saved.jpg") in groups
    # The two pattern plates form a second group.
    assert ("patternA.png", "patternB.png") in groups


def test_similar_omits_lone_and_duplicate_assets(client, auth_headers, assets_root):
    # A single picture, and an exact byte copy, must never appear in a group:
    # the copy is folded by the content hash, the lone picture has no match.
    only = _gradient()
    _save(assets_root / "goals", "solo.png", only)
    exact = assets_root / "transport" / "cars" / "same_bytes.png"
    exact.parent.mkdir(parents=True, exist_ok=True)
    exact.write_bytes((assets_root / "goals" / "solo.png").read_bytes())
    _scan(client, auth_headers)

    body = client.get("/api/assets/similar", headers=auth_headers).json()
    assert body["groups"] == []


def test_similar_empty_library_reports_nothing(client, auth_headers, assets_root):
    _scan(client, auth_headers)
    body = client.get("/api/assets/similar", headers=auth_headers).json()
    assert body["groups"] == []
