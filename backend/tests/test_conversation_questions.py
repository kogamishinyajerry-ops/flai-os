"""P2.3 structured conversation Question/Answer API contract.

The seam under test is the authenticated HTTP API.  A Question is an ordinary
clarification owned by one exact ``username``; it is deliberately unrelated to
task review/sign-off.  Invalid, stale, foreign and duplicate submissions must
fail before the model or any conversation message is changed.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from conftest import (
    TEST_DISPLAY_NAME,
    TEST_USERNAME,
    login,
    seed_pre_p23_legacy_conversation,
    seed_user,
)

from backend.app.core.errors import ConversationQuestionConflictError, ModelUpstreamError
from backend.app.main import create_app
from backend.app.storage import repos


REPO_ROOT = Path(__file__).resolve().parents[2]


def _public_contract_validators():
    contracts = REPO_ROOT / "contracts"
    answer_schema = json.loads(
        (contracts / "conversation_answer.schema.json").read_text(encoding="utf-8")
    )
    question_schema = json.loads(
        (contracts / "conversation_question.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resource(
        answer_schema["$id"], Resource.from_contents(answer_schema)
    )
    checker = FormatChecker()
    return (
        Draft202012Validator(
            question_schema, registry=registry, format_checker=checker
        ),
        Draft202012Validator(answer_schema, format_checker=checker),
    )


class _SequenceGateway:
    """Deterministic external-boundary stub; entries may be replies or errors."""

    def __init__(self, entries: list[str | Exception]) -> None:
        self.entries = list(entries)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        index = len(self.calls) - 1
        if index >= len(self.entries):
            raise AssertionError("Question request unexpectedly invoked the model again")
        entry = self.entries[index]
        if isinstance(entry, Exception):
            raise entry
        return {
            "content": entry,
            "token_usage": None,
            "model_name": "p23-question-stub",
            "finish_reason": "stop",
        }


class _BarrierGateway:
    """Force two answer rounds to reach the model before either can commit."""

    def __init__(self) -> None:
        self.barrier = threading.Barrier(2, timeout=5)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        self.barrier.wait()
        return {
            "content": "并发回答后的唯一可提交回复。",
            "token_usage": None,
            "model_name": "p23-concurrency-stub",
            "finish_reason": "stop",
        }


def _question_reply(
    *,
    kind: str = "single_choice",
    prompt: str = "这次先覆盖哪个系统？",
) -> str:
    proposal: dict[str, Any] = {"kind": kind, "prompt": prompt}
    if kind == "single_choice":
        proposal.update(
            {
                "description": "请选择最接近的一项，也可以自行填写。",
                "options": [
                    {"label": "供电系统", "description": "主电源与应急电源"},
                    {"label": "液压系统"},
                ],
            }
        )
    return (
        "先确认分析范围。\n<<QUESTION>>\n"
        f"{json.dumps(proposal, ensure_ascii=False)}\n"
        "<<END_QUESTION>>"
    )


def _open_conversation(client: TestClient) -> str:
    response = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _history(client: TestClient, conversation_id: str) -> list[dict[str, Any]]:
    response = client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()["messages"]


def _issue_question(
    client: TestClient,
    conversation_id: str,
    *,
    content: str = "请帮我分析",
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": content}
    )
    assert response.status_code == 200, response.text
    message = response.json()["message"]
    question = message["question"]
    assert message["role"] == "assistant"
    assert message["message_id"].startswith("msg_")
    assert question["prompt_message_id"] == message["message_id"]
    return message, question


def _answer(
    client: TestClient,
    conversation_id: str,
    question_id: str,
    *,
    submission_id: str,
    payload: dict[str, Any],
) -> Any:
    return client.post(
        f"/api/conversations/{conversation_id}/questions/{question_id}/answer",
        json={
            "question_revision": 1,
            "submission_id": submission_id,
            "payload": payload,
        },
    )


def _question_in_history(
    client: TestClient, conversation_id: str, question_id: str
) -> dict[str, Any]:
    for message in _history(client, conversation_id):
        question = message.get("question")
        if question and question.get("id") == question_id:
            return question
    raise AssertionError(f"Question {question_id} was not restored with its prompt message")


def _row_counts(app: Any, tables: tuple[str, ...]) -> dict[str, int]:
    conn = app.state.conn_factory()
    try:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
    finally:
        conn.close()


@pytest.fixture()
def same_display_users(tmp_path: Path) -> Iterator[tuple[TestClient, TestClient, Any]]:
    """Two exact usernames with one colliding display name and separate cookies."""
    db_path = tmp_path / "same-display.db"
    app = create_app(
        agents_dir=REPO_ROOT / "agents",
        tools_dir=REPO_ROOT / "tools_impl",
        contracts_dir=REPO_ROOT / "contracts",
        db_path=db_path,
        uploads_dir=tmp_path / "uploads",
        task_runs_dir=tmp_path / "task-runs",
    )
    with TestClient(app) as alice:
        seed_user(
            db_path,
            username="alice",
            display_name="同名工程师",
            password="alice-pass-123",
        )
        seed_user(
            db_path,
            username="bob",
            display_name="同名工程师",
            password="bob-pass-123",
        )
        login(alice, username="alice", password="alice-pass-123")
        bob = TestClient(app)
        login(bob, username="bob", password="bob-pass-123")
        try:
            yield alice, bob, app
        finally:
            bob.close()


def test_explicit_question_is_issued_with_public_message_id_and_restored(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    assistant, question = _issue_question(client, conversation_id)

    assert assistant["content"] == "先确认分析范围。"
    assert "<<QUESTION>>" not in assistant["content"]
    assert question["schema_version"] == "conversation-question/v1"
    assert question["id"].startswith("q_")
    assert question["conversation_id"] == conversation_id
    assert question["revision"] == 1
    assert question["kind"] == "single_choice"
    assert question["asked_to_username"] == TEST_USERNAME
    assert question["status"] == "pending"
    assert question["answer"] is None and question["closed_at"] is None
    assert [option["id"] for option in question["options"]] == [
        "option_1",
        "option_2",
    ]

    first_history = _history(client, conversation_id)
    second_history = _history(client, conversation_id)
    assert [message["message_id"] for message in first_history] == [
        message["message_id"] for message in second_history
    ]
    assert all(message["message_id"].startswith("msg_") for message in first_history)
    restored = _question_in_history(client, conversation_id, question["id"])
    assert restored == question
    assert len(gateway.calls) == 1


def test_http_question_and_answer_projections_validate_against_public_schemas(
    app_env,
) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply(), "已根据回答继续。"])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    question_validator, answer_validator = _public_contract_validators()
    question_validator.validate(question)

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-contract-001",
        payload={"kind": "option", "option_id": "option_1"},
    )
    assert response.status_code == 200, response.text
    answered = response.json()["question"]
    question_validator.validate(answered)
    answer_validator.validate(answered["answer"])
    restored = _question_in_history(client, conversation_id, question["id"])
    question_validator.validate(restored)
    answer_validator.validate(restored["answer"])


@pytest.mark.parametrize(
    ("question_kind", "payload", "expected_payload"),
    [
        (
            "single_choice",
            {"kind": "option", "option_id": "option_1"},
            {"kind": "option", "option_id": "option_1"},
        ),
        (
            "single_choice",
            {"kind": "text", "text": "只看应急供电支路"},
            {"kind": "text", "text": "只看应急供电支路"},
        ),
        (
            "free_text",
            {"kind": "text", "text": "以故障树节点完整且可追溯为准"},
            {"kind": "text", "text": "以故障树节点完整且可追溯为准"},
        ),
    ],
)
def test_owner_can_answer_option_custom_text_or_free_text(
    app_env,
    question_kind: str,
    payload: dict[str, Any],
    expected_payload: dict[str, Any],
) -> None:
    client, app = app_env
    gateway = _SequenceGateway(
        [_question_reply(kind=question_kind), "已按你的回答继续整理。"]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-answer-001",
        payload=payload,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replayed"] is False
    assert body["answer_message"]["role"] == "user"
    assert body["answer_message"]["message_id"].startswith("msg_")
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "已按你的回答继续整理。"
    assert body["message"]["message_id"].startswith("msg_")
    assert body["question"]["status"] == "answered"
    answer = body["question"]["answer"]
    assert answer["schema_version"] == "conversation-answer/v1"
    assert answer["payload"] == expected_payload
    assert answer["answered_by_username"] == TEST_USERNAME
    assert answer["answer_message_id"] == body["answer_message"]["message_id"]
    assert answer["response_message_id"] == body["message"]["message_id"]
    assert _question_in_history(client, conversation_id, question["id"])["status"] == "answered"
    assert len(gateway.calls) == 2


def test_invalid_answer_shapes_and_unknown_option_are_422_before_model_or_write(
    app_env,
) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)

    invalid_bodies = [
        {
            "question_revision": 1,
            "submission_id": "submission-invalid-001",
            "payload": {"kind": "option", "option_id": "option_999"},
        },
        {
            "question_revision": 1,
            "submission_id": "submission-invalid-002",
            "payload": {
                "kind": "option",
                "option_id": "option_1",
                "action": "approve",
            },
        },
        {
            "question_revision": 1,
            "submission_id": "submission-invalid-003",
            "payload": {"kind": "text", "text": "答案", "reviewer": "alice"},
        },
        {
            "question_revision": 2,
            "submission_id": "submission-invalid-004",
            "payload": {"kind": "option", "option_id": "option_1"},
        },
        {
            "question_revision": 1,
            "submission_id": "submission-invalid-005",
            "payload": {"kind": "option", "option_id": "option_1"},
            "answered_by_username": "bob",
        },
        {
            "question_revision": True,
            "submission_id": "submission-invalid-006",
            "payload": {"kind": "option", "option_id": "option_1"},
        },
    ]
    url = (
        f"/api/conversations/{conversation_id}/questions/{question['id']}/answer"
    )
    for body in invalid_bodies:
        response = client.post(url, json=body)
        assert response.status_code == 422, (body, response.text)

    assert _history(client, conversation_id) == before
    assert _question_in_history(client, conversation_id, question["id"])["status"] == "pending"
    assert len(gateway.calls) == 1


def test_pending_question_blocks_generic_message_without_superseding_or_calling_model(
    app_env,
) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "试图绕开结构化回答直接继续"},
    )

    assert response.status_code == 409, response.text
    assert _history(client, conversation_id) == before
    assert _question_in_history(client, conversation_id, question["id"])["status"] == "pending"
    assert len(gateway.calls) == 1


def test_same_submission_and_payload_replays_without_second_model_or_write(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply(), "继续后的唯一回复。"])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    request = {
        "submission_id": "submission-replay-001",
        "payload": {"kind": "option", "option_id": "option_1"},
    }

    first = _answer(client, conversation_id, question["id"], **request)
    assert first.status_code == 200, first.text
    after_first = _history(client, conversation_id)
    second = _answer(client, conversation_id, question["id"], **request)

    assert second.status_code == 200, second.text
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["answer_message"] == first.json()["answer_message"]
    assert second.json()["message"] == first.json()["message"]
    assert second.json()["question"] == first.json()["question"]
    assert _history(client, conversation_id) == after_first
    assert len(gateway.calls) == 2


@pytest.mark.parametrize(
    ("submission_id", "payload"),
    [
        ("submission-distinct-002", {"kind": "option", "option_id": "option_1"}),
        ("submission-duplicate-001", {"kind": "option", "option_id": "option_2"}),
    ],
)
def test_answered_question_rejects_distinct_submission_or_changed_payload(
    app_env, submission_id: str, payload: dict[str, Any]
) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply(), "唯一回复。"])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    first = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-duplicate-001",
        payload={"kind": "option", "option_id": "option_1"},
    )
    assert first.status_code == 200, first.text
    before = _history(client, conversation_id)

    conflict = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id=submission_id,
        payload=payload,
    )

    assert conflict.status_code == 409, conflict.text
    assert _history(client, conversation_id) == before
    assert len(gateway.calls) == 2


def test_answer_can_atomically_issue_the_next_question(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway(
        [_question_reply(), _question_reply(kind="free_text", prompt="请补充验收标准。")]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, first_question = _issue_question(client, conversation_id)

    response = _answer(
        client,
        conversation_id,
        first_question["id"],
        submission_id="submission-next-question-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"]["status"] == "answered"
    next_question = body["message"]["question"]
    assert next_question["id"] != first_question["id"]
    assert next_question["kind"] == "free_text"
    assert next_question["status"] == "pending"
    assert next_question["prompt_message_id"] == body["message"]["message_id"]
    restored = _question_in_history(client, conversation_id, next_question["id"])
    assert restored == next_question


def test_concurrent_distinct_answers_have_exactly_one_committed_winner(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _SequenceGateway([_question_reply()])
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before_count = len(_history(client, conversation_id))

    barrier_gateway = _BarrierGateway()
    app.state.conversation_service.model_gateway = barrier_gateway
    principal = {"username": TEST_USERNAME, "display_name": TEST_DISPLAY_NAME}

    def submit(submission_id: str, option_id: str):
        try:
            return app.state.conversation_service.answer_question(
                conversation_id=conversation_id,
                question_id=question["id"],
                question_revision=1,
                submission_id=submission_id,
                payload={"kind": "option", "option_id": option_id},
                principal=principal,
            )
        except Exception as exc:  # assertion below checks the exact loser class
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda args: submit(*args),
            [
                ("submission-concurrent-001", "option_1"),
                ("submission-concurrent-002", "option_2"),
            ],
        ))

    winners = [result for result in results if isinstance(result, dict)]
    losers = [result for result in results if isinstance(result, Exception)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert isinstance(losers[0], ConversationQuestionConflictError)
    assert len(_history(client, conversation_id)) == before_count + 2
    assert _question_in_history(client, conversation_id, question["id"])["status"] == "answered"
    assert len(barrier_gateway.calls) == 2


def test_model_failure_leaves_question_pending_and_messages_unchanged(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway(
        [
            _question_reply(),
            ModelUpstreamError("上游网络错误：question answer timeout"),
        ]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-upstream-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 502, response.text
    assert _history(client, conversation_id) == before
    restored = _question_in_history(client, conversation_id, question["id"])
    assert restored["status"] == "pending" and restored["answer"] is None
    assert len(gateway.calls) == 2


def test_malformed_next_question_leaves_current_question_pending(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway(
        [
            _question_reply(),
            "下一问损坏。\n<<QUESTION>>\n"
            '{"kind":"single_choice","prompt":"缺选项","options":[]}'
            "\n<<END_QUESTION>>",
        ]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-malformed-next-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 502, response.text
    assert _history(client, conversation_id) == before
    pending = _question_in_history(client, conversation_id, question["id"])
    assert pending["status"] == "pending" and pending["answer"] is None
    assert len(gateway.calls) == 2


def test_concluded_conversation_rejects_answer_before_model_or_write(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)
    before_messages = [
        (item["message_id"], item["role"], item["content"]) for item in before
    ]
    concluded = client.post(
        f"/api/conversations/{conversation_id}/conclude",
        json={"lifecycle_revision": 0},
    )
    assert concluded.status_code == 200, concluded.text

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-closed-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 409, response.text
    after = _history(client, conversation_id)
    assert [
        (item["message_id"], item["role"], item["content"]) for item in after
    ] == before_messages
    closed = _question_in_history(client, conversation_id, question["id"])
    assert closed["status"] == "superseded"
    assert closed["answer"] is None
    assert len(gateway.calls) == 1


def test_foreign_same_display_name_cannot_answer_and_question_stays_pending(
    same_display_users,
) -> None:
    alice, bob, app = same_display_users
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(alice)
    _, question = _issue_question(alice, conversation_id)
    before = _history(alice, conversation_id)

    response = _answer(
        bob,
        conversation_id,
        question["id"],
        submission_id="submission-foreign-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 404, response.text
    assert _history(alice, conversation_id) == before
    assert _question_in_history(alice, conversation_id, question["id"])["status"] == "pending"
    assert len(gateway.calls) == 1


def test_legacy_null_owner_answer_surface_is_uniform_404(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = "conv_" + "a" * 32
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

    response = _answer(
        client,
        conversation_id,
        "q_" + "b" * 32,
        submission_id="submission-legacy-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 404, response.text
    assert gateway.calls == []


def test_exact_expiry_boundary_is_409_and_marks_question_expired(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The equality boundary is expired: ``now >= expires_at`` (never truthiness)."""
    from backend.app.api import conversations as conversations_api
    from backend.app.runtime import conversation as conversation_runtime

    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway

    def freeze(iso_timestamp: str) -> None:
        clock = lambda: iso_timestamp
        monkeypatch.setattr(repos, "_now_iso", clock)
        # P2.3 may keep the transaction-time clock in either boundary; pin both
        # named seams so the equality case is deterministic rather than sleeping.
        monkeypatch.setattr(conversation_runtime, "_now_iso", clock, raising=False)
        monkeypatch.setattr(conversations_api, "_now_iso", clock, raising=False)

    freeze("2026-01-01T00:00:00+00:00")
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)
    before_messages = [
        (item["message_id"], item["role"], item["content"]) for item in before
    ]
    freeze(question["expires_at"])

    response = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-expired-001",
        payload={"kind": "option", "option_id": "option_1"},
    )

    assert response.status_code == 409, response.text
    after = _history(client, conversation_id)
    assert [
        (item["message_id"], item["role"], item["content"]) for item in after
    ] == before_messages
    expired = _question_in_history(client, conversation_id, question["id"])
    assert expired["status"] == "expired"
    assert expired["answer"] is None
    assert len(gateway.calls) == 1


