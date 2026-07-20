from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from backend.app.auth import service as auth_service
from backend.app.storage import repos
from backend.app.storage import db as db_mod
from backend.app.storage.db import get_conn, init_db
from backend.tests.conftest import TEST_PASSWORD, login, seed_user


CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def _review_inbox_validator() -> Draft202012Validator:
    task_schema = json.loads(
        (CONTRACTS / "task.schema.json").read_text(encoding="utf-8")
    )
    inbox_schema = json.loads(
        (CONTRACTS / "review-inbox.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        task_schema["$id"], Resource.from_contents(task_schema)
    )
    return Draft202012Validator(inbox_schema, registry=registry)


def _create_task(client, *, requested_from: str | None = None):
    body = {
        "agent_id": "hello_agent",
        "name": "需要人工核对的任务",
        "inputs": {"name": "P2.5"},
    }
    if requested_from is not None:
        body["review_requested_from_username"] = requested_from
    return client.post("/api/tasks", json=body)


def _mark_waiting_review(db_path, task_id: str) -> None:
    conn = get_conn(db_path)
    try:
        conn.execute(
            "UPDATE tasks SET status = 'waiting_review', updated_at = ? WHERE id = ?",
            ("2026-07-20T01:00:00+00:00", task_id),
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "bad_value",
    ["", "   ", " alice", "alice ", "a" * 101],
)
def test_review_route_username_rejects_noncanonical_values_before_writes(
    app_env, bad_value: str
) -> None:
    client, app = app_env
    response = client.post(
        "/api/tasks",
        json={
            "agent_id": "hello_agent",
            "inputs": {"name": "invalid"},
            "review_requested_from_username": bad_value,
        },
    )
    assert response.status_code == 422
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        conn.close()


def test_unknown_or_inactive_review_route_is_rejected_without_task_write(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="inactive_reviewer",
        display_name="同名工程师",
        password=TEST_PASSWORD,
    )
    conn = app.state.conn_factory()
    try:
        auth_service.set_user_active(conn, "inactive_reviewer", False)
    finally:
        conn.close()

    for username in ("missing_reviewer", "inactive_reviewer"):
        response = _create_task(client, requested_from=username)
        assert response.status_code == 422

    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        conn.close()


def test_review_route_roundtrips_and_cannot_be_reassigned_by_raw_sql(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="同名工程师",
        password=TEST_PASSWORD,
    )
    response = _create_task(client, requested_from="alice_reviewer")
    assert response.status_code == 200
    task = response.json()
    assert task["review_requested_from_username"] == "alice_reviewer"

    conn = app.state.conn_factory()
    try:
        stored = repos.get_task(conn, task["id"])
        assert stored is not None
        assert stored["review_requested_from_username"] == "alice_reviewer"
        with pytest.raises(sqlite3.IntegrityError, match="review route is immutable"):
            conn.execute(
                "UPDATE tasks SET review_requested_from_username = ? WHERE id = ?",
                ("test_engineer", task["id"]),
            )
        columns = [row[1] for row in conn.execute("PRAGMA table_info(tasks)")]
        select_values = [
            "?" if column == "review_requested_from_username" else f'"{column}"'
            for column in columns
        ]
        with pytest.raises(sqlite3.IntegrityError, match="review route is immutable"):
            conn.execute(
                f"INSERT OR REPLACE INTO tasks ({','.join(columns)}) "
                f"SELECT {','.join(select_values)} FROM tasks WHERE id = ?",
                ("test_engineer", task["id"]),
            )
    finally:
        conn.close()


def test_review_route_cannot_be_rebound_by_conflicting_update_or_replace(app_env) -> None:
    client, app = app_env
    for username in ("alice_reviewer", "bob_reviewer"):
        seed_user(
            app.state.db_path,
            username=username,
            display_name=username,
            password=TEST_PASSWORD,
        )
    source = _create_task(client, requested_from="alice_reviewer").json()
    target = _create_task(client, requested_from="bob_reviewer").json()

    conn = app.state.conn_factory()
    try:
        conn.execute("PRAGMA recursive_triggers = OFF")
        assert conn.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="review route is immutable"):
            conn.execute(
                "UPDATE OR REPLACE tasks SET id = ? WHERE id = ?",
                (target["id"], source["id"]),
            )
        assert repos.get_task(conn, source["id"])[
            "review_requested_from_username"
        ] == "alice_reviewer"
        assert repos.get_task(conn, target["id"])[
            "review_requested_from_username"
        ] == "bob_reviewer"
    finally:
        conn.close()


