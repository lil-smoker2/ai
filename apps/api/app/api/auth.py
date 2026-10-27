import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.inventory import InventoryCategory
from app.models.user import User
from app.schemas.auth import (
    GoogleLoginRequest,
    LoginRequest,
    OnboardingUpdate,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import google_auth
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEFAULT_CATEGORIES = [
    "Clothing",
    "Household",
    "Electronics",
    "Food",
    "Study materials",
    "Personal care",
    "Transport",
]

# Fixed identity for single-user local mode (the packaged desktop app).
LOCAL_EMAIL = "local@lifesmart.desktop"


def _seed_default_categories(db: Session, user: User) -> None:
    for name in DEFAULT_CATEGORIES:
        db.add(InventoryCategory(user_id=user.id, name=name))


def _issue_token(user: User, settings: Settings) -> TokenResponse:
    token = create_access_token(user.id, settings.secret_key,
                                settings.access_token_expire_minutes)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db),
             settings: Settings = Depends(get_settings)):
    email = body.email.lower()
    if db.scalars(select(User).where(User.email == email)).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name.strip(),
    )
    db.add(user)
    db.flush()
    _seed_default_categories(db, user)
    db.commit()
    return _issue_token(user, settings)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings)):
    user = db.scalars(
        select(User).where(User.email == body.email.lower())
    ).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _issue_token(user, settings)


@router.post("/google", response_model=TokenResponse)
def google_signin(body: GoogleLoginRequest, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    """Verify a Google ID token, then find-or-create the local account.

    Accounts are matched by the email Google attests to be verified, so a
    user who previously registered with email/password is linked (not
    duplicated). New Google-only users get an unusable random password hash
    so the existing NOT NULL column stays satisfied and password login for
    them is impossible by construction.
    """
    if not settings.google_client_id:
        raise HTTPException(
            status_code=503, detail="Google sign-in is not configured on this deployment"
        )
    try:
        payload = google_auth.verify_google_id_token(
            body.credential, settings.google_client_id
        )
    except google_auth.GoogleTokenError:
        # Same generic message regardless of failure mode (no info leakage).
        raise HTTPException(status_code=401, detail="Google sign-in failed")

    email = payload["email"].lower()
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        full_name = (payload.get("name") or email.split("@")[0]).strip()[:120]
        user = User(
            email=email,
            full_name=full_name or "New user",
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.flush()
        _seed_default_categories(db, user)
        db.commit()
    return _issue_token(user, settings)


@router.post("/local", response_model=TokenResponse)
def local_bootstrap(db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    """Single-user local mode: create or reuse the one local account and log in.

    Enabled only when the deployment is marked ``local_single_user`` (the
    packaged desktop app), so there is no login screen, password or terms step.
    Data isolation is unchanged: this account still owns its rows and every
    other route still requires the issued bearer token. On a hosted multi-user
    deployment the flag is False and this route is hidden (404).
    """
    if not settings.local_single_user:
        raise HTTPException(status_code=404, detail="Not found")

    user = db.scalars(select(User).where(User.email == LOCAL_EMAIL)).first()
    if user is None:
        user = User(
            email=LOCAL_EMAIL,
            full_name="Local User",
            # Unusable random hash: satisfies NOT NULL, no password login.
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.flush()
        _seed_default_categories(db, user)
        db.commit()
    return _issue_token(user, settings)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: OnboardingUpdate, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    return UserOut.model_validate(user)
