"""LifeSmart entrypoint: API plus (when built) the bundled desktop UI.

If the Vite build output exists, it is served from the same origin so the
frozen app is a single self-contained executable; otherwise the API runs
standalone (dev uses the Vite server on :5173 instead).
"""
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    account,
    assistant,
    assets,
    auth,
    dashboard,
    earnings,
    finance,
    goals,
    inventory,
    notifications,
    reports,
    settings as settings_api,
    shopping,
    student,
    tasks,
    valuation,
)
from app.core.config import get_settings

settings = get_settings()


def _frontend_dist() -> Path | None:
    """Built SPA location: bundled in the frozen binary, or apps/web/dist."""
    if getattr(sys, "frozen", False):
        cand = Path(sys._MEIPASS) / "web_dist"  # set by PyInstaller
    else:
        cand = Path(__file__).resolve().parents[2] / "web" / "dist"
    return cand if (cand / "index.html").is_file() else None


def create_app() -> FastAPI:
    app = FastAPI(
        title="LifeSmart API",
        version="0.1.0",
        description="Plan. Manage. Grow. - personal life-management platform.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(inventory.router)
    app.include_router(finance.router)
    app.include_router(goals.router)
    app.include_router(shopping.router)
    app.include_router(earnings.router)
    app.include_router(tasks.router)
    app.include_router(student.router)
    app.include_router(notifications.router)
    app.include_router(assistant.router)
    app.include_router(reports.router)
    app.include_router(assets.router)
    app.include_router(dashboard.router)
    app.include_router(valuation.router)
    app.include_router(settings_api.router)
    app.include_router(account.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    dist = _frontend_dist()
    if dist is not None:
        # Single-origin desktop mode: static assets + client-side routing.
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="spa")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            # Unknown API/docs paths stay 404; everything else is the SPA.
            if full_path.startswith(("api/", "openapi.json", "docs", "redoc")):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist / full_path).resolve()
            if (".." in full_path
                    or not candidate.is_relative_to(dist.resolve())
                    or not candidate.is_file()):
                # Client-side route -> let the React router handle it.
                return FileResponse(dist / "index.html")
            return FileResponse(candidate)

    return app


app = create_app()
