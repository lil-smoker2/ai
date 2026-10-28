"""Put a LifeSmart export back into the account that wrote it.

The export answers "what do you know about me". This answers the only question
that makes a backup worth keeping: "can I get it back". It reads the same
archive byte for byte, and the rules are the export's turned around.

* Money travels as the integer minor units it was stored in. Nothing here
  divides by 100 or re-rounds, because 125050 is KES 1,250.50 and the archive
  says so. An amount that is not a whole number of minor units is refused
  rather than quietly rounded.
* A null is still "never recorded". It is restored as null, never as 0 or an
  empty string, so a shortage with no price stays a shortage with no price.
* A bad archive is refused before anything is written, and the whole restore is
  one transaction. Half a life is worse than none: if any row is rejected,
  every row is rolled back and the account is left exactly as it was found.
* The archive's primary keys are not reused. Ids are allocated fresh and every
  reference inside the restored set is re-pointed, so a restore cannot collide
  with another account's rows on a hosted deployment.
* The picture index is machine-wide and deliberately not exported, so an item's
  photo link is kept only while that picture is still on this machine.
  Otherwise it is cleared and counted - never left pointing at somebody else's
  image, and never silently dropped.
* Your sign-in and profile are not overwritten. A reset already kept them, so
  there is nothing for a restore to bring back, and replacing the name or the
  currency on an account that is signed in would be its own surprise. The
  currency is the one exception, because the amounts are only meaningful in the
  currency they were written in.
"""
import base64
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import sqlalchemy as sa
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.user import User
from app.services import account as account_service

# A personal export is small. This is a ceiling for refusing a pathological
# upload before it is decoded, not a limit anyone is expected to reach.
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024

DATA_JSON = "data.json"
EXPORT_KIND = "account_data_export"

# Stated back to the caller so a restore can be described rather than asserted.
RESTORE_NOTE = (
    "Every record in your account was replaced by the contents of the archive. "
    "Anything you recorded after the export was not in it and is gone; the "
    "rows now in your account are the archive's rows, with the values exactly "
    "as they were written - including the ones you never filled in."
)


# Every refusal has to end with this, because the person reading it is deciding
# whether their account is still intact.
REFUSAL_PROMISE = "Nothing was changed."


class RestoreError(ValueError):
    """The archive cannot be trusted. Raised only while nothing is written.

    The promise that nothing was written is added here rather than typed into
    each message, so no future reason for refusing can forget it. A message that
    already carries the sentence - the ones about a rolled-back write, which
    phrase it mid-sentence - is left as its author wrote it.
    """

    def __init__(self, message: str) -> None:
        # Compared without the full stop: the rolled-back-write reasons work the
        # sentence into the middle of a longer one and must not hear it twice.
        if REFUSAL_PROMISE.rstrip(".").lower() not in message.lower():
            message = f"{message.rstrip()} {REFUSAL_PROMISE}"
        super().__init__(message)


