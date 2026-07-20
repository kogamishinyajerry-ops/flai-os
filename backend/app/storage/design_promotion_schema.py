"""Canonical SQLite contract for P2.8 design comparison and promotion.

The tables in this module are evidence ledgers.  They are append-only at the
database boundary, including ``INSERT OR REPLACE`` conflict paths, and their
complete SQL/index/trigger shapes are witnessed rather than inferred from
object names.  Installation is intentionally separate from ``db.py`` so the
P2.6 owner can integrate one additive call after its migration lands.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache


DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS = (
    "table_shapes",
    "required_indexes",
    "required_triggers",
    "row_integrity",
    "reference_integrity",
)

DESIGN_PROMOTION_TABLES = (
    "design_comparisons",
    "design_candidate_selections",
    "design_release_requests",
    "design_release_decisions",
    "design_publish_events",
    "design_idempotency",
)

_TABLE_DDL = (
    """
    CREATE TABLE design_comparisons (
        id TEXT PRIMARY KEY NOT NULL,
        task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE RESTRICT,
        candidate_id TEXT NOT NULL,
        asset_slot TEXT NOT NULL,
        candidate_asset_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
        candidate_asset_sha256 TEXT NOT NULL,
        candidate_manifest_sha256 TEXT NOT NULL,
        comparison_json BLOB NOT NULL,
        comparison_sha256 TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_relative_path TEXT NOT NULL,
        target_preimage_kind TEXT NOT NULL,
        target_preimage_sha256 TEXT,
        created_by_username TEXT NOT NULL,
        created_by_display_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (typeof(id) = 'text' AND length(id) = 43 AND substr(id, 1, 11) = 'comparison_' AND substr(id, 12) NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(candidate_id) = 'text' AND length(candidate_id) = 36 AND substr(candidate_id, 1, 4) = 'odc-' AND substr(candidate_id, 5) NOT GLOB '*[^0-9a-f]*'),
        CHECK (asset_slot IN ('task_review_summary','agent_activity_indicator','workflow_monitor_sidebar')),
        CHECK (typeof(candidate_asset_sha256) = 'text' AND length(candidate_asset_sha256) = 64 AND candidate_asset_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(candidate_manifest_sha256) = 'text' AND length(candidate_manifest_sha256) = 64 AND candidate_manifest_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(comparison_json) = 'blob' AND length(comparison_json) BETWEEN 2 AND 4194304 AND json_valid(CAST(comparison_json AS TEXT))),
        CHECK (typeof(comparison_sha256) = 'text' AND length(comparison_sha256) = 64 AND comparison_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(target_id) = 'text' AND length(trim(target_id)) BETWEEN 1 AND 128),
        CHECK (typeof(target_relative_path) = 'text' AND length(trim(target_relative_path)) BETWEEN 1 AND 240),
        CHECK (target_preimage_kind IN ('present', 'absent')),
        CHECK ((target_preimage_kind = 'present' AND typeof(target_preimage_sha256) = 'text' AND length(target_preimage_sha256) = 64 AND target_preimage_sha256 NOT GLOB '*[^0-9a-f]*') OR (target_preimage_kind = 'absent' AND target_preimage_sha256 IS NULL)),
        CHECK (typeof(created_by_username) = 'text' AND length(trim(created_by_username)) BETWEEN 1 AND 128),
        CHECK (typeof(created_by_display_name) = 'text' AND length(trim(created_by_display_name)) BETWEEN 1 AND 256),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
    """
    CREATE TABLE design_candidate_selections (
        id TEXT PRIMARY KEY NOT NULL,
        comparison_id TEXT NOT NULL UNIQUE REFERENCES design_comparisons(id) ON DELETE RESTRICT,
        task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE RESTRICT,
        action TEXT NOT NULL,
        candidate_id TEXT,
        candidate_asset_sha256 TEXT,
        comparison_sha256 TEXT NOT NULL,
        task_decision_id TEXT NOT NULL UNIQUE REFERENCES task_human_decisions(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
        decided_by_username TEXT NOT NULL,
        decided_by_display_name TEXT NOT NULL,
        reason_code TEXT,
        comment TEXT,
        created_at TEXT NOT NULL,
        CHECK (typeof(id) = 'text' AND length(id) = 42 AND substr(id, 1, 10) = 'selection_' AND substr(id, 11) NOT GLOB '*[^0-9a-f]*'),
        CHECK (action IN ('approve', 'reject')),
        CHECK ((action = 'approve' AND typeof(candidate_id) = 'text' AND length(candidate_id) = 36 AND substr(candidate_id, 1, 4) = 'odc-' AND substr(candidate_id, 5) NOT GLOB '*[^0-9a-f]*' AND typeof(candidate_asset_sha256) = 'text' AND length(candidate_asset_sha256) = 64 AND candidate_asset_sha256 NOT GLOB '*[^0-9a-f]*' AND reason_code IS NULL) OR (action = 'reject' AND candidate_id IS NULL AND candidate_asset_sha256 IS NULL AND reason_code IN ('visual_mismatch','trust_semantics','accessibility','incomplete_matrix','other'))),
        CHECK (typeof(comparison_sha256) = 'text' AND length(comparison_sha256) = 64 AND comparison_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(decided_by_username) = 'text' AND length(trim(decided_by_username)) BETWEEN 1 AND 128),
        CHECK (typeof(decided_by_display_name) = 'text' AND length(trim(decided_by_display_name)) BETWEEN 1 AND 256),
        CHECK (comment IS NULL OR (typeof(comment) = 'text' AND length(comment) <= 2000)),
        CHECK (reason_code != 'other' OR (comment IS NOT NULL AND length(trim(comment)) > 0)),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
    """
    CREATE TABLE design_release_requests (
        id TEXT PRIMARY KEY NOT NULL,
        selection_id TEXT NOT NULL UNIQUE REFERENCES design_candidate_selections(id) ON DELETE RESTRICT,
        comparison_id TEXT NOT NULL REFERENCES design_comparisons(id) ON DELETE RESTRICT,
        candidate_asset_file_id TEXT NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
        candidate_asset_sha256 TEXT NOT NULL,
        comparison_sha256 TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_relative_path TEXT NOT NULL,
        target_preimage_kind TEXT NOT NULL,
        target_preimage_sha256 TEXT,
        summary_json BLOB NOT NULL,
        summary_sha256 TEXT NOT NULL,
        requested_by_username TEXT NOT NULL,
        requested_by_display_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (typeof(id) = 'text' AND length(id) = 40 AND substr(id, 1, 8) = 'release_' AND substr(id, 9) NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(candidate_asset_sha256) = 'text' AND length(candidate_asset_sha256) = 64 AND candidate_asset_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(comparison_sha256) = 'text' AND length(comparison_sha256) = 64 AND comparison_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (target_preimage_kind IN ('present', 'absent')),
        CHECK ((target_preimage_kind = 'present' AND typeof(target_preimage_sha256) = 'text' AND length(target_preimage_sha256) = 64 AND target_preimage_sha256 NOT GLOB '*[^0-9a-f]*') OR (target_preimage_kind = 'absent' AND target_preimage_sha256 IS NULL)),
        CHECK (typeof(summary_json) = 'blob' AND length(summary_json) BETWEEN 2 AND 4194304 AND json_valid(CAST(summary_json AS TEXT))),
        CHECK (typeof(summary_sha256) = 'text' AND length(summary_sha256) = 64 AND summary_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(requested_by_username) = 'text' AND length(trim(requested_by_username)) BETWEEN 1 AND 128),
        CHECK (typeof(requested_by_display_name) = 'text' AND length(trim(requested_by_display_name)) BETWEEN 1 AND 256),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
    """
    CREATE TABLE design_release_decisions (
        id TEXT PRIMARY KEY NOT NULL,
        release_request_id TEXT NOT NULL UNIQUE REFERENCES design_release_requests(id) ON DELETE RESTRICT,
        action TEXT NOT NULL,
        summary_sha256 TEXT NOT NULL,
        reason_code TEXT,
        comment TEXT,
        decided_by_username TEXT NOT NULL,
        decided_by_display_name TEXT NOT NULL,
        release_package_json BLOB,
        release_package_sha256 TEXT,
        created_at TEXT NOT NULL,
        CHECK (typeof(id) = 'text' AND length(id) = 49 AND substr(id, 1, 17) = 'release_decision_' AND substr(id, 18) NOT GLOB '*[^0-9a-f]*'),
        CHECK (action IN ('approve', 'reject')),
        CHECK (typeof(summary_sha256) = 'text' AND length(summary_sha256) = 64 AND summary_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK ((action = 'approve' AND reason_code IS NULL AND typeof(release_package_json) = 'blob' AND length(release_package_json) BETWEEN 2 AND 4194304 AND json_valid(CAST(release_package_json AS TEXT)) AND typeof(release_package_sha256) = 'text' AND length(release_package_sha256) = 64 AND release_package_sha256 NOT GLOB '*[^0-9a-f]*') OR (action = 'reject' AND reason_code IN ('visual_mismatch','trust_semantics','accessibility','incomplete_matrix','other') AND release_package_json IS NULL AND release_package_sha256 IS NULL)),
        CHECK (comment IS NULL OR (typeof(comment) = 'text' AND length(comment) <= 2000)),
        CHECK (reason_code != 'other' OR (comment IS NOT NULL AND length(trim(comment)) > 0)),
        CHECK (typeof(decided_by_username) = 'text' AND length(trim(decided_by_username)) BETWEEN 1 AND 128),
        CHECK (typeof(decided_by_display_name) = 'text' AND length(trim(decided_by_display_name)) BETWEEN 1 AND 256),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
    """
    CREATE TABLE design_publish_events (
        id TEXT PRIMARY KEY NOT NULL,
        attempt_id TEXT NOT NULL,
        release_request_id TEXT NOT NULL REFERENCES design_release_requests(id) ON DELETE RESTRICT,
        release_decision_id TEXT NOT NULL REFERENCES design_release_decisions(id) ON DELETE RESTRICT,
        event_type TEXT NOT NULL,
        actor_username TEXT NOT NULL,
        actor_display_name TEXT NOT NULL,
        release_package_sha256 TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_relative_path TEXT NOT NULL,
        before_kind TEXT NOT NULL,
        before_sha256 TEXT,
        after_kind TEXT NOT NULL,
        after_sha256 TEXT,
        backup_relative_path TEXT,
        backup_sha256 TEXT,
        details_json BLOB NOT NULL,
        details_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (attempt_id, event_type),
        CHECK (typeof(id) = 'text' AND length(id) = 48 AND substr(id, 1, 16) = 'promotion_event_' AND substr(id, 17) NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(attempt_id) = 'text' AND length(attempt_id) = 40 AND substr(attempt_id, 1, 8) = 'attempt_' AND substr(attempt_id, 9) NOT GLOB '*[^0-9a-f]*'),
        CHECK (event_type IN ('publish_intent','publish_commit','publish_abort','publish_recovered_commit','publish_manual_intervention','rollback_intent','rollback_commit','rollback_abort','rollback_recovered_commit','rollback_manual_intervention')),
        CHECK (typeof(actor_username) = 'text' AND length(trim(actor_username)) BETWEEN 1 AND 128),
        CHECK (typeof(actor_display_name) = 'text' AND length(trim(actor_display_name)) BETWEEN 1 AND 256),
        CHECK (typeof(release_package_sha256) = 'text' AND length(release_package_sha256) = 64 AND release_package_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (before_kind IN ('present','absent') AND after_kind IN ('present','absent')),
        CHECK ((before_kind = 'present' AND typeof(before_sha256) = 'text' AND length(before_sha256) = 64 AND before_sha256 NOT GLOB '*[^0-9a-f]*') OR (before_kind = 'absent' AND before_sha256 IS NULL)),
        CHECK ((after_kind = 'present' AND typeof(after_sha256) = 'text' AND length(after_sha256) = 64 AND after_sha256 NOT GLOB '*[^0-9a-f]*') OR (after_kind = 'absent' AND after_sha256 IS NULL)),
        CHECK ((backup_relative_path IS NULL AND backup_sha256 IS NULL) OR (typeof(backup_relative_path) = 'text' AND length(trim(backup_relative_path)) BETWEEN 1 AND 240 AND typeof(backup_sha256) = 'text' AND length(backup_sha256) = 64 AND backup_sha256 NOT GLOB '*[^0-9a-f]*')),
        CHECK (typeof(details_json) = 'blob' AND length(details_json) BETWEEN 2 AND 1048576 AND json_valid(CAST(details_json AS TEXT))),
        CHECK (typeof(details_sha256) = 'text' AND length(details_sha256) = 64 AND details_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
    """
    CREATE TABLE design_idempotency (
        id TEXT PRIMARY KEY NOT NULL,
        operation TEXT NOT NULL,
        actor_username TEXT NOT NULL,
        request_id TEXT NOT NULL,
        request_sha256 TEXT NOT NULL,
        response_status INTEGER NOT NULL,
        response_json BLOB NOT NULL,
        response_sha256 TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (operation, actor_username, request_id),
        CHECK (typeof(id) = 'text' AND length(id) = 44 AND substr(id, 1, 12) = 'idempotency_' AND substr(id, 13) NOT GLOB '*[^0-9a-f]*'),
        CHECK (operation IN ('comparison_create','candidate_selection','release_request_create','release_decision','publish','rollback')),
        CHECK (typeof(actor_username) = 'text' AND length(trim(actor_username)) BETWEEN 1 AND 128),
        CHECK (typeof(request_id) = 'text' AND length(request_id) = 36 AND substr(request_id, 1, 4) = 'req_' AND substr(request_id, 5) NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(request_sha256) = 'text' AND length(request_sha256) = 64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(response_status) = 'integer' AND response_status IN (200, 201)),
        CHECK (typeof(response_json) = 'blob' AND length(response_json) BETWEEN 2 AND 4194304 AND json_valid(CAST(response_json AS TEXT))),
        CHECK (typeof(response_sha256) = 'text' AND length(response_sha256) = 64 AND response_sha256 NOT GLOB '*[^0-9a-f]*'),
        CHECK (typeof(resource_id) = 'text' AND length(trim(resource_id)) BETWEEN 1 AND 160),
        CHECK (typeof(created_at) = 'text' AND length(created_at) IN (25, 32) AND substr(created_at, -6) = '+00:00')
    )
    """,
)

_INDEX_DDL = (
    "CREATE INDEX idx_design_comparisons_task_created ON design_comparisons(task_id, created_at, id)",
    "CREATE INDEX idx_design_comparisons_target_created ON design_comparisons(target_id, created_at, id)",
    "CREATE INDEX idx_design_publish_release_created ON design_publish_events(release_request_id, created_at, id)",
    "CREATE INDEX idx_design_publish_target_created ON design_publish_events(target_id, created_at, id)",
)


def _append_only_triggers(
    table: str, conflicting_expression: str
) -> tuple[str, ...]:
    return (
        f"CREATE TRIGGER trg_{table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END",
        f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END",
        f"CREATE TRIGGER trg_{table}_no_conflicting_insert BEFORE INSERT ON {table} WHEN EXISTS (SELECT 1 FROM {table} WHERE {conflicting_expression}) BEGIN SELECT RAISE(ABORT, '{table} conflicting insert is forbidden'); END",
        f"CREATE TRIGGER trg_{table}_positive_rowid AFTER INSERT ON {table} WHEN NEW.rowid <= 0 BEGIN SELECT RAISE(ABORT, '{table} rowid must be positive'); END",
    )


_TRIGGER_DDL = (
    *_append_only_triggers("design_comparisons", "id = NEW.id"),
    *_append_only_triggers(
        "design_candidate_selections",
        "id = NEW.id OR comparison_id = NEW.comparison_id OR task_id = NEW.task_id OR task_decision_id = NEW.task_decision_id",
    ),
    *_append_only_triggers(
        "design_release_requests", "id = NEW.id OR selection_id = NEW.selection_id"
    ),
    *_append_only_triggers(
        "design_release_decisions",
        "id = NEW.id OR release_request_id = NEW.release_request_id",
    ),
    *_append_only_triggers(
        "design_publish_events",
        "id = NEW.id OR (attempt_id = NEW.attempt_id AND event_type = NEW.event_type)",
    ),
    *_append_only_triggers(
        "design_idempotency",
        "id = NEW.id OR (operation = NEW.operation AND actor_username = NEW.actor_username AND request_id = NEW.request_id)",
    ),
    """
    CREATE TRIGGER trg_p28_publish_event_release_binding
    BEFORE INSERT ON design_publish_events
    WHEN NOT EXISTS (
        SELECT 1
        FROM design_release_requests AS release
        JOIN design_release_decisions AS decision
          ON decision.release_request_id = release.id
        WHERE release.id = NEW.release_request_id
          AND decision.id = NEW.release_decision_id
          AND decision.action = 'approve'
          AND NEW.release_package_sha256 IS decision.release_package_sha256
          AND NEW.target_id IS release.target_id
          AND NEW.target_relative_path IS release.target_relative_path
          AND (
              (
                  NEW.event_type LIKE 'publish_%'
                  AND NEW.before_kind IS release.target_preimage_kind
                  AND NEW.before_sha256 IS release.target_preimage_sha256
                  AND NEW.after_kind = 'present'
                  AND NEW.after_sha256 IS release.candidate_asset_sha256
              )
              OR (
                  NEW.event_type LIKE 'rollback_%'
                  AND NEW.before_kind = 'present'
                  AND NEW.before_sha256 IS release.candidate_asset_sha256
                  AND NEW.after_kind IS release.target_preimage_kind
                  AND NEW.after_sha256 IS release.target_preimage_sha256
              )
          )
          AND (
              (
                  release.target_preimage_kind = 'present'
                  AND NEW.backup_relative_path IS NOT NULL
                  AND NEW.backup_sha256 IS release.target_preimage_sha256
              )
              OR (
                  release.target_preimage_kind = 'absent'
                  AND NEW.backup_relative_path IS NULL
                  AND NEW.backup_sha256 IS NULL
              )
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'publish event release binding is invalid');
    END
    """,
    """
    CREATE TRIGGER trg_p28_design_decision_requires_selection
    BEFORE INSERT ON task_human_decisions
    WHEN (
        SELECT agent_id = 'open_design_daemon_candidate_agent'
            OR json_extract(metadata_json, '$.review_contract') = 'open-design-candidate/v1'
        FROM tasks WHERE id = NEW.task_id
    )
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1 FROM design_candidate_selections AS selection
            WHERE selection.task_id = NEW.task_id
              AND selection.task_decision_id = NEW.id
              AND selection.action = NEW.action
              AND selection.decided_by_username = NEW.reviewer_username
        ) THEN RAISE(ABORT, 'design selection witness is required') END;
    END
    """,
    """
    CREATE TRIGGER trg_p28_design_review_exit_requires_selection
    BEFORE UPDATE OF status ON tasks
    WHEN OLD.status = 'waiting_review'
     AND NEW.status <> 'waiting_review'
     AND (
        OLD.agent_id = 'open_design_daemon_candidate_agent'
        OR json_extract(OLD.metadata_json, '$.review_contract') = 'open-design-candidate/v1'
     )
    BEGIN
        SELECT CASE WHEN NOT EXISTS (
            SELECT 1
            FROM design_candidate_selections AS selection
            JOIN task_human_decisions AS decision
              ON decision.id = selection.task_decision_id
             AND decision.task_id = selection.task_id
             AND decision.action = selection.action
             AND decision.reviewer_username = selection.decided_by_username
            WHERE selection.task_id = OLD.id
              AND ((selection.action = 'approve' AND NEW.status = 'completed')
                OR (selection.action = 'reject' AND NEW.status = 'failed'))
        ) THEN RAISE(ABORT, 'design selection and human decision are required') END;
    END
    """,
)

DESIGN_PROMOTION_INDEX_NAMES = tuple(
    statement.split()[2] for statement in _INDEX_DDL
)
DESIGN_PROMOTION_TRIGGER_NAMES = tuple(
    statement.strip().split()[2] for statement in _TRIGGER_DDL
)


@dataclass(frozen=True)
class _CanonicalSchema:
    tables: tuple[tuple[str, tuple[object, ...]], ...]
    indexes: tuple[tuple[str, tuple[object, ...]], ...]
    index_inventory: tuple[tuple[str, tuple[object, ...]], ...]
    triggers: tuple[tuple[str, tuple[object, ...]], ...]
    trigger_inventory: tuple[tuple[str, tuple[object, ...]], ...]


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().split())


def _digest(sql: str | bytes) -> str:
    data = sql if isinstance(sql, bytes) else _normalize_sql(sql).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_contract(conn: sqlite3.Connection, table: str) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return None
    quoted = _quoted(table)
    return (
        _digest(str(row[0])),
        tuple(tuple(item) for item in conn.execute(f"PRAGMA table_xinfo({quoted})")),
        tuple(tuple(item) for item in conn.execute(f"PRAGMA foreign_key_list({quoted})")),
    )


def _index_contract(conn: sqlite3.Connection, name: str) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    table = str(row[0])
    list_row = next(
        (
            tuple(item)
            for item in conn.execute(f"PRAGMA index_list({_quoted(table)})")
            if str(item[1]) == name
        ),
        None,
    )
    if list_row is None:
        return None
    quoted = _quoted(name)
    return (
        table,
        None if row[1] is None else _digest(str(row[1])),
        list_row,
        tuple(tuple(item) for item in conn.execute(f"PRAGMA index_xinfo({quoted})")),
    )


def _trigger_contract(conn: sqlite3.Connection, name: str) -> tuple[object, ...] | None:
    row = conn.execute(
        "SELECT tbl_name, sql FROM sqlite_master WHERE type='trigger' AND name=?",
        (name,),
    ).fetchone()
    if row is None or row[1] is None:
        return None
    return str(row[0]), _digest(str(row[1]))


def _managed_index_inventory(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    placeholders = ",".join("?" for _ in DESIGN_PROMOTION_TABLES)
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            f"AND lower(tbl_name) IN ({placeholders}) ORDER BY name",
            DESIGN_PROMOTION_TABLES,
        )
    ]
    result: list[tuple[str, tuple[object, ...]]] = []
    for name in names:
        contract = _index_contract(conn, name)
        if contract is None:
            raise RuntimeError(f"P2.8 index is unreadable: {name}")
        result.append((name, contract))
    return tuple(result)


def _managed_trigger_inventory(
    conn: sqlite3.Connection,
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    placeholders = ",".join("?" for _ in DESIGN_PROMOTION_TABLES)
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            f"AND lower(tbl_name) IN ({placeholders}) ORDER BY name",
            DESIGN_PROMOTION_TABLES,
        )
    ]
    result: list[tuple[str, tuple[object, ...]]] = []
    for name in names:
        contract = _trigger_contract(conn, name)
        if contract is None:
            raise RuntimeError(f"P2.8 trigger is unreadable: {name}")
        result.append((name, contract))
    return tuple(result)


def _canonical_parent_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            data_classification TEXT,
            output_file_ids TEXT
        );
        CREATE TABLE files (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            kind TEXT,
            filename TEXT,
            path TEXT,
            size_bytes INTEGER,
            sha256 TEXT,
            classification TEXT
        );
        CREATE TABLE task_human_decisions (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reviewer_username TEXT NOT NULL,
            reviewer_display_name TEXT,
            reason_code TEXT,
            comment TEXT,
            created_at TEXT
        );
        """
    )


@lru_cache(maxsize=1)
def _canonical_schema() -> _CanonicalSchema:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _canonical_parent_schema(conn)
        for statement in (*_TABLE_DDL, *_INDEX_DDL, *_TRIGGER_DDL):
            conn.execute(statement)
        return _CanonicalSchema(
            tables=tuple(
                (name, _table_contract(conn, name))  # type: ignore[arg-type]
                for name in DESIGN_PROMOTION_TABLES
            ),
            indexes=tuple(
                (name, _index_contract(conn, name))  # type: ignore[arg-type]
                for name in DESIGN_PROMOTION_INDEX_NAMES
            ),
            index_inventory=_managed_index_inventory(conn),
            triggers=tuple(
                (name, _trigger_contract(conn, name))  # type: ignore[arg-type]
                for name in DESIGN_PROMOTION_TRIGGER_NAMES
            ),
            trigger_inventory=_managed_trigger_inventory(conn),
        )
    finally:
        conn.close()


def _managed_objects_present(conn: sqlite3.Connection) -> bool:
    names = (*DESIGN_PROMOTION_TABLES, *DESIGN_PROMOTION_INDEX_NAMES, *DESIGN_PROMOTION_TRIGGER_NAMES)
    placeholders = ",".join("?" for _ in names)
    return conn.execute(
        f"SELECT 1 FROM sqlite_master WHERE name IN ({placeholders}) LIMIT 1", names
    ).fetchone() is not None


def _managed_object_names_are_known(conn: sqlite3.Connection) -> bool:
    canonical = _canonical_schema()
    return (
        {name for name, _contract in _managed_index_inventory(conn)}
        <= {name for name, _contract in canonical.index_inventory}
        and {name for name, _contract in _managed_trigger_inventory(conn)}
        <= {name for name, _contract in canonical.trigger_inventory}
    )


def _open_design_parent_evidence_exists(conn: sqlite3.Connection) -> bool:
    marker = """
        task.agent_id = 'open_design_daemon_candidate_agent'
        OR json_extract(
            CASE WHEN json_valid(task.metadata_json)
                 THEN task.metadata_json ELSE '{}' END,
            '$.review_contract'
        ) = 'open-design-candidate/v1'
    """
    decision = conn.execute(
        f"""
        SELECT 1
        FROM task_human_decisions AS decision
        JOIN tasks AS task ON task.id=decision.task_id
        WHERE {marker}
        LIMIT 1
        """
    ).fetchone()
    terminal = conn.execute(
        f"""
        SELECT 1
        FROM tasks AS task
        WHERE ({marker})
          AND task.status IN ('completed','failed','cancelled')
        LIMIT 1
        """
    ).fetchone()
    return decision is not None or terminal is not None


def _managed_ledgers_are_canonical_and_empty(conn: sqlite3.Connection) -> bool:
    """Return true only when resealing cannot bless persisted P2.8 evidence."""

    if not _managed_object_names_are_known(conn):
        return False
    if _open_design_parent_evidence_exists(conn):
        return False
    canonical_tables = dict(_canonical_schema().tables)
    for table in DESIGN_PROMOTION_TABLES:
        if _table_contract(conn, table) != canonical_tables[table]:
            return False
        quoted = _quoted(table)
        if conn.execute(
            f"SELECT EXISTS(SELECT 1 FROM {quoted} LIMIT 1)"
        ).fetchone()[0] == 1:
            return False
    return True


def _canonical_bytes_hash_ok(blob: object, expected: object) -> bool:
    if not isinstance(blob, bytes) or not isinstance(expected, str):
        return False
    try:
        value = json.loads(blob.decode("utf-8", errors="strict"))
        canonical = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return canonical == blob and _digest(blob) == expected


def _canonical_json_object(
    blob: object, expected: object
) -> dict[str, object] | None:
    if not _canonical_bytes_hash_ok(blob, expected):
        return None
    value = json.loads(bytes(blob).decode("utf-8"))
    return value if isinstance(value, dict) else None


def _rows_as_dicts(
    conn: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> list[dict[str, object]]:
    cursor = conn.execute(sql, parameters)
    names = tuple(str(item[0]) for item in cursor.description or ())
    return [dict(zip(names, tuple(row), strict=True)) for row in cursor]


def _expected_target(kind: object, sha256: object) -> dict[str, object]:
    return {"kind": kind, **({"sha256": sha256} if sha256 is not None else {})}


def _exact_prefixed_hex(
    value: object, *, prefix: str, suffix_length: int
) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(prefix) + suffix_length
        and value.startswith(prefix)
        and all(character in "0123456789abcdef" for character in value[len(prefix) :])
    )


def _comparison_evidence_integrity(conn: sqlite3.Connection) -> bool:
    files = {
        str(row["id"]): row
        for row in _rows_as_dicts(
            conn, "SELECT id, task_id, sha256 FROM files"
        )
    }
    for row in _rows_as_dicts(conn, "SELECT * FROM design_comparisons"):
        evidence = _canonical_json_object(
            row["comparison_json"], row["comparison_sha256"]
        )
        if evidence is None:
            return False
        candidate = evidence.get("candidate")
        target = evidence.get("target")
        creator = evidence.get("created_by")
        artifact = files.get(str(row["candidate_asset_file_id"]))
        if (
            evidence.get("schema_version") != "flai-design-comparison/v1"
            or evidence.get("comparison_id") != row["id"]
            or evidence.get("task_id") != row["task_id"]
            or not isinstance(candidate, dict)
            or candidate.get("candidate_id") != row["candidate_id"]
            or candidate.get("asset_slot") != row["asset_slot"]
            or candidate.get("asset_file_id") != row["candidate_asset_file_id"]
            or candidate.get("asset_sha256") != row["candidate_asset_sha256"]
            or not isinstance(target, dict)
            or target.get("target_id") != row["target_id"]
            or target.get("relative_path") != row["target_relative_path"]
            or target.get("preimage")
            != _expected_target(
                row["target_preimage_kind"], row["target_preimage_sha256"]
            )
            or not isinstance(creator, dict)
            or creator
            != {
                "username": row["created_by_username"],
                "display_name": row["created_by_display_name"],
            }
            or evidence.get("created_at") != row["created_at"]
            or artifact is None
            or artifact["task_id"] != row["task_id"]
            or artifact["sha256"] != row["candidate_asset_sha256"]
        ):
            return False
    return True


def _open_design_parent_evidence_integrity(conn: sqlite3.Connection) -> bool:
    marker = """
        task.agent_id = 'open_design_daemon_candidate_agent'
        OR json_extract(
            CASE WHEN json_valid(task.metadata_json)
                 THEN task.metadata_json ELSE '{}' END,
            '$.review_contract'
        ) = 'open-design-candidate/v1'
    """
    orphan_decision = conn.execute(
        f"""
        SELECT 1
        FROM task_human_decisions AS decision
        JOIN tasks AS task ON task.id=decision.task_id
        WHERE ({marker})
          AND NOT EXISTS (
              SELECT 1
              FROM design_candidate_selections AS selection
              WHERE selection.task_decision_id=decision.id
                AND selection.task_id=decision.task_id
                AND selection.action=decision.action
                AND selection.decided_by_username=decision.reviewer_username
          )
        LIMIT 1
        """
    ).fetchone()
    terminal_without_review = conn.execute(
        f"""
        SELECT 1
        FROM tasks AS task
        WHERE ({marker})
          AND task.status IN ('completed','failed','cancelled')
          AND NOT EXISTS (
              SELECT 1
              FROM design_candidate_selections AS selection
              JOIN task_human_decisions AS decision
                ON decision.id=selection.task_decision_id
               AND decision.task_id=selection.task_id
               AND decision.action=selection.action
               AND decision.reviewer_username=selection.decided_by_username
              WHERE selection.task_id=task.id
                AND (
                    (task.status='completed' AND selection.action='approve')
                    OR (task.status='failed' AND selection.action='reject')
                )
          )
        LIMIT 1
        """
    ).fetchone()
    return orphan_decision is None and terminal_without_review is None


def _release_evidence_integrity(conn: sqlite3.Connection) -> bool:
    comparisons = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_comparisons")
    }
    selections = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_candidate_selections")
    }
    human_decisions = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM task_human_decisions")
    }
    releases = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_release_requests")
    }
    for release in releases.values():
        selection = selections.get(str(release["selection_id"]))
        comparison = comparisons.get(str(release["comparison_id"]))
        if selection is None or comparison is None:
            return False
        human_decision = human_decisions.get(str(selection["task_decision_id"]))
        if (
            human_decision is None
            or selection["action"] != "approve"
            or release["comparison_id"] != selection["comparison_id"]
            or release["comparison_sha256"] != selection["comparison_sha256"]
            or release["comparison_sha256"] != comparison["comparison_sha256"]
            or release["candidate_asset_file_id"]
            != comparison["candidate_asset_file_id"]
            or release["candidate_asset_sha256"]
            != comparison["candidate_asset_sha256"]
            or release["candidate_asset_sha256"]
            != selection["candidate_asset_sha256"]
            or release["target_id"] != comparison["target_id"]
            or release["target_relative_path"]
            != comparison["target_relative_path"]
            or release["target_preimage_kind"]
            != comparison["target_preimage_kind"]
            or release["target_preimage_sha256"]
            != comparison["target_preimage_sha256"]
        ):
            return False
        expected_summary = {
            "candidate": {
                "task_id": selection["task_id"],
                "candidate_id": selection["candidate_id"],
                "asset_slot": comparison["asset_slot"],
                "asset_sha256": selection["candidate_asset_sha256"],
                "comparison_sha256": selection["comparison_sha256"],
                "candidate_approval": {
                    "decision_id": selection["task_decision_id"],
                    "username": selection["decided_by_username"],
                    "display_name": selection["decided_by_display_name"],
                    "at": human_decision["created_at"],
                },
            },
            "target": {
                "target_id": comparison["target_id"],
                "relative_path": comparison["target_relative_path"],
                "preimage": _expected_target(
                    comparison["target_preimage_kind"],
                    comparison["target_preimage_sha256"],
                ),
                "postimage_sha256": selection["candidate_asset_sha256"],
            },
        }
        summary = _canonical_json_object(
            release["summary_json"], release["summary_sha256"]
        )
        if summary != expected_summary:
            return False

    for decision in _rows_as_dicts(conn, "SELECT * FROM design_release_decisions"):
        release = releases.get(str(decision["release_request_id"]))
        if release is None or decision["summary_sha256"] != release["summary_sha256"]:
            return False
        if decision["action"] == "approve":
            summary = _canonical_json_object(
                release["summary_json"], release["summary_sha256"]
            )
            package = _canonical_json_object(
                decision["release_package_json"],
                decision["release_package_sha256"],
            )
            expected_package = {
                "schema_version": "flai-design-release-package/v1",
                "summary": summary,
                "release_approval": {
                    "decision_id": decision["id"],
                    "username": decision["decided_by_username"],
                    "display_name": decision["decided_by_display_name"],
                    "at": decision["created_at"],
                },
            }
            if package != expected_package:
                return False
        elif (
            decision["release_package_json"] is not None
            or decision["release_package_sha256"] is not None
        ):
            return False
    return True


def _publish_public_result(event: dict[str, object], operation: str) -> dict[str, object]:
    if operation == "publish":
        return {
            "schema_version": "flai-design-publish-result/v1",
            "release_request_id": event["release_request_id"],
            "state": "published",
            "publish_event_id": event["id"],
            "target_id": event["target_id"],
            "before_sha256": event["before_sha256"],
            "after_sha256": event["after_sha256"],
            "backup_sha256": event["backup_sha256"],
            "release_package_sha256": event["release_package_sha256"],
            "published_by": {
                "username": event["actor_username"],
                "display_name": event["actor_display_name"],
            },
            "published_at": event["created_at"],
        }
    return {
        "schema_version": "flai-design-publish-result/v1",
        "release_request_id": event["release_request_id"],
        "state": "rolled_back",
        "rollback_event_id": event["id"],
        "target_id": event["target_id"],
        "before_sha256": event["before_sha256"],
        "after_sha256": event["after_sha256"],
        "backup_sha256": event["backup_sha256"],
        "release_package_sha256": event["release_package_sha256"],
        "rolled_back_by": {
            "username": event["actor_username"],
            "display_name": event["actor_display_name"],
        },
        "rolled_back_at": event["created_at"],
    }


def _publish_event_details_integrity(event: dict[str, object]) -> bool:
    details = _canonical_json_object(event["details_json"], event["details_sha256"])
    if details is None:
        return False
    event_type = str(event["event_type"])
    operation = "publish" if event_type.startswith("publish_") else "rollback"
    if event_type.endswith("_intent"):
        if not _exact_prefixed_hex(
            details.get("request_id"), prefix="req_", suffix_length=32
        ) or not (
            isinstance(details.get("request_sha256"), str)
            and len(str(details["request_sha256"])) == 64
            and all(
                character in "0123456789abcdef"
                for character in str(details["request_sha256"])
            )
        ):
            return False
        if operation == "publish":
            return details == {
                "schema_version": "flai-design-publish-intent/v1",
                "operation": "publish",
                "request_id": details["request_id"],
                "request_sha256": details["request_sha256"],
                "candidate_asset_file_id": event["candidate_asset_file_id"],
                "candidate_asset_sha256": event["candidate_asset_sha256"],
                "expected_target": _expected_target(
                    event["before_kind"], event["before_sha256"]
                ),
            }
        quarantine = (
            f"{event['target_relative_path']}.rollback-{event['attempt_id']}.quarantine.png"
            if event["after_kind"] == "absent"
            else None
        )
        return details == {
            "schema_version": "flai-design-rollback-intent/v1",
            "operation": "rollback",
            "request_id": details["request_id"],
            "request_sha256": details["request_sha256"],
            "expected_current_sha256": event["before_sha256"],
            "restore_target": _expected_target(
                event["after_kind"], event["after_sha256"]
            ),
            "quarantine_relative_path": quarantine,
        }

    terminal = {
        "publish_commit": ("commit", False),
        "publish_abort": ("abort", True),
        "publish_recovered_commit": ("recovered_commit", True),
        "publish_manual_intervention": ("manual_intervention", True),
        "rollback_commit": ("commit", False),
        "rollback_abort": ("abort", True),
        "rollback_recovered_commit": ("recovered_commit", True),
        "rollback_manual_intervention": ("manual_intervention", True),
    }.get(event_type)
    if terminal is None:
        return False
    outcome, reconciliation = terminal
    public_result = (
        _publish_public_result(event, operation)
        if outcome in {"commit", "recovered_commit"}
        else None
    )
    if not reconciliation:
        return details == {
            "schema_version": f"flai-design-{operation}-commit/v1",
            "operation": operation,
            "outcome": "commit",
            "public_result": public_result,
        }
    required = {
        "schema_version",
        "operation",
        "outcome",
        "observed_target",
        "public_result",
    }
    if (
        not required.issubset(details)
        or not set(details).issubset(
            required | {"observation_error", "artifact_error"}
        )
        or details["schema_version"]
        != "flai-design-publish-reconciliation/v1"
        or details["operation"] != operation
        or details["outcome"] != outcome
        or details["public_result"] != public_result
        or not isinstance(details["observed_target"], dict)
        or details["observed_target"].get("kind")
        not in {"present", "absent", "unreadable"}
        or any(
            key not in {"kind", "sha256"} for key in details["observed_target"]
        )
        or any(
            key in details and not isinstance(details[key], str)
            for key in ("observation_error", "artifact_error")
        )
    ):
        return False
    if outcome == "recovered_commit":
        return details["observed_target"] == _expected_target(
            event["after_kind"], event["after_sha256"]
        )
    if outcome == "abort":
        return details["observed_target"] == _expected_target(
            event["before_kind"], event["before_sha256"]
        )
    return True


def _publish_event_integrity(conn: sqlite3.Connection) -> bool:
    events = _rows_as_dicts(
        conn,
        """
        SELECT event.rowid AS event_rowid, event.*,
               release.candidate_asset_file_id,
               release.candidate_asset_sha256
        FROM design_publish_events AS event
        JOIN design_release_requests AS release
          ON release.id=event.release_request_id
        ORDER BY event.release_request_id, event.rowid
        """,
    )
    groups: dict[str, list[dict[str, object]]] = {}
    for event in events:
        groups.setdefault(str(event["release_request_id"]), []).append(event)
    exact_binding_columns = (
        "attempt_id",
        "release_request_id",
        "release_decision_id",
        "actor_username",
        "actor_display_name",
        "release_package_sha256",
        "target_id",
        "target_relative_path",
        "before_kind",
        "before_sha256",
        "after_kind",
        "after_sha256",
        "backup_relative_path",
        "backup_sha256",
    )
    for release_events in groups.values():
        phase = "publish_ready"
        pending: dict[str, object] | None = None
        for event in release_events:
            if not _publish_event_details_integrity(event):
                return False
            event_type = str(event["event_type"])
            if event_type == "publish_intent":
                if phase != "publish_ready" or pending is not None:
                    return False
                pending = event
                continue
            if event_type in {
                "publish_commit",
                "publish_abort",
                "publish_recovered_commit",
                "publish_manual_intervention",
            }:
                if (
                    pending is None
                    or pending["event_type"] != "publish_intent"
                    or any(event[column] != pending[column] for column in exact_binding_columns)
                ):
                    return False
                pending = None
                if event_type == "publish_abort":
                    phase = "publish_ready"
                elif event_type == "publish_manual_intervention":
                    phase = "manual_intervention"
                else:
                    phase = "published"
                continue
            if event_type == "rollback_intent":
                if phase != "published" or pending is not None:
                    return False
                pending = event
                continue
            if event_type in {
                "rollback_commit",
                "rollback_abort",
                "rollback_recovered_commit",
                "rollback_manual_intervention",
            }:
                if (
                    pending is None
                    or pending["event_type"] != "rollback_intent"
                    or any(event[column] != pending[column] for column in exact_binding_columns)
                ):
                    return False
                pending = None
                if event_type == "rollback_abort":
                    phase = "published"
                elif event_type == "rollback_manual_intervention":
                    phase = "manual_intervention"
                else:
                    phase = "rolled_back"
                continue
            return False
    return True


def _public_comparison_core(
    comparison: dict[str, object], comparison_sha256: object
) -> dict[str, object] | None:
    try:
        public = json.loads(
            json.dumps(comparison, ensure_ascii=False, allow_nan=False)
        )
        frames = public["frames"]
        if not isinstance(frames, list):
            return None
        for frame in frames:
            if not isinstance(frame, dict):
                return None
            current = frame.get("current")
            candidate = frame.get("candidate")
            if not isinstance(current, dict) or not isinstance(candidate, dict):
                return None
            current.pop("_relative_path", None)
            candidate.pop("_file_id", None)
    except (KeyError, TypeError, ValueError):
        return None
    public["comparison_sha256"] = comparison_sha256
    return public


def _utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _not_after(value: object, cutoff: object) -> bool:
    parsed = _utc_timestamp(value)
    parsed_cutoff = _utc_timestamp(cutoff)
    return parsed is not None and parsed_cutoff is not None and parsed <= parsed_cutoff


def _selection_public_response(row: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "flai-design-selection/v1",
        "selection_id": row["id"],
        "comparison_id": row["comparison_id"],
        "comparison_sha256": row["comparison_sha256"],
        "task_id": row["task_id"],
        "action": row["action"],
        "candidate_id": row["candidate_id"],
        "candidate_sha256": row["candidate_asset_sha256"],
        "task_decision_id": row["task_decision_id"],
        "selected_by": {
            "username": row["decided_by_username"],
            "display_name": row["decided_by_display_name"],
        },
        "reason_code": row["reason_code"],
        "comment": row["comment"],
        "created_at": row["created_at"],
        "task_status": "completed" if row["action"] == "approve" else "failed",
    }


def _release_public_response(row: dict[str, object]) -> dict[str, object] | None:
    summary = _canonical_json_object(row["summary_json"], row["summary_sha256"])
    if summary is None:
        return None
    return {
        "schema_version": "flai-design-release-request/v1",
        "release_request_id": row["id"],
        "selection_id": row["selection_id"],
        "comparison_id": row["comparison_id"],
        "state": "awaiting_release_approval",
        "summary": summary,
        "summary_sha256": row["summary_sha256"],
        "requested_by": {
            "username": row["requested_by_username"],
            "display_name": row["requested_by_display_name"],
        },
        "created_at": row["created_at"],
    }


def _release_decision_public_response(
    row: dict[str, object],
) -> dict[str, object] | None:
    package = None
    if row["action"] == "approve":
        package = _canonical_json_object(
            row["release_package_json"], row["release_package_sha256"]
        )
        if package is None:
            return None
        package = dict(package)
        package["release_package_sha256"] = row["release_package_sha256"]
    return {
        "schema_version": "flai-design-release-decision/v1",
        "release_request_id": row["release_request_id"],
        "state": (
            "release_approved" if row["action"] == "approve" else "release_rejected"
        ),
        "decision_id": row["id"],
        "action": row["action"],
        "summary_sha256": row["summary_sha256"],
        "decided_by": {
            "username": row["decided_by_username"],
            "display_name": row["decided_by_display_name"],
        },
        "reason_code": row["reason_code"],
        "comment": row["comment"],
        "created_at": row["created_at"],
        "release_package": package,
    }


def _publish_projection_at(
    events: list[dict[str, object]], cutoff: object
) -> tuple[str, dict[str, object] | None] | None:
    phase = "publish_ready"
    pending: dict[str, object] | None = None
    latest: dict[str, object] | None = None
    ordered = sorted(events, key=lambda row: int(row["event_rowid"]))
    for event in ordered:
        if not _not_after(event["created_at"], cutoff):
            continue
        event_type = str(event["event_type"])
        if event_type == "publish_intent":
            if phase != "publish_ready" or pending is not None:
                return None
            pending = event
            continue
        if event_type in {
            "publish_commit",
            "publish_abort",
            "publish_recovered_commit",
            "publish_manual_intervention",
        }:
            if pending is None or pending["attempt_id"] != event["attempt_id"]:
                return None
            pending = None
            if event_type == "publish_abort":
                phase = "publish_ready"
                latest = None
            elif event_type == "publish_manual_intervention":
                phase = "manual_intervention"
                latest = None
            else:
                phase = "published"
                latest = _publish_public_result(event, "publish")
            continue
        if event_type == "rollback_intent":
            if phase != "published" or pending is not None:
                return None
            pending = event
            continue
        if event_type in {
            "rollback_commit",
            "rollback_abort",
            "rollback_recovered_commit",
            "rollback_manual_intervention",
        }:
            if pending is None or pending["attempt_id"] != event["attempt_id"]:
                return None
            pending = None
            if event_type == "rollback_abort":
                phase = "published"
            elif event_type == "rollback_manual_intervention":
                phase = "manual_intervention"
                latest = None
            else:
                phase = "rolled_back"
                latest = _publish_public_result(event, "rollback")
            continue
        return None
    if pending is not None:
        return None
    return phase, latest


def _comparison_replay_workflow_integrity(
    response: dict[str, object],
    *,
    replay_created_at: object,
    comparison_id: str,
    selections: dict[str, dict[str, object]],
    releases: dict[str, dict[str, object]],
    decisions: dict[str, dict[str, object]],
    events: list[dict[str, object]],
) -> bool:
    workflow = response.get("workflow")
    if not isinstance(workflow, dict) or set(workflow) != {
        "selection",
        "release_request",
        "release_decision",
        "latest_publish",
    }:
        return False
    selection_value = workflow["selection"]
    if selection_value is None:
        return (
            response.get("phase") == "candidate_pending"
            and workflow["release_request"] is None
            and workflow["release_decision"] is None
            and workflow["latest_publish"] is None
        )
    if not isinstance(selection_value, dict):
        return False
    selection = selections.get(str(selection_value.get("selection_id")))
    if (
        selection is None
        or selection["comparison_id"] != comparison_id
        or not _not_after(selection["created_at"], replay_created_at)
        or selection_value != _selection_public_response(selection)
    ):
        return False
    if selection["action"] == "reject":
        return (
            response.get("phase") == "candidate_rejected"
            and workflow["release_request"] is None
            and workflow["release_decision"] is None
            and workflow["latest_publish"] is None
        )

    release_value = workflow["release_request"]
    if release_value is None:
        return (
            response.get("phase") == "candidate_approved"
            and workflow["release_decision"] is None
            and workflow["latest_publish"] is None
        )
    if not isinstance(release_value, dict):
        return False
    release = releases.get(str(release_value.get("release_request_id")))
    expected_release = _release_public_response(release) if release is not None else None
    if (
        release is None
        or release["selection_id"] != selection["id"]
        or not _not_after(release["created_at"], replay_created_at)
        or expected_release is None
        or release_value != expected_release
    ):
        return False

    decision_value = workflow["release_decision"]
    if decision_value is None:
        return response.get("phase") == "release_pending" and workflow["latest_publish"] is None
    if not isinstance(decision_value, dict):
        return False
    decision = decisions.get(str(decision_value.get("decision_id")))
    expected_decision = (
        _release_decision_public_response(decision) if decision is not None else None
    )
    if (
        decision is None
        or decision["release_request_id"] != release["id"]
        or not _not_after(decision["created_at"], replay_created_at)
        or expected_decision is None
        or decision_value != expected_decision
    ):
        return False
    if decision["action"] == "reject":
        return response.get("phase") == "release_rejected" and workflow["latest_publish"] is None

    publish_projection = _publish_projection_at(
        [event for event in events if event["release_request_id"] == release["id"]],
        replay_created_at,
    )
    return publish_projection is not None and (
        response.get("phase"), workflow["latest_publish"]
    ) == publish_projection


def _idempotency_integrity(conn: sqlite3.Connection) -> bool:
    comparisons = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_comparisons")
    }
    selections = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_candidate_selections")
    }
    releases = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_release_requests")
    }
    decisions = {
        str(row["id"]): row
        for row in _rows_as_dicts(conn, "SELECT * FROM design_release_decisions")
    }
    event_rows = _rows_as_dicts(
        conn, "SELECT rowid AS event_rowid, * FROM design_publish_events"
    )
    events = {str(row["id"]): row for row in event_rows}
    for replay in _rows_as_dicts(conn, "SELECT * FROM design_idempotency"):
        response = _canonical_json_object(
            replay["response_json"], replay["response_sha256"]
        )
        if response is None:
            return False
        operation = str(replay["operation"])
        resource_id = str(replay["resource_id"])
        expected: dict[str, object] | None = None
        expected_status = 200
        expected_actor: object | None = None
        if operation == "comparison_create":
            resource = comparisons.get(resource_id)
            if resource is None:
                return False
            evidence = _canonical_json_object(
                resource["comparison_json"], resource["comparison_sha256"]
            )
            core = (
                _public_comparison_core(evidence, resource["comparison_sha256"])
                if evidence is not None
                else None
            )
            if core is None:
                return False
            immutable_keys = set(core) - {"phase"}
            if (
                any(response.get(key) != core[key] for key in immutable_keys)
                or set(response) != set(core) | {"workflow"}
                or not _comparison_replay_workflow_integrity(
                    response,
                    replay_created_at=replay["created_at"],
                    comparison_id=resource_id,
                    selections=selections,
                    releases=releases,
                    decisions=decisions,
                    events=event_rows,
                )
            ):
                return False
            expected_status = 201
        elif operation == "candidate_selection":
            resource = selections.get(resource_id)
            if resource is None:
                return False
            expected = _selection_public_response(resource)
            expected_actor = resource["decided_by_username"]
        elif operation == "release_request_create":
            resource = releases.get(resource_id)
            if resource is None:
                return False
            expected = _release_public_response(resource)
            if expected is None:
                return False
            expected_status = 201
            expected_actor = resource["requested_by_username"]
        elif operation == "release_decision":
            resource = decisions.get(resource_id)
            if resource is None:
                return False
            expected = _release_decision_public_response(resource)
            if expected is None:
                return False
            expected_actor = resource["decided_by_username"]
        elif operation in {"publish", "rollback"}:
            resource = events.get(resource_id)
            if resource is None or resource["event_type"] not in {
                f"{operation}_commit",
                f"{operation}_recovered_commit",
            }:
                return False
            details = _canonical_json_object(
                resource["details_json"], resource["details_sha256"]
            )
            if details is None:
                return False
            expected = _publish_public_result(resource, operation)
            if details.get("public_result") != expected:
                return False
            intent = next(
                (
                    event
                    for event in events.values()
                    if event["attempt_id"] == resource["attempt_id"]
                    and event["event_type"] == f"{operation}_intent"
                ),
                None,
            )
            if intent is None:
                return False
            intent_details = _canonical_json_object(
                intent["details_json"], intent["details_sha256"]
            )
            if (
                intent_details is None
                or intent_details.get("request_id") != replay["request_id"]
                or intent_details.get("request_sha256")
                != replay["request_sha256"]
            ):
                return False
            expected_actor = resource["actor_username"]
        else:
            return False
        if (
            expected is not None
            and response != expected
            or replay["response_status"] != expected_status
            or expected_actor is not None
            and replay["actor_username"] != expected_actor
        ):
            return False
    return True


def _row_integrity(conn: sqlite3.Connection) -> bool:
    for table in DESIGN_PROMOTION_TABLES:
        quoted = _quoted(table)
        checks = [tuple(row) for row in conn.execute(f"PRAGMA integrity_check({quoted})")]
        if checks != [("ok",)]:
            return False
        if conn.execute(f"PRAGMA foreign_key_check({quoted})").fetchone() is not None:
            return False
        if conn.execute(f"SELECT 1 FROM {quoted} WHERE rowid <= 0 LIMIT 1").fetchone():
            return False
    hashed_columns = (
        ("design_comparisons", "comparison_json", "comparison_sha256"),
        ("design_release_requests", "summary_json", "summary_sha256"),
        ("design_idempotency", "response_json", "response_sha256"),
        ("design_publish_events", "details_json", "details_sha256"),
    )
    for table, blob_column, hash_column in hashed_columns:
        for blob, expected in conn.execute(
            f"SELECT {blob_column}, {hash_column} FROM {table}"
        ):
            if not _canonical_bytes_hash_ok(blob, expected):
                return False
    for blob, expected in conn.execute(
        "SELECT release_package_json, release_package_sha256 "
        "FROM design_release_decisions WHERE action='approve'"
    ):
        if not _canonical_bytes_hash_ok(blob, expected):
            return False
    return True


def _reference_integrity(conn: sqlite3.Connection) -> bool:
    bad_selection = conn.execute(
        """
        SELECT 1
        FROM design_candidate_selections AS selection
        JOIN design_comparisons AS comparison ON comparison.id=selection.comparison_id
        JOIN task_human_decisions AS decision ON decision.id=selection.task_decision_id
        WHERE selection.task_id<>comparison.task_id
           OR selection.comparison_sha256<>comparison.comparison_sha256
           OR selection.action<>decision.action
           OR selection.task_id<>decision.task_id
           OR selection.decided_by_username<>decision.reviewer_username
           OR (selection.action='approve' AND (
                selection.candidate_id<>comparison.candidate_id OR
                selection.candidate_asset_sha256<>comparison.candidate_asset_sha256
           ))
        LIMIT 1
        """
    ).fetchone()
    bad_release = conn.execute(
        """
        SELECT 1
        FROM design_release_requests AS release
        JOIN design_candidate_selections AS selection ON selection.id=release.selection_id
        JOIN design_comparisons AS comparison ON comparison.id=release.comparison_id
        WHERE selection.action<>'approve'
           OR selection.comparison_id<>release.comparison_id
           OR release.comparison_sha256<>comparison.comparison_sha256
           OR release.candidate_asset_sha256<>comparison.candidate_asset_sha256
           OR release.candidate_asset_file_id<>comparison.candidate_asset_file_id
        LIMIT 1
        """
    ).fetchone()
    bad_decision = conn.execute(
        """
        SELECT 1
        FROM design_release_decisions AS decision
        JOIN design_release_requests AS release ON release.id=decision.release_request_id
        WHERE decision.summary_sha256<>release.summary_sha256
        LIMIT 1
        """
    ).fetchone()
    bad_publish_event = conn.execute(
        """
        SELECT 1
        FROM design_publish_events AS event
        LEFT JOIN design_release_requests AS release
          ON release.id=event.release_request_id
        LEFT JOIN design_release_decisions AS decision
          ON decision.id=event.release_decision_id
        WHERE release.id IS NULL
           OR decision.id IS NULL
           OR decision.release_request_id IS NOT event.release_request_id
           OR decision.action <> 'approve'
           OR event.release_package_sha256 IS NOT decision.release_package_sha256
           OR event.target_id IS NOT release.target_id
           OR event.target_relative_path IS NOT release.target_relative_path
           OR (
                event.event_type LIKE 'publish_%'
                AND (
                    event.before_kind IS NOT release.target_preimage_kind
                    OR event.before_sha256 IS NOT release.target_preimage_sha256
                    OR event.after_kind <> 'present'
                    OR event.after_sha256 IS NOT release.candidate_asset_sha256
                )
           )
           OR (
                event.event_type LIKE 'rollback_%'
                AND (
                    event.before_kind <> 'present'
                    OR event.before_sha256 IS NOT release.candidate_asset_sha256
                    OR event.after_kind IS NOT release.target_preimage_kind
                    OR event.after_sha256 IS NOT release.target_preimage_sha256
                )
           )
           OR (
                release.target_preimage_kind = 'present'
                AND (
                    event.backup_relative_path IS NULL
                    OR event.backup_sha256 IS NOT release.target_preimage_sha256
                )
           )
           OR (
                release.target_preimage_kind = 'absent'
                AND (
                    event.backup_relative_path IS NOT NULL
                    OR event.backup_sha256 IS NOT NULL
                )
           )
        LIMIT 1
        """
    ).fetchone()
    return (
        bad_selection is None
        and bad_release is None
        and bad_decision is None
        and bad_publish_event is None
        and _comparison_evidence_integrity(conn)
        and _open_design_parent_evidence_integrity(conn)
        and _release_evidence_integrity(conn)
        and _publish_event_integrity(conn)
        and _idempotency_integrity(conn)
    )


def design_promotion_schema_witnesses(conn: sqlite3.Connection) -> dict[str, bool]:
    failed = {key: False for key in DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS}
    try:
        canonical = _canonical_schema()
        table_shapes = tuple(
            (name, _table_contract(conn, name)) for name, _ in canonical.tables
        ) == canonical.tables
        indexes = (
            tuple(
                (name, _index_contract(conn, name))
                for name, _ in canonical.indexes
            )
            == canonical.indexes
            and _managed_index_inventory(conn) == canonical.index_inventory
        )
        triggers = (
            tuple(
                (name, _trigger_contract(conn, name))
                for name, _ in canonical.triggers
            )
            == canonical.triggers
            and _managed_trigger_inventory(conn) == canonical.trigger_inventory
        )
        return {
            "table_shapes": table_shapes,
            "required_indexes": indexes,
            "required_triggers": triggers,
            "row_integrity": table_shapes and _row_integrity(conn),
            "reference_integrity": table_shapes and _reference_integrity(conn),
        }
    except (sqlite3.Error, TypeError, ValueError, RuntimeError):
        return failed


def assert_design_promotion_schema(conn: sqlite3.Connection) -> None:
    witnesses = design_promotion_schema_witnesses(conn)
    failed = [key for key, value in witnesses.items() if value is not True]
    if failed:
        raise RuntimeError(
            "P2.8 design promotion schema is not canonical: " + ", ".join(failed)
        )


def install_design_promotion_schema(conn: sqlite3.Connection) -> None:
    """Install once, or prove an existing installation is exactly canonical.

    Partial/tampered installations beside persisted P2.8 evidence are never
    repaired in place.  When all six exact ledgers are present, canonical, and
    empty, indexes/triggers may be resealed: there is no P2.8 row whose history
    could be falsely blessed, and parent-table rebuilds legitimately drop their
    cross-table triggers.
    """

    parent_columns = {
        "tasks": {"id", "agent_id", "status", "metadata_json"},
        "files": {"id", "task_id"},
        "task_human_decisions": {"id", "task_id", "action", "reviewer_username"},
    }
    for table, required in parent_columns.items():
        actual = {str(row[1]) for row in conn.execute(f"PRAGMA table_xinfo({_quoted(table)})")}
        if not required.issubset(actual):
            raise RuntimeError(f"P2.8 parent schema is incomplete: {table}")

    managed_objects_present = _managed_objects_present(conn)
    if managed_objects_present:
        witnesses = design_promotion_schema_witnesses(conn)
        if all(value is True for value in witnesses.values()):
            return
        if not _managed_ledgers_are_canonical_and_empty(conn):
            assert_design_promotion_schema(conn)

    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        if managed_objects_present:
            for trigger_name in DESIGN_PROMOTION_TRIGGER_NAMES:
                conn.execute(f"DROP TRIGGER IF EXISTS {_quoted(trigger_name)}")
            for index_name in DESIGN_PROMOTION_INDEX_NAMES:
                conn.execute(f"DROP INDEX IF EXISTS {_quoted(index_name)}")
            for statement in (*_INDEX_DDL, *_TRIGGER_DDL):
                conn.execute(statement)
        else:
            for statement in (*_TABLE_DDL, *_INDEX_DDL, *_TRIGGER_DDL):
                conn.execute(statement)
        if owns_transaction:
            conn.execute("COMMIT")
    except Exception:
        if owns_transaction and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    assert_design_promotion_schema(conn)
