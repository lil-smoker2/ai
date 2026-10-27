# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the LifeSmart single-file desktop app.

Build (from apps/api):
    pyinstaller --noconfirm --clean lifesmart.spec
Produces dist/lifesmart - a self-contained executable that serves the API +
bundled React UI and opens a window. The built frontend (apps/web/dist) must
exist before building; see scripts/build_app.sh.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

API_DIR = Path(SPECPATH)                                   # apps/api
WEB_DIST = API_DIR.parent / "web" / "dist"                 # apps/web/dist
PACKAGING = API_DIR / "packaging"                          # native window + icon

if not (WEB_DIST / "index.html").is_file():
    raise SystemExit(
        f"Frontend build not found at {WEB_DIST}. Run `npm run build` in apps/web first."
    )

# The assistant's local LLM runtime is optional. When llama-cpp-python is
# installed we bundle its Python module plus the native llama.cpp shared
# libraries (loaded via ctypes, which PyInstaller can't see otherwise). When
# it's absent the app still builds and the assistant stays deterministic.
hiddenimports = [
    # Imported dynamically / via entry points PyInstaller can't see.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "sqlalchemy.dialects.sqlite",
    "email_validator",
    "PIL",
    "PIL.Image",
    "app.models",
]
binaries = []
datas = [
    (str(WEB_DIST), "web_dist"),
    # Native GTK window shell + icon, run by the system python at launch.
    (str(PACKAGING / "window_opener.py"), "packaging"),
    (str(PACKAGING / "lifesmart.svg"), "packaging"),
]
try:
    import llama_cpp  # noqa: F401

    hiddenimports.append("llama_cpp")
    binaries += collect_dynamic_libs("llama_cpp")
    datas += collect_data_files("llama_cpp")
except Exception:
    pass

a = Analysis(
    ["desktop.py"],
    pathex=[str(API_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="lifesmart",
    debug=False,
    strip=False,
    upx=False,
    console=True,          # keep a log window; launcher also prints the URL
    disable_windowed_traceback=False,
)
