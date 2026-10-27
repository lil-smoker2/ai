"""Single-user local mode bootstrap used by the packaged desktop app.

The route is gated on ``local_single_user``: hidden (404) by default so a
hosted multi-user deployment stays safe, and enabled only when the desktop
binary marks itself local.
"""
from app.core.config import get_settings
from app.api.auth import LOCAL_EMAIL


def _enable_local(client):
    base = get_settings()
    local = base.model_copy(update={"local_single_user": True})
    client.app.dependency_overrides[get_settings] = lambda: local


def _disable_local(client):
    client.app.dependency_overrides.clear()


def test_local_bootstrap_hidden_when_not_local_mode(client):
    # Default settings: local_single_user is False -> route is not exposed.
    resp = client.post("/api/auth/local")
    assert resp.status_code == 404


def test_local_bootstrap_issues_token_and_creates_user(client):
    _enable_local(client)
    try:
        resp = client.post("/api/auth/local")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["access_token"]
        assert data["user"]["email"] == LOCAL_EMAIL
        assert data["user"]["onboarded"] is False

        headers = {"Authorization": f"Bearer {data['access_token']}"}
        # The issued token authenticates against the normal isolated routes.
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        assert client.get("/api/inventory/categories", headers=headers).status_code == 200
    finally:
        _disable_local(client)


def test_local_bootstrap_reuses_the_same_single_user(client):
    _enable_local(client)
    try:
        first = client.post("/api/auth/local").json()["user"]["id"]
        second = client.post("/api/auth/local").json()["user"]["id"]
        assert first == second  # idempotent: never spawns duplicate accounts
    finally:
        _disable_local(client)