@dataclass
class Plan:
    """A validated archive, ready to be written, plus what writing it means."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    archive_counts: dict[str, int] = field(default_factory=dict)
    currency_of_origin: str | None = None
    generated_at: str | None = None
    photo_links_kept: int = 0
    photo_links_cleared: int = 0
    warnings: list[str] = field(default_factory=list)


# --- table metadata, read once ---------------------------------------------

def _spec() -> dict[str, dict[str, Any]]:
    """Per owned table: its model, columns, and where its references point.

    All of it is derived from the mapped schema rather than written out by
    hand, so a new column or a new foreign key is respected by a restore
    without anyone remembering to edit this module.
    """
    table_names = {
        inspect(model).local_table.name: key
        for model, key, _label in account_service.OWNED_TABLES
    }
    out: dict[str, dict[str, Any]] = {}
    for model, key, label in account_service.OWNED_TABLES:
        table = inspect(model).local_table
        columns = {c.key: c for c in table.columns}
        owned_fk: dict[str, str] = {}
        self_fk: list[str] = []
        external_fk: dict[str, str] = {}
        deps: set[str] = set()
        for col in table.columns:
            for fk in col.foreign_keys:
                target = fk.target_fullname.split(".")[0]
                if target == table.name:
                    # A row pointing into its own table - a reversal at the
                    # transaction that cancelled it - cannot be ordered by
                    # table, so it is filled in on a second pass.
                    self_fk.append(col.key)
                elif target == "users":
                    continue
                elif table_names.get(target):
                    owned_fk[col.key] = table_names[target]
                    deps.add(table_names[target])
                else:
                    external_fk[col.key] = target
        out[key] = {
            "key": key,
            "label": label,
            "model": model,
            "columns": columns,
            "owned_fk": owned_fk,
            "self_fk": self_fk,
            "external_fk": external_fk,
            # An account holds one row of these however many the file carries.
            "unique_user": bool(columns["user_id"].unique),
        }
    return out


SPEC = _spec()


def _insert_order() -> list[str]:
    """Parents before children. A circle would be a schema mistake, and it is
    reported as one rather than producing inserts that cannot be satisfied."""
    remaining = {key: {d for d in meta["owned_fk"].values()} for key, meta in SPEC.items()}
    rank = {key: i for i, (_m, key, _l) in enumerate(account_service.OWNED_TABLES)}
    order: list[str] = []
    placed: set[str] = set()
    while remaining:
        ready = sorted(
            (k for k, deps in remaining.items() if not (deps - placed)),
            key=lambda k: rank[k],
        )
        if not ready:
            raise RestoreError(
                "The tables in a LifeSmart export depend on each other in a "
                "circle, so this archive cannot be restored."
            )
        for key in ready:
            order.append(key)
            remaining.pop(key)
        placed.update(ready)
    return order


INSERT_ORDER = _insert_order()


# The export's labels are plural group names ("Goals", "Inventory categories").
# A message reading "1 goals" looks like a bug and makes people distrust the
# number next to it, so the singular is derived - with hand-written exceptions
# for the two labels that are not a noun with an s on the end.
SINGULAR_OVERRIDES = {
    "tasks": "task",
    "assistant_proposed_actions": "assistant proposal",
}


def _singular(key: str) -> str:
    if key in SINGULAR_OVERRIDES:
        return SINGULAR_OVERRIDES[key]
    label = SPEC[key]["label"].lower()
    if label.endswith("ies"):
        return label[:-3] + "y"
    return label[:-1] if label.endswith("s") else label


def _of(count: int, key: str) -> str:
    """"1 task" / "4 fee obligations", in the wording a person reads."""
    return f"{count} {(_singular(key) if count == 1 else SPEC[key]['label'].lower())}"


def _a(word: str) -> str:
    return f"an {word}" if word[:1].lower() in "aeiou" else f"a {word}"


# References that must land somewhere: into another owned table, or into the
# same one. Both are checked against the ids the archive itself carries.
def _all_refs(key: str) -> dict[str, str]:
    spec = SPEC[key]
    return {**spec["owned_fk"], **{col: key for col in spec["self_fk"]}}


# --- reading the archive ---------------------------------------------------

def decode_archive(archive_base64: str) -> dict:
    """Turn the bytes of a downloaded export back into its data.json structure."""
    if not archive_base64 or not archive_base64.strip():
        raise RestoreError("No file was sent. Nothing was changed.")
    try:
        raw = base64.b64decode(archive_base64, validate=True)
    except Exception as exc:  # binascii raises several types; all mean one thing
        raise RestoreError(
            "That file could not be read as an archive. Nothing was changed."
        ) from exc
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise RestoreError(
            f"That archive is bigger than "
            f"{MAX_ARCHIVE_BYTES // (1024 * 1024)} MB, which is more than any "
            "LifeSmart export holds. Nothing was changed."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            # Only this one member is ever read, and only into memory: no path
            # inside the zip is resolved against the file system.
            if DATA_JSON not in archive.namelist():
                raise RestoreError(
                    f"That zip has no {DATA_JSON} in it, so it is not a "
                    "LifeSmart data export. Nothing was changed."
                )
            payload = json.loads(archive.read(DATA_JSON))
    except RestoreError:
        raise
    except zipfile.BadZipFile as exc:
        raise RestoreError(
            "That file is not a zip archive. Use the .zip the app produced, or "
            "download a fresh export from Settings > Your data."
        ) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RestoreError(
            f"The {DATA_JSON} inside that archive is not readable as JSON "
            f"({exc.msg}, line {exc.lineno}). Nothing was changed."
        ) from exc
    except Exception as exc:  # a truncated or corrupt member
        raise RestoreError(
            "That archive could not be opened. Nothing was changed."
        ) from exc
    if not isinstance(payload, dict):
        raise RestoreError(
            "That file is not a LifeSmart data export. Nothing was changed."
        )
    return payload


# --- value conversion ------------------------------------------------------

def _coerce(col: sa.Column, value: Any, where: str) -> Any:
    """Turn a JSON value back into what the column holds.

    The export flattened dates, datetimes and times into ISO strings, so they
    are parsed here. Money is checked rather than converted: 125050 means
    1,250.50 of some currency and no rounding is welcome in a backup.
    """
    if value is None:
        return None
    ttype = col.type
    if isinstance(ttype, (sa.Integer, sa.BigInteger)) and not isinstance(ttype, sa.Boolean):
        if isinstance(value, bool):
            raise RestoreError(f"{where} is {value!r}, which is not a number.")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        unit = "a whole number of minor units" if col.key.endswith("_minor") else "a whole number"
        raise RestoreError(
            f"{where} is {value!r}, which is not {unit}. Nothing in a LifeSmart "
            "export is stored in parts of a unit, so that value did not come "
            "from the app."
        )
    if isinstance(ttype, sa.DateTime):
        return _parse(where, value, datetime.fromisoformat, "a date and a time")
    if isinstance(ttype, sa.Date):
        return _parse(where, value, date.fromisoformat, "a date")
    if isinstance(ttype, sa.Time):
        return _parse(where, value, time.fromisoformat, "a time")
    if isinstance(ttype, sa.Enum):
        if str(value) not in ttype.enums:
            raise RestoreError(
                f"{where} is {value!r}, which is not one of the values this "
                f"build knows ({', '.join(ttype.enums)})."
            )
        return value
    if isinstance(ttype, sa.Boolean):
        if isinstance(value, bool):
            return value
        if value in ("true", "false", 1, 0, "1", "0"):
            return str(value) == "true" or value in (1, "1")
        raise RestoreError(f"{where} is {value!r}, which is neither yes nor no.")
    if isinstance(ttype, sa.Numeric):
        # No owned column uses Numeric today; a float that arrived would be a
        # silent change of precision, so it is refused rather than guessed at.
        raise RestoreError(f"{where} is a decimal amount, which this build does not store.")
    return value


def _parse(where: str, value: Any, parser: Any, describe: str) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value
    try:
        return parser(str(value).replace("Z", "").strip())
    except (ValueError, TypeError) as exc:
        raise RestoreError(
            f"{where} is {value!r}, which is not readable as {describe}."
        ) from exc


# --- validation ------------------------------------------------------------

def build_plan(payload: dict, db: Session, user: User) -> Plan:
    """Check every row against this build's schema. Raises RestoreError."""
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("kind") != EXPORT_KIND:
        raise RestoreError(
            "That file was not written by LifeSmart's data export, so its "
            "meaning cannot be checked. Nothing was changed."
        )
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise RestoreError("That export has no tables in it. Nothing was changed.")
    unknown = sorted(str(k) for k in tables if k not in SPEC)
    if unknown:
        # Written by a newer build. Restoring it would mean quietly losing what
        # it holds, so it is refused and named instead.
        raise RestoreError(
            "That export holds records this build does not know "
            f"({', '.join(unknown)}). It was probably written by a newer "
            "version of LifeSmart. Nothing was changed."
        )
    origin = meta.get("currency_of_origin")
    if origin is not None and not isinstance(origin, str):
        raise RestoreError("The currency named in that export is not a name.")

    plan = Plan(
        currency_of_origin=origin or None,
        generated_at=meta.get("generated_at") if isinstance(meta.get("generated_at"), str) else None,
    )
    for key in SPEC:
        plan.archive_counts[key] = 0

    for key in INSERT_ORDER:
        spec = SPEC[key]
        raw_rows = tables.get(key, [])
        if not isinstance(raw_rows, list):
            raise RestoreError(
                f"The {spec['label'].lower()} in that export are not a list of "
                "records. Nothing was changed."
            )
        plan.archive_counts[key] = len(raw_rows)
        if spec["unique_user"] and len(raw_rows) > 1:
            raise RestoreError(
                f"That export carries {_of(len(raw_rows), key)}, and an account "
                "can hold only one of them. Nothing was changed."
            )

        prepared: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for position, row in enumerate(raw_rows):
            where = f"{spec['label']} #{position + 1}"
            if not isinstance(row, dict):
                raise RestoreError(f"{where} is not a record. Nothing was changed.")
            extra = sorted(str(c) for c in row if c not in spec["columns"])
            if extra:
                # A column this build has never heard of would be dropped, and
                # a dropped value cannot be explained to the person later.
                raise RestoreError(
                    f"{where} has a column this build does not store "
                    f"({', '.join(extra)}). Nothing was changed."
                )
            arch_id = row.get("id")
            if not isinstance(arch_id, int) or isinstance(arch_id, bool):
                raise RestoreError(
                    f"{where} has an id of {arch_id!r}, so nothing in the "
                    "archive can point at it. Nothing was changed."
                )
            if arch_id in seen_ids:
                raise RestoreError(
                    f"{spec['label']} uses the id {arch_id} twice, so the "
                    "archive contradicts itself. Nothing was changed."
                )
            seen_ids.add(arch_id)

            values: dict[str, Any] = {}
            for col_name, col in spec["columns"].items():
                if col_name in ("id", "user_id"):
                    continue  # ids are allocated here; ownership is this account
                if col_name not in row:
                    if not col.nullable and col.default is None:
                        raise RestoreError(
                            f"{where} has no {col_name}, and that value cannot "
                            "be left blank. Nothing was changed."
                        )
                    continue
                values[col_name] = _coerce(col, row[col_name], f"{where} {col_name}")

            prepared.append({"id": arch_id, **values})

        plan.rows[key] = prepared

    _check_references(plan, db)
    return plan


