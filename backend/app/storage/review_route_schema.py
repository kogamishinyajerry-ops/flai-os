"""Exact SQLite witnesses for the P2.5 named-review routing axis.

This axis lives on ``tasks`` and must not weaken P2.3's exhaustive inventory of
conversation-table objects.  It therefore owns a small, explicit object set:
one nullable exact-username column, one partial inbox index, four guards, and a
persisted-row sanity witness.  Names alone never count as evidence.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import lru_cache


REVIEW_ROUTE_SCHEMA_WITNESS_KEYS = (
    "route_column_shape",
    "required_index",
    "required_triggers",
    "persisted_routes_valid",
)


def _digest(sql: str) -> str:
    normalized = " ".join(sql.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _column_contract(conn: sqlite3.Connection) -> tuple[object, ...] | None:
    for row in conn.execute("PRAGMA table_xinfo(tasks)"):
        if row[1] == "review_requested_from_username":
            return tuple(row[1:])
    return None


def _object_contract(
    conn: sqlite3.Connection, object_type: str, name: str
) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, name),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return str(row[0]), _digest(str(row[1]))


def _index_contract(conn: sqlite3.Connection, name: str) -> tuple[object, ...] | None:
    base = _object_contract(conn, "index", name)
    if base is None:
        return None
    table = base[0]
    list_row = next(
        (row for row in conn.execute(f'PRAGMA index_list("{table}")') if row[1] == name),
        None,
    )
    if list_row is None:
        return None
    columns = tuple(
        (row[0], row[2], row[3], row[4], row[5])
        for row in conn.execute(f'PRAGMA index_xinfo("{name}")')
    )
    # index_xinfo's collation field witnesses inherited column collation.
    # sqlite_schema SQL alone cannot distinguish TEXT from TEXT COLLATE NOCASE.
    return (
        table,
        base[1],
        list_row[2],
        list_row[3],
        list_row[4],
        columns,
    )


@dataclass(frozen=True)
class _Canonical:
    column: tuple[object, ...]
    index: tuple[object, ...]
    triggers: tuple[tuple[str, tuple[str, str]], ...]


@lru_cache(maxsize=1)
def _canonical() -> _Canonical:
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._INDEX_DDL:
            conn.execute(statement)
        column = _column_contract(conn)
        index = _index_contract(conn, db_mod._REVIEW_ROUTE_MANAGED_INDEXES[0])
        triggers = tuple(
            (name, _object_contract(conn, "trigger", name))
            for name in db_mod._REVIEW_ROUTE_MANAGED_TRIGGERS
        )
        if column is None or index is None or any(value is None for _, value in triggers):
            raise RuntimeError("canonical review route schema is incomplete")
        return _Canonical(
            column=column,
            index=index,
            triggers=tuple((name, value) for name, value in triggers if value is not None),
        )
    finally:
        conn.close()


def _persisted_routes_valid(conn: sqlite3.Connection) -> bool:
    poison = conn.execute(
        """
        SELECT 1
        FROM tasks AS task
        LEFT JOIN users AS route_user
          ON route_user.username = task.review_requested_from_username
        WHERE task.review_requested_from_username IS NOT NULL
          AND (
              task.origin IS NOT 'user'
              OR typeof(task.review_requested_from_username) <> 'text'
              OR length(task.review_requested_from_username) = 0
              OR length(task.review_requested_from_username) > 100
              OR task.review_requested_from_username
                 IS NOT trim(task.review_requested_from_username)
              OR route_user.username IS NULL
          )
        LIMIT 1
        """
    ).fetchone()
    return poison is None


def review_route_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    failed = {key: False for key in REVIEW_ROUTE_SCHEMA_WITNESS_KEYS}
    try:
        canonical = _canonical()
        from . import db as db_mod

        triggers = tuple(
            (name, _object_contract(conn, "trigger", name))
            for name in db_mod._REVIEW_ROUTE_MANAGED_TRIGGERS
        )
        return {
            "route_column_shape": _column_contract(conn) == canonical.column,
            "required_index": _index_contract(
                conn, db_mod._REVIEW_ROUTE_MANAGED_INDEXES[0]
            )
            == canonical.index,
            "required_triggers": triggers == canonical.triggers,
            "persisted_routes_valid": _persisted_routes_valid(conn),
        }
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed


def assert_review_route_schema(conn: sqlite3.Connection) -> None:
    witnesses = review_route_schema_witnesses(conn)
    failed = [
        key
        for key in REVIEW_ROUTE_SCHEMA_WITNESS_KEYS
        if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            "review route schema witness failed: " + ", ".join(failed)
        )
