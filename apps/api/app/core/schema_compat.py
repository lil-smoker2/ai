"""Bring an existing database up to the shape the models expect.

The desktop launcher builds its schema with ``create_all``, which only ever
creates missing *tables* - it never touches a table that already exists. So a
person who installed LifeSmart before a column was added would open the app
after an update and get "no such column" errors against their own data.

Adding a nullable column is the one change every SQLite version can do in
place, so those are applied here. Anything harder (a new table, a NOT NULL
column, a rename, a constraint) is left to Alembic and reported instead of
half-done, because silently guessing at a schema is worse than a loud gap.
"""

import logging

from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("lifesmart.schema")


def _missing_columns(engine: Engine, base: type[DeclarativeBase]) -> tuple[list, list]:
    """Split absent columns into (safe to add in place, needs Alembic)."""
    addable: list = []
    needs_migration: list[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in base.metadata.sorted_tables:
        if table.name not in existing_tables:
            # create_all builds these with every column already in place.
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if column.nullable and column.server_default is None and not column.primary_key:
                addable.append((table, column))
            else:
                needs_migration.append(f"{table.name}.{column.name}")
    return addable, needs_migration


def apply_missing_columns(engine: Engine, base: type[DeclarativeBase]) -> list[str]:
    """Add nullable columns the table lacks; return what was changed."""
    addable, needs_migration = _missing_columns(engine, base)
    added: list[str] = []
    for table, column in addable:
        spec = column.type.compile(engine.dialect)
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {spec}'))
        added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("Added columns to the local database: %s", ", ".join(added))
    if needs_migration:
        logger.warning(
            "Columns missing from the local database that need a migration: %s",
            ", ".join(needs_migration),
        )
    return added
