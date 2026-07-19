"""Canonical, pure-stdlib witnesses for the judgment-asset SQLite contract.

The judgment ledger is a trust boundary, so object names are not evidence.  A
same-name no-op trigger, loose lookalike table, or wrong-column index must keep
startup/readiness red.  This module compares complete normalized DDL together
with PRAGMA table, foreign-key, and index metadata; it never inspects outcomes
to infer that a schema is trustworthy.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import lru_cache


JUDGMENT_SCHEMA_WITNESS_KEYS = (
    "advice_table_shape",
    "human_decision_table_shape",
    "required_indexes",
    "required_triggers",
)
_JUDGMENT_TABLES = ("task_review_advice", "task_human_decisions")
_JUDGMENT_TRIGGER_TABLES = (*_JUDGMENT_TABLES, "model_calls")


@dataclass(frozen=True)
class _CanonicalSchema:
    tables: tuple[tuple[str, tuple[object, ...]], ...]
    indexes: tuple[tuple[str, tuple[object, ...]], ...]
    all_indexes: tuple[tuple[str, tuple[object, ...]], ...]
    triggers: tuple[tuple[str, tuple[object, ...]], ...]


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().split())


def _sql_digest(sql: str) -> str:
    return hashlib.sha256(_normalize_sql(sql).encode("utf-8")).hexdigest()


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_contract(
    conn: sqlite3.Connection, table: str
) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    quoted = _quoted_identifier(table)
    xinfo = tuple(tuple(item) for item in conn.execute(f"PRAGMA table_xinfo({quoted})"))
    foreign_keys = tuple(
        tuple(item) for item in conn.execute(f"PRAGMA foreign_key_list({quoted})")
    )
    return (_sql_digest(str(row[0])), xinfo, foreign_keys)


def _index_contract(
    conn: sqlite3.Connection, name: str
) -> tuple[object, ...] | None:
    schema_row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (name,),
    ).fetchone()
    if schema_row is None:
        return None
    table = str(schema_row[0])
    sql_digest = (
        None if schema_row[1] is None else _sql_digest(str(schema_row[1]))
    )
    quoted_table = _quoted_identifier(table)
    list_row = next(
        (
            row
            for row in conn.execute(f"PRAGMA index_list({quoted_table})")
            if row[1] == name
        ),
        None,
    )
    if list_row is None:
        return None
    quoted_name = _quoted_identifier(name)
    xinfo = tuple(
        (row[0], row[1], row[2], row[3], row[4], row[5])
        for row in conn.execute(f"PRAGMA index_xinfo({quoted_name})")
    )
    return (
        table,
        sql_digest,
        list_row[2],
        list_row[3],
        list_row[4],
        xinfo,
    )


def _all_index_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for table in _JUDGMENT_TABLES:
        quoted = _quoted_identifier(table)
        for row in conn.execute(f"PRAGMA index_list({quoted})"):
            name = str(row[1])
            contract = _index_contract(conn, name)
            if contract is None:
                raise RuntimeError(f"judgment index is unreadable: {name}")
            contracts.append((name, contract))
    return tuple(sorted(contracts, key=lambda item: item[0]))


def _all_trigger_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    placeholders = ",".join("?" for _ in _JUDGMENT_TRIGGER_TABLES)
    rows = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master "
        f"WHERE type = 'trigger' AND tbl_name IN ({placeholders}) ORDER BY name",
        _JUDGMENT_TRIGGER_TABLES,
    ).fetchall()
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for name, table, sql in rows:
        if sql is None:
            raise RuntimeError(f"judgment trigger SQL is unreadable: {name}")
        contracts.append((str(name), (str(table), _sql_digest(str(sql)))))
    return tuple(contracts)


@lru_cache(maxsize=1)
def _canonical_schema() -> _CanonicalSchema:
    # Lazy import keeps this pure-stdlib module safe for offline probes and
    # avoids review_schema -> db -> review_schema recursion at module load.
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._JUDGMENT_OBJECT_DDL:
            conn.execute(statement)

        tables: list[tuple[str, tuple[object, ...]]] = []
        for table in _JUDGMENT_TABLES:
            contract = _table_contract(conn, table)
            if contract is None:
                raise RuntimeError(f"canonical judgment table is missing: {table}")
            tables.append((table, contract))

        indexes: list[tuple[str, tuple[object, ...]]] = []
        for name in db_mod._JUDGMENT_MANAGED_INDEXES:
            contract = _index_contract(conn, name)
            if contract is None:
                raise RuntimeError(f"canonical judgment index is missing: {name}")
            indexes.append((name, contract))

        all_indexes = _all_index_contracts(conn)
        explicit_names = {
            name for name, contract in all_indexes if contract[1] is not None
        }
        if explicit_names != set(db_mod._JUDGMENT_MANAGED_INDEXES):
            raise RuntimeError("canonical judgment index set differs from managed names")

        triggers = _all_trigger_contracts(conn)
        if {name for name, _contract in triggers} != set(
            db_mod._JUDGMENT_MANAGED_TRIGGERS
        ):
            raise RuntimeError("canonical judgment trigger set differs from managed names")

        return _CanonicalSchema(
            tables=tuple(tables),
            indexes=tuple(indexes),
            all_indexes=all_indexes,
            triggers=triggers,
        )
    finally:
        conn.close()


def judgment_required_trigger_names() -> tuple[str, ...]:
    return tuple(name for name, _contract in _canonical_schema().triggers)


def judgment_required_index_names() -> tuple[str, ...]:
    return tuple(name for name, _contract in _canonical_schema().indexes)


def judgment_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    """Return exact structural witnesses; any unreadable state fails closed."""
    failed = {key: False for key in JUDGMENT_SCHEMA_WITNESS_KEYS}
    try:
        canonical = _canonical_schema()
        table_map = dict(canonical.tables)
        advice_ok = (
            _table_contract(conn, "task_review_advice")
            == table_map["task_review_advice"]
        )
        human_ok = (
            _table_contract(conn, "task_human_decisions")
            == table_map["task_human_decisions"]
        )
        indexes = tuple(
            (name, _index_contract(conn, name))
            for name, _contract in canonical.indexes
        )
        indexes_ok = (
            indexes == canonical.indexes
            and _all_index_contracts(conn) == canonical.all_indexes
        )
        triggers_ok = _all_trigger_contracts(conn) == canonical.triggers
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed

    return {
        "advice_table_shape": advice_ok,
        "human_decision_table_shape": human_ok,
        "required_indexes": indexes_ok,
        "required_triggers": triggers_ok,
    }


def assert_judgment_schema(conn: sqlite3.Connection) -> None:
    witnesses = judgment_schema_witnesses(conn)
    failed = [
        key
        for key in JUDGMENT_SCHEMA_WITNESS_KEYS
        if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            f"judgment schema witness failed: {', '.join(failed)}"
        )
