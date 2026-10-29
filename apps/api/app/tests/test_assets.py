"""Dynamic asset pipeline tests, including the spec's acceptance scenarios.

Images are created with arbitrary filenames; nothing is renamed or hardcoded.
"""
from io import BytesIO

from PIL import Image

from app.core.config import get_settings
from app.services.asset_scanner import scan_assets
from app.core.database import SessionLocal


def _make_image(path, fmt="JPEG", size=(160, 120), color=(120, 60, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, fmt)
    return path


def _scan():
    with SessionLocal() as db:
        return scan_assets(db, get_settings())


def test_acceptance_random_filename_appears_without_rename(client, auth_headers,
                                                           assets_root):
    """Spec acceptance test 1: add IMG_3821.jpg to trousers, scan, it appears
    in the right category with its name untouched and no frontend change."""
    _make_image(assets_root / "clothing" / "trousers" / "IMG_3821.jpg")

    resp = client.post("/api/assets/scan", json={}, headers=auth_headers)
    assert resp.status_code == 202

    listing = client.get("/api/assets", params={"category": "clothing/trousers"},
                         headers=auth_headers).json()
    assert listing["page"]["total"] == 1
    asset = listing["assets"][0]
    assert asset["original_filename"] == "IMG_3821.jpg"
    assert asset["category"] == "clothing/trousers"
    assert asset["status"] == "active"
    assert asset["analysis"]["source"] == "folder"


def test_acceptance_new_category_folder_discovered(client, auth_headers, assets_root):
    """Spec acceptance test 2: a brand-new folder becomes available with no
    hardcoded entry anywhere."""
    _make_image(assets_root / "musical-instruments" / "guitars" / "download (3).webp",
                fmt="WEBP")

    client.post("/api/assets/scan", json={}, headers=auth_headers)

    categories = client.get("/api/assets/categories", headers=auth_headers).json()
    assert "musical-instruments/guitars" in categories
    listing = client.get("/api/assets",
                         params={"category": "musical-instruments"},
                         headers=auth_headers).json()
    assert listing["page"]["total"] == 1


def test_category_label_matches_a_nested_folder_segment(client, auth_headers,
                                                        assets_root):
    """The inventory UI sends a short slug ("trousers") while assets are filed
    by folder path ("clothing/trousers"), so the slug must resolve at depth."""
    _make_image(assets_root / "clothing" / "trousers" / "chino.jpg",
                color=(200, 30, 30))
    _make_image(assets_root / "clothing" / "jeans" / "denim.jpg",
                color=(30, 200, 30))
    _make_image(assets_root / "household" / "cups" / "mug.png", fmt="PNG",
                color=(30, 30, 200))
    client.post("/api/assets/scan", json={}, headers=auth_headers)

    def categories(label):
        body = client.get("/api/assets", params={"category": label},
                          headers=auth_headers).json()
        return {a["category"] for a in body["assets"]}

    assert categories("trousers") == {"clothing/trousers"}   # leaf segment
    assert categories("clothing") == {"clothing/trousers", "clothing/jeans"}  # subtree
    assert categories("clothing/trousers") == {"clothing/trousers"}  # full path
    assert categories("cups") == {"household/cups"}
    assert categories("wardrobe") == set()                   # unknown label
    assert categories("%") == set()                          # wildcard is literal


def test_mixed_formats_and_preserved_names(assets_root):
    _make_image(assets_root / "clothing" / "shoes" / "photo_2026.png", fmt="PNG")
    _make_image(assets_root / "clothing" / "shoes" / "download (3).webp", fmt="WEBP")
    _make_image(assets_root / "clothing" / "shoes" / "IMG_3821.jpg")
    summary = _scan()
    assert summary.new == 3
    assert summary.files_seen == 3

    with SessionLocal() as db:
        from app.models.asset import Asset

        assets = db.query(Asset).all()
        assert {a.format for a in assets} == {"PNG", "WEBP", "JPEG"}
        # Original filenames preserved exactly.
        assert {a.original_filename for a in assets} == {
            "photo_2026.png", "download (3).webp", "IMG_3821.jpg"
        }


def test_duplicate_content_detected_by_hash(assets_root):
    source = _make_image(assets_root / "clothing" / "trousers" / "one.jpg")
    # Same content bytes, arbitrary different filename - no renaming involved.
    copy = assets_root / "household" / "plates" / "copy-with-other-name.jpg"
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(source.read_bytes())
    summary = _scan()
    assert summary.duplicates >= 1

    with SessionLocal() as db:
        from app.models.asset import Asset

        dupes = db.query(Asset).filter(Asset.status == "duplicate").all()
        assert len(dupes) == 1
        assert dupes[0].duplicate_of is not None


def test_corrupted_file_rejected_gracefully(assets_root):
    bad = assets_root / "clothing" / "shirts" / "not-really-an-image.jpg"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"this is definitely not image data")
    _make_image(assets_root / "clothing" / "shirts" / "good.png", fmt="PNG")

    summary = _scan()
    assert summary.corrupted == 1
    assert summary.new == 1  # the app still indexed the valid image

    with SessionLocal() as db:
        from app.models.asset import Asset

        asset = db.query(Asset).filter(
            Asset.rel_path == "clothing/shirts/not-really-an-image.jpg"
        ).first()
        assert asset is None or asset.status == "corrupted"


