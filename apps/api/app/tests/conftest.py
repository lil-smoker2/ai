"""Test configuration: isolated temp SQLite DB and temp assets root.

Environment variables MUST be set before any app import so cached settings
and the module-level engine point at the test resources.
"""
import os
import shutil
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="lifesmart-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ASSETS_ROOT"] = os.path.join(_tmpdir, "assets")
os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
# Keep the assistant deterministic in tests: the optional local LLM is never
# offered or loaded, so no turn can depend on llama.cpp being installed.
os.environ["ASSISTANT_LLM_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401 - register all tables with Base.metadata
from app.main import app  # noqa: E402


@pytest.fixture(scope="function", autouse=True)
def _database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def assets_root():
    root = get_settings().assets_root_path
    root.mkdir(parents=True, exist_ok=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="function")
def auth_headers(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test User",
            "email": "test@example.com",
            "password": "supersecret1",
            "terms_accepted": True,
        },
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="function")
def second_user_headers(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "full_name": "Other User",
            "email": "other@example.com",
            "password": "othersecret1",
            "terms_accepted": True,
        },
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
