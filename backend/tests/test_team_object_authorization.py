"""Team blueprints are private to their authenticated owner.

The authorization contract is exercised only through the public HTTP API.  Direct
repository writes below are test setup: they let the cases establish precise
Alice/Bob and legacy-owner rows without depending on Guide model output.
"""

from __future__ import annotations

from typing import Any

from backend.app.api import teams as teams_api
from backend.app.storage import repos
from backend.tests.conftest import (
    TEST_DISPLAY_NAME,
    TEST_PASSWORD,
    TEST_USERNAME,
    login,
    seed_user,
)


BOB_USERNAME = "bob_engineer"
BOB_PASSWORD = "Bob-Engineer-Password-2026!"

_SINGLE_MEMBER = [
    {
        "agent_id": "hello_agent",
        "agent_version_at_save": "0.1.0",
        "role": "执行工作",
        "seq": 0,
        "after": [],
    }
]


def _seed_team(
    app: Any,
    *,
    team_id: str,
    owner_user: str,
    created_at: str,
) -> None:
    conn = app.state.conn_factory()
    try:
        repos.create_team(
            conn,
            team_id=team_id,
            name=f"团队 {team_id}",
            owner_user=owner_user,
            members=_SINGLE_MEMBER,
            goal_template="完成 owner 授权验收",
        )
        # Stable timestamps make the pre-pagination owner filter observable.
        conn.execute(
            "UPDATE teams SET created_at = ? WHERE id = ?",
            (created_at, team_id),
        )
    finally:
        conn.close()


def _seed_plan_conversation(
    app: Any,
    *,
    conversation_id: str,
    owner_username: str | None,
) -> None:
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=owner_username,
        )
        repos.set_conversation_recommendation(
            conn,
            conversation_id,
            {
                "decision": "orchestrate",
                "goal": "完成 owner 授权验收",
                "agents": [{"agent_id": "hello_agent", "role": "执行工作"}],
            },
        )
    finally:
        conn.close()


def _seed_bob(app: Any) -> None:
    seed_user(
        app.state.db_path,
        username=BOB_USERNAME,
        display_name="Bob 工程师",
        password=BOB_PASSWORD,
    )


def _attach_bob_file_to_alice_conversation(
    client: Any,
    app: Any,
    *,
    conversation_id: str,
) -> str:
    _login_bob(client)
    upload = client.post(
        "/api/files/upload",
        files={"file": ("bob-private.txt", b"bob private history", "text/plain")},
        data={"classification": "internal"},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["id"]
    _login_alice(client)

    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="模拟旧版本残留的跨 owner 附件",
            file_ids=[file_id],
        )
    finally:
        conn.close()
    return file_id


