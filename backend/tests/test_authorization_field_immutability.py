"""Authorization routing fields are immutable at the SQLite boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.app.storage import asset_candidates, db, repos, skill_packages

_NOW = "2026-08-03T00:00:00+00:00"


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "authorization-field-immutability.db"
    db.init_db(db_path)
    connection = db.get_conn(db_path)
    yield connection
    connection.close()


def _seed_authorization_records(conn: sqlite3.Connection) -> None:
    repos.create_conversation(
        conn,
        conversation_id="conv_authorization_fields",
        agent_id="guide_agent",
        created_by="Alice Engineer",
        created_by_username="alice",
    )
    repos.create_task(
        conn,
        task_id="task_authorization_fields",
        agent_id="report_agent",
        agent_version="1.0.0",
        name="authorization field witness",
        created_by="Alice Engineer",
        created_by_username="alice",
        conversation_id="conv_authorization_fields",
        origin="user",
    )
    asset_candidates.insert_candidate(
        conn,
        {
            "id": "asset_candidate_authorization_fields",
            "schema_version": "asset_candidate.v1",
            "source_task_id": "task_authorization_fields",
            "source_conversation_id": "conv_authorization_fields",
            "revision": 1,
            "supersedes_candidate_digest": None,
            "bundle_digest": f"sha256:{'1' * 64}",
            "lineage_digest": f"sha256:{'2' * 64}",
            "candidate_digest": f"sha256:{'3' * 64}",
            "bundle_json": "{}",
            "lineage_json": "{}",
            "proposal_provenance_json": "{}",
            "state": "awaiting_human_review",
            "data_classification": "internal",
            "initiated_by_user_id": 7,
            "initiated_by_username": "alice",
            "created_at": _NOW,
            "updated_at": _NOW,
        },
    )
    skill_packages.insert_package(
        conn,
        {
            "id": "skill_package_authorization_fields",
            "schema_version": "skill_package_revision.v1",
            "name": "authorization-field-witness",
            "version": "0.1.0",
            "package_digest": f"sha256:{'4' * 64}",
            "state": "pending_review",
            "source_candidate_id": "asset_candidate_authorization_fields",
            "source_candidate_digest": f"sha256:{'3' * 64}",
            "source_bundle_digest": f"sha256:{'1' * 64}",
            "source_skill_digest": f"sha256:{'5' * 64}",
            "source_acceptance_event_digest": f"sha256:{'6' * 64}",
            "source_task_id": "task_authorization_fields",
            "source_agent_id": "report_agent",
            "owner_username": "alice",
            "storage_relpath": "quarantine/skill_package_authorization_fields",
            "file_manifest_json": "[]",
            "created_at": _NOW,
            "updated_at": _NOW,
        },
    )


@pytest.mark.parametrize(
    ("table", "column", "replacement", "expected", "message"),
    [
        ("tasks", "origin", "eval", "user", "tasks.origin is immutable"),
        (
            "asset_candidates",
            "initiated_by_user_id",
            8,
            7,
            "asset_candidates initiator is immutable",
        ),
        (
            "asset_candidates",
            "initiated_by_username",
            "bob",
            "alice",
            "asset_candidates initiator is immutable",
        ),
        (
            "skill_packages",
            "owner_username",
            "bob",
            "alice",
            "skill_packages.owner_username is immutable",
        ),
    ],
)
def test_authorization_routing_fields_reject_direct_reassignment(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    replacement: object,
    expected: object,
    message: str,
) -> None:
    _seed_authorization_records(conn)
    row_id = {
        "tasks": "task_authorization_fields",
        "asset_candidates": "asset_candidate_authorization_fields",
        "skill_packages": "skill_package_authorization_fields",
    }[table]

    with pytest.raises(sqlite3.IntegrityError, match=message.replace(".", r"\.")):
        conn.execute(
            f"UPDATE {table} SET {column} = ? WHERE id = ?",
            (replacement, row_id),
        )

    persisted = conn.execute(
        f"SELECT {column} FROM {table} WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert persisted is not None
    assert persisted[column] == expected


def test_authorization_guards_preserve_legitimate_state_transitions(
    conn: sqlite3.Connection,
) -> None:
    _seed_authorization_records(conn)

    task = repos.set_task_status(conn, "task_authorization_fields", "queued")
    candidate_updated = asset_candidates.cas_decision(
        conn,
        candidate_id="asset_candidate_authorization_fields",
        expected_candidate_digest=f"sha256:{'3' * 64}",
        event_id="asset_candidate_event_authorization_fields",
        state="accepted",
        updated_at="2026-08-03T00:01:00+00:00",
    )
    package_updated = skill_packages.cas_decision(
        conn,
        package_id="skill_package_authorization_fields",
        expected_package_digest=f"sha256:{'4' * 64}",
        event_id="skill_package_event_authorization_fields",
        state="approved",
        updated_at="2026-08-03T00:02:00+00:00",
    )

    assert task["status"] == "queued"
    assert task["origin"] == "user"
    assert candidate_updated == 1
    assert package_updated == 1
    assert asset_candidates.get_by_id(conn, "asset_candidate_authorization_fields")[
        "initiated_by_username"
    ] == "alice"
    assert skill_packages.get_by_id(conn, "skill_package_authorization_fields")[
        "owner_username"
    ] == "alice"


def test_existing_database_reinstalls_authorization_field_guards(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "existing-authorization-fields.db"
    db.init_db(db_path)
    existing = db.get_conn(db_path)
    try:
        _seed_authorization_records(existing)
        for trigger_name in (
            "trg_tasks_origin_immutable",
            "trg_asset_candidates_initiator_immutable",
            "trg_skill_packages_owner_username_immutable",
        ):
            existing.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    finally:
        existing.close()

    db.init_db(db_path)
    migrated = db.get_conn(db_path)
    try:
        updates = (
            (
                "UPDATE tasks SET origin = 'eval' WHERE id = ?",
                "task_authorization_fields",
                "tasks.origin is immutable",
            ),
            (
                "UPDATE asset_candidates SET initiated_by_username = 'bob' WHERE id = ?",
                "asset_candidate_authorization_fields",
                "asset_candidates initiator is immutable",
            ),
            (
                "UPDATE skill_packages SET owner_username = 'bob' WHERE id = ?",
                "skill_package_authorization_fields",
                "skill_packages.owner_username is immutable",
            ),
        )
        for statement, row_id, message in updates:
            with pytest.raises(
                sqlite3.IntegrityError, match=message.replace(".", r"\.")
            ):
                migrated.execute(statement, (row_id,))
    finally:
        migrated.close()
