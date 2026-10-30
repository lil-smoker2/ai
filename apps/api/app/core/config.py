"""Application settings.

Dev mode: repository-root .env, repo-relative paths (unchanged).
Frozen desktop app (PyInstaller): data lives in a user directory
(~/.local/share/lifesmart) - db, asset folders and a persisted secret key.
"""
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> api -> apps -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[4]

# Set by the PyInstaller bootloader for frozen builds.
FROZEN = getattr(sys, "frozen", False)

# Category folders users can drop images into (created on first app run).
DEFAULT_ASSET_FOLDERS = ["clothing", "electronics", "household", "illustrations"]


def data_home() -> Path:
    """Base directory for runtime data (db, assets, secret)."""
    env = os.environ.get("LIFESMART_HOME")
    if env:
        return Path(env).expanduser()
    if FROZEN:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
        return base / "lifesmart"
    return REPO_ROOT


def _persisted_secret(home: Path) -> str:
    """Stable SECRET_KEY for the desktop app so sessions survive restarts."""
    key_file = home / "secret.key"
    if key_file.is_file():
        value = key_file.read_text().strip()
        if value:
            return value
    home.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    key_file.write_text(value)
    key_file.chmod(0o600)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./lifesmart.db"
    secret_key: str = "change-me-to-a-random-32-byte-value"
    access_token_expire_minutes: int = 60

    assets_root: str = "assets"
    max_image_bytes: int = 20_000_000
    supported_image_formats: str = "JPEG,PNG,WEBP"

    frontend_origin: str = "http://localhost:5173"

    # Google Sign-In (GIS credential flow). Empty = feature disabled.
    google_client_id: str = ""

    # Single-user local mode: auto sign-in without login/password/terms for the
    # packaged desktop app and local personal use. This defaults to True so a
    # single-user developer setup works without an explicit login flow; set it to
    # False when hosting a shared multi-user deployment.
    local_single_user: bool = False

    # Local LLM for the assistant (a Qwen *.gguf loaded via llama.cpp). Optional
    # and strictly grounded: the model only classifies intent and rephrases the
    # summary text; every figure still comes from the deterministic read-tools.
    # This switch only offers the feature - the GGUF itself is loaded on demand
    # from the AI page, never at startup, so the app opens fast either way. If
    # the runtime or the model file is missing, the assistant transparently
    # falls back to its keyword router, so nothing breaks when this is off.
    assistant_llm_enabled: bool = False
    assistant_model_path: str = ""
    assistant_llm_threads: int = 2
    assistant_llm_ctx: int = 2048

    @property
    def assets_root_path(self) -> Path:
        p = Path(self.assets_root)
        return p if p.is_absolute() else REPO_ROOT / p

    @property
    def assistant_model_file(self) -> Path | None:
        """Resolve the assistant GGUF, or None when no model is available.

        Honour an explicit ASSISTANT_MODEL_PATH; otherwise prefer the smaller
        q2_K Qwen build, then fall back to the smallest *.gguf we can find so a
        lower-memory model is always chosen over a larger one.
        """
        raw = self.assistant_model_path.strip()
        base = data_home() if FROZEN else REPO_ROOT
        if raw:
            p = Path(raw).expanduser()
            return p if p.is_absolute() else base / p
        preferred = (
            base / "models" / "Qwen2.5-3B-Instruct-Q3_K_L.gguf",
            REPO_ROOT / "ai model" / "Qwen2.5-3B-Instruct-Q3_K_L.gguf",
        )
        for cand in preferred:
            if cand.is_file():
                return cand
        found: list[Path] = []
        for d in (base / "models", REPO_ROOT / "ai model"):
            if d.is_dir():
                found.extend(d.glob("*.gguf"))
        if found:
            return min(found, key=lambda p: p.stat().st_size)
        return None

    @property
    def supported_formats(self) -> set[str]:
        return {
            f.strip().upper()
            for f in self.supported_image_formats.split(",")
            if f.strip()
        }


@lru_cache
def get_settings() -> Settings:
    if not FROZEN:
        return Settings()
    home = data_home()
    home.mkdir(parents=True, exist_ok=True)
    for folder in DEFAULT_ASSET_FOLDERS:
        (home / "assets" / folder).mkdir(parents=True, exist_ok=True)
    overrides: dict = {
        "database_url": f"sqlite:///{home / 'lifesmart.db'}",
        "assets_root": str(home / "assets"),
        "frontend_origin": "http://127.0.0.1:8756",
        "local_single_user": True,
        # The desktop app ships with the local model, so offer it on the AI
        # page. It is still only loaded when the user presses Load, and it
        # no-ops gracefully if the runtime/file is absent.
        "assistant_llm_enabled": True,
    }
    # Env vars still win (explicit overrides, e.g. Postgres in the future).
    for field, env in {
        "database_url": "DATABASE_URL",
        "assets_root": "ASSETS_ROOT",
        "frontend_origin": "FRONTEND_ORIGIN",
        "assistant_llm_enabled": "ASSISTANT_LLM_ENABLED",
        "assistant_model_path": "ASSISTANT_MODEL_PATH",
    }.items():
        if os.environ.get(env):
            overrides.pop(field, None)
    overrides["secret_key"] = os.environ.get("SECRET_KEY") or _persisted_secret(home)
    return Settings(**overrides)
