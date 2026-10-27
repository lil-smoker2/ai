"""Authentication, authorization and user isolation tests."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User


def _register(client, email, password="supersecret1"):
    return client.post(
        "/api/auth/register",
        json={
            "full_name": "A User",
            "email": email,
            "password": password,
            "terms_accepted": True,
        },
    )


def test_register_returns_token_and_user(client):
    resp = _register(client, "alice@example.com")
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["currency"] == "KES"
    assert "password_hash" not in body["user"]


def test_password_is_never_stored_in_plaintext(client):
    _register(client, "bob@example.com", password="plaintext-check-9")
    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.email == "bob@example.com")).one()
        assert user.password_hash != "plaintext-check-9"
        assert user.password_hash.startswith("$2b$")  # bcrypt


def test_duplicate_email_rejected(client):
    assert _register(client, "dup@example.com").status_code == 201
    assert _register(client, "dup@example.com").status_code == 409


def test_short_password_rejected(client):
    resp = _register(client, "short@example.com", password="abc")
    assert resp.status_code == 422


def test_terms_required(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "full_name": "No Terms",
            "email": "noterms@example.com",
            "password": "longenough1",
            "terms_accepted": False,
        },
    )
    assert resp.status_code == 422


def test_login_success_and_wrong_password(client):
    _register(client, "carol@example.com")
    ok = client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "supersecret1"},
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/auth/login",
        json={"email": "carol@example.com", "password": "wrongpassword"},
    )
    assert bad.status_code == 401


def test_me_requires_valid_token(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"

    assert client.get("/api/auth/me").status_code == 401
    assert client.get(
        "/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"}
    ).status_code == 401


def test_onboarding_update(client, auth_headers):
    resp = client.patch(
        "/api/auth/me",
        json={"is_student": True, "currency": "KES", "onboarded": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_student"] is True
    assert body["onboarded"] is True


def test_user_data_isolated_between_accounts(client, auth_headers, second_user_headers):
    # Create an inventory item as user 1.
    cats = client.get("/api/inventory/categories", headers=auth_headers).json()
    item = client.post(
        "/api/inventory/items",
        json={"name": "My trousers", "category_id": cats[0]["id"],
              "quantity_owned": 5},
        headers=auth_headers,
    ).json()

    # User 2 must not see or touch it.
    listing = client.get("/api/inventory/items", headers=second_user_headers).json()
    assert listing["items"] == []
    assert client.get(
        f"/api/inventory/items/{item['id']}", headers=second_user_headers
    ).status_code == 404
    assert client.delete(
        f"/api/inventory/items/{item['id']}?confirm=true",
        headers=second_user_headers,
    ).status_code == 404
