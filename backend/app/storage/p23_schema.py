"""Canonical, pure-stdlib P2.3 SQLite schema witnesses.

The API health/readiness endpoints, the offline deployment probe, and DB startup
all consume this module.  Canonical SQL is built lazily from ``db._DDL`` and
``db._INDEX_DDL`` in an isolated in-memory database, so trigger changes have one
source of truth and importing the deployment probe remains stdlib-only.

Names alone are not evidence: SQLite permits same-name, same-table no-op
triggers.  Required objects are compared using complete whitespace-normalized
``sqlite_schema.sql`` digests plus PRAGMA metadata.  This witnesses structure
only; it never infers claims about historical rows or answer outcomes.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from functools import lru_cache


P23_SCHEMA_WITNESS_KEYS = (
    "conversation_table_shape",
    "message_table_shape",
    "question_table_shape",
    "required_indexes",
    "required_triggers",
)
_P23_SCHEMA_TABLES = (
    "conversations",
    "conversation_messages",
    "conversation_questions",
)


@dataclass(frozen=True)
class _CanonicalSchema:
    conversation_owner_metadata: tuple[object, ...]
    message_public_id_metadata: tuple[object, ...]
    question_table_digest: str
    question_table_xinfo: tuple[tuple[object, ...], ...]
    indexes: tuple[tuple[str, tuple[object, ...]], ...]
    all_indexes: tuple[tuple[str, tuple[object, ...]], ...]
    triggers: tuple[tuple[str, tuple[str, str]], ...]


def _normalize_sql(sql: str) -> str:
    """Collapse formatting only; preserve case and all SQL literal content."""
    return " ".join(sql.strip().split())


def _sql_digest(sql: str) -> str:
    return hashlib.sha256(_normalize_sql(sql).encode("utf-8")).hexdigest()


def _quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_xinfo(conn: sqlite3.Connection, table: str) -> tuple[tuple[object, ...], ...]:
    quoted_table = _quoted_identifier(table)
    return tuple(
        tuple(row) for row in conn.execute(f"PRAGMA table_xinfo({quoted_table})")
    )


def _column_metadata(
    conn: sqlite3.Connection, table: str, column: str
) -> tuple[object, ...] | None:
    quoted_table = _quoted_identifier(table)
    for row in conn.execute(f"PRAGMA table_xinfo({quoted_table})"):
        if row[1] == column:
            # cid is position-dependent on a migrated table; the remaining
            # metadata (name/type/not-null/default/pk/hidden) is contractual.
            return tuple(row[1:])
    return None


def _schema_object(
    conn: sqlite3.Connection, object_type: str, name: str
) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, name),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return str(row[0]), _sql_digest(str(row[1]))


def _index_contract(
    conn: sqlite3.Connection, name: str, *, allow_implicit: bool = False
) -> tuple[object, ...] | None:
    schema_row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type = 'index' AND name = ?",
        (name,),
    ).fetchone()
    if schema_row is None:
        return None
    table = str(schema_row[0])
    if schema_row[1] is None:
        if allow_implicit is not True:
            return None
        sql_digest: str | None = None
    else:
        sql_digest = _sql_digest(str(schema_row[1]))
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
    # table, complete SQL, unique/origin/partial, and semantic indexed-column
    # metadata.  PRAGMA index_xinfo.cid is intentionally omitted: a supported
    # legacy ALTER migration appends message_id at a different table position
    # than fresh DDL, while seq/name/order/collation/key semantics are identical.
    quoted_name = _quoted_identifier(name)
    index_columns = tuple(
        (row[0], row[2], row[3], row[4], row[5])
        for row in conn.execute(f"PRAGMA index_xinfo({quoted_name})")
    )
    return (
        table,
        sql_digest,
        list_row[2],
        list_row[3],
        list_row[4],
        index_columns,
    )


def _all_p23_index_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    """Return every explicit/implicit index on the three P2.3 tables.

    Even a non-unique expression/partial/collated index is write-path behavior:
    evaluating its expression may reject an otherwise legal fact.  Every index
    therefore requires an explicit canonical contract; future phases register
    their additions rather than passing an unknown object optimistically.
    """
    contracts: list[tuple[str, tuple[object, ...]]] = []
    for table in _P23_SCHEMA_TABLES:
        quoted_table = _quoted_identifier(table)
        for row in conn.execute(f"PRAGMA index_list({quoted_table})"):
            name = str(row[1])
            contract = _index_contract(conn, name, allow_implicit=True)
            if contract is None:
                raise RuntimeError(f"P2.3 index is unreadable: {name}")
            contracts.append((name, contract))
    return tuple(sorted(contracts, key=lambda item: item[0]))


def _is_fresh_message_inline_unique(
    item: tuple[str, tuple[object, ...]],
) -> bool:
    name, contract = item
    table, sql_digest, unique, origin, partial, columns = contract
    key_names = tuple(
        column[1] for column in columns if int(column[4]) == 1
    )
    return (
        name.startswith("sqlite_autoindex_conversation_messages_")
        and table == "conversation_messages"
        and sql_digest is None
        and int(unique) == 1
        and origin == "u"
        and int(partial) == 0
        and key_names == ("message_id",)
    )


def _all_p23_trigger_contracts(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[str, str]], ...]:
    placeholders = ",".join("?" for _ in _P23_SCHEMA_TABLES)
    rows = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master "
        f"WHERE type = 'trigger' AND tbl_name IN ({placeholders}) ORDER BY name",
        _P23_SCHEMA_TABLES,
    ).fetchall()
    contracts: list[tuple[str, tuple[str, str]]] = []
    for name, table, sql in rows:
        if sql is None:
            raise RuntimeError(f"P2.3 trigger SQL is unreadable: {name}")
        contracts.append((str(name), (str(table), _sql_digest(str(sql)))))
    return tuple(contracts)


@lru_cache(maxsize=1)
def _canonical_schema() -> _CanonicalSchema:
    # Lazy import avoids db -> p23_schema -> db recursion when DB startup later
    # calls assert_p23_schema().  db.py itself imports only stdlib + config.
    from . import db as db_mod

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(db_mod._DDL)
        for statement in db_mod._INDEX_DDL:
            conn.execute(statement)

        index_names = tuple(db_mod._P23_MANAGED_INDEXES)
        trigger_names = tuple(db_mod._P23_MANAGED_TRIGGERS)

        question_object = _schema_object(conn, "table", "conversation_questions")
        owner_metadata = _column_metadata(
            conn, "conversations", "created_by_username"
        )
        message_metadata = _column_metadata(
            conn, "conversation_messages", "message_id"
        )
        if (
            question_object is None
            or owner_metadata is None
            or message_metadata is None
        ):
            raise RuntimeError("canonical P2.3 schema source is incomplete")

        indexes: list[tuple[str, tuple[object, ...]]] = []
        for name in index_names:
            contract = _index_contract(conn, name)
            if contract is None:
                raise RuntimeError(f"canonical P2.3 index is missing: {name}")
            indexes.append((name, contract))

        all_triggers = _all_p23_trigger_contracts(conn)
        all_trigger_map = dict(all_triggers)
        if set(all_trigger_map) != set(trigger_names):
            raise RuntimeError(
                "canonical P2.3 trigger set differs from managed names"
            )
        triggers = tuple((name, all_trigger_map[name]) for name in trigger_names)

        all_indexes = _all_p23_index_contracts(conn)
        explicit_index_names = {
            name for name, contract in all_indexes if contract[1] is not None
        }
        if explicit_index_names != set(index_names):
            raise RuntimeError(
                "canonical P2.3 explicit index set differs from managed names"
            )

        return _CanonicalSchema(
            conversation_owner_metadata=owner_metadata,
            message_public_id_metadata=message_metadata,
            question_table_digest=question_object[1],
            question_table_xinfo=_table_xinfo(conn, "conversation_questions"),
            indexes=tuple(indexes),
            all_indexes=all_indexes,
            triggers=triggers,
        )
    finally:
        conn.close()


def p23_required_trigger_names() -> tuple[str, ...]:
    """Expose the derived canonical trigger set for exhaustive tests/audits."""
    # Force canonical construction so stale/missing names fail before return.
    return tuple(name for name, _contract in _canonical_schema().triggers)


def p23_required_index_names() -> tuple[str, ...]:
    """Expose the DB-managed canonical index set for exhaustive tests/audits."""
    return tuple(name for name, _contract in _canonical_schema().indexes)


def p23_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    """Return exact boolean P2.3 structure witnesses; every error fails closed."""
    failed = {key: False for key in P23_SCHEMA_WITNESS_KEYS}
    try:
        from . import db as db_mod

        canonical = _canonical_schema()
        identity_table_shapes = db_mod._p23_identity_table_shape_witnesses(conn)
        owner_metadata = _column_metadata(
            conn, "conversations", "created_by_username"
        )
        message_metadata = _column_metadata(
            conn, "conversation_messages", "message_id"
        )
        question_object = _schema_object(conn, "table", "conversation_questions")
        question_shape_ok = (
            question_object is not None
            and question_object[1] == canonical.question_table_digest
            and _table_xinfo(conn, "conversation_questions")
            == canonical.question_table_xinfo
        )

        actual_indexes = tuple(
            (name, _index_contract(conn, name))
            for name, _contract in canonical.indexes
        )
        actual_all_indexes = _all_p23_index_contracts(conn)
        legacy_all_indexes = tuple(
            item
            for item in canonical.all_indexes
            if _is_fresh_message_inline_unique(item) is not True
        )
        indexes_ok = (
            db_mod._p23_index_set_is_canonical(conn) is True
            and actual_indexes == canonical.indexes
            and actual_all_indexes
            in (canonical.all_indexes, legacy_all_indexes)
        )
        triggers_ok = (
            db_mod._p23_trigger_set_is_canonical(conn) is True
            and _all_p23_trigger_contracts(conn)
            == tuple(sorted(canonical.triggers, key=lambda item: item[0]))
        )
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed

    return {
        "conversation_table_shape": (
            identity_table_shapes.get("conversation_table_shape") is True
            and owner_metadata == canonical.conversation_owner_metadata
        ),
        # Legacy migration #15 differs from fresh DDL only in NOT NULL (0 vs
        # 1).  Name/type/default/PK/hidden must remain canonical; otherwise a
        # generated/defaulted lookalike can make explicit repository writes fail
        # while a name-only deployment gate reports green.
        "message_table_shape": (
            identity_table_shapes.get("message_table_shape") is True
            and message_metadata is not None
            and message_metadata[2] in (0, 1)
            and message_metadata[:2] + message_metadata[3:]
            == canonical.message_public_id_metadata[:2]
            + canonical.message_public_id_metadata[3:]
        ),
        "question_table_shape": question_shape_ok,
        "required_indexes": indexes_ok,
        "required_triggers": triggers_ok,
    }


def assert_p23_schema(conn: sqlite3.Connection) -> None:
    """Raise on any non-canonical P2.3 shape; intended for DB startup gates."""
    witnesses = p23_schema_witnesses(conn)
    failed = [
        key for key in P23_SCHEMA_WITNESS_KEYS if witnesses.get(key) is not True
    ]
    if failed:
        raise sqlite3.IntegrityError(
            f"P2.3 schema witness failed: {', '.join(failed)}"
        )
