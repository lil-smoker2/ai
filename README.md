# LifeSmart

Personal life-management platform — inventory, shopping, money, savings, goals,
tasks and student life. Built for the Kenyan market (KES-first). Milestone 1
delivers the running foundation: authentication, responsive navigation, database
persistence, inventory, financial transactions, goals, and the dynamic asset
(image) discovery system.

- `apps/api` — FastAPI + SQLAlchemy backend (SQLite in dev, Postgres-ready)
- `apps/web` — Vite + React + TypeScript frontend
- `assets/` — drop images into category folders; the scanner discovers them

## Quick start (development)

```bash
# Backend
cd apps/api
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../../.env.example ../../.env   # then set SECRET_KEY
.venv/bin/uvicorn app.main:app --port 8000

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev                        # http://localhost:5173
```

Run tests: `apps/api/.venv/bin/python -m pytest` (49 tests) and
`cd apps/web && npm test` (frontend) / `npm run build` (type-check + bundle).

## Arch Linux desktop app

A single self-contained executable that bundles the backend **and** the built UI,
then opens a native window. No server, no database install, no `sudo` required —
your data lives in `~/.local/share/lifesmart`.

### Build & install (per-user)

```bash
# One-time backend tooling for packaging
apps/api/.venv/bin/pip install -r apps/api/requirements-build.txt

# Build the frontend, freeze the app, install it into ~/.local
bash scripts/build_app.sh
```

That installs:

- `~/.local/bin/lifesmart` — the app
- `~/.local/share/applications/lifesmart.desktop` — menu entry (search "LifeSmart")
- `~/.local/share/lifesmart/` — your database, secret key and image folders

### Run it

Launch from your application menu, or:

```bash
~/.local/bin/lifesmart
```

It prints the local address and opens a **real native application window**
(a GTK window hosting WebKitGTK) — its own window and taskbar entry, no
browser chrome and no lingering terminal. Closing that window quits the app.

The native window is drawn by your **system Python**, which on a GNOME desktop
already ships the required toolkit (`python-gobject` + `webkit2gtk-4.1`); no
extra `pip` install is needed. If that toolkit is ever missing, the launcher
automatically falls back to a standalone Chromium app window (then your default
browser). Run it from a terminal to see the local address and stop it with
Ctrl-C; launching from the menu opens the window with no terminal.

### Rebuild after code changes

```bash
bash scripts/build_app.sh          # rebuilds the UI and re-freezes
```

### Image drop-folders

Place pictures (no renaming needed) under `~/.local/share/lifesmart/assets/` in
category folders such as `clothing/`, `electronics/`, `household/`. Use **Inventory
→ Rescan library** (or the CLI `scripts/scan_assets.py`) to index them; thumbnails
are generated automatically. New folders are picked up with no code changes.

### Uninstall

```bash
rm ~/.local/bin/lifesmart ~/.local/share/applications/lifesmart.desktop
# your data stays in ~/.local/share/lifesmart (remove it to wipe everything)
```

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///./lifesmart.db` |
| `SECRET_KEY` | JWT signing key | persisted per-user in the app |
| `ASSETS_ROOT` | Image library root | `assets/` (app: `~/.local/share/lifesmart/assets`) |
| `LIFESMART_HOME` | Override the app data directory | `~/.local/share/lifesmart` |
| `LIFESMART_NO_WINDOW` | Set to start headless (no window opened) | unset |
| `ASSISTANT_LLM_ENABLED` | Offer the optional local Qwen `*.gguf` on the AI page; it is loaded only when you press Load, never at startup | `false` (offered in the desktop app) |
| `ASSISTANT_MODEL_PATH` | Preferred `*.gguf` (relative to repo root, or absolute) | empty → `models/`, then `ai model/` |

Money is stored as integer minor units everywhere; balances are only meaningful
once an account is initialized (unknown is never shown as zero), and transfers
are never counted as income or expenses.

## Status

Milestone 1 (foundation) is implemented and tested. Shopping, Earnings &
Savings, Reports, Tasks, Student Life, Notifications and the AI Assistant are
routed to honest "Not built yet" placeholders — no simulated data.