def _check_references(plan: Plan, db: Session) -> None:
    """Every reference must land on a record the archive also carries."""
    ids_by_key = {key: {row["id"] for row in rows} for key, rows in plan.rows.items()}
    for key in INSERT_ORDER:
        spec = SPEC[key]
        for col_name, target_key in _all_refs(key).items():
            col = spec["columns"][col_name]
            target_ids = ids_by_key.get(target_key, set())
            bad = [
                row for row in plan.rows[key]
                if row.get(col_name) is not None and row[col_name] not in target_ids
            ]
            if bad:
                verb = "points" if len(bad) == 1 else "point"
                raise RestoreError(
                    f"{_of(len(bad), key)} {verb} at "
                    f"{_a(_singular(target_key))} that the archive does not "
                    "contain. That record is missing from the file, so this "
                    "would come back broken. Nothing was changed."
                )
            missing = [
                row for row in plan.rows[key]
                if not col.nullable and row.get(col_name) is None
            ]
            if missing:
                verb = "has" if len(missing) == 1 else "have"
                raise RestoreError(
                    f"{_of(len(missing), key)} {verb} no {_singular(target_key)} "
                    "to belong to, and that cannot be left blank. Nothing was "
                    "changed."
                )

    # The picture index is not in the archive. A photo link survives only while
    # the picture is still on this machine.
    kept = cleared = 0
    for key in INSERT_ORDER:
        for col_name in SPEC[key]["external_fk"]:
            refs = {
                row[col_name] for row in plan.rows[key] if row.get(col_name) is not None
            }
            if not refs:
                continue
            alive = set(db.scalars(select(Asset.id).where(Asset.id.in_(refs))).all())
            for row in plan.rows[key]:
                value = row.get(col_name)
                if value is None:
                    continue
                if value in alive:
                    kept += 1
                else:
                    cleared += 1
                    row[col_name] = None
    plan.photo_links_kept = kept
    plan.photo_links_cleared = cleared
    if cleared:
        plan.warnings.append(
            f"{cleared} record{'s' if cleared != 1 else ''} referred to a picture "
            "that is not in this machine's picture index, so the link was "
            "cleared and the record itself was restored. Re-scan the images "
            "folder and the pictures come back."
        )


