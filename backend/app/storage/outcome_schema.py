"""Canonical pure-stdlib witness for the ADR-0036 outcome ledger.

Names and column sets alone are not evidence: a loose lookalike table, an
extra UNIQUE index that collapses repeated deliveries, or a same-name no-op
trigger must keep startup/readiness/deploy reporting red.  The witness compares
normalized table/index/trigger SQL plus PRAGMA metadata against a fresh schema
built from the same canonical DDL used by ``init_db``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import lru_cache


OUTCOME_SCHEMA_WITNESS_KEYS = (
    "outcome_table_shape",
    "required_indexes",
    "required_triggers",
)


@dataclass(frozen=True)
class _CanonicalSchema:
    table: tuple[object, ...]
    indexes: tuple[tuple[str, tuple[object, ...]], ...]
    all_indexes: tuple[tuple[str, tuple[object, ...]], ...]
    triggers: tuple[tuple[str, tuple[object, ...]], ...]
    artifact_table_triggers: tuple[tuple[str, tuple[object, ...]], ...]


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().split())


def _sql_digest(sql: str) -> str:
    return hashlib.sha256(_normalize_sql(sql).encode("utf-8")).hexdigest()


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_contract(conn: sqlite3.Connection) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = 'artifact_outcome_events'"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    table = _quoted("artifact_outcome_events")
    return (
        _sql_digest(str(row[0])),
        tuple(tuple(item) for item in conn.execute(f"PRAGMA table_xinfo({table})")),
        tuple(tuple(item) for item in conn.execute(f"PRAGMA foreign_key_list({table})")),
    )


def _index_contract(
    conn: sqlite3.Connection, name: str
) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    table = str(row[0])
    list_row = next(
        (
            item
            for item in conn.execute(f"PRAGMA index_list({_quoted(table)})")
            if item[1] == name
        ),
        None,
    )
    if list_row is None:
        return None
    return (
        table,
        None if row[1] is None else _sql_digest(str(row[1])),
        list_row[2],
        list_row[3],
        list_row[4],
        tuple(
            (item[0], item[1], item[2], item[3], item[4], item[5])
            for item in conn.execute(f"PRAGMA index_xinfo({_quoted(name)})")
        ),
    )


def _all_index_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for row in conn.execute("PRAGMA index_list(artifact_outcome_events)"):
        name = str(row[1])
        contract = _index_contract(conn, name)
        if contract is None:
            raise RuntimeError(f"outcome index is unreadable: {name}")
        contracts.append((name, contract))
    return tuple(sorted(contracts, key=lambda item: item[0]))


def _trigger_contract(
    conn: sqlite3.Connection, name: str
) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (name,),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return (str(row[0]), _sql_digest(str(row[1])))


def _artifact_table_trigger_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'trigger' AND tbl_name = 'artifact_outcome_events' "
        "ORDER BY name"
    ).fetchall()
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for row in rows:
        name = str(row[0])
        contract = _trigger_contract(conn, name)
        if contract is None:
            raise RuntimeError(f"outcome trigger is unreadable: {name}")
        contracts.append((name, contract))
    return tuple(contracts)


@lru_cache(maxsize=1)
def _canonical_schema() -> _CanonicalSchema:
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._OUTCOME_OBJECT_DDL:
            conn.execute(statement)
        table = _table_contract(conn)
        if table is None:
            raise RuntimeError("canonical outcome table is missing")
        indexes: list[tuple[str, tuple[object, ...]]] = []
        for name in db_mod._OUTCOME_MANAGED_INDEXES:
            contract = _index_contract(conn, name)
            if contract is None:
                raise RuntimeError(f"canonical outcome index is missing: {name}")
            indexes.append((name, contract))
        triggers: list[tuple[str, tuple[object, ...]]] = []
        for name in db_mod._OUTCOME_MANAGED_TRIGGERS:
            contract = _trigger_contract(conn, name)
            if contract is None:
                raise RuntimeError(f"canonical outcome trigger is missing: {name}")
            triggers.append((name, contract))
        return _CanonicalSchema(
            table=table,
            indexes=tuple(indexes),
            all_indexes=_all_index_contracts(conn),
            triggers=tuple(triggers),
            artifact_table_triggers=_artifact_table_trigger_contracts(conn),
        )
    finally:
        conn.close()


def outcome_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    """Return exact structural witnesses; any unreadable state fails closed."""
    failed = {key: False for key in OUTCOME_SCHEMA_WITNESS_KEYS}
    try:
        canonical = _canonical_schema()
        indexes = tuple(
            (name, _index_contract(conn, name))
            for name, _contract in canonical.indexes
        )
        triggers = tuple(
            (name, _trigger_contract(conn, name))
            for name, _contract in canonical.triggers
        )
        return {
            "outcome_table_shape": _table_contract(conn) == canonical.table,
            "required_indexes": (
                indexes == canonical.indexes
                and _all_index_contracts(conn) == canonical.all_indexes
            ),
            "required_triggers": (
                triggers == canonical.triggers
                and _artifact_table_trigger_contracts(conn)
                == canonical.artifact_table_triggers
            ),
        }
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed


def assert_outcome_schema(conn: sqlite3.Connection) -> None:
    witnesses = outcome_schema_witnesses(conn)
    failed = [
        key for key in OUTCOME_SCHEMA_WITNESS_KEYS
        if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            f"outcome schema witness failed: {', '.join(failed)}"
        )
