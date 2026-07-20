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
from datetime import datetime, timedelta
from functools import lru_cache


JUDGMENT_SCHEMA_WITNESS_KEYS = (
    "advice_table_shape",
    "human_decision_table_shape",
    "review_event_witness_table_shape",
    "required_indexes",
    "required_triggers",
    "rowid_integrity",
    "provenance_integrity",
)
_JUDGMENT_TABLES = (
    "task_review_advice",
    "task_human_decisions",
    "task_review_event_witnesses",
)
_JUDGMENT_EXCLUSIVE_TRIGGER_TABLES = (*_JUDGMENT_TABLES, "model_calls")
_JUDGMENT_SHARED_TRIGGER_NAMES = (
    "trg_task_events_no_update",
    "trg_task_events_no_delete",
    "trg_task_events_no_conflicting_insert",
    "trg_task_events_positive_rowid",
    "trg_structured_review_events_decision_witness",
    "trg_structured_review_events_capture_witness",
)
# This trigger is owned and byte-witnessed by design_promotion_schema.  The
# judgment inventory still rejects every unknown extra trigger on its exclusive
# tables; it ignores only this explicitly delegated cross-ledger guard so a
# legitimate pre-P2.8 nonempty judgment ledger can be upgraded in place.
_JUDGMENT_DELEGATED_TRIGGER_NAMES = (
    "trg_p28_design_decision_requires_selection",
)


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
    table_placeholders = ",".join(
        "?" for _ in _JUDGMENT_EXCLUSIVE_TRIGGER_TABLES
    )
    shared_placeholders = ",".join(
        "?" for _ in _JUDGMENT_SHARED_TRIGGER_NAMES
    )
    delegated_placeholders = ",".join(
        "?" for _ in _JUDGMENT_DELEGATED_TRIGGER_NAMES
    )
    rows = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master "
        "WHERE type = 'trigger' AND ("
        f"tbl_name IN ({table_placeholders}) "
        f"OR name IN ({shared_placeholders})"
        f") AND name NOT IN ({delegated_placeholders}) ORDER BY name",
        (
            *_JUDGMENT_EXCLUSIVE_TRIGGER_TABLES,
            *_JUDGMENT_SHARED_TRIGGER_NAMES,
            *_JUDGMENT_DELEGATED_TRIGGER_NAMES,
        ),
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
        required_trigger_names = set(db_mod._JUDGMENT_MANAGED_TRIGGERS) | set(
            _JUDGMENT_SHARED_TRIGGER_NAMES
        )
        if {name for name, _contract in triggers} != required_trigger_names:
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


def _table_integrity_is_ok(conn: sqlite3.Connection, table: str) -> bool:
    rows = conn.execute(
        f"PRAGMA integrity_check({_quoted_identifier(table)})"
    ).fetchall()
    return len(rows) == 1 and str(rows[0][0]) == "ok"


def _is_canonical_utc_timestamp(value: object) -> bool:
    """Judgment windows rely on byte ordering, so persisted times are UTC ISO."""
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


