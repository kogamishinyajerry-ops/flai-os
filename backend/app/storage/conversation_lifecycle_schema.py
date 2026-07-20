"""Exact P2.6 conversation-lifecycle SQLite witnesses.

The lifecycle event ledger is evidence-bearing: a same-name no-op trigger is
not protection, and a repaired guard cannot prove what happened while it was
missing.  This module therefore witnesses complete table/index/trigger SQL and
replays every persisted event chain against the current conversation
projection.  Legacy rows are preserved as revision-zero facts and receive no
invented events.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache


CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS = (
    "projection_columns",
    "event_table_shape",
    "required_indexes",
    "required_triggers",
    "persisted_event_chains",
)

_EVENT_ID_RE = re.compile(r"^cle_[0-9a-f]{32}$")
_UTC_MICROSECOND_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{6}\+00:00$"
)


def _digest(sql: str) -> str:
    normalized = " ".join(sql.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _projection_columns(
    conn: sqlite3.Connection,
) -> tuple[tuple[object, ...], ...] | None:
    wanted = ("title", "lifecycle_revision", "archived_at")
    rows = {
        str(row[1]): tuple(row[1:])
        for row in conn.execute("PRAGMA table_xinfo(conversations)")
    }
    if any(name not in rows for name in wanted):
        return None
    return tuple(rows[name] for name in wanted)


def _object_contract(
    conn: sqlite3.Connection, object_type: str, name: str
) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, name),
    ).fetchone()
    if row is None or not isinstance(row[1], str):
        return None
    return str(row[0]), _digest(str(row[1]))


def _event_table_contract(
    conn: sqlite3.Connection,
) -> tuple[object, ...] | None:
    base = _object_contract(conn, "table", "conversation_lifecycle_events")
    if base is None:
        return None
    xinfo = tuple(
        tuple(row)
        for row in conn.execute(
            "PRAGMA table_xinfo(conversation_lifecycle_events)"
        )
    )
    foreign_keys = tuple(
        tuple(row)
        for row in conn.execute(
            "PRAGMA foreign_key_list(conversation_lifecycle_events)"
        )
    )
    return base[1], xinfo, foreign_keys


def _index_contract(
    conn: sqlite3.Connection, table: str, name: str
) -> tuple[object, ...] | None:
    quoted_table = _quoted(table)
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
    schema_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (name,),
    ).fetchone()
    sql_digest = (
        _digest(str(schema_row[0]))
        if schema_row is not None and isinstance(schema_row[0], str)
        else None
    )
    columns = tuple(
        (row[0], row[2], row[3], row[4], row[5])
        for row in conn.execute(f"PRAGMA index_xinfo({_quoted(name)})")
    )
    return (
        table,
        sql_digest,
        list_row[2],
        list_row[3],
        list_row[4],
        columns,
    )


def _event_indexes(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    table = "conversation_lifecycle_events"
    rows = conn.execute(f"PRAGMA index_list({_quoted(table)})").fetchall()
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for row in rows:
        name = str(row[1])
        contract = _index_contract(conn, table, name)
        if contract is None:
            raise RuntimeError(f"unreadable lifecycle index: {name}")
        contracts.append((name, contract))
    return tuple(sorted(contracts, key=lambda item: item[0]))


def _trigger_contracts(
    conn: sqlite3.Connection, names: tuple[str, ...]
) -> tuple[tuple[str, tuple[str, str] | None], ...]:
    return tuple(
        (name, _object_contract(conn, "trigger", name)) for name in names
    )


def _event_table_triggers(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[str, str]], ...]:
    rows = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master "
        "WHERE type = 'trigger' AND tbl_name = 'conversation_lifecycle_events' "
        "ORDER BY name"
    ).fetchall()
    result: list[tuple[str, tuple[str, str]]] = []
    for name, table, sql in rows:
        if not isinstance(sql, str):
            raise RuntimeError(f"unreadable lifecycle trigger: {name}")
        result.append((str(name), (str(table), _digest(sql))))
    return tuple(result)


@dataclass(frozen=True)
class _Canonical:
    projection_columns: tuple[tuple[object, ...], ...]
    event_table: tuple[object, ...]
    indexes: tuple[tuple[str, tuple[object, ...]], ...]
    triggers: tuple[tuple[str, tuple[str, str]], ...]
    event_table_triggers: tuple[tuple[str, tuple[str, str]], ...]


@lru_cache(maxsize=1)
def _canonical() -> _Canonical:
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._INDEX_DDL:
            conn.execute(statement)
        projection = _projection_columns(conn)
        event_table = _event_table_contract(conn)
        raw_triggers = _trigger_contracts(
            conn, db_mod._CONVERSATION_LIFECYCLE_MANAGED_TRIGGERS
        )
        if (
            projection is None
            or event_table is None
            or any(contract is None for _name, contract in raw_triggers)
        ):
            raise RuntimeError("canonical conversation lifecycle schema is incomplete")
        return _Canonical(
            projection_columns=projection,
            event_table=event_table,
            indexes=_event_indexes(conn),
            triggers=tuple(
                (name, contract)
                for name, contract in raw_triggers
                if contract is not None
            ),
            event_table_triggers=_event_table_triggers(conn),
        )
    finally:
        conn.close()


def _canonical_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _UTC_MICROSECOND_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.utcoffset().total_seconds() == 0
        and parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
        == value
    )


def _valid_title(value: object) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 1 <= len(value) <= 60
        and all(
            unicodedata.category(char) not in {"Cc", "Zl", "Zp"}
            for char in value
        )
    )


def _persisted_event_chains_valid(conn: sqlite3.Connection) -> bool:
    conversations = conn.execute(
        "SELECT id, status, created_by_username, title, lifecycle_revision, "
        "archived_at FROM conversations"
    ).fetchall()
    events = conn.execute(
        "SELECT rowid, id, conversation_id, event_type, lifecycle_revision, "
        "actor_username, prior_status, prior_title, prior_archived_at, "
        "title, created_at FROM conversation_lifecycle_events "
        "ORDER BY conversation_id, lifecycle_revision"
    ).fetchall()

    by_conversation: dict[str, list[tuple[object, ...]]] = {}
    for raw in events:
        row = tuple(raw)
        conversation_id = row[2]
        if not isinstance(conversation_id, str):
            return False
        by_conversation.setdefault(conversation_id, []).append(row)

    for raw_conversation in conversations:
        (
            conversation_id,
            status,
            owner,
            projected_title,
            revision,
            projected_archived_at,
        ) = tuple(raw_conversation)
        if (
            not isinstance(conversation_id, str)
            or status not in ("active", "concluded")
            or type(revision) is not int
            or revision < 0
            or (owner is not None and not isinstance(owner, str))
        ):
            return False
        chain = by_conversation.pop(conversation_id, [])
        if revision != len(chain):
            return False
        if not chain:
            if revision != 0 or projected_title is not None or projected_archived_at is not None:
                return False
            continue
        if not isinstance(owner, str) or not owner:
            return False

        first = chain[0]
        state_status = first[6]
        state_title = first[7]
        state_archived_at = first[8]
        # Every pre-P2.6 fact began with no title/archive projection.  Legacy
        # status may already be concluded, so it is the only permitted base
        # variation and is explicitly anchored in the first event.
        if (
            state_status not in ("active", "concluded")
            or state_title is not None
            or state_archived_at is not None
        ):
            return False

        for expected_revision, row in enumerate(chain, start=1):
            (
                internal_rowid,
                event_id,
                event_conversation_id,
                event_type,
                event_revision,
                actor_username,
                prior_status,
                prior_title,
                prior_archived_at,
                event_title,
                created_at,
            ) = row
            if (
                type(internal_rowid) is not int
                or internal_rowid <= 0
                or not isinstance(event_id, str)
                or _EVENT_ID_RE.fullmatch(event_id) is None
                or event_conversation_id != conversation_id
                or type(event_revision) is not int
                or event_revision != expected_revision
                or actor_username != owner
                or prior_status != state_status
                or prior_title != state_title
                or prior_archived_at != state_archived_at
                or not _canonical_timestamp(created_at)
            ):
                return False
            if event_type == "renamed":
                if not _valid_title(event_title) or event_title == state_title:
                    return False
                state_title = event_title
            elif event_type == "concluded":
                if event_title is not None or state_status != "active":
                    return False
                state_status = "concluded"
            elif event_type == "archived":
                if event_title is not None or state_archived_at is not None:
                    return False
                state_archived_at = created_at
            else:
                return False

        if (
            state_status != status
            or state_title != projected_title
            or state_archived_at != projected_archived_at
        ):
            return False
    return not by_conversation


def conversation_lifecycle_schema_witnesses(
    conn: sqlite3.Connection,
) -> dict[str, bool]:
    failed = {
        key: False for key in CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
    }
    try:
        from . import db as db_mod

        canonical = _canonical()
        triggers = _trigger_contracts(
            conn, db_mod._CONVERSATION_LIFECYCLE_MANAGED_TRIGGERS
        )
        return {
            "projection_columns": (
                _projection_columns(conn) == canonical.projection_columns
            ),
            "event_table_shape": (
                _event_table_contract(conn) == canonical.event_table
            ),
            "required_indexes": _event_indexes(conn) == canonical.indexes,
            "required_triggers": (
                triggers == canonical.triggers
                and _event_table_triggers(conn)
                == canonical.event_table_triggers
            ),
            "persisted_event_chains": _persisted_event_chains_valid(conn),
        }
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed


def assert_conversation_lifecycle_schema(conn: sqlite3.Connection) -> None:
    witnesses = conversation_lifecycle_schema_witnesses(conn)
    failed = [
        key
        for key in CONVERSATION_LIFECYCLE_SCHEMA_WITNESS_KEYS
        if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            "conversation lifecycle schema witness failed: "
            + ", ".join(failed)
        )
