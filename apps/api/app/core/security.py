"""Password hashing and JWT access tokens."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

ACCESS_ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode())
    except ValueError:
        return False


def create_access_token(user_id: int, secret: str, expire_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm=ACCESS_ALGORITHM)


def decode_access_token(token: str, secret: str) -> int | None:
    """Return the user id in a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ACCESS_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None
