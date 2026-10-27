"""Google ID-token verification for the "Sign in with Google" flow.

The frontend obtains an ID token (credential) from Google Identity Services;
we verify it server-side before trusting any claim in it:

- signature against Google's published JWKS keys (RS256),
- audience must be our own OAuth client id,
- issuer must be Google,
- exp/iat/iss/aud/sub must be present and exp unexpired (PyJWT checks),
- the Google account's email must be marked verified.

No Google SDK is used on purpose: PyJWT + cryptography keeps the frozen
desktop binary lean.
"""
from functools import lru_cache

import jwt
from jwt import PyJWKClient

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


class GoogleTokenError(Exception):
    """Credential is not a valid Google ID token for this client."""


@lru_cache
def _jwks_client() -> PyJWKClient:
    # PyJWKClient caches keys per kid; a shared instance avoids refetching.
    return PyJWKClient(GOOGLE_JWKS_URL, lifespan=3600)


def verify_google_id_token(credential: str, client_id: str) -> dict:
    """Return the validated token payload, or raise GoogleTokenError."""
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(credential)
        payload = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except Exception as exc:  # signature, expiry, audience, malformed token...
        raise GoogleTokenError(f"Invalid Google credential: {exc}") from exc

    if payload.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("Unexpected token issuer")
    if not payload.get("email"):
        raise GoogleTokenError("Token carries no email")
    # Google omits email_verified for Workspace-hosted domains; an explicit
    # false is the only rejection case.
    if payload.get("email_verified") is False:
        raise GoogleTokenError("Email address is not verified")
    return payload
