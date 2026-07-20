"""Exact SQLite witness for the frozen Agent execution binding axis.

Column names alone are not evidence.  A nullable lookalike column, a missing
immutable guard, or a same-name no-op trigger would reopen task rebinding while
startup still appeared healthy.  This witness compares the live column and
trigger contracts with a fresh canonical schema and validates every persisted
binding as an exact adapter/contract pair.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import lru_cache


EXECUTION_BINDING_SCHEMA_WITNESS_KEYS = (
    "binding_column_shape",
    "required_triggers",
    "persisted_bindings_valid",
)


def _digest(sql: str) -> str:
    normalized = " ".join(sql.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _column_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[object, ...], ...] | None:
    wanted = {"execution_adapter", "execution_contract_version"}
    rows = tuple(
        tuple(row[1:])
        for row in conn.execute("PRAGMA table_xinfo(tasks)")
        if row[1] in wanted
    )
    if {str(row[0]) for row in rows} != wanted:
        return None
    return tuple(sorted(rows, key=lambda row: str(row[0])))


def _trigger_contract(
    conn: sqlite3.Connection, name: str
) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (name,),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return str(row[0]), _digest(str(row[1]))


def _persisted_bindings_valid(conn: sqlite3.Connection) -> bool:
    poison = conn.execute(
        """
        SELECT 1 FROM tasks
        WHERE typeof(execution_adapter) <> 'text'
           OR typeof(execution_contract_version) <> 'text'
           OR NOT (
                (execution_adapter = 'native_python'
                 AND execution_contract_version = 'native.workflow.v1')
                OR
                (execution_adapter = 'jerryagent_sidecar'
                 AND execution_contract_version = 'flai.agent-layer.v1')
           )
        LIMIT 1
        """
    ).fetchone()
    return poison is None


@dataclass(frozen=True)
class _Canonical:
    columns: tuple[tuple[object, ...], ...]
    triggers: tuple[tuple[str, tuple[str, str]], ...]


@lru_cache(maxsize=1)
def _canonical() -> _Canonical:
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._EXECUTION_BINDING_TRIGGER_DDL:
            conn.execute(statement)
        columns = _column_contracts(conn)
        triggers = tuple(
            (name, _trigger_contract(conn, name))
            for name in db_mod._EXECUTION_BINDING_MANAGED_TRIGGERS
        )
        if columns is None or any(value is None for _, value in triggers):
            raise RuntimeError("canonical execution binding schema is incomplete")
        return _Canonical(
            columns=columns,
            triggers=tuple(
                (name, value) for name, value in triggers if value is not None
            ),
        )
    finally:
        conn.close()


def execution_binding_schema_witnesses(
    conn: sqlite3.Connection,
) -> dict[str, bool]:
    failed = {key: False for key in EXECUTION_BINDING_SCHEMA_WITNESS_KEYS}
    try:
        canonical = _canonical()
        from . import db as db_mod

        triggers = tuple(
            (name, _trigger_contract(conn, name))
            for name in db_mod._EXECUTION_BINDING_MANAGED_TRIGGERS
        )
        return {
            "binding_column_shape": _column_contracts(conn) == canonical.columns,
            "required_triggers": triggers == canonical.triggers,
            "persisted_bindings_valid": _persisted_bindings_valid(conn),
        }
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed


def assert_execution_binding_schema(conn: sqlite3.Connection) -> None:
    witnesses = execution_binding_schema_witnesses(conn)
    failed = [
        key
        for key in EXECUTION_BINDING_SCHEMA_WITNESS_KEYS
        if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            "execution binding schema witness failed: " + ", ".join(failed)
        )