def test_question_answer_is_isolated_from_tasks_reviews_events_and_samples(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply(), "已继续。"])
    app.state.conversation_service.model_gateway = gateway
    tables = ("tasks", "task_events", "samples")
    before = _row_counts(app, tables)
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)

    fake_review = client.post(
        f"/api/tasks/{question['id']}/review", json={"action": "approve"}
    )
    assert fake_review.status_code == 404, fake_review.text
    answered = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-isolation-001",
        payload={"kind": "option", "option_id": "option_1"},
    )
    assert answered.status_code == 200, answered.text

    assert _row_counts(app, tables) == before
    assert answered.json()["question"]["answer"]["answered_by_username"] == TEST_USERNAME


def test_answer_round_rolls_back_if_assistant_message_insert_fails(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway(
        [_question_reply(), "这条回复会被故障注入拦截。", "重试成功。"]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)
    before = _history(client, conversation_id)

    conn = app.state.conn_factory()
    try:
        conn.execute(
            """
            CREATE TRIGGER p23_force_answer_assistant_failure
            BEFORE INSERT ON conversation_messages
            WHEN NEW.role = 'assistant'
            BEGIN
                SELECT RAISE(ABORT, 'forced answer assistant insert failure');
            END
            """
        )
    finally:
        conn.close()

    try:
        response = None
        caught: BaseException | None = None
        try:
            response = _answer(
                client,
                conversation_id,
                question["id"],
                submission_id="submission-rollback-001",
                payload={"kind": "option", "option_id": "option_1"},
            )
        except sqlite3.IntegrityError as exc:
            caught = exc
        if caught is None:
            assert response is not None and response.status_code >= 500, response.text
    finally:
        conn = app.state.conn_factory()
        try:
            conn.execute("DROP TRIGGER p23_force_answer_assistant_failure")
        finally:
            conn.close()

    assert _history(client, conversation_id) == before
    pending = _question_in_history(client, conversation_id, question["id"])
    assert pending["status"] == "pending" and pending["answer"] is None

    retry = _answer(
        client,
        conversation_id,
        question["id"],
        submission_id="submission-rollback-001",
        payload={"kind": "option", "option_id": "option_1"},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["replayed"] is False


def test_question_spec_is_sqlite_immutable_and_rows_are_not_replaceable(app_env) -> None:
    client, app = app_env
    gateway = _SequenceGateway([_question_reply()])
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    _, question = _issue_question(client, conversation_id)

    conn = app.state.conn_factory()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE conversation_questions SET prompt = ? WHERE id = ?",
                ("被篡改的问题", question["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE conversation_questions SET asked_to_username = ? WHERE id = ?",
                ("bob", question["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "DELETE FROM conversation_questions WHERE id = ?", (question["id"],)
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT OR REPLACE INTO conversation_questions "
                "SELECT * FROM conversation_questions WHERE id = ?",
                (question["id"],),
            )
    finally:
        conn.close()

    restored = _question_in_history(client, conversation_id, question["id"])
    assert restored["prompt"] == "这次先覆盖哪个系统？"
    assert restored["asked_to_username"] == TEST_USERNAME
    assert restored["status"] == "pending"
