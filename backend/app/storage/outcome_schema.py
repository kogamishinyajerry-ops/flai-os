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
from datetime import datetime, timedelta
from functools import lru_cache


OUTCOME_SCHEMA_WITNESS_KEYS = (
    "outcome_table_shape",
    "required_indexes",
    "required_triggers",
    "provenance_integrity",
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


def _is_canonical_utc_timestamp(value: object) -> bool:
    """Outcome windows use byte ordering; accept only our two writer encodings."""
    if not isinstance(value, str):
        return False
    if len(value) == 25:
        timespec = "seconds"
    elif len(value) == 32:
        timespec = "microseconds"
    else:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() == timedelta(0)
        and value == parsed.isoformat(timespec=timespec)
    )


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


def _provenance_integrity(conn: sqlite3.Connection) -> bool:
    """Validate persisted parent/flow witnesses, not just schema object names.

    Source task/file rows are signed into each telemetry row, while the exact
    decision/review-event witness stays normalized and is joined byte-for-byte.
    Canonical triggers freeze them prospectively; this anti-join suite keeps
    startup/health red if an earlier missing guard or foreign-keys-off writer
    left an observable orphan or mismatch.
    Repeated downloads are validated by their shared capture tuple, so only the
    byte-equality query scales with delivery-event count.
    """
    # An outcome says that a *human-signed* artifact flowed.  Require the exact
    # decision/event-witness tables and their canonical guards here; the
    # per-capture anti-join below binds the concrete bytes.  Machine-advice
    # provenance remains the separate judgment axis and must not relabel an
    # otherwise valid outcome failure as an outcome-schema failure at startup.
    from .review_schema import judgment_schema_witnesses

    judgment_witnesses = judgment_schema_witnesses(conn)
    if not all(
        judgment_witnesses.get(key) is True
        for key in (
            "human_decision_table_shape",
            "review_event_witness_table_shape",
            "required_triggers",
        )
    ):
        return False

    if conn.execute(
        "PRAGMA foreign_key_check(artifact_outcome_events)"
    ).fetchone() is not None:
        return False
    if conn.execute(
        """
        SELECT 1
        FROM (
            SELECT rowid FROM artifact_outcome_events WHERE rowid <= 0
            UNION ALL
            SELECT rowid FROM task_events WHERE rowid <= 0
            UNION ALL
            SELECT rowid FROM task_human_decisions WHERE rowid <= 0
            UNION ALL
            SELECT rowid FROM task_review_event_witnesses WHERE rowid <= 0
            UNION ALL
            SELECT rowid FROM files WHERE rowid <= 0
            UNION ALL
            SELECT rowid FROM tasks WHERE rowid <= 0
        ) AS nonpositive_internal_identity
        LIMIT 1
        """
    ).fetchone() is not None:
        return False

    invalid_shape = conn.execute(
        """
        SELECT 1
        FROM artifact_outcome_events AS outcome
        WHERE typeof(outcome.id) <> 'text'
           OR typeof(outcome.event_type) <> 'text'
           OR typeof(outcome.source_task_id) <> 'text'
           OR typeof(outcome.source_file_id) <> 'text'
           OR typeof(outcome.review_event_id) <> 'text'
           OR typeof(outcome.source_task_witness_json) <> 'text'
           OR json_valid(outcome.source_task_witness_json) IS NOT 1
           OR json_type(outcome.source_task_witness_json) IS NOT 'object'
           OR typeof(outcome.source_file_witness_json) <> 'text'
           OR json_valid(outcome.source_file_witness_json) IS NOT 1
           OR json_type(outcome.source_file_witness_json) IS NOT 'object'
           OR typeof(outcome.schema_version) <> 'integer'
           OR outcome.schema_version IS NOT 1
           OR typeof(outcome.created_at) <> 'text'
           OR outcome.event_type NOT IN (
               'capture_started', 'full_download', 'pipeline_handoff'
           )
           OR NOT (
               (
                   outcome.event_type = 'capture_started'
                   AND outcome.actor_username IS NULL
                   AND outcome.downstream_task_id IS NULL
                   AND outcome.delivered_bytes IS NULL
               )
               OR (
                   outcome.event_type = 'full_download'
                   AND typeof(outcome.actor_username) = 'text'
                   AND length(trim(outcome.actor_username, char(
                       9,10,11,12,13,28,29,30,31,32,133,160,5760,
                       8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
                       8232,8233,8239,8287,12288
                   ))) > 0
                   AND outcome.downstream_task_id IS NULL
                   AND typeof(outcome.delivered_bytes) = 'integer'
                   AND outcome.delivered_bytes >= 0
               )
               OR (
                   outcome.event_type = 'pipeline_handoff'
                   AND outcome.actor_username IS NULL
                   AND typeof(outcome.downstream_task_id) = 'text'
                   AND outcome.delivered_bytes IS NULL
               )
           )
        LIMIT 1
        """
    ).fetchone()
    if invalid_shape is not None:
        return False

    for row in conn.execute("SELECT created_at FROM artifact_outcome_events"):
        if not _is_canonical_utc_timestamp(row[0]):
            return False

    safe_review_payload = (
        "CASE WHEN json_valid(review.payload_json) "
        "THEN review.payload_json ELSE '{}' END"
    )
    safe_outputs = (
        "CASE WHEN json_valid(source.output_file_ids) THEN "
        "CASE WHEN json_type(source.output_file_ids) = 'array' "
        "THEN source.output_file_ids ELSE '[]' END ELSE '[]' END"
    )
    invalid_capture = conn.execute(
        f"""
        SELECT 1
        FROM artifact_outcome_events AS capture
        LEFT JOIN tasks AS source
          ON source.id = capture.source_task_id
        LEFT JOIN files AS artifact
          ON artifact.id = capture.source_file_id
        LEFT JOIN task_events AS review
          ON review.event_id = capture.review_event_id
        LEFT JOIN task_review_event_witnesses AS review_witness
          ON review_witness.event_id = review.event_id
         AND review_witness.event_internal_id = review.id
         AND review_witness.task_id = review.task_id
         AND review_witness.agent_id IS review.agent_id
         AND review_witness.event_type = review.event_type
         AND review_witness.level = review.level
         AND review_witness.message = review.message
         AND review_witness.payload_json = review.payload_json
         AND review_witness.created_at = review.created_at
         AND review_witness.witness_kind = 'structured_v1'
         AND review_witness.schema_version = 1
        LEFT JOIN task_human_decisions AS decision
          ON decision.id = review_witness.decision_id
         AND decision.task_id = capture.source_task_id
         AND decision.action = 'approve'
        WHERE capture.event_type = 'capture_started'
          AND (
              source.id IS NULL
              OR source.origin IS NOT 'user'
              OR source.status IS NOT 'completed'
              OR capture.source_task_witness_json IS NOT json_object(
                  'agent_id', source.agent_id,
                  'agent_version', source.agent_version,
                  'conversation_id', source.conversation_id,
                  'created_at', source.created_at,
                  'created_by', source.created_by,
                  'created_by_username', source.created_by_username,
                  'data_classification', source.data_classification,
                  'depends_on', source.depends_on,
                  'error_message', source.error_message,
                  'finished_at', source.finished_at,
                  'id', source.id,
                  'input_binding', source.input_binding,
                  'input_file_ids', source.input_file_ids,
                  'inputs_json', source.inputs_json,
                  'metadata_json', source.metadata_json,
                  'name', source.name,
                  'origin', source.origin,
                  'output_file_ids', source.output_file_ids,
                  'retry_of', source.retry_of,
                  'rowid', source.rowid,
                  'started_at', source.started_at,
                  'status', source.status,
                  'updated_at', source.updated_at
              )
              OR artifact.id IS NULL
              OR artifact.task_id IS NOT source.id
              OR artifact.kind IS NOT 'output'
              OR capture.source_file_witness_json IS NOT json_object(
                  'classification', artifact.classification,
                  'created_at', artifact.created_at,
                  'filename', artifact.filename,
                  'id', artifact.id,
                  'kind', artifact.kind,
                  'path', artifact.path,
                  'rowid', artifact.rowid,
                  'sha256', artifact.sha256,
                  'size_bytes', artifact.size_bytes,
                  'task_id', artifact.task_id,
                  'uploaded_by', artifact.uploaded_by
              )
              OR review.event_id IS NULL
              OR review.task_id IS NOT source.id
              OR review.event_type IS NOT 'review_approved'
              OR review_witness.event_id IS NULL
              OR json_type({safe_review_payload}, '$.decision_id') IS NOT 'text'
              OR decision.id IS NULL
              OR json_extract({safe_review_payload}, '$.decision_id') IS NOT decision.id
              OR NOT EXISTS (
                  SELECT 1 FROM json_each({safe_outputs}) AS output_ref
                  WHERE output_ref.type = 'text'
                    AND output_ref.value = capture.source_file_id
              )
          )
        LIMIT 1
        """
    ).fetchone()
    if invalid_capture is not None:
        return False

    flow_without_capture = conn.execute(
        """
        SELECT 1
        FROM artifact_outcome_events AS flow
        WHERE flow.event_type IN ('full_download', 'pipeline_handoff')
          AND NOT EXISTS (
              SELECT 1
              FROM artifact_outcome_events AS capture
              WHERE capture.event_type = 'capture_started'
                AND capture.source_task_id = flow.source_task_id
                AND capture.source_file_id = flow.source_file_id
                AND capture.review_event_id = flow.review_event_id
                AND capture.source_task_witness_json IS flow.source_task_witness_json
                AND capture.source_file_witness_json IS flow.source_file_witness_json
          )
        LIMIT 1
        """
    ).fetchone()
    if flow_without_capture is not None:
        return False

    invalid_download = conn.execute(
        """
        SELECT 1
        FROM artifact_outcome_events AS download
        LEFT JOIN files AS artifact ON artifact.id = download.source_file_id
        WHERE download.event_type = 'full_download'
          AND (
              artifact.id IS NULL
              OR download.delivered_bytes IS NOT artifact.size_bytes
          )
        LIMIT 1
        """
    ).fetchone()
    if invalid_download is not None:
        return False

    safe_depends = (
        "CASE WHEN json_valid(downstream.depends_on) THEN "
        "CASE WHEN json_type(downstream.depends_on) = 'array' "
        "THEN downstream.depends_on ELSE '[]' END ELSE '[]' END"
    )
    safe_inputs = (
        "CASE WHEN json_valid(downstream.input_file_ids) THEN "
        "CASE WHEN json_type(downstream.input_file_ids) = 'array' "
        "THEN downstream.input_file_ids ELSE '[]' END ELSE '[]' END"
    )
    invalid_handoff = conn.execute(
        f"""
        SELECT 1
        FROM artifact_outcome_events AS handoff
        LEFT JOIN tasks AS downstream
          ON downstream.id = handoff.downstream_task_id
        WHERE handoff.event_type = 'pipeline_handoff'
          AND (
              downstream.id IS NULL
              OR downstream.origin IS NOT 'user'
              OR NOT EXISTS (
                  SELECT 1 FROM json_each({safe_depends}) AS upstream_ref
                  WHERE upstream_ref.type = 'text'
                    AND upstream_ref.value = handoff.source_task_id
              )
              OR NOT EXISTS (
                  SELECT 1 FROM json_each({safe_inputs}) AS input_ref
                  WHERE input_ref.type = 'text'
                    AND input_ref.value = handoff.source_file_id
              )
          )
        LIMIT 1
        """
    ).fetchone()
    return invalid_handoff is None


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
        for name in db_mod._OUTCOME_REQUIRED_TRIGGERS:
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