def _authorization_write_snapshot(app: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
    conn = app.state.conn_factory()
    try:
        return {
            "conversations": tuple(
                tuple(row)
                for row in conn.execute("SELECT * FROM conversations ORDER BY id")
            ),
            "conversation_messages": tuple(
                tuple(row)
                for row in conn.execute(
                    "SELECT * FROM conversation_messages ORDER BY id"
                )
            ),
            "files": tuple(
                tuple(row) for row in conn.execute("SELECT * FROM files ORDER BY id")
            ),
            "teams": tuple(
                tuple(row) for row in conn.execute("SELECT * FROM teams ORDER BY id")
            ),
            "team_members": tuple(
                tuple(row)
                for row in conn.execute(
                    "SELECT * FROM team_members ORDER BY team_id, seq"
                )
            ),
            "tasks": tuple(
                tuple(row) for row in conn.execute("SELECT * FROM tasks ORDER BY id")
            ),
            "task_events": tuple(
                tuple(row)
                for row in conn.execute("SELECT * FROM task_events ORDER BY id")
            ),
        }
    finally:
        conn.close()


def _login_alice(client: Any) -> None:
    login(client, username=TEST_USERNAME, password=TEST_PASSWORD)


def _login_bob(client: Any) -> None:
    login(client, username=BOB_USERNAME, password=BOB_PASSWORD)


def _ids(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()]


def _assert_same_generic_not_found(known: Any, unknown: Any, secret_id: str) -> None:
    assert known.status_code == 404
    assert unknown.status_code == 404
    assert known.json() == unknown.json()
    assert secret_id not in known.text


def test_team_list_filters_exact_owner_before_limit_and_offset(app_env) -> None:
    client, app = app_env
    _seed_bob(app)
    _seed_team(
        app,
        team_id="team_alice_old",
        owner_user=TEST_USERNAME,
        created_at="2026-01-01T00:00:00Z",
    )
    _seed_team(
        app,
        team_id="team_bob_newest",
        owner_user=BOB_USERNAME,
        created_at="2026-01-03T00:00:00Z",
    )
    _seed_team(
        app,
        team_id="team_alice_new",
        owner_user=TEST_USERNAME,
        created_at="2026-01-02T00:00:00Z",
    )

    assert _ids(client.get("/api/teams", params={"limit": 1, "offset": 0})) == [
        "team_alice_new"
    ]
    assert _ids(client.get("/api/teams", params={"limit": 1, "offset": 1})) == [
        "team_alice_old"
    ]
    alice_page = client.get("/api/teams", params={"limit": 10, "offset": 0}).json()
    assert {team["owner_user"] for team in alice_page} == {TEST_USERNAME}

    _login_bob(client)
    assert _ids(client.get("/api/teams", params={"limit": 10, "offset": 0})) == [
        "team_bob_newest"
    ]


def test_cross_owner_team_detail_and_summon_are_indistinguishable_and_write_nothing(
    app_env,
) -> None:
    client, app = app_env
    _seed_bob(app)
    secret_team_id = "team_alice_private"
    _seed_team(
        app,
        team_id=secret_team_id,
        owner_user=TEST_USERNAME,
        created_at="2026-01-01T00:00:00Z",
    )

    alice_tasks_before = _ids(client.get("/api/tasks"))
    alice_teams_before = _ids(client.get("/api/teams"))
    _login_bob(client)
    bob_tasks_before = _ids(client.get("/api/tasks"))
    bob_teams_before = _ids(client.get("/api/teams"))

    known_detail = client.get(f"/api/teams/{secret_team_id}")
    unknown_detail = client.get("/api/teams/team_does_not_exist")
    _assert_same_generic_not_found(known_detail, unknown_detail, secret_team_id)

    summon_body = {"items": [{"seq": 0, "inputs": {"name": "不得启动"}}]}
    known_summon = client.post(
        f"/api/teams/{secret_team_id}/summon", json=summon_body
    )
    unknown_summon = client.post(
        "/api/teams/team_does_not_exist/summon", json=summon_body
    )
    _assert_same_generic_not_found(known_summon, unknown_summon, secret_team_id)
    assert _ids(client.get("/api/tasks")) == bob_tasks_before
    assert _ids(client.get("/api/teams")) == bob_teams_before

    _login_alice(client)
    assert _ids(client.get("/api/tasks")) == alice_tasks_before
    assert _ids(client.get("/api/teams")) == alice_teams_before
    assert client.get(f"/api/teams/{secret_team_id}").status_code == 200
    owner_summon = client.post(
        f"/api/teams/{secret_team_id}/summon",
        json={"items": [{"seq": 0, "inputs": {"name": "owner 正向"}}]},
    )
    assert owner_summon.status_code == 200, owner_summon.text
    assert len(owner_summon.json()["tasks"]) == 1


def test_blank_team_owner_fails_closed_like_an_unknown_team(app_env) -> None:
    client, app = app_env
    blank_owner_team_id = "team_legacy_blank_owner"
    _seed_team(
        app,
        team_id=blank_owner_team_id,
        owner_user="   ",
        created_at="2026-01-01T00:00:00Z",
    )

    assert blank_owner_team_id not in _ids(client.get("/api/teams"))
    known_detail = client.get(f"/api/teams/{blank_owner_team_id}")
    unknown_detail = client.get("/api/teams/team_does_not_exist")
    _assert_same_generic_not_found(known_detail, unknown_detail, blank_owner_team_id)

    summon_body = {"items": [{"seq": 0, "inputs": {"name": "不得启动"}}]}
    known_summon = client.post(
        f"/api/teams/{blank_owner_team_id}/summon", json=summon_body
    )
    unknown_summon = client.post(
        "/api/teams/team_does_not_exist/summon", json=summon_body
    )
    _assert_same_generic_not_found(known_summon, unknown_summon, blank_owner_team_id)
    assert _ids(client.get("/api/tasks")) == []


def test_team_summon_cannot_bind_tasks_to_another_owners_conversation(
    app_env,
) -> None:
    client, app = app_env
    _seed_bob(app)
    bob_team_id = "team_bob_owned"
    alice_conversation_id = "conv_alice_private_for_summon"
    _seed_team(
        app,
        team_id=bob_team_id,
        owner_user=BOB_USERNAME,
        created_at="2026-01-01T00:00:00Z",
    )
    _seed_plan_conversation(
        app,
        conversation_id=alice_conversation_id,
        owner_username=TEST_USERNAME,
    )

    _login_bob(client)
    tasks_before = _ids(client.get("/api/tasks"))
    known = client.post(
        f"/api/teams/{bob_team_id}/summon",
        json={
            "conversation_id": alice_conversation_id,
            "items": [{"seq": 0, "inputs": {"name": "不得跨 owner 归属"}}],
        },
    )
    unknown = client.post(
        f"/api/teams/{bob_team_id}/summon",
        json={
            "conversation_id": "conv_does_not_exist",
            "items": [{"seq": 0, "inputs": {"name": "不得创建"}}],
        },
    )
    _assert_same_generic_not_found(known, unknown, alice_conversation_id)
    assert _ids(client.get("/api/tasks")) == tasks_before


def test_create_team_requires_an_owned_nonlegacy_source_conversation(app_env) -> None:
    client, app = app_env
    _seed_bob(app)
    _seed_plan_conversation(
        app,
        conversation_id="conv_alice_private_plan",
        owner_username=TEST_USERNAME,
    )
    _seed_plan_conversation(
        app,
        conversation_id="conv_legacy_unowned_plan",
        owner_username=None,
    )

    _login_bob(client)
    teams_before = _ids(client.get("/api/teams"))
    known = client.post(
        "/api/teams",
        json={"name": "偷用 Alice 方案", "conversation_id": "conv_alice_private_plan"},
    )
    unknown = client.post(
        "/api/teams",
        json={"name": "不存在方案", "conversation_id": "conv_does_not_exist"},
    )
    _assert_same_generic_not_found(known, unknown, "conv_alice_private_plan")
    legacy = client.post(
        "/api/teams",
        json={"name": "偷用 legacy 方案", "conversation_id": "conv_legacy_unowned_plan"},
    )
    assert legacy.status_code == unknown.status_code
    assert legacy.json() == unknown.json()
    assert _ids(client.get("/api/teams")) == teams_before

    _login_alice(client)
    owner_create = client.post(
        "/api/teams",
        json={"name": "Alice 自有方案", "conversation_id": "conv_alice_private_plan"},
    )
    assert owner_create.status_code == 200, owner_create.text
    assert owner_create.json()["owner_user"] == TEST_USERNAME


def test_create_team_rejects_foreign_historical_attachment_before_plan_or_write(
    app_env,
) -> None:
    client, app = app_env
    _seed_bob(app)
    conversation_id = "conv_alice_foreign_history_for_team_create"
    _seed_plan_conversation(
        app,
        conversation_id=conversation_id,
        owner_username=TEST_USERNAME,
    )
    _attach_bob_file_to_alice_conversation(
        client,
        app,
        conversation_id=conversation_id,
    )
    conn = app.state.conn_factory()
    try:
        repos.set_conversation_recommendation(
            conn,
            conversation_id,
            {"decision": "single", "agents": []},
        )
    finally:
        conn.close()

    known_get = client.get(f"/api/conversations/{conversation_id}")
    unknown_get = client.get("/api/conversations/conv_does_not_exist")
    _assert_same_generic_not_found(known_get, unknown_get, conversation_id)
    before = _authorization_write_snapshot(app)

    known = client.post(
        "/api/teams",
        json={"name": "不得读取方案", "conversation_id": conversation_id},
    )
    unknown = client.post(
        "/api/teams",
        json={"name": "不存在方案", "conversation_id": "conv_does_not_exist"},
    )
    _assert_same_generic_not_found(known, unknown, conversation_id)
    assert _authorization_write_snapshot(app) == before


def test_team_summon_rejects_foreign_historical_attachment_before_state_or_write(
    app_env,
    monkeypatch,
) -> None:
    client, app = app_env
    _seed_bob(app)
    team_id = "team_alice_foreign_history_summon"
    conversation_id = "conv_alice_foreign_history_for_summon"
    _seed_team(
        app,
        team_id=team_id,
        owner_user=TEST_USERNAME,
        created_at="2026-01-01T00:00:00Z",
    )
    _seed_plan_conversation(
        app,
        conversation_id=conversation_id,
        owner_username=TEST_USERNAME,
    )
    _attach_bob_file_to_alice_conversation(
        client,
        app,
        conversation_id=conversation_id,
    )

    known_get = client.get(f"/api/conversations/{conversation_id}")
    unknown_get = client.get("/api/conversations/conv_does_not_exist")
    _assert_same_generic_not_found(known_get, unknown_get, conversation_id)
    before = _authorization_write_snapshot(app)

    original_snapshot = app.state.agent_registry.package_snapshot
    registry_reads: list[str] = []

    def recording_snapshot(agent_id: str):
        registry_reads.append(agent_id)
        return original_snapshot(agent_id)

    original_run_batch_creation = teams_api.run_batch_creation
    batch_calls = 0

    def recording_run_batch_creation(**kwargs: Any):
        nonlocal batch_calls
        batch_calls += 1
        return original_run_batch_creation(**kwargs)

    monkeypatch.setattr(app.state.agent_registry, "package_snapshot", recording_snapshot)
    monkeypatch.setattr(
        teams_api,
        "run_batch_creation",
        recording_run_batch_creation,
    )

    body = {
        "items": [{"seq": 0, "inputs": {"name": "不得读取 registry"}}],
    }
    known = client.post(
        f"/api/teams/{team_id}/summon",
        json={**body, "conversation_id": conversation_id},
    )
    unknown = client.post(
        f"/api/teams/{team_id}/summon",
        json={**body, "conversation_id": "conv_does_not_exist"},
    )
    _assert_same_generic_not_found(known, unknown, conversation_id)
    assert registry_reads == []
    assert batch_calls == 0
    assert _authorization_write_snapshot(app) == before
