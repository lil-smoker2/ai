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

### Net worth

**Net worth** (sidebar, under Money) lists the things you own and prices each
row: how many you have, how many more you may need, what one costs and what
yours add up to. The total is *derived* from your inventory - you never type it
in - and is re-recorded automatically whenever an item or a price changes, so
the saved figure cannot drift out of step with your records. Rows carry their
picture from the same asset library (matched by category folder), and an item
with no price keeps the total **unknown** rather than counting it as free.
`GET /api/networth` serves the same data.

### Derived readings

Six small analyses read a picture of your own records that you never typed in -
every figure is recomputed from saved rows, and a number you did not record
stays unknown instead of becoming a guess:

- **Replenishment forecast** (Inventory) - a per-day consumption rate from an
  item's own quantity history, floored so a run-out date is never over-optimistic.
- **Goal completion pace** (Goals) - how fast contributions have actually been
  landing, projected against the deadline; silent when nothing was recently saved.
- **Expense anomalies** (Money) - a category's own recent middle (median) with
  outliers flagged by a MAD z-score; a category too thin to have a dependable
  middle reports nothing. `GET /api/transactions/anomalies`.
- **Net-worth trend** (Net worth) - a least-squares slope and moving average over
  saved snapshots; gap days are named and left out, never interpolated.
- **Task urgency** (Tasks) - a deterministic priority-plus-overdue score used to
  order the list; `?sort=urgency`.
- **Pictures that look alike** (Images) - *near-duplicate* detection. Exact
  byte-for-byte copies are already folded away by the content hash; a deterministic,
  offline perceptual hash (a 64-bit DCT fingerprint computed with Pillow alone) then
  groups genuinely different files - the same shot re-saved, resized or lightly
  edited. `GET /api/assets/similar`.

Semantic / embedding image search was considered and **deliberately not built**:
it needs a heavyweight model dependency and either a network round-trip or a
large local model, which contradicts this app's deterministic, offline,
small-data design. Near-duplicate detection gets the practical win (spotting the
re-saved photo) with no model and no new dependency.

### Places to save: a reading list

Under **Savings & Earnings → Places to save** there is a curated, static reading
list of investment and betting sites for Kenya and America - where to learn
(CMA, Investor.gov), practise with virtual money (TradingView), research
companies (NSE, SEC EDGAR), and, by your own choice, buy Kenyan or US shares
(CDSC, Interactive Brokers, Trading 212), with the betting entries (Betika,
Aviator) kept clearly apart and labelled as gambling. It is *reference, not a
record*: nothing is saved to your database, no rate or price is quoted, and
LifeSmart is not connected to any of these sites, so it cannot verify a fee, an
operator's licence, or whether a platform still accepts Kenyan residents. Each
entry states how you can lose money, and the one worked example (what a swing
does to KSh 5,000) is marked as a hypothetical before fees and tax - never a
prediction. The list lives in `apps/web/src/features/earnings/investmentGuide.ts`.

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

The AI Assistant runs on-device with a deterministic natural-language router (a
stopworded, stem-tokenising scorer) plus a built-in knowledge base of "how do I
use the app" answers, so it works on any device with nothing to download: it
replies only from your saved records and its app help, never invents a figure,
and any change it proposes waits for your confirmation. Optionally, pressing
**Load** on the AI page puts a local Qwen `*.gguf` (via llama.cpp) into memory
for that session; it can sharpen the intent, reword a summary and answer
questions the router does not cover - strictly grounded on your own records and
the built-in help, and any reply that introduces a new figure is rejected. It is
never loaded at startup and unloading frees the RAM again.

Money is stored as integer minor units everywhere; balances are only meaningful
once an account is initialized (unknown is never shown as zero), and transfers
are never counted as income or expenses.

## Status

Milestone 1 (foundation) is implemented and tested. Shopping, Earnings &
Savings, Reports, Tasks, Student Life, Notifications and the AI Assistant are
routed to honest "Not built yet" placeholders — no simulated data.