# --- the two answers -------------------------------------------------------

def current_counts(db: Session, user: User) -> dict[str, int]:
    """Rows this account holds right now, per owned table."""
    out: dict[str, int] = {}
    for key, spec in SPEC.items():
        model = spec["model"]
        out[key] = int(
            db.scalar(
                select(func.count()).select_from(model).where(model.user_id == user.id)
            )
            or 0
        )
    return out


def preview(payload: dict, db: Session, user: User) -> dict:
    """What restoring this archive would do. Writes nothing."""
    plan = build_plan(payload, db, user)
    now = current_counts(db, user)
    warnings = list(plan.warnings)
    if not any(plan.archive_counts.values()):
        warnings.append(
            "That export holds no records at all, so restoring it would empty "
            "the account rather than fill it."
        )
    if plan.currency_of_origin and plan.currency_of_origin != user.currency:
        warnings.append(
            f"Every amount in the archive was written in {plan.currency_of_origin}, "
            f"while this account is currently set to {user.currency}. Restoring "
            f"switches the account to {plan.currency_of_origin} so the figures "
            "keep their meaning."
        )
    replaced = sum(now.values())
    if replaced:
        warnings.append(
            f"Your account holds {replaced} record{'s' if replaced != 1 else ''} "
            "now. A restore replaces them, so anything recorded after this "
            "export would be lost."
        )
    return {
        "generated_at": plan.generated_at,
        "currency_of_origin": plan.currency_of_origin,
        "current_currency": user.currency,
        "photo_links_kept": plan.photo_links_kept,
        "photo_links_cleared": plan.photo_links_cleared,
        "archive_total": sum(plan.archive_counts.values()),
        "current_total": replaced,
        "warnings": warnings,
        "tables": [
            {
                "key": key,
                "label": SPEC[key]["label"],
                "archive_rows": plan.archive_counts[key],
                "current_rows": now[key],
            }
            for key in INSERT_ORDER
            if plan.archive_counts[key] or now[key]
        ],
    }