def test_nonempty_review_route_rejects_same_name_noop_guard_on_restart(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="Alice",
        password=TEST_PASSWORD,
    )
    task = _create_task(client, requested_from="alice_reviewer").json()
    conn = app.state.conn_factory()
    try:
        conn.execute("DROP TRIGGER trg_tasks_review_route_immutable")
        conn.execute(
            "CREATE TRIGGER trg_tasks_review_route_immutable "
            "BEFORE UPDATE OF review_requested_from_username ON tasks BEGIN SELECT 1; END"
        )
    finally:
        conn.close()

    with pytest.raises(sqlite3.IntegrityError, match="review route schema witness"):
        init_db(app.state.db_path)

    conn = app.state.conn_factory()
    try:
        assert repos.get_task(conn, task["id"])[
            "review_requested_from_username"
        ] == "alice_reviewer"
    finally:
        conn.close()


def test_review_route_schema_rejects_nocase_column_semantics() -> None:
    from backend.app.storage.review_route_schema import review_route_schema_witnesses

    conn = sqlite3.connect(":memory:")
    try:
        drifted = db_mod._DDL.replace(
            "review_requested_from_username TEXT,",
            "review_requested_from_username TEXT COLLATE NOCASE,",
        )
        assert drifted != db_mod._DDL
        conn.executescript(drifted)
        for statement in db_mod._INDEX_DDL:
            conn.execute(statement)
        witnesses = review_route_schema_witnesses(conn)
        assert witnesses["required_index"] is False
    finally:
        conn.close()


def test_pre_p25_database_with_review_evidence_upgrades_without_rewriting_facts(
    app_env,
) -> None:
    client, app = app_env
    task = _create_task(client).json()
    conn = app.state.conn_factory()
    try:
        event_count = conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ?", (task["id"],)
        ).fetchone()[0]
        assert event_count > 0
        for name in db_mod._REVIEW_ROUTE_MANAGED_TRIGGERS:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        for name in db_mod._REVIEW_ROUTE_MANAGED_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {name}")
        conn.execute("ALTER TABLE tasks DROP COLUMN review_requested_from_username")
    finally:
        conn.close()

    init_db(app.state.db_path)
    conn = app.state.conn_factory()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        assert "review_requested_from_username" in columns
        assert conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ?", (task["id"],)
        ).fetchone()[0] == event_count
        assert repos.get_task(conn, task["id"])[
            "review_requested_from_username"
        ] is None
    finally:
        conn.close()


def test_personal_review_inbox_uses_exact_username_not_display_name(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="同名工程师",
        password=TEST_PASSWORD,
    )
    seed_user(
        app.state.db_path,
        username="bob_reviewer",
        display_name="同名工程师",
        password=TEST_PASSWORD,
    )
    assigned = _create_task(client, requested_from="alice_reviewer").json()
    other = _create_task(client, requested_from="bob_reviewer").json()
    unassigned = _create_task(client).json()
    for task in (assigned, other, unassigned):
        _mark_waiting_review(app.state.db_path, task["id"])

    client.cookies.clear()
    login(client, username="alice_reviewer", password=TEST_PASSWORD)
    response = client.get("/api/me/review-inbox?limit=1&offset=0")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    page = response.json()
    _review_inbox_validator().validate(page)
    assert page["schema_version"] == "review-inbox/v1"
    assert [item["id"] for item in page["items"]] == [assigned["id"]]
    assert page["has_more"] is False
    assert page["next_offset"] is None

    client.cookies.clear()
    login(client, username="bob_reviewer", password=TEST_PASSWORD)
    bob_page = client.get("/api/me/review-inbox").json()
    assert [item["id"] for item in bob_page["items"]] == [other["id"]]


def test_review_inbox_snapshot_rejects_page_mixing_after_membership_change(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="Alice",
        password=TEST_PASSWORD,
    )
    first = _create_task(client, requested_from="alice_reviewer").json()
    second = _create_task(client, requested_from="alice_reviewer").json()
    for task in (first, second):
        _mark_waiting_review(app.state.db_path, task["id"])

    client.cookies.clear()
    login(client, username="alice_reviewer", password=TEST_PASSWORD)
    first_page = client.get("/api/me/review-inbox?limit=1&offset=0")
    assert first_page.status_code == 200
    payload = first_page.json()
    _review_inbox_validator().validate(payload)
    assert payload["has_more"] is True
    assert payload["total"] == 2
    assert isinstance(payload["snapshot_id"], str)

    added = _create_task(client, requested_from="alice_reviewer").json()
    _mark_waiting_review(app.state.db_path, added["id"])
    mixed = client.get(
        "/api/me/review-inbox",
        params={
            "limit": 1,
            "offset": payload["next_offset"],
            "snapshot_id": payload["snapshot_id"],
        },
    )
    assert mixed.status_code == 409


def test_review_inbox_contract_covers_sensitive_redaction(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="Alice",
        password=TEST_PASSWORD,
    )
    task = _create_task(client, requested_from="alice_reviewer").json()
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE tasks SET data_classification = 'sensitive', "
            "error_message = ? WHERE id = ?",
            ("private-error", task["id"]),
        )
    finally:
        conn.close()
    _mark_waiting_review(app.state.db_path, task["id"])
    client.cookies.clear()
    login(client, username="alice_reviewer", password=TEST_PASSWORD)
    payload = client.get("/api/me/review-inbox").json()
    _review_inbox_validator().validate(payload)
    assert payload["items"][0]["content_withheld"] is True
    assert payload["items"][0]["error_message"] is None


