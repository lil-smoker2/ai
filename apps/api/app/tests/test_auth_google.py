"""Google Sign-In endpoint + token-verification tests.

Real ID tokens are minted locally with an RSA keypair and the JWKS lookup is
stubbed to return our public key - so the full verify -> find-or-create path
runs without touching Google's servers.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings, get_settings
from app.services import google_auth

CLIENT_ID = "test-client.apps.googleusercontent.com"  # set by conftest env

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_PEM = _private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


class _StubJwks:
    def get_signing_key_from_jwt(self, token: str):
        return SimpleNamespace(key=_PUBLIC_PEM)


@pytest.fixture(autouse=True)
def _stub_google_keys(monkeypatch):
    monkeypatch.setattr(google_auth, "_jwks_client", lambda: _StubJwks())


def make_token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-user-123",
        "email": "User@Example.com",
        "name": "User Example",
        "email_verified": True,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, _private_key, algorithm="RS256",
                      headers={"kid": "test-key"})


def test_verify_accepts_valid_token():
    payload = google_auth.verify_google_id_token(make_token(), CLIENT_ID)
    assert payload["email"] == "User@Example.com"


@pytest.mark.parametrize("bad", [
    "not-a-jwt",
    make_token(aud="some-other-client"),
    make_token(exp=datetime.now(timezone.utc) - timedelta(minutes=5)),
    make_token(iss="https://evil.example.com"),
    make_token(email_verified=False),
    make_token(email=""),
])
def test_verify_rejects_bad_tokens(bad):
    with pytest.raises(google_auth.GoogleTokenError):
        google_auth.verify_google_id_token(bad, CLIENT_ID)


def test_google_creates_new_user_with_defaults(client):
    resp = client.post("/api/auth/google", json={"credential": make_token()})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["email"] == "user@example.com"  # lower-cased
    assert data["user"]["full_name"] == "User Example"
    assert data["user"]["onboarded"] is False

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    # New accounts get the same starter categories as email registration.
    cats = client.get("/api/inventory/categories", headers=headers).json()
    assert {c["name"] for c in cats}  # non-empty


def test_google_links_existing_email_password_user(client):
    reg = client.post("/api/auth/register", json={
        "full_name": "Existing", "email": "user@example.com",
        "password": "supersecret1", "terms_accepted": True,
    })
    assert reg.status_code == 201
    existing_id = reg.json()["user"]["id"]

    resp = client.post("/api/auth/google", json={"credential": make_token()})
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == existing_id  # linked, not duplicated


def test_google_invalid_credential_is_401(client):
    # Long enough to pass schema validation, but not a verifiable token.
    resp = client.post("/api/auth/google", json={"credential": "x" * 80})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Google sign-in failed"


def test_google_short_credential_is_422(client):
    # Schema guards reject malformed input before verification.
    resp = client.post("/api/auth/google", json={"credential": "short"})
    assert resp.status_code == 422


def test_google_disabled_when_unconfigured(client, monkeypatch):
    # Endpoint must refuse when no client id is configured on the deployment.
    disabled = Settings(google_client_id="")
    app_module = __import__("app.main", fromlist=["app"])
    app_module.app.dependency_overrides[get_settings] = lambda: disabled
    try:
        resp = client.post("/api/auth/google", json={"credential": make_token()})
        assert resp.status_code == 503
    finally:
        app_module.app.dependency_overrides.clear()