def task_event_append_only_triggers_are_canonical(
    conn: sqlite3.Connection,
) -> bool:
    """Preflight the shared task-event parent before any startup repair.

    A nonempty task_events ledger may already contain the exact approval event
    referenced by a future or existing capture.  Missing/same-name no-op
    append-only guards make its historical protection window unknowable, so
    init_db must inspect these four contracts before dropping/recreating any
    outcome-managed object.
    """
    try:
        canonical = dict(_canonical_schema().triggers)
        names = (
            "trg_task_events_no_update",
            "trg_task_events_no_delete",
            "trg_task_events_no_conflicting_insert",
            "trg_task_events_positive_rowid",
        )
        return all(
            _trigger_contract(conn, name) == canonical.get(name)
            for name in names
        )
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return False


def review_seal_triggers_are_canonical(conn: sqlite3.Connection) -> bool:
    """Preflight post-generation review evidence before schema convergence.

    The outcome table is the durable generation marker.  Once it exists and a
    task event, decision, or sealed task has been recorded, startup may not
    replace a missing/no-op parent or review-package guard and thereby claim an
    unbroken protection window.
    """
    try:
        from . import db as db_mod

        canonical = dict(_canonical_schema().triggers)
        names = (
            *db_mod._OUTCOME_SHARED_PARENT_TRIGGERS,
            *db_mod._OUTCOME_REVIEW_SEAL_TRIGGERS,
        )
        return all(
            _trigger_contract(conn, name) == canonical.get(name)
            for name in names
        )
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return False


def outcome_schema_witnesses(
    conn: sqlite3.Connection,
) -> dict[str, bool]:
    """Return exact witnesses; any unreadable state fails closed.

    Every caller performs the persisted-provenance audit.  A cached startup
    boolean or SQLite schema cookie can be replayed after a privileged writer
    drops guards, mutates parents, restores the SQL, and resets the cookie;
    neither is strong enough to support a live ``True`` trust claim.
    """
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
            "provenance_integrity": _provenance_integrity(conn),
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
