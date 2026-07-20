from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.storage.design_promotion_schema import (
    DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS,
    assert_design_promotion_schema,
    design_promotion_schema_witnesses,
    install_design_promotion_schema,
)
from scripts import deploy_selfcheck


_CANONICAL_EMPTY_OBJECT = b"{}"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seed_completed_publish_attempt(
    conn: sqlite3.Connection, *, include_publish: bool = True
) -> dict[str, str]:
    """Persist one valid public-service-shaped intent/commit chain."""

    candidate_sha = "a" * 64
    manifest_sha = "b" * 64
    request_sha = "c" * 64
    target_id = "open_design_task_review_summary_v1"
    target_path = "frontend/src/assets/open-design/task-review-summary.png"
    comparison_id = "comparison_" + "1" * 32
    selection_id = "selection_" + "2" * 32
    task_decision_id = "decision_" + "3" * 32
    release_id = "release_" + "4" * 32
    release_decision_id = "release_decision_" + "5" * 32
    attempt_id = "attempt_" + "6" * 32
    intent_id = "promotion_event_" + "7" * 32
    terminal_id = "promotion_event_" + "8" * 32
    request_id = "req_" + "9" * 32
    intent_at = "2026-07-20T00:00:00+00:00"
    terminal_at = "2026-07-20T00:00:01+00:00"
    candidate_id = "odc-" + "d" * 32
    comparison_evidence = {
        "schema_version": "flai-design-comparison/v1",
        "comparison_id": comparison_id,
        "task_id": "task_design",
        "candidate": {
            "candidate_id": candidate_id,
            "asset_slot": "task_review_summary",
            "asset_file_id": "file_design_candidate",
            "asset_sha256": candidate_sha,
            "media_type": "image/png",
            "execution_trust": "untrusted_generated",
        },
        "target": {
            "target_id": target_id,
            "relative_path": target_path,
            "preimage": {"kind": "absent"},
        },
        "phase": "candidate_pending",
        "provenance": {"mock": False},
        "frames": [],
        "created_by": {"username": "reviewer", "display_name": "Reviewer"},
        "created_at": intent_at,
    }
    comparison_bytes = _canonical_json(comparison_evidence)
    comparison_sha = hashlib.sha256(comparison_bytes).hexdigest()

    repos.create_task(
        conn,
        task_id="task_design",
        agent_id="open_design_daemon_candidate_agent",
        agent_version="0.1.0",
        name="Design candidate",
        created_by="Reviewer",
        created_by_username="reviewer",
        metadata={
            "review_contract": "open-design-candidate/v1",
            "generator_kind": "open_design_daemon",
            "candidate_manifest_sha256": manifest_sha,
        },
    )
    repos.create_file(
        conn,
        file_id="file_design_candidate",
        task_id="task_design",
        kind="output",
        filename="candidate.png",
        path="task_runs/task_design/candidate.png",
        size_bytes=16,
        sha256=candidate_sha,
        classification="internal",
    )
    repos.set_task_outputs(conn, "task_design", ["file_design_candidate"])
    repos.set_task_data_classification(conn, "task_design", "internal")
    for status in ("queued", "validating", "running", "waiting_review"):
        repos.set_task_status(conn, "task_design", status)
    conn.execute(
        """
        INSERT INTO design_comparisons (
            id, task_id, candidate_id, asset_slot, candidate_asset_file_id,
            candidate_asset_sha256, candidate_manifest_sha256,
            comparison_json, comparison_sha256, target_id,
            target_relative_path, target_preimage_kind,
            target_preimage_sha256, created_by_username,
            created_by_display_name, created_at
        ) VALUES (?, 'task_design', ?, 'task_review_summary',
                  'file_design_candidate', ?, ?, ?, ?, ?, ?, 'absent', NULL,
                  'reviewer', 'Reviewer', ?)
        """,
        (
            comparison_id,
            candidate_id,
            candidate_sha,
            manifest_sha,
            sqlite3.Binary(comparison_bytes),
            comparison_sha,
            target_id,
            target_path,
            intent_at,
        ),
    )

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            INSERT INTO design_candidate_selections (
                id, comparison_id, task_id, action, candidate_id,
                candidate_asset_sha256, comparison_sha256, task_decision_id,
                decided_by_username, decided_by_display_name, reason_code,
                comment, created_at
            ) VALUES (?, ?, 'task_design', 'approve', ?, ?, ?, ?,
                      'reviewer', 'Reviewer', NULL, NULL, ?)
            """,
            (
                selection_id,
                comparison_id,
                candidate_id,
                candidate_sha,
                comparison_sha,
                task_decision_id,
                intent_at,
            ),
        )
        repos.apply_human_review_in_transaction(
            conn,
            "task_design",
            decision_id=task_decision_id,
            action="approve",
            reviewer_display_name="Reviewer",
            reviewer_username="reviewer",
            reason_code=None,
            comment=None,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    candidate_decision = conn.execute(
        "SELECT created_at FROM task_human_decisions WHERE id=?",
        (task_decision_id,),
    ).fetchone()
    assert candidate_decision is not None
    candidate_decision_at = str(candidate_decision[0])
    release_summary = {
        "candidate": {
            "task_id": "task_design",
            "candidate_id": candidate_id,
            "asset_slot": "task_review_summary",
            "asset_sha256": candidate_sha,
            "comparison_sha256": comparison_sha,
            "candidate_approval": {
                "decision_id": task_decision_id,
                "username": "reviewer",
                "display_name": "Reviewer",
                "at": candidate_decision_at,
            },
        },
        "target": {
            "target_id": target_id,
            "relative_path": target_path,
            "preimage": {"kind": "absent"},
            "postimage_sha256": candidate_sha,
        },
    }
    summary_bytes = _canonical_json(release_summary)
    summary_sha = hashlib.sha256(summary_bytes).hexdigest()

    conn.execute(
        """
        INSERT INTO design_release_requests (
            id, selection_id, comparison_id, candidate_asset_file_id,
            candidate_asset_sha256, comparison_sha256, target_id,
            target_relative_path, target_preimage_kind,
            target_preimage_sha256, summary_json, summary_sha256,
            requested_by_username, requested_by_display_name, created_at
        ) VALUES (?, ?, ?, 'file_design_candidate', ?, ?, ?, ?, 'absent',
                  NULL, ?, ?, 'requester', 'Requester', ?)
        """,
        (
            release_id,
            selection_id,
            comparison_id,
            candidate_sha,
            comparison_sha,
            target_id,
            target_path,
            sqlite3.Binary(summary_bytes),
            summary_sha,
            candidate_decision_at,
        ),
    )
    release_approval = {
        "decision_id": release_decision_id,
        "username": "release_reviewer",
        "display_name": "Release Reviewer",
        "at": candidate_decision_at,
    }
    unsigned_package = {
        "schema_version": "flai-design-release-package/v1",
        "summary": release_summary,
        "release_approval": release_approval,
    }
    package_bytes = _canonical_json(unsigned_package)
    package_sha = hashlib.sha256(package_bytes).hexdigest()
    conn.execute(
        """
        INSERT INTO design_release_decisions (
            id, release_request_id, action, summary_sha256, reason_code,
            comment, decided_by_username, decided_by_display_name,
            release_package_json, release_package_sha256, created_at
        ) VALUES (?, ?, 'approve', ?, NULL, NULL, 'release_reviewer',
                  'Release Reviewer', ?, ?, ?)
        """,
        (
            release_decision_id,
            release_id,
            summary_sha,
            sqlite3.Binary(package_bytes),
            package_sha,
            candidate_decision_at,
        ),
    )

    ids = {
        "comparison_id": comparison_id,
        "selection_id": selection_id,
        "release_id": release_id,
        "release_decision_id": release_decision_id,
        "attempt_id": attempt_id,
        "intent_id": intent_id,
        "terminal_id": terminal_id,
    }
    if not include_publish:
        assert all(
            value is True
            for value in design_promotion_schema_witnesses(conn).values()
        )
        return ids

    intent_details = {
        "schema_version": "flai-design-publish-intent/v1",
        "operation": "publish",
        "request_id": request_id,
        "request_sha256": request_sha,
        "candidate_asset_file_id": "file_design_candidate",
        "candidate_asset_sha256": candidate_sha,
        "expected_target": {"kind": "absent"},
    }
    public_result = {
        "schema_version": "flai-design-publish-result/v1",
        "release_request_id": release_id,
        "state": "published",
        "publish_event_id": terminal_id,
        "target_id": target_id,
        "before_sha256": None,
        "after_sha256": candidate_sha,
        "backup_sha256": None,
        "release_package_sha256": package_sha,
        "published_by": {
            "username": "publisher",
            "display_name": "Publisher",
        },
        "published_at": terminal_at,
    }
    terminal_details = {
        "schema_version": "flai-design-publish-commit/v1",
        "operation": "publish",
        "outcome": "commit",
        "public_result": public_result,
    }

    def insert_event(
        event_id: str,
        event_type: str,
        details: dict[str, object],
        created_at: str,
    ) -> None:
        raw_details = _canonical_json(details)
        conn.execute(
            """
            INSERT INTO design_publish_events (
                id, attempt_id, release_request_id, release_decision_id,
                event_type, actor_username, actor_display_name,
                release_package_sha256, target_id, target_relative_path,
                before_kind, before_sha256, after_kind, after_sha256,
                backup_relative_path, backup_sha256, details_json,
                details_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, 'publisher', 'Publisher', ?, ?, ?,
                      'absent', NULL, 'present', ?, NULL, NULL, ?, ?, ?)
            """,
            (
                event_id,
                attempt_id,
                release_id,
                release_decision_id,
                event_type,
                package_sha,
                target_id,
                target_path,
                candidate_sha,
                sqlite3.Binary(raw_details),
                hashlib.sha256(raw_details).hexdigest(),
                created_at,
            ),
        )

    insert_event(intent_id, "publish_intent", intent_details, intent_at)
    insert_event(terminal_id, "publish_commit", terminal_details, terminal_at)
    response_bytes = _canonical_json(public_result)
    conn.execute(
        """
        INSERT INTO design_idempotency (
            id, operation, actor_username, request_id, request_sha256,
            response_status, response_json, response_sha256, resource_id,
            created_at
        ) VALUES (?, 'publish', 'publisher', ?, ?, 200, ?, ?, ?, ?)
        """,
        (
            "idempotency_" + "e" * 32,
            request_id,
            request_sha,
            sqlite3.Binary(response_bytes),
            hashlib.sha256(response_bytes).hexdigest(),
            terminal_id,
            terminal_at,
        ),
    )
    assert all(
        value is True for value in design_promotion_schema_witnesses(conn).values()
    )
    return ids


def _waiting_design_task(
    conn: sqlite3.Connection,
    task_id: str = "task_design",
    *,
    include_metadata_marker: bool = True,
) -> None:
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id="open_design_daemon_candidate_agent",
        agent_version="0.1.0",
        name="Design candidate",
        created_by="Reviewer",
        created_by_username="reviewer",
        metadata=(
            {
                "review_contract": "open-design-candidate/v1",
                "generator_kind": "open_design_daemon",
                "candidate_manifest_sha256": "a" * 64,
            }
            if include_metadata_marker
            else {}
        ),
    )
    repos.set_task_status(conn, task_id, "queued")
    repos.set_task_status(conn, task_id, "validating")
    repos.set_task_status(conn, task_id, "running")
    repos.set_task_status(conn, task_id, "waiting_review")


def test_schema_install_has_exact_witnesses_and_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        # Startup owns the canonical install; feature code must never depend on
        # a later lazy migration that could race requests or hide partial DDL.
        assert design_promotion_schema_witnesses(conn) == {
            key: True for key in DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
        }
        install_design_promotion_schema(conn)
        install_design_promotion_schema(conn)
        assert design_promotion_schema_witnesses(conn) == {
            key: True for key in DESIGN_PROMOTION_SCHEMA_WITNESS_KEYS
        }
        assert_design_promotion_schema(conn)
    finally:
        conn.close()


def test_empty_ledgers_reseal_cross_table_trigger_after_parent_rebuild(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute("DROP TRIGGER trg_p28_design_decision_requires_selection")

        install_design_promotion_schema(conn)

        assert design_promotion_schema_witnesses(conn)["required_triggers"] is True
        _waiting_design_task(conn)
        with pytest.raises(sqlite3.IntegrityError, match="design selection"):
            conn.execute(
                """
                INSERT INTO task_human_decisions
                    (id, task_id, action, reviewer_username,
                     reviewer_display_name, schema_version, created_at)
                VALUES (?, ?, 'approve', 'reviewer', 'Reviewer', 1, ?)
                """,
                (
                    "decision_" + "0" * 32,
                    "task_design",
                    "2026-07-20T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


def test_nonempty_promotion_ledger_refuses_missing_trigger_repair(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO design_idempotency (
                id, operation, actor_username, request_id, request_sha256,
                response_status, response_json, response_sha256,
                resource_id, created_at
            ) VALUES (?, 'comparison_create', 'reviewer', ?, ?, 200, ?, ?, ?, ?)
            """,
            (
                "idempotency_" + "1" * 32,
                "req_" + "2" * 32,
                "3" * 64,
                sqlite3.Binary(b"{}"),
                hashlib.sha256(b"{}").hexdigest(),
                "comparison_evidence",
                "2026-07-20T00:00:00+00:00",
            ),
        )
        conn.execute("DROP TRIGGER trg_p28_design_decision_requires_selection")

        with pytest.raises(RuntimeError, match="required_triggers"):
            install_design_promotion_schema(conn)

        assert design_promotion_schema_witnesses(conn)["required_triggers"] is False
    finally:
        conn.close()