def test_extension_spoofing_rejected(assets_root):
    """A .png file containing a text document must be rejected by content."""
    fake = assets_root / "electronics" / "phones" / "fake.png"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text("pretending to be a png", encoding="utf-8")
    summary = _scan()
    assert summary.corrupted == 1
    assert summary.new == 0


def test_thumbnail_generated_and_served(client, auth_headers, assets_root):
    _make_image(assets_root / "clothing" / "trousers" / "IMG_1.jpg")
    client.post("/api/assets/scan", json={}, headers=auth_headers)
    asset = client.get("/api/assets", headers=auth_headers).json()["assets"][0]

    thumb = client.get(f"/api/assets/{asset['id']}/thumbnail", headers=auth_headers)
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/webp"
    # Thumbnail stays within size limits.
    img = Image.open(BytesIO(thumb.content))
    assert max(img.size) <= 320


def test_rescan_is_incremental_and_stable(assets_root):
    path = _make_image(assets_root / "food" / "fruits" / "a.jpg")
    first = _scan()
    assert first.new == 1

    with SessionLocal() as db:
        from app.models.asset import Asset

        stable_id = db.query(Asset).one().id

    second = _scan()
    assert second.new == 0
    assert second.unchanged == 1

    with SessionLocal() as db:
        from app.models.asset import Asset

        asset = db.query(Asset).one()
        assert asset.id == stable_id  # id stable across rescans

        # Modify the file: hash updates, id stays.
        img = Image.new("RGB", (60, 60), (0, 255, 0))
        img.save(path, "JPEG")
        _scan()
        db.expire_all()  # pick up changes committed by the scan session
        asset = db.query(Asset).one()
        assert asset.id == stable_id
        assert (asset.width, asset.height) == (60, 60)


def test_removed_file_marked_missing(assets_root):
    path = _make_image(assets_root / "goals" / "gone.jpg")
    _scan()
    path.unlink()
    summary = _scan()
    assert summary.removed == 1

    with SessionLocal() as db:
        from app.models.asset import Asset

        assert db.query(Asset).one().status == "missing"


def test_asset_endpoints_require_auth(client, assets_root):
    assert client.get("/api/assets").status_code == 401
    assert client.post("/api/assets/scan", json={}).status_code == 401
    assert client.get("/api/assets/scan/status").status_code == 401


def test_empty_category_folder_does_not_crash_scan(client, auth_headers, assets_root):
    (assets_root / "transport" / "bicycles").mkdir(parents=True, exist_ok=True)
    resp = client.post("/api/assets/scan", json={}, headers=auth_headers)
    assert resp.status_code == 202
    assert client.get("/api/assets", headers=auth_headers).status_code == 200
