#!/usr/bin/env bash
# Build the LifeSmart desktop app and install it per-user (Arch Linux).
#
#   scripts/build_app.sh            # frontend build + freeze + install
#   scripts/build_app.sh --no-frontend   # skip npm build (reuse apps/web/dist)
#
# Installs:
#   ~/.local/bin/lifesmart                       single-file executable
#   ~/.local/share/lifesmart/lifesmart.svg       app icon
#   ~/.local/share/applications/lifesmart.desktop
# User data (db, drop-folders, secret) lives in ~/.local/share/lifesmart/.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$REPO/apps/api"
WEB="$REPO/apps/web"
PYINSTALLER="$API/.venv/bin/pyinstaller"
PKG="$API/packaging"
BIN_DEST="$HOME/.local/bin/lifesmart"
DATA_DEST="$HOME/.local/share/lifesmart"
DESKTOP_DEST="$HOME/.local/share/applications/lifesmart.desktop"

if [[ "${1:-}" != "--no-frontend" ]]; then
  echo "==> Building frontend (vite)"
  # Force same-origin API calls in the packaged UI (the binary serves API + UI
  # together on one loopback port); override any local apps/web/.env.
  (cd "$WEB" && VITE_API_BASE_URL="" npm run build)
fi

if [[ ! -f "$WEB/dist/index.html" ]]; then
  echo "error: $WEB/dist not built yet (run without --no-frontend)" >&2
  exit 1
fi

echo "==> Freezing backend + UI with PyInstaller (this takes a minute)"
(cd "$API" && "$PYINSTALLER" --noconfirm --clean lifesmart.spec)

echo "==> Installing per-user"
mkdir -p "$HOME/.local/bin" "$DATA_DEST" "$(dirname "$DESKTOP_DEST")"
# Ship the assistant's local model into the per-user data dir (kept out of
# the single-file binary so the executable stays small and starts fast). The app
# prefers the q2_K build and otherwise falls back to the smallest *.gguf it can
# find (Settings.assistant_model_file), so resolve the same file here instead of
# hardcoding a name that may no longer be in the folder.
MODEL_DIR="$REPO/ai model"
MODEL_SRC=""
if [[ -f "$MODEL_DIR/qwen2.5-0.5b-instruct-q2_k.gguf" ]]; then
  MODEL_SRC="$MODEL_DIR/qwen2.5-0.5b-instruct-q2_k.gguf"
elif compgen -G "$MODEL_DIR/*.gguf" > /dev/null; then
  MODEL_SRC="$(find "$MODEL_DIR" -maxdepth 1 -name '*.gguf' -printf '%s\t%p\n' \
    | sort -n | head -1 | cut -f2-)"
fi
if [[ -n "$MODEL_SRC" ]]; then
  mkdir -p "$DATA_DEST/models"
  cp -n "$MODEL_SRC" "$DATA_DEST/models/"
  echo "    - model: $(basename "$MODEL_SRC") -> $DATA_DEST/models/"
else
  echo "    - no *.gguf in '$MODEL_DIR'; the assistant keeps using its keyword router"
fi
cp "$API/dist/lifesmart" "$BIN_DEST"
cp "$PKG/lifesmart.svg" "$DATA_DEST/lifesmart.svg"
sed -e "s|__LIFESMART_BIN__|$BIN_DEST|g" \
    -e "s|__LIFESMART_ICON__|$DATA_DEST/lifesmart.svg|g" \
    "$PKG/lifesmart.desktop.template" > "$DESKTOP_DEST"
chmod +x "$BIN_DEST"
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true

echo
echo "Done. LifeSmart is installed:"
echo "  - from your application menu: search 'LifeSmart'"
echo "  - or run:  $BIN_DEST"
echo "Your image drop-folders are under: $DATA_DEST/assets/"