@pytest.mark.parametrize("tamper", ("remove_intent", "corrupt_intent_details"))
def test_publish_terminal_requires_its_exact_persisted_intent(
    tmp_path, tamper: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        ids = _seed_completed_publish_attempt(conn)
        if tamper == "remove_intent":
            trigger_name = "trg_design_publish_events_no_delete"
            trigger_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger_name,),
            ).fetchone()[0]
            conn.execute(f'DROP TRIGGER "{trigger_name}"')
            conn.execute(
                "DELETE FROM design_publish_events WHERE id=?", (ids["intent_id"],)
            )
        else:
            trigger_name = "trg_design_publish_events_no_update"
            trigger_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger_name,),
            ).fetchone()[0]
            corrupted = {
                "schema_version": "flai-design-publish-intent/v1",
                "operation": "rollback",
                "request_id": "req_" + "9" * 32,
                "request_sha256": "c" * 64,
                "candidate_asset_file_id": "file_design_candidate",
                "candidate_asset_sha256": "a" * 64,
                "expected_target": {"kind": "absent"},
            }
            corrupted_bytes = _canonical_json(corrupted)
            conn.execute(f'DROP TRIGGER "{trigger_name}"')
            conn.execute(
                "UPDATE design_publish_events SET details_json=?, details_sha256=? "
                "WHERE id=?",
                (
                    sqlite3.Binary(corrupted_bytes),
                    hashlib.sha256(corrupted_bytes).hexdigest(),
                    ids["intent_id"],
                ),
            )
        conn.execute(trigger_sql)

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["row_integrity"] is True
        assert witnesses["reference_integrity"] is False
        with pytest.raises(RuntimeError, match="reference_integrity"):
            install_design_promotion_schema(conn)
        assert deploy_selfcheck.check_design_promotion_schema(conn).ok is False
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("object_name", "ddl", "witness_key"),
    (
        (
            "idx_p28_unexpected_operation",
            "CREATE INDEX idx_p28_unexpected_operation "
            "ON design_idempotency(operation)",
            "required_indexes",
        ),
        (
            "idx_p28_unexpected_operation_uppercase",
            "CREATE INDEX idx_p28_unexpected_operation_uppercase "
            "ON DESIGN_IDEMPOTENCY(operation)",
            "required_indexes",
        ),
        (
            "trg_p28_unexpected_insert",
            "CREATE TRIGGER trg_p28_unexpected_insert "
            "AFTER INSERT ON design_idempotency BEGIN SELECT 1; END",
            "required_triggers",
        ),
        (
            "trg_p28_unexpected_insert_uppercase",
            "CREATE TRIGGER trg_p28_unexpected_insert_uppercase "
            "AFTER INSERT ON DESIGN_IDEMPOTENCY BEGIN SELECT 1; END",
            "required_triggers",
        ),
    ),
)
def test_unknown_object_on_managed_promotion_table_fails_closed(
    tmp_path, object_name: str, ddl: str, witness_key: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO design_idempotency (
                id, operation, actor_username, request_id, request_sha256,
                response_status, response_json, response_sha256,
                resource_id, created_at
            ) VALUES (?, 'comparison_create', 'reviewer', ?, ?, 200, ?, ?, ?, ?)
            """,
            (
                "idempotency_" + "1" * 32,
                "req_" + "2" * 32,
                "3" * 64,
                sqlite3.Binary(_CANONICAL_EMPTY_OBJECT),
                hashlib.sha256(_CANONICAL_EMPTY_OBJECT).hexdigest(),
                "comparison_evidence",
                "2026-07-20T00:00:00+00:00",
            ),
        )
        conn.execute(ddl)

        assert design_promotion_schema_witnesses(conn)[witness_key] is False
        with pytest.raises(RuntimeError, match=witness_key):
            install_design_promotion_schema(conn)
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name=?", (object_name,)
        ).fetchone() is not None
        assert conn.execute(
            "SELECT COUNT(*) FROM design_idempotency"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_empty_ledgers_with_open_design_parent_decision_refuse_reseal(
    tmp_path,
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _waiting_design_task(conn)
        trigger_name = "trg_p28_design_decision_requires_selection"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            """
            INSERT INTO task_human_decisions (
                id, task_id, paired_advice_id, action, reason_code, comment,
                reviewer_username, reviewer_display_name, schema_version,
                created_at
            ) VALUES (?, 'task_design', NULL, 'approve', NULL, NULL,
                      'reviewer', 'Reviewer', 1, ?)
            """,
            (
                "decision_" + "f" * 32,
                "2026-07-20T00:00:00+00:00",
            ),
        )
        conn.execute(trigger_sql)

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["required_triggers"] is True
        assert witnesses["reference_integrity"] is False
        with pytest.raises(RuntimeError, match="reference_integrity"):
            install_design_promotion_schema(conn)
        assert conn.execute(
            "SELECT COUNT(*) FROM task_human_decisions WHERE task_id='task_design'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM design_candidate_selections"
        ).fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("terminal_status", ("completed", "failed", "cancelled"))
def test_empty_ledgers_with_terminal_open_design_task_refuse_reseal(
    tmp_path, terminal_status: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        repos.create_task(
            conn,
            task_id="task_terminal_design",
            agent_id="open_design_daemon_candidate_agent",
            agent_version="0.1.0",
            name="Historical design candidate",
            created_by="Reviewer",
            created_by_username="reviewer",
            metadata={"review_contract": "open-design-candidate/v1"},
        )
        conn.execute(
            "UPDATE tasks SET status=?, updated_at=?, finished_at=? "
            "WHERE id='task_terminal_design'",
            (
                terminal_status,
                "2026-07-20T00:00:00+00:00",
                "2026-07-20T00:00:00+00:00",
            ),
        )
        trigger_name = "trg_design_comparisons_no_update"
        conn.execute(f'DROP TRIGGER "{trigger_name}"')

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["required_triggers"] is False
        assert witnesses["reference_integrity"] is False
        with pytest.raises(RuntimeError, match="required_triggers"):
            install_design_promotion_schema(conn)
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        ).fetchone() is None
        assert conn.execute(
            "SELECT status FROM tasks WHERE id='task_terminal_design'"
        ).fetchone()[0] == terminal_status
        assert conn.execute(
            "SELECT COUNT(*) FROM design_candidate_selections"
        ).fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("operation", "resource_id", "response_status"),
    (
        ("comparison_create", "comparison_" + "a" * 32, 201),
        ("candidate_selection", "selection_" + "b" * 32, 200),
        ("release_request_create", "release_" + "c" * 32, 201),
        ("release_decision", "release_decision_" + "d" * 32, 200),
        ("publish", "promotion_event_" + "e" * 32, 200),
        ("rollback", "promotion_event_" + "f" * 32, 200),
    ),
)
def test_idempotent_replay_requires_operation_resource_and_exact_response(
    tmp_path, operation: str, resource_id: str, response_status: int
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO design_idempotency (
                id, operation, actor_username, request_id, request_sha256,
                response_status, response_json, response_sha256, resource_id,
                created_at
            ) VALUES (?, ?, 'reviewer', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "idempotency_" + "1" * 32,
                operation,
                "req_" + "2" * 32,
                "3" * 64,
                response_status,
                sqlite3.Binary(_CANONICAL_EMPTY_OBJECT),
                hashlib.sha256(_CANONICAL_EMPTY_OBJECT).hexdigest(),
                resource_id,
                "2026-07-20T00:00:00+00:00",
            ),
        )

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["row_integrity"] is True
        assert witnesses["reference_integrity"] is False
        with pytest.raises(RuntimeError, match="reference_integrity"):
            install_design_promotion_schema(conn)
        assert deploy_selfcheck.check_design_promotion_schema(conn).ok is False
    finally:
        conn.close()


def test_idempotent_publish_response_must_match_its_terminal_event(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        _seed_completed_publish_attempt(conn)
        trigger_name = "trg_design_idempotency_no_update"
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{trigger_name}"')
        conn.execute(
            "UPDATE design_idempotency SET response_json=?, response_sha256=? "
            "WHERE operation='publish'",
            (
                sqlite3.Binary(_CANONICAL_EMPTY_OBJECT),
                hashlib.sha256(_CANONICAL_EMPTY_OBJECT).hexdigest(),
            ),
        )
        conn.execute(trigger_sql)

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["row_integrity"] is True
        assert witnesses["reference_integrity"] is False
    finally:
        conn.close()


@pytest.mark.parametrize("tamper", ("phase_only", "invented_selection"))
def test_comparison_create_replay_cannot_invent_later_phase_or_workflow(
    tmp_path, tamper: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        ids = _seed_completed_publish_attempt(conn, include_publish=False)
        comparison_blob, comparison_sha = conn.execute(
            "SELECT comparison_json, comparison_sha256 FROM design_comparisons WHERE id=?",
            (ids["comparison_id"],),
        ).fetchone()
        response = json.loads(bytes(comparison_blob).decode("utf-8"))
        response["comparison_sha256"] = comparison_sha
        response["phase"] = "published"
        response["workflow"] = {
            "selection": ({"invented": True} if tamper == "invented_selection" else None),
            "release_request": None,
            "release_decision": None,
            "latest_publish": None,
        }
        response_bytes = _canonical_json(response)
        conn.execute(
            """
            INSERT INTO design_idempotency (
                id, operation, actor_username, request_id, request_sha256,
                response_status, response_json, response_sha256, resource_id,
                created_at
            ) VALUES (?, 'comparison_create', 'reviewer', ?, ?, 201, ?, ?, ?, ?)
            """,
            (
                "idempotency_" + "a" * 32,
                "req_" + "b" * 32,
                "c" * 64,
                sqlite3.Binary(response_bytes),
                hashlib.sha256(response_bytes).hexdigest(),
                ids["comparison_id"],
                "2026-07-20T00:00:02+00:00",
            ),
        )

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["row_integrity"] is True
        assert witnesses["reference_integrity"] is False
    finally:
        conn.close()


@pytest.mark.parametrize("tamper", ("summary_and_package", "release_target"))
def test_release_evidence_is_exactly_bound_to_selection_and_comparison(
    tmp_path, tamper: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        ids = _seed_completed_publish_attempt(conn, include_publish=False)
        release_trigger = "trg_design_release_requests_no_update"
        release_trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (release_trigger,),
        ).fetchone()[0]
        conn.execute(f'DROP TRIGGER "{release_trigger}"')
        if tamper == "summary_and_package":
            decision_trigger = "trg_design_release_decisions_no_update"
            decision_trigger_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (decision_trigger,),
            ).fetchone()[0]
            conn.execute(f'DROP TRIGGER "{decision_trigger}"')
            empty_sha = hashlib.sha256(_CANONICAL_EMPTY_OBJECT).hexdigest()
            conn.execute(
                "UPDATE design_release_requests "
                "SET summary_json=?, summary_sha256=? WHERE id=?",
                (
                    sqlite3.Binary(_CANONICAL_EMPTY_OBJECT),
                    empty_sha,
                    ids["release_id"],
                ),
            )
            conn.execute(
                "UPDATE design_release_decisions SET summary_sha256=?, "
                "release_package_json=?, release_package_sha256=? WHERE id=?",
                (
                    empty_sha,
                    sqlite3.Binary(_CANONICAL_EMPTY_OBJECT),
                    empty_sha,
                    ids["release_decision_id"],
                ),
            )
            conn.execute(decision_trigger_sql)
        else:
            conn.execute(
                "UPDATE design_release_requests SET target_id='drifted_target', "
                "target_relative_path='drifted/target.png' WHERE id=?",
                (ids["release_id"],),
            )
        conn.execute(release_trigger_sql)

        witnesses = design_promotion_schema_witnesses(conn)
        assert witnesses["row_integrity"] is True
        assert witnesses["reference_integrity"] is False
    finally:
        conn.close()


def test_generic_human_decision_cannot_bypass_design_selection(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        install_design_promotion_schema(conn)
        _waiting_design_task(conn)
        with pytest.raises(sqlite3.IntegrityError, match="design selection"):
            conn.execute(
                """
                INSERT INTO task_human_decisions
                    (id, task_id, action, reviewer_username,
                     reviewer_display_name, schema_version, created_at)
                VALUES (?, ?, 'approve', ?, ?, 1, ?)
                """,
                (
                    "decision_" + "1" * 32,
                    "task_design",
                    "reviewer",
                    "Reviewer",
                    "2026-07-20T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


def test_candidate_agent_cannot_fail_open_when_metadata_marker_is_missing(tmp_path) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        install_design_promotion_schema(conn)
        _waiting_design_task(conn, include_metadata_marker=False)
        with pytest.raises(sqlite3.IntegrityError, match="design selection"):
            conn.execute(
                """
                INSERT INTO task_human_decisions
                    (id, task_id, action, reviewer_username,
                     reviewer_display_name, schema_version, created_at)
                VALUES (?, ?, 'approve', ?, ?, 1, ?)
                """,
                (
                    "decision_" + "2" * 32,
                    "task_design",
                    "reviewer",
                    "Reviewer",
                    "2026-07-20T00:00:00+00:00",
                ),
            )
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("record_id", "request_id"),
    (
        ("idempotency_" + "a" * 31 + "z", "req_" + "b" * 32),
        ("idempotency_" + "a" * 32, "req_" + "b" * 31 + "z"),
    ),
)
def test_schema_rejects_nonhex_poison_in_exact_ids(
    tmp_path, record_id: str, request_id: str
) -> None:
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        install_design_promotion_schema(conn)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint"):
            conn.execute(
                """
                INSERT INTO design_idempotency
                    (id, operation, actor_username, request_id, request_sha256,
                     response_status, response_json, response_sha256,
                     resource_id, created_at)
                VALUES (?, 'comparison_create', 'reviewer', ?, ?, 200, ?, ?,
                        'comparison_test', '2026-07-20T00:00:00+00:00')
                """,
                (
                    record_id,
                    request_id,
                    "c" * 64,
                    sqlite3.Binary(b"{}"),
                    "d" * 64,
                ),
            )
    finally:
        conn.close()


def test_publish_event_insert_requires_exact_release_decision_and_target_binding(
    tmp_path,
) -> None:
    """The append ledger must reject a plausible row with a wrong target immediately."""
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    conn = get_conn(db_path)
    try:
        # Minimal parent facts are deliberately inserted with deferred FKs off
        # the hot service path; this test targets the cross-ledger insert guard.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            """
            INSERT INTO design_publish_events (
                id, attempt_id, release_request_id, release_decision_id,
                event_type, actor_username, actor_display_name,
                release_package_sha256, target_id, target_relative_path,
                before_kind, before_sha256, after_kind, after_sha256,
                backup_relative_path, backup_sha256, details_json,
                details_sha256, created_at
            ) VALUES (?, ?, ?, ?, 'publish_intent', 'publisher', 'Publisher',
                      ?, 'wrong_target',
                      'frontend/src/assets/open-design/task-review-summary.png',
                      'absent', NULL, 'present', ?, NULL, NULL, ?, ?, ?)
            """,
            (
                "promotion_event_" + "1" * 32,
                "attempt_" + "2" * 32,
                "release_" + "3" * 32,
                "release_decision_" + "4" * 32,
                "5" * 64,
                "6" * 64,
                sqlite3.Binary(b"{}"),
                hashlib.sha256(b"{}").hexdigest(),
                "2026-07-20T00:00:00+00:00",
            ),
        )
    except sqlite3.IntegrityError as exc:
        assert "release binding" in str(exc)
    else:
        pytest.fail("cross-ledger publish event was accepted")
    finally:
        conn.close()
