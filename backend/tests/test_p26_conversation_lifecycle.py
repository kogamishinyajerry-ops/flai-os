"""P2.6 trusted conversation lifecycle public-contract tests."""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from conftest import (
    TEST_DISPLAY_NAME,
    TEST_USERNAME,
    seed_pre_p23_legacy_conversation,
)

from backend.app.core.errors import (
    ConversationConflictError,
    ConversationNotFoundError,
)
from backend.app.storage import repos


def _open_conversation(client) -> dict[str, Any]:
    response = client.post(
        "/api/conversations", json={"agent_id": "guide_agent"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _lifecycle_snapshot(app, conversation_id: str) -> tuple[Any, ...]:
    conn = app.state.conn_factory()
    try:
        projection = conn.execute(
            "SELECT title, status, lifecycle_revision, archived_at "
            "FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        event_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_lifecycle_events "
            "WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
        assert projection is not None
        return (*tuple(projection), event_count)
    finally:
        conn.close()


def _lifecycle_events(app, conversation_id: str) -> list[dict[str, Any]]:
    conn = app.state.conn_factory()
    try:
        return repos.list_conversation_lifecycle_events(conn, conversation_id)
    finally:
        conn.close()


class _QuestionGateway:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, profile, messages, **kwargs):
        self.calls += 1
        proposal = {
            "kind": "single_choice",
            "prompt": "先确认覆盖范围？",
            "options": [{"label": "供电"}, {"label": "液压"}],
        }
        return {
            "content": (
                "请先确认。\n<<QUESTION>>\n"
                f"{json.dumps(proposal, ensure_ascii=False)}\n"
                "<<END_QUESTION>>"
            ),
            "token_usage": None,
            "model_name": "p26-question-stub",
            "finish_reason": "stop",
        }


def _issue_question(client, app, conversation_id: str) -> dict[str, Any]:
    gateway = _QuestionGateway()
    app.state.conversation_service.model_gateway = gateway
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请开始分析"},
    )
    assert response.status_code == 200, response.text
    assert gateway.calls == 1
    return response.json()["message"]["question"]


def _question_projection(client, conversation_id: str, question_id: str):
    response = client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    for message in response.json()["messages"]:
        question = message.get("question")
        if question is not None and question["id"] == question_id:
            return question
    raise AssertionError(f"question not found: {question_id}")


@pytest.mark.parametrize(
    ("path_suffix", "body"),
    [
        ("/title", {"lifecycle_revision": True, "title": "有效标题"}),
        ("/title", {"lifecycle_revision": "0", "title": "有效标题"}),
        ("/title", {"lifecycle_revision": 0.0, "title": "有效标题"}),
        ("/title", {"lifecycle_revision": -1, "title": "有效标题"}),
        ("/conclude", {"lifecycle_revision": False}),
        ("/conclude", {"lifecycle_revision": "0"}),
        ("/conclude", {"lifecycle_revision": 0.0}),
        ("/conclude", {"lifecycle_revision": -1}),
        ("/archive", {"lifecycle_revision": True}),
        ("/archive", {"lifecycle_revision": "0"}),
        ("/archive", {"lifecycle_revision": 0.0}),
        ("/archive", {"lifecycle_revision": -1}),
    ],
)
def test_lifecycle_revision_rejects_non_exact_integers_before_writes(
    app_env, path_suffix: str, body: dict[str, Any]
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)

    response = client.request(
        "PATCH" if path_suffix == "/title" else "POST",
        f"/api/conversations/{conversation['id']}{path_suffix}",
        json=body,
    )

    assert response.status_code == 422, response.text
    assert _lifecycle_snapshot(app, conversation["id"]) == (
        None,
        "active",
        0,
        None,
        0,
    )


@pytest.mark.parametrize(
    "title",
    [
        "",
        "   ",
        " 首尾空白 ",
        "x" * 61,
        "合法标题\n第二行",
        "合法标题\r第二行",
        "合法\t标题",
        "合法\x00标题",
        "合法\x85标题",
        "合法\u2028标题",
        "合法\u2029标题",
    ],
)
def test_rename_rejects_invalid_trimmed_titles_before_writes(
    app_env, title: str
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)

    response = client.patch(
        f"/api/conversations/{conversation['id']}/title",
        json={"lifecycle_revision": 0, "title": title},
    )

    assert response.status_code == 422, response.text
    assert _lifecycle_snapshot(app, conversation["id"]) == (
        None,
        "active",
        0,
        None,
        0,
    )


@pytest.mark.parametrize(
    ("path_suffix", "body"),
    [
        ("/title", {"lifecycle_revision": 0, "title": "标题", "owner": "x"}),
        ("/conclude", {"lifecycle_revision": 0, "force": True}),
        ("/archive", {"lifecycle_revision": 0, "force": True}),
    ],
)
def test_lifecycle_requests_forbid_extra_fields_without_writes(
    app_env, path_suffix: str, body: dict[str, Any]
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)

    response = client.request(
        "PATCH" if path_suffix == "/title" else "POST",
        f"/api/conversations/{conversation['id']}{path_suffix}",
        json=body,
    )

    assert response.status_code == 422, response.text
    assert _lifecycle_snapshot(app, conversation["id"]) == (
        None,
        "active",
        0,
        None,
        0,
    )


def test_lifecycle_successes_preserve_orthogonal_state_axes_and_projection_shape(
    app_env,
) -> None:
    client, app = app_env
    first = _open_conversation(client)
    assert {
        key: first[key]
        for key in ("title", "status", "lifecycle_revision", "archived_at")
    } == {
        "title": None,
        "status": "active",
        "lifecycle_revision": 0,
        "archived_at": None,
    }

    renamed = client.patch(
        f"/api/conversations/{first['id']}/title",
        json={"lifecycle_revision": 0, "title": "第一会话"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "第一会话"
    assert renamed.json()["lifecycle_revision"] == 1

    archived = client.post(
        f"/api/conversations/{first['id']}/archive",
        json={"lifecycle_revision": 1},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "active"
    assert archived.json()["archived_at"] is not None
    assert archived.json()["lifecycle_revision"] == 2

    renamed_archived_active = client.patch(
        f"/api/conversations/{first['id']}/title",
        json={"lifecycle_revision": 2, "title": "归档但仍进行中"},
    )
    assert renamed_archived_active.status_code == 200
    assert renamed_archived_active.json()["status"] == "active"
    assert renamed_archived_active.json()["archived_at"] == archived.json()["archived_at"]

    concluded_archived = client.post(
        f"/api/conversations/{first['id']}/conclude",
        json={"lifecycle_revision": 3},
    )
    assert concluded_archived.status_code == 200, concluded_archived.text
    assert concluded_archived.json()["status"] == "concluded"
    assert concluded_archived.json()["archived_at"] == archived.json()["archived_at"]
    assert concluded_archived.json()["lifecycle_revision"] == 4
    assert [event["event_type"] for event in _lifecycle_events(app, first["id"])] == [
        "renamed",
        "archived",
        "renamed",
        "concluded",
    ]

    second = _open_conversation(client)
    concluded_visible = client.post(
        f"/api/conversations/{second['id']}/conclude",
        json={"lifecycle_revision": 0},
    )
    assert concluded_visible.status_code == 200
    assert concluded_visible.json()["archived_at"] is None

    renamed_concluded_visible = client.patch(
        f"/api/conversations/{second['id']}/title",
        json={"lifecycle_revision": 1, "title": "已结束仍可命名"},
    )
    assert renamed_concluded_visible.status_code == 200
    assert renamed_concluded_visible.json()["status"] == "concluded"
    assert renamed_concluded_visible.json()["archived_at"] is None

    archived_concluded = client.post(
        f"/api/conversations/{second['id']}/archive",
        json={"lifecycle_revision": 2},
    )
    assert archived_concluded.status_code == 200
    assert archived_concluded.json()["status"] == "concluded"
    assert archived_concluded.json()["archived_at"] is not None


def test_stale_and_noop_lifecycle_mutations_are_409_with_zero_writes(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    conversation_id = conversation["id"]
    first = client.patch(
        f"/api/conversations/{conversation_id}/title",
        json={"lifecycle_revision": 0, "title": "稳定标题"},
    )
    assert first.status_code == 200

    before = _lifecycle_snapshot(app, conversation_id)
    stale_requests = [
        ("PATCH", "/title", {"lifecycle_revision": 0, "title": "过期标题"}),
        ("POST", "/conclude", {"lifecycle_revision": 0}),
        ("POST", "/archive", {"lifecycle_revision": 0}),
        ("PATCH", "/title", {"lifecycle_revision": 1, "title": "稳定标题"}),
    ]
    for method, suffix, body in stale_requests:
        response = client.request(
            method, f"/api/conversations/{conversation_id}{suffix}", json=body
        )
        assert response.status_code == 409, response.text
        assert _lifecycle_snapshot(app, conversation_id) == before

    concluded = client.post(
        f"/api/conversations/{conversation_id}/conclude",
        json={"lifecycle_revision": 1},
    )
    assert concluded.status_code == 200
    before_repeat = _lifecycle_snapshot(app, conversation_id)
    repeated = client.post(
        f"/api/conversations/{conversation_id}/conclude",
        json={"lifecycle_revision": 2},
    )
    assert repeated.status_code == 409
    assert _lifecycle_snapshot(app, conversation_id) == before_repeat

    archived = client.post(
        f"/api/conversations/{conversation_id}/archive",
        json={"lifecycle_revision": 2},
    )
    assert archived.status_code == 200
    before_repeat = _lifecycle_snapshot(app, conversation_id)
    repeated = client.post(
        f"/api/conversations/{conversation_id}/archive",
        json={"lifecycle_revision": 3},
    )
    assert repeated.status_code == 409
    assert _lifecycle_snapshot(app, conversation_id) == before_repeat


def test_conclude_closes_pending_question_in_same_transaction(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    question = _issue_question(client, app, conversation["id"])

    response = client.post(
        f"/api/conversations/{conversation['id']}/conclude",
        json={"lifecycle_revision": 0},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "concluded"
    closed = _question_projection(client, conversation["id"], question["id"])
    assert closed["status"] == "superseded"
    event = _lifecycle_events(app, conversation["id"])[0]
    assert closed["closed_at"] == event["created_at"]


def test_conclude_event_failure_rolls_back_question_and_projection(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    question = _issue_question(client, app, conversation["id"])
    before = _lifecycle_snapshot(app, conversation["id"])

    def fail_event(*args, **kwargs):
        raise RuntimeError("injected lifecycle event failure")

    monkeypatch.setattr(repos, "append_conversation_lifecycle_event", fail_event)
    with pytest.raises(RuntimeError, match="injected lifecycle event failure"):
        app.state.conversation_service.conclude(
            conversation["id"],
            lifecycle_revision=0,
            principal={
                "username": TEST_USERNAME,
                "display_name": TEST_DISPLAY_NAME,
            },
        )

    assert _lifecycle_snapshot(app, conversation["id"]) == before
    assert _question_projection(client, conversation["id"], question["id"])["status"] == "pending"


def test_archive_does_not_conclude_or_close_pending_question(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    question = _issue_question(client, app, conversation["id"])

    response = client.post(
        f"/api/conversations/{conversation['id']}/archive",
        json={"lifecycle_revision": 0},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
    assert response.json()["archived_at"] is not None
    assert _question_projection(client, conversation["id"], question["id"])["status"] == "pending"


def test_visibility_filter_is_owner_scoped_and_archived_is_explicit(app_env) -> None:
    client, _app = app_env
    visible = _open_conversation(client)
    archived = _open_conversation(client)
    response = client.post(
        f"/api/conversations/{archived['id']}/archive",
        json={"lifecycle_revision": 0},
    )
    assert response.status_code == 200

    default_rows = client.get("/api/conversations").json()
    archived_rows = client.get("/api/conversations?visibility=archived").json()
    assert {row["id"] for row in default_rows} == {visible["id"]}
    assert {row["id"] for row in archived_rows} == {archived["id"]}

    invalid = client.get("/api/conversations?visibility=all")
    assert invalid.status_code == 422


def test_lifecycle_projection_is_uniform_in_get_list_message_and_answer(
    app_env,
) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    renamed = client.patch(
        f"/api/conversations/{conversation['id']}/title",
        json={"lifecycle_revision": 0, "title": "统一投影"},
    ).json()
    archived = client.post(
        f"/api/conversations/{conversation['id']}/archive",
        json={"lifecycle_revision": 1},
    ).json()
    expected = {
        "title": "统一投影",
        "status": "active",
        "lifecycle_revision": 2,
        "archived_at": archived["archived_at"],
    }
    assert renamed["archived_at"] is None

    gateway = _QuestionGateway()
    app.state.conversation_service.model_gateway = gateway
    posted = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "请发出结构化问题"},
    )
    assert posted.status_code == 200, posted.text
    assert {
        key: posted.json()["conversation"][key] for key in expected
    } == expected
    question = posted.json()["message"]["question"]

    fetched = client.get(f"/api/conversations/{conversation['id']}")
    assert fetched.status_code == 200
    assert {key: fetched.json()[key] for key in expected} == expected

    listed = client.get("/api/conversations?visibility=archived")
    assert listed.status_code == 200
    listed_row = next(
        row for row in listed.json() if row["id"] == conversation["id"]
    )
    assert {key: listed_row[key] for key in expected} == expected

    answered = client.post(
        f"/api/conversations/{conversation['id']}/questions/{question['id']}/answer",
        json={
            "question_revision": 1,
            "submission_id": "p26-projection-answer-001",
            "payload": {"kind": "option", "option_id": "option_1"},
        },
    )
    assert answered.status_code == 200, answered.text
    assert {
        key: answered.json()["conversation"][key] for key in expected
    } == expected


def test_exact_owner_is_required_for_all_lifecycle_mutations(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    foreign = {"username": "other_engineer", "display_name": TEST_DISPLAY_NAME}
    before = _lifecycle_snapshot(app, conversation["id"])

    for mutation in (
        lambda: app.state.conversation_service.rename(
            conversation["id"], title="越权", lifecycle_revision=0, principal=foreign
        ),
        lambda: app.state.conversation_service.conclude(
            conversation["id"], lifecycle_revision=0, principal=foreign
        ),
        lambda: app.state.conversation_service.archive(
            conversation["id"], lifecycle_revision=0, principal=foreign
        ),
    ):
        with pytest.raises(ConversationNotFoundError):
            mutation()
        assert _lifecycle_snapshot(app, conversation["id"]) == before


def test_legacy_null_owner_is_uniformly_invisible_to_lifecycle_api(app_env) -> None:
    client, app = app_env
    conversation_id = "conv_" + "e" * 32
    conn = app.state.conn_factory()
    try:
        seed_pre_p23_legacy_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by=TEST_DISPLAY_NAME,
        )
    finally:
        conn.close()
    before = _lifecycle_snapshot(app, conversation_id)

    for method, suffix, body in (
        ("PATCH", "/title", {"lifecycle_revision": 0, "title": "不可认领"}),
        ("POST", "/conclude", {"lifecycle_revision": 0}),
        ("POST", "/archive", {"lifecycle_revision": 0}),
    ):
        response = client.request(
            method, f"/api/conversations/{conversation_id}{suffix}", json=body
        )
        assert response.status_code == 404, response.text
        assert _lifecycle_snapshot(app, conversation_id) == before


def test_projection_and_event_ledger_reject_raw_mutation_and_replace(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    conversation_id = conversation["id"]
    renamed = client.patch(
        f"/api/conversations/{conversation_id}/title",
        json={"lifecycle_revision": 0, "title": "受保护"},
    )
    assert renamed.status_code == 200
    conn = app.state.conn_factory()
    try:
        for sql, params in (
            ("UPDATE conversations SET title='绕过' WHERE id=?", (conversation_id,)),
            ("UPDATE conversations SET status='concluded' WHERE id=?", (conversation_id,)),
            ("UPDATE conversations SET archived_at='x' WHERE id=?", (conversation_id,)),
            (
                "INSERT OR REPLACE INTO conversations "
                "SELECT * FROM conversations WHERE id=?",
                (conversation_id,),
            ),
            (
                "UPDATE conversation_lifecycle_events SET title='篡改' "
                "WHERE conversation_id=?",
                (conversation_id,),
            ),
            (
                "DELETE FROM conversation_lifecycle_events WHERE conversation_id=?",
                (conversation_id,),
            ),
            (
                "INSERT OR REPLACE INTO conversation_lifecycle_events "
                "SELECT * FROM conversation_lifecycle_events WHERE conversation_id=?",
                (conversation_id,),
            ),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql, params)
        assert _lifecycle_snapshot(app, conversation_id) == (
            "受保护", "active", 1, None, 1
        )
    finally:
        conn.close()


def test_concurrent_same_revision_has_exactly_one_winner(app_env) -> None:
    client, app = app_env
    conversation = _open_conversation(client)
    barrier = threading.Barrier(2, timeout=5)
    principal = {"username": TEST_USERNAME, "display_name": TEST_DISPLAY_NAME}

    def rename(title: str) -> str:
        barrier.wait()
        try:
            app.state.conversation_service.rename(
                conversation["id"],
                title=title,
                lifecycle_revision=0,
                principal=principal,
            )
            return "won"
        except ConversationConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(rename, ["并发甲", "并发乙"]))

    assert sorted(results) == ["conflict", "won"]
    projection = _lifecycle_snapshot(app, conversation["id"])
    assert projection[0] in {"并发甲", "并发乙"}
    assert projection[1:] == ("active", 1, None, 1)
