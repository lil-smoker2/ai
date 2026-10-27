"""Build the privacy data export: every row this account owns.

Deliberately a dump, not a report. It answers "what do you know about me"
without interpretation, so:

* Column names are the stored names. Money columns keep their integer minor
  units (KES 1,250.50 is 125050) and are listed in the manifest, because a
  rounded major-unit figure would silently change what you recorded.
* A value that was never entered is null in JSON and empty in CSV - never 0,
  never "N/A", never inferred. The manifest repeats which columns are money so
  an empty cell cannot be mistaken for free.
* Only tables owned by the requesting account are included. The picture index
  is shared machine-wide and holds other accounts' images on a hosted
  deployment, so it is excluded rather than filtered (see account.NOT_EXPORTED).
* No filesystem path of any kind goes into the archive; it is a file you may
  end up emailing or keeping in cloud storage.
"""
import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.services import account

MANIFEST_NOTE = (
    "This manifest describes the export itself. Columns named in "
    "money_minor_columns are amounts in integer minor units (divide by 100 "
    "for the ordinary figure). A null in data.json or an empty cell in a CSV "
    "means the value was never recorded - it does not mean zero or free."
)

README_TEXT = """LifeSmart data export
=====================

Contents
  manifest.json  what is in the archive, column by column, including which
                 columns are money.
  data.json      every row owned by this account, by table. Nulls are kept.
  csv/<table>.csv  the same rows as spreadsheets. An empty cell is a value
                 that was never recorded, never zero.
  README.txt     this file.

Money is stored in integer minor units: 125050 means KES 1,250.50. Check the
manifest before treating a column as a currency amount.

Not included
  The picture index and its classification records describe image files on the
  machine and are shared by every account, so they are excluded. Your image
  files were never touched or copied by this export; they stay where you put
  them.

This archive contains no file-system paths and no sign-in secrets.
"""


def _columns(model) -> list[str]:
    return [c.key for c in inspect(model).mapper.column_attrs]


def _jsonable(value: Any) -> Any:
    """Native JSON types only; dates and datetimes become ISO strings."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def table_rows(db: Session, model, user_id: int) -> list[dict]:
    cols = _columns(model)
    rows = db.scalars(
        select(model).where(model.user_id == user_id).order_by(model.id)
    ).all()
    return [{c: _jsonable(getattr(r, c)) for c in cols} for r in rows]


def profile_block(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "currency": user.currency,
        "country": user.country,
        "timezone": user.timezone,
        "is_student": user.is_student,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def bundle(db: Session, user: User) -> dict:
    """Everything the account owns, as plain JSON-ready structures."""
    tables: dict[str, list[dict]] = {}
    manifest_tables: list[dict] = []
    for model, key, label in account.OWNED_TABLES:
        cols = _columns(model)
        rows = table_rows(db, model, user.id)
        tables[key] = rows
        manifest_tables.append({
            "key": key,
            "label": label,
            "columns": cols,
            "money_minor_columns": [c for c in cols if c.endswith("_minor")],
            "rows": len(rows),
        })
    now = datetime.now(timezone.utc)
    return {
        "meta": {
            "app": "LifeSmart",
            "kind": "account_data_export",
            "generated_at": now.isoformat(),
            "currency_of_origin": user.currency,
            "money_note": (
                "Amounts are integer minor units; divide by 100. Column names "
                "end in _minor."
            ),
            "null_note": "null / empty means never recorded, not zero.",
        },
        "profile": profile_block(user),
        "tables": tables,
        "manifest": {
            "note": MANIFEST_NOTE,
            "tables": manifest_tables,
            "excluded": account.NOT_EXPORTED,
            "row_total": sum(t["rows"] for t in manifest_tables),
        },
    }


def _csv_text(rows: list[dict], cols: list[str]) -> str:
    """CSV body. JSON-encoded cells keep structure instead of truncating it."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(cols)
    for row in rows:
        out = []
        for c in cols:
            v = row.get(c)
            if v is None:
                out.append("")
            elif isinstance(v, (dict, list)):
                out.append(json.dumps(v, sort_keys=True))
            elif isinstance(v, bool):
                out.append("true" if v else "false")
            else:
                out.append(v)
        writer.writerow(out)
    return buf.getvalue()


def make_zip(data: dict) -> bytes:
    """Pack the bundle plus one CSV per table into a single archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", README_TEXT)
        zf.writestr("manifest.json", json.dumps(data["manifest"], indent=2))
        zf.writestr(
            "data.json",
            json.dumps(
                {"meta": data["meta"], "profile": data["profile"],
                 "tables": data["tables"]},
                indent=2, sort_keys=False,
            ),
        )
        for table in data["manifest"]["tables"]:
            cols = table["columns"]
            zf.writestr(
                f"csv/{table['key']}.csv",
                _csv_text(data["tables"][table["key"]], cols),
            )
    return buf.getvalue()


def export_filename() -> str:
    """Deterministic, path-free download name."""
    return f"lifesmart-export-{date.today().isoformat()}.zip"


def export_archive(db: Session, user: User) -> tuple[bytes, str]:
    return make_zip(bundle(db, user)), export_filename()