def _provenance_integrity(conn: sqlite3.Connection) -> bool:
    """Replay durable judgment semantics after same-SQL guard restoration."""
    for table in _JUDGMENT_TABLES:
        if not _table_integrity_is_ok(conn, table):
            return False
        if conn.execute(
            f"PRAGMA foreign_key_check({_quoted_identifier(table)})"
        ).fetchone() is not None:
            return False

    safe_doubts = (
        "CASE WHEN json_valid(advice.doubts_json) "
        "AND json_type(advice.doubts_json) = 'array' "
        "THEN advice.doubts_json ELSE '[]' END"
    )
    safe_evidence = (
        "CASE WHEN json_valid(advice.evidence_file_ids_json) "
        "AND json_type(advice.evidence_file_ids_json) = 'array' "
        "THEN advice.evidence_file_ids_json ELSE '[]' END"
    )
    invalid_advice = conn.execute(
        f"""
        SELECT 1
        FROM task_review_advice AS advice
        LEFT JOIN model_calls AS model_call
          ON model_call.id = advice.model_call_id
        WHERE typeof(advice.id) <> 'text'
           OR typeof(advice.task_id) <> 'text'
           OR typeof(advice.model_call_id) <> 'integer'
           OR typeof(advice.advisor_id) <> 'text'
           OR typeof(advice.advisor_version) <> 'text'
           OR typeof(advice.model_profile) <> 'text'
           OR typeof(advice.model_name) NOT IN ('null', 'text')
           OR typeof(advice.advisory_outcome) <> 'text'
           OR typeof(advice.doubts_json) <> 'text'
           OR typeof(advice.evidence_file_ids_json) <> 'text'
           OR typeof(advice.schema_version) <> 'integer'
           OR typeof(advice.created_at) <> 'text'
           OR model_call.id IS NULL
           OR model_call.task_id IS NOT advice.task_id
           OR model_call.status IS NOT 'success'
           OR model_call.agent_id IS NOT advice.advisor_id
           OR model_call.model_profile IS NOT advice.model_profile
           OR model_call.model_name IS NOT advice.model_name
           OR advice.advisory_outcome NOT IN ('clear', 'concerns', 'abstain')
           OR advice.schema_version IS NOT 1
           OR json_valid(advice.doubts_json) IS NOT 1
           OR json_type(advice.doubts_json) IS NOT 'array'
           OR json_valid(advice.evidence_file_ids_json) IS NOT 1
           OR json_type(advice.evidence_file_ids_json) IS NOT 'array'
           OR (
               advice.advisory_outcome = 'clear'
               AND json_array_length({safe_doubts}) <> 0
           )
           OR (
               advice.advisory_outcome = 'concerns'
               AND json_array_length({safe_doubts}) = 0
           )
           OR json_array_length({safe_doubts}) > 20
           OR EXISTS (
               SELECT 1
               FROM json_each({safe_doubts}) AS doubt
               WHERE doubt.type <> 'object'
                  OR (SELECT COUNT(*) FROM json_each(doubt.value)) <> 2
                  OR NOT EXISTS (
                      SELECT 1 FROM json_each(doubt.value) AS field
                      WHERE field.key = 'code'
                        AND field.type = 'text'
                        AND field.value IN (
                            'source_doubt', 'method_error',
                            'conclusion_overreach', 'insufficient_evidence',
                            'classification_issue', 'other'
                        )
                  )
                  OR NOT EXISTS (
                      SELECT 1 FROM json_each(doubt.value) AS field
                      WHERE field.key = 'detail'
                        AND field.type = 'text'
                        AND length(trim(field.value, char(
                            9,10,11,12,13,28,29,30,31,32,133,160,5760,
                            8192,8193,8194,8195,8196,8197,8198,8199,
                            8200,8201,8202,8232,8233,8239,8287,12288
                        ))) > 0
                        AND length(field.value) <= 2000
                  )
           )
           OR json_array_length({safe_evidence}) > 50
           OR (
               SELECT COUNT(*) FROM json_each({safe_evidence})
           ) <> (
               SELECT COUNT(DISTINCT value) FROM json_each({safe_evidence})
           )
           OR EXISTS (
               SELECT 1
               FROM json_each({safe_evidence}) AS evidence
               WHERE evidence.type <> 'text'
                  OR length(evidence.value) = 0
                  OR length(evidence.value) > 100
                  OR NOT EXISTS (
                      SELECT 1 FROM files WHERE id = evidence.value
                  )
           )
        LIMIT 1
        """
    ).fetchone()
    if invalid_advice is not None:
        return False

    for row in conn.execute(
        "SELECT created_at FROM task_review_advice "
        "UNION ALL SELECT created_at FROM task_human_decisions "
        "UNION ALL SELECT created_at FROM task_review_event_witnesses "
        "WHERE witness_kind = 'structured_v1'"
    ):
        if not _is_canonical_utc_timestamp(row[0]):
            return False

    safe_review_payload = (
        "CASE WHEN json_valid(review.payload_json) THEN "
        "CASE WHEN json_type(review.payload_json) = 'object' "
        "THEN review.payload_json ELSE '{}' END ELSE '{}' END"
    )
    invalid_event_witness = conn.execute(
        """
        SELECT 1
        FROM task_review_event_witnesses AS witness
        LEFT JOIN task_events AS review ON review.event_id = witness.event_id
        LEFT JOIN task_human_decisions AS decision
          ON decision.id = witness.decision_id
        WHERE typeof(witness.event_id) <> 'text'
           OR typeof(witness.event_internal_id) <> 'integer'
           OR typeof(witness.task_id) <> 'text'
           OR typeof(witness.agent_id) NOT IN ('null', 'text')
           OR typeof(witness.event_type) <> 'text'
           OR typeof(witness.level) <> 'text'
           OR typeof(witness.message) <> 'text'
           OR typeof(witness.payload_json) <> 'text'
           OR typeof(witness.created_at) <> 'text'
           OR typeof(witness.decision_id) NOT IN ('null', 'text')
           OR typeof(witness.witness_kind) <> 'text'
           OR typeof(witness.schema_version) <> 'integer'
           OR witness.schema_version IS NOT 1
           OR review.event_id IS NULL
           OR review.id IS NOT witness.event_internal_id
           OR review.task_id IS NOT witness.task_id
           OR review.agent_id IS NOT witness.agent_id
           OR review.event_type IS NOT witness.event_type
           OR review.level IS NOT witness.level
           OR review.message IS NOT witness.message
           OR review.payload_json IS NOT witness.payload_json
           OR review.created_at IS NOT witness.created_at
           OR witness.event_type NOT IN ('review_approved', 'review_rejected')
           OR json_valid(witness.payload_json) IS NOT 1
           OR json_type(witness.payload_json) IS NOT 'object'
           OR (
               witness.witness_kind = 'legacy_pre_instrumentation'
               AND (
                   witness.decision_id IS NOT NULL
                   OR EXISTS (
                       SELECT 1 FROM json_each(witness.payload_json) AS field
                       WHERE field.key = 'decision_id'
                   )
               )
           )
           OR (
               witness.witness_kind = 'structured_v1'
               AND (
                   decision.id IS NULL
                   OR decision.task_id IS NOT witness.task_id
                   OR json_type(witness.payload_json, '$.decision_id') <> 'text'
                   OR json_extract(witness.payload_json, '$.decision_id')
                      IS NOT decision.id
               )
           )
        LIMIT 1
        """
    ).fetchone()
    if invalid_event_witness is not None:
        return False

    unwitnessed_review = conn.execute(
        """
        SELECT 1
        FROM task_events AS review
        LEFT JOIN task_review_event_witnesses AS witness
          ON witness.event_id = review.event_id
        WHERE review.event_type IN ('review_approved', 'review_rejected')
          AND (
              witness.event_id IS NULL
              OR witness.event_internal_id IS NOT review.id
              OR witness.task_id IS NOT review.task_id
              OR witness.agent_id IS NOT review.agent_id
              OR witness.event_type IS NOT review.event_type
              OR witness.level IS NOT review.level
              OR witness.message IS NOT review.message
              OR witness.payload_json IS NOT review.payload_json
              OR witness.created_at IS NOT review.created_at
          )
        LIMIT 1
        """
    ).fetchone()
    if unwitnessed_review is not None:
        return False

    invalid_decision = conn.execute(
        f"""
        SELECT 1
        FROM task_human_decisions AS decision
        LEFT JOIN tasks AS task ON task.id = decision.task_id
        WHERE typeof(decision.id) <> 'text'
           OR typeof(decision.task_id) <> 'text'
           OR typeof(decision.paired_advice_id) NOT IN ('null', 'text')
           OR typeof(decision.action) <> 'text'
           OR typeof(decision.reason_code) NOT IN ('null', 'text')
           OR typeof(decision.comment) NOT IN ('null', 'text')
           OR typeof(decision.reviewer_username) <> 'text'
           OR typeof(decision.reviewer_display_name) <> 'text'
           OR typeof(decision.schema_version) <> 'integer'
           OR typeof(decision.created_at) <> 'text'
           OR task.id IS NULL
           OR (decision.action = 'approve' AND task.status IS NOT 'completed')
           OR (decision.action = 'reject' AND task.status IS NOT 'failed')
           OR task.updated_at IS NOT decision.created_at
           OR task.finished_at IS NOT decision.created_at
           OR task.error_message IS NOT CASE decision.action
               WHEN 'approve' THEN NULL
               ELSE '人工拒绝（reviewer=' || decision.reviewer_display_name
                    || '；reason=' || decision.reason_code || '）'
                    || CASE WHEN decision.comment IS NULL THEN ''
                            ELSE '：' || decision.comment END
           END
           OR (
               decision.paired_advice_id IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM task_review_advice AS paired
                   WHERE paired.id = decision.paired_advice_id
                     AND paired.task_id = decision.task_id
               )
           )
           OR (
               SELECT COUNT(*)
               FROM task_events AS review
               JOIN task_review_event_witnesses AS witness
                 ON witness.event_id = review.event_id
                AND witness.event_internal_id = review.id
                AND witness.task_id = review.task_id
                AND witness.agent_id IS review.agent_id
                AND witness.event_type = review.event_type
                AND witness.level = review.level
                AND witness.message = review.message
                AND witness.payload_json = review.payload_json
                AND witness.created_at = review.created_at
                AND witness.decision_id = decision.id
                AND witness.witness_kind = 'structured_v1'
               WHERE review.task_id = decision.task_id
                 AND review.agent_id IS task.agent_id
                 AND review.event_type = CASE decision.action
                     WHEN 'approve' THEN 'review_approved'
                     ELSE 'review_rejected'
                 END
                 AND review.level = CASE decision.action
                     WHEN 'approve' THEN 'info'
                     ELSE 'warning'
                 END
                 AND typeof(review.payload_json) = 'text'
                 AND json_valid(review.payload_json) = 1
                 AND json_type(review.payload_json) = 'object'
                 AND (SELECT COUNT(*) FROM json_each({safe_review_payload})) = 6
                 AND (
                     SELECT COUNT(DISTINCT key)
                     FROM json_each({safe_review_payload})
                 ) = 6
                 AND NOT EXISTS (
                     SELECT 1 FROM json_each({safe_review_payload}) AS field
                     WHERE field.key NOT IN (
                         'reviewer', 'reviewer_username', 'comment',
                         'decision_id', 'reason_code', 'paired_advice_id'
                     )
                 )
                 AND json_type({safe_review_payload}, '$.decision_id') = 'text'
                 AND json_extract({safe_review_payload}, '$.decision_id') IS decision.id
                 AND json_type({safe_review_payload}, '$.reviewer') = 'text'
                 AND json_extract({safe_review_payload}, '$.reviewer')
                     IS decision.reviewer_display_name
                 AND json_type(
                     {safe_review_payload}, '$.reviewer_username'
                 ) = 'text'
                 AND json_extract(
                     {safe_review_payload}, '$.reviewer_username'
                 ) IS decision.reviewer_username
                 AND (
                     (decision.comment IS NULL
                      AND json_type({safe_review_payload}, '$.comment') = 'null')
                     OR (decision.comment IS NOT NULL
                         AND json_type({safe_review_payload}, '$.comment') = 'text'
                         AND json_extract({safe_review_payload}, '$.comment')
                             IS decision.comment)
                 )
                 AND (
                     (decision.reason_code IS NULL
                      AND json_type({safe_review_payload}, '$.reason_code') = 'null')
                     OR (decision.reason_code IS NOT NULL
                         AND json_type(
                             {safe_review_payload}, '$.reason_code'
                         ) = 'text'
                         AND json_extract(
                             {safe_review_payload}, '$.reason_code'
                         ) IS decision.reason_code)
                 )
                 AND (
                     (decision.paired_advice_id IS NULL
                      AND json_type(
                          {safe_review_payload}, '$.paired_advice_id'
                      ) = 'null')
                     OR (decision.paired_advice_id IS NOT NULL
                         AND json_type(
                             {safe_review_payload}, '$.paired_advice_id'
                         ) = 'text'
                         AND json_extract(
                             {safe_review_payload}, '$.paired_advice_id'
                         ) IS decision.paired_advice_id)
                 )
           ) <> 1
        LIMIT 1
        """
    ).fetchone()
    if invalid_decision is not None:
        return False

    invalid_structured_review = conn.execute(
        f"""
        SELECT 1
        FROM task_events AS review
        WHERE review.event_type IN ('review_approved', 'review_rejected')
          AND (
              typeof(review.payload_json) <> 'text'
              OR json_valid(review.payload_json) IS NOT 1
              OR json_type({safe_review_payload}) IS NOT 'object'
              OR (
                  EXISTS (
                      SELECT 1 FROM json_each({safe_review_payload}) AS field
                      WHERE field.key = 'decision_id'
                  )
                  AND (
                      (SELECT COUNT(*) FROM json_each({safe_review_payload})) <> 6
                      OR (
                          SELECT COUNT(DISTINCT key)
                          FROM json_each({safe_review_payload})
                      ) <> 6
                      OR EXISTS (
                          SELECT 1
                          FROM json_each({safe_review_payload}) AS field
                          WHERE field.key NOT IN (
                              'reviewer', 'reviewer_username', 'comment',
                              'decision_id', 'reason_code', 'paired_advice_id'
                          )
                      )
                      OR NOT EXISTS (
                          SELECT 1
                          FROM task_human_decisions AS decision
                          JOIN tasks AS task ON task.id = decision.task_id
                          WHERE decision.task_id = review.task_id
                            AND review.agent_id IS task.agent_id
                            AND review.event_type = CASE decision.action
                                WHEN 'approve' THEN 'review_approved'
                                ELSE 'review_rejected'
                            END
                            AND review.level = CASE decision.action
                                WHEN 'approve' THEN 'info'
                                ELSE 'warning'
                            END
                            AND json_type(
                                {safe_review_payload}, '$.decision_id'
                            ) = 'text'
                            AND json_extract(
                                {safe_review_payload}, '$.decision_id'
                            ) IS decision.id
                            AND json_type(
                                {safe_review_payload}, '$.reviewer'
                            ) = 'text'
                            AND json_extract(
                                {safe_review_payload}, '$.reviewer'
                            ) IS decision.reviewer_display_name
                            AND json_type(
                                {safe_review_payload}, '$.reviewer_username'
                            ) = 'text'
                            AND json_extract(
                                {safe_review_payload}, '$.reviewer_username'
                            ) IS decision.reviewer_username
                            AND (
                                (decision.comment IS NULL
                                 AND json_type(
                                     {safe_review_payload}, '$.comment'
                                 ) = 'null')
                                OR (decision.comment IS NOT NULL
                                    AND json_type(
                                        {safe_review_payload}, '$.comment'
                                    ) = 'text'
                                    AND json_extract(
                                        {safe_review_payload}, '$.comment'
                                    ) IS decision.comment)
                            )
                            AND (
                                (decision.reason_code IS NULL
                                 AND json_type(
                                     {safe_review_payload}, '$.reason_code'
                                 ) = 'null')
                                OR (decision.reason_code IS NOT NULL
                                    AND json_type(
                                        {safe_review_payload}, '$.reason_code'
                                    ) = 'text'
                                    AND json_extract(
                                        {safe_review_payload}, '$.reason_code'
                                    ) IS decision.reason_code)
                            )
                            AND (
                                (decision.paired_advice_id IS NULL
                                 AND json_type(
                                     {safe_review_payload}, '$.paired_advice_id'
                                 ) = 'null')
                                OR (decision.paired_advice_id IS NOT NULL
                                    AND json_type(
                                        {safe_review_payload}, '$.paired_advice_id'
                                    ) = 'text'
                                    AND json_extract(
                                        {safe_review_payload}, '$.paired_advice_id'
                                    ) IS decision.paired_advice_id)
                            )
                      )
                  )
              )
          )
        LIMIT 1
        """
    ).fetchone()
    return invalid_structured_review is None


def judgment_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    """Return exact structure plus persisted internal-identity integrity."""
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
        event_witness_ok = (
            _table_contract(conn, "task_review_event_witnesses")
            == table_map["task_review_event_witnesses"]
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
        rowid_ok = conn.execute(
            """
            SELECT 1
            FROM (
                SELECT rowid FROM model_calls WHERE rowid <= 0
                UNION ALL
                SELECT rowid FROM task_review_advice WHERE rowid <= 0
                UNION ALL
                SELECT rowid FROM task_human_decisions WHERE rowid <= 0
                UNION ALL
                SELECT rowid FROM task_review_event_witnesses WHERE rowid <= 0
            ) AS nonpositive_internal_identity
            LIMIT 1
            """
        ).fetchone() is None
        provenance_ok = _provenance_integrity(conn)
    except (sqlite3.Error, RuntimeError, TypeError, ValueError):
        return failed

    return {
        "advice_table_shape": advice_ok,
        "human_decision_table_shape": human_ok,
        "review_event_witness_table_shape": event_witness_ok,
        "required_indexes": indexes_ok,
        "required_triggers": triggers_ok,
        "rowid_integrity": rowid_ok,
        "provenance_integrity": provenance_ok,
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