def restore(payload: dict, db: Session, user: User) -> dict:
    """Replace this account's records with the archive's, in one transaction."""
    plan = build_plan(payload, db, user)
    before = current_counts(db, user)
    currency_changed_from = None
    if plan.currency_of_origin and plan.currency_of_origin != user.currency:
        currency_changed_from = user.currency

    try:
        written = _write(db, user, plan, currency_changed_from)
    except RestoreError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise RestoreError(
            "The archive could not be written into this account, so nothing was "
            f"changed ({exc.orig})."
        ) from exc
    except Exception as exc:
        db.rollback()
        raise RestoreError(
            "The archive could not be written, so nothing was changed "
            f"({type(exc).__name__})."
        ) from exc

    return {
        "written": written,
        "written_total": sum(written.values()),
        "replaced": before,
        "replaced_total": sum(before.values()),
        "generated_at": plan.generated_at,
        "currency": user.currency,
        "currency_changed_from": currency_changed_from,
        "photo_links_kept": plan.photo_links_kept,
        "photo_links_cleared": plan.photo_links_cleared,
        "warnings": list(plan.warnings),
        "reseeded_categories": not plan.rows.get("inventory_categories"),
        "kept": [
            "account sign-in",
            "profile details",
            "picture index",
            "your image files on disk",
        ],
        "note": RESTORE_NOTE,
    }


def _write(db: Session, user: User, plan: Plan, currency_changed_from: str | None) -> dict[str, int]:
    """Delete, then insert parents first with every reference re-pointed."""
    db.flush()
    # Children first, for the reason account.py gives: SQLite is not enforcing
    # these foreign keys, so an ordered delete is the only thing standing
    # between a restore and a table of orphans.
    for model, key, _label in account_service.OWNED_TABLES:
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()

    id_map: dict[str, dict[Any, Any]] = {}
    written: dict[str, int] = {}
    for key in INSERT_ORDER:
        spec = SPEC[key]
        model = spec["model"]
        id_map[key] = {}
        batch: list[tuple[int, Any]] = []
        deferred: list[tuple[int, dict[str, int]]] = []
        for row in plan.rows[key]:
            values = dict(row)
            arch_id = values.pop("id")
            for col_name, target_key in spec["owned_fk"].items():
                if values.get(col_name) is not None:
                    values[col_name] = id_map[target_key][values[col_name]]
            self_refs = {col: values.pop(col) for col in spec["self_fk"] if col in values}
            if self_refs:
                deferred.append((arch_id, self_refs))
            obj = model(user_id=user.id, **values)
            db.add(obj)
            batch.append((arch_id, obj))
        db.flush()
        for arch_id, obj in batch:
            id_map[key][arch_id] = obj.id
        written[key] = len(batch)

        # Same-table references now have ids to point at.
        for arch_id, refs in deferred:
            target = db.get(model, id_map[key][arch_id])
            for col_name, archived in refs.items():
                setattr(target, col_name, id_map[key].get(archived))
        if deferred:
            db.flush()

    if currency_changed_from is not None:
        # Same transaction as the rows: the amounts and the currency that gives
        # them meaning cannot land at different moments.
        user.currency = plan.currency_of_origin  # type: ignore[assignment]

    if not plan.rows.get("inventory_categories"):
        # The reset seeds these for the same reason: with no category at all the
        # Inventory page has nowhere to put a first item.
        account_service.seed_default_categories(db, user)
    db.commit()
    return written
