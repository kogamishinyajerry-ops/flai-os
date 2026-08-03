"""Owner identity columns are insert-once evidence at the SQLite boundary."""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.app.storage import db as db_mod
from backend.app.storage import repos


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "owner-immutability.db"
    db_mod.init_db(db_path)
    connection = db_mod.get_conn(db_path)
    yield connection
    connection.close()


@pytest.mark.parametrize(
    ("initial_owner", "replacement_owner"),
    [
        (None, "test_engineer"),
        ("test_engineer", None),
        ("test_engineer", "another_engineer"),
    ],
    ids=["null-to-value", "value-to-null", "value-to-other-value"],
)
def test_task_owner_username_is_immutable_for_every_transition(
    conn: sqlite3.Connection,
    initial_owner: str | None,
    replacement_owner: str | None,
) -> None:
    task_id = f"task_owner_immutable_{uuid.uuid4().hex}"
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="owner immutability witness",
        created_by="测试工程师",
        created_by_username=initial_owner,
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match=r"tasks\.created_by_username is immutable",
    ):
        conn.execute(
            "UPDATE tasks SET created_by_username = ? WHERE id = ?",
            (replacement_owner, task_id),
        )

    persisted = conn.execute(
        "SELECT created_by_username FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    assert persisted is not None
    assert persisted["created_by_username"] == initial_owner


def test_existing_database_reinstalls_missing_task_owner_trigger(tmp_path) -> None:
    db_path = tmp_path / "existing-without-task-trigger.db"
    db_mod.init_db(db_path)
    existing = db_mod.get_conn(db_path)
    try:
        existing.execute("DROP TRIGGER trg_tasks_created_by_username_immutable")
        repos.create_task(
            existing,
            task_id="task_existing_owner",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="existing database witness",
            created_by="历史工程师",
            created_by_username=None,
        )
    finally:
        existing.close()

    db_mod.init_db(db_path)
    migrated = db_mod.get_conn(db_path)
    try:
        with pytest.raises(
            sqlite3.IntegrityError,
            match=r"tasks\.created_by_username is immutable",
        ):
            migrated.execute(
                "UPDATE tasks SET created_by_username = ? WHERE id = ?",
                ("claimed_later", "task_existing_owner"),
            )
        persisted = migrated.execute(
            "SELECT created_by_username FROM tasks WHERE id = ?",
            ("task_existing_owner",),
        ).fetchone()
        assert persisted is not None
        assert persisted["created_by_username"] is None
    finally:
        migrated.close()


_LEGACY_NULLABLE_TEAMS_DDL = """
CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal_template TEXT,
    owner_user TEXT,
    created_from_conversation_id TEXT,
    created_at TEXT NOT NULL
)
"""


@pytest.mark.parametrize(
    ("initial_owner", "replacement_owner"),
    [
        (None, "test_engineer"),
        ("test_engineer", None),
        ("test_engineer", "another_engineer"),
    ],
    ids=["null-to-value", "value-to-null", "value-to-other-value"],
)
def test_team_owner_user_is_immutable_for_every_transition(
    tmp_path,
    initial_owner: str | None,
    replacement_owner: str | None,
) -> None:
    db_path = tmp_path / f"team-owner-{initial_owner or 'null'}.db"
    team_id = f"team_owner_immutable_{uuid.uuid4().hex}"

    if initial_owner is None:
        # Earlier/externally created databases may have allowed an unproven owner.
        # init_db must install the same fail-closed trigger without claiming it.
        legacy = db_mod.get_conn(db_path)
        try:
            legacy.execute(_LEGACY_NULLABLE_TEAMS_DDL)
            legacy.execute(
                "INSERT INTO teams "
                "(id, name, owner_user, created_at) VALUES (?, ?, NULL, ?)",
                (team_id, "legacy team", "2026-01-01T00:00:00+00:00"),
            )
        finally:
            legacy.close()
        db_mod.init_db(db_path)
    else:
        db_mod.init_db(db_path)
        fresh = db_mod.get_conn(db_path)
        try:
            repos.create_team(
                fresh,
                team_id=team_id,
                name="owner immutability witness",
                owner_user=initial_owner,
                members=[],
            )
        finally:
            fresh.close()

    connection = db_mod.get_conn(db_path)
    try:
        with pytest.raises(
            sqlite3.IntegrityError,
            match=r"teams\.owner_user is immutable",
        ):
            connection.execute(
                "UPDATE teams SET owner_user = ? WHERE id = ?",
                (replacement_owner, team_id),
            )

        persisted = connection.execute(
            "SELECT owner_user FROM teams WHERE id = ?", (team_id,)
        ).fetchone()
        assert persisted is not None
        assert persisted["owner_user"] == initial_owner
    finally:
        connection.close()