def test_health_and_readyz_recheck_exact_review_route_guards(app_env) -> None:
    client, app = app_env
    health = client.get("/api/health").json()
    assert health["named_review_inbox_axis"] is True
    assert all(health["review_route_schema_witnesses"].values()) is True

    conn = app.state.conn_factory()
    try:
        conn.execute("DROP TRIGGER trg_tasks_review_route_immutable")
        conn.execute(
            "CREATE TRIGGER trg_tasks_review_route_immutable "
            "BEFORE UPDATE OF review_requested_from_username ON tasks BEGIN SELECT 1; END"
        )
    finally:
        conn.close()
    health = client.get("/api/health").json()
    assert health["review_route_schema_witnesses"]["required_triggers"] is False
    ready = client.get("/api/readyz")
    assert ready.status_code == 503
    assert ready.json()["named_review_inbox"]["schema_ready"] is False


def test_batch_route_validation_is_atomic_and_valid_route_propagates(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="审核人",
        password=TEST_PASSWORD,
    )
    body = {
        "review_requested_from_username": "missing_reviewer",
        "items": [
            {"agent_id": "hello_agent", "inputs": {"name": "one"}},
            {"agent_id": "hello_agent", "inputs": {"name": "two"}},
        ],
    }
    rejected = client.post("/api/tasks/batch", json=body)
    assert rejected.status_code == 422
    conn = app.state.conn_factory()
    try:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        conn.close()

    body["review_requested_from_username"] = "alice_reviewer"
    accepted = client.post("/api/tasks/batch", json=body)
    assert accepted.status_code == 200
    assert {
        task["review_requested_from_username"] for task in accepted.json()["tasks"]
    } == {"alice_reviewer"}


def test_named_route_does_not_exclude_another_authenticated_human_signer(app_env) -> None:
    client, app = app_env
    for username in ("alice_reviewer", "bob_reviewer"):
        seed_user(
            app.state.db_path,
            username=username,
            display_name="同名工程师",
            password=TEST_PASSWORD,
        )
    task = _create_task(client, requested_from="alice_reviewer").json()
    _mark_waiting_review(app.state.db_path, task["id"])

    client.cookies.clear()
    login(client, username="bob_reviewer", password=TEST_PASSWORD)
    reviewed = client.post(
        f"/api/tasks/{task['id']}/review",
        json={"action": "approve", "reason_code": None, "comment": None},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "completed"
    conn = app.state.conn_factory()
    try:
        decision = repos.get_human_decision(conn, task["id"])
        assert decision is not None
        assert decision["reviewer_username"] == "bob_reviewer"
    finally:
        conn.close()


def test_team_summon_propagates_one_named_route_to_the_atomic_batch(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="审核人",
        password=TEST_PASSWORD,
    )
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_p25_team",
            agent_id="guide_agent",
            created_by="测试工程师",
            created_by_username="test_engineer",
        )
        repos.set_conversation_recommendation(
            conn,
            "conv_p25_team",
            {
                "decision": "orchestrate",
                "goal": "验证签收路由",
                "agents": [
                    {"agent_id": "hello_agent", "role": "上游"},
                    {"agent_id": "hello_agent", "role": "下游", "after": [0]},
                ],
            },
        )
    finally:
        conn.close()
    saved = client.post(
        "/api/teams",
        json={"name": "P2.5 团队", "conversation_id": "conv_p25_team"},
    )
    assert saved.status_code == 200
    summoned = client.post(
        f"/api/teams/{saved.json()['id']}/summon",
        json={
            "review_requested_from_username": "alice_reviewer",
            "items": [
                {"seq": 0, "inputs": {"name": "one"}},
                {"seq": 1, "inputs": {"name": "two"}},
            ],
        },
    )
    assert summoned.status_code == 200, summoned.text
    assert {
        task["review_requested_from_username"]
        for task in summoned.json()["tasks"]
    } == {"alice_reviewer"}


def test_active_review_routing_users_exposes_only_safe_identity_fields(app_env) -> None:
    client, app = app_env
    seed_user(
        app.state.db_path,
        username="alice_reviewer",
        display_name="同名工程师",
        password=TEST_PASSWORD,
    )
    seed_user(
        app.state.db_path,
        username="disabled_reviewer",
        display_name="停用用户",
        password=TEST_PASSWORD,
    )
    conn = app.state.conn_factory()
    try:
        auth_service.set_user_active(conn, "disabled_reviewer", False)
    finally:
        conn.close()

    response = client.get("/api/me/review-routing-users")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    rows = response.json()
    assert [row["username"] for row in rows] == ["alice_reviewer", "test_engineer"]
    assert all(set(row) == {"username", "display_name"} for row in rows)
    assert all(row["username"] != "disabled_reviewer" for row in rows)
