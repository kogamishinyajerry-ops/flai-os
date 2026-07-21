"""跨刷新会话恢复与 safe-auto 当前轮附件来源契约。

这些测试只走认证 HTTP 入口；浏览器重建服务实例后仍由数据库回执兜住幂等，
附件来源不可信时必须在模型调用与消息/任务落库前 fail-closed。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from backend.app.runtime.conversation import ConversationService
from backend.app.storage import repos
from conftest import TEST_DISPLAY_NAME, TEST_ROLE, TEST_USERNAME, login, seed_user


class _ClarifyingStub:
    def __init__(self) -> None:
        self.calls = 0

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls += 1
        return {
            "content": "请补充完整的结构化输入。",
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


class _CapturingDispatch:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def eligible_agent_ids(self, actor_role: str) -> set[str]:
        return set()

    def dispatch_in_transaction(self, conn, **kwargs: Any) -> dict[str, Any]:
        assert conn.in_transaction
        self.calls.append(kwargs)
        return {
            "status": "awaiting_plan",
            "request_id": kwargs["request_id"],
            "task_ids": [],
            "issues": [],
            "replayed": False,
        }


class _TamperDuringChatStub(_ClarifyingStub):
    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = Path(path)

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = super().chat(profile, messages, **kwargs)
        self.path.write_bytes(b"TAMPERED")
        return result


def _create(client, *, request_id: str, agent_id: str = "guide_agent"):
    return client.post(
        "/api/conversations",
        json={"agent_id": agent_id, "request_id": request_id},
    )


def _safe_auto(client, conversation_id: str, *, request_id: str, file_ids=None):
    return client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "content": "请处理本轮输入",
            "file_ids": file_ids or [],
            "execution_mode": "safe_auto",
            "request_id": request_id,
        },
    )


def _upload(client, *, classification: str = "internal", task_id: str | None = None) -> str:
    data = {"classification": classification}
    if task_id is not None:
        data["task_id"] = task_id
    response = client.post(
        "/api/files/upload",
        files={"file": ("evidence.txt", b"current turn evidence")},
        data=data,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _assert_no_turn_side_effects(
    app, conversation_id: str, *, request_id: str | None = None
) -> None:
    conn = app.state.conn_factory()
    try:
        assert repos.list_messages(conn, conversation_id) == []
        assert repos.list_tasks(conn, conversation_id=conversation_id) == []
        if request_id is not None:
            assert repos.get_conversation_dispatch(
                conn, conversation_id, request_id
            ) is None
    finally:
        conn.close()


def test_auth_login_and_me_expose_server_derived_role(app_env) -> None:
    client, _app = app_env
    login = client.post(
        "/api/auth/login",
        json={"username": TEST_USERNAME, "password": "test-password-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json() == {
        "username": TEST_USERNAME,
        "display_name": TEST_DISPLAY_NAME,
        "role": TEST_ROLE,
    }
    assert client.get("/api/auth/me").json() == {
        "username": TEST_USERNAME,
        "display_name": TEST_DISPLAY_NAME,
        "role": TEST_ROLE,
    }


def test_create_conversation_same_owner_and_request_replays_one_row(app_env) -> None:
    client, app = app_env

    first = _create(client, request_id="create_reload_001")
    assert first.status_code == 200, first.text
    app.state.conversation_service = ConversationService(
        app.state.agent_registry,
        app.state.model_gateway,
        app.state.conn_factory,
        uploads_dir=app.state.uploads_dir,
    )
    replay = _create(client, request_id="create_reload_001")

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    conn = app.state.conn_factory()
    try:
        rows = repos.list_conversations(conn, created_by=TEST_DISPLAY_NAME)
        assert [row["id"] for row in rows] == [first.json()["id"]]
    finally:
        conn.close()


def test_create_conversation_request_key_is_bound_to_agent(app_env) -> None:
    client, app = app_env
    first = _create(client, request_id="create_agent_bound_001")
    assert first.status_code == 200, first.text

    guide = app.state.agent_registry.get("guide_agent")
    assert guide is not None
    alias_id = "guide_agent_alias_for_test"
    app.state.agent_registry._agents[alias_id] = {**copy.deepcopy(guide), "id": alias_id}
    try:
        conflict = _create(
            client,
            request_id="create_agent_bound_001",
            agent_id=alias_id,
        )
    finally:
        app.state.agent_registry._agents.pop(alias_id, None)

    assert conflict.status_code == 409
    assert "request_id" in conflict.json()["detail"]
    conn = app.state.conn_factory()
    try:
        assert len(repos.list_conversations(conn, created_by=TEST_DISPLAY_NAME)) == 1
    finally:
        conn.close()


def test_create_conversation_request_key_is_namespaced_by_authenticated_owner(
    app_env,
) -> None:
    client, app = app_env
    first = _create(client, request_id="create_owner_bound_001")
    assert first.status_code == 200, first.text

    seed_user(
        app.state.db_path,
        username="second_engineer",
        display_name="第二工程师",
        password="second-password-123",
        role="admin",
    )
    login(client, username="second_engineer", password="second-password-123")
    second = _create(client, request_id="create_owner_bound_001")

    assert second.status_code == 200, second.text
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["created_by_username"] == "second_engineer"


def test_safe_auto_receipt_replays_after_service_reconstruction(app_env) -> None:
    client, app = app_env
    first_stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = first_stub
    conversation = _create(client, request_id="create_reload_dispatch_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]

    first = _safe_auto(
        client,
        conversation_id,
        request_id="turn_reload_dispatch_001",
    )
    assert first.status_code == 200, first.text
    assert first_stub.calls == 1

    replay_stub = _ClarifyingStub()
    app.state.conversation_service = ConversationService(
        app.state.agent_registry,
        replay_stub,
        app.state.conn_factory,
        uploads_dir=app.state.uploads_dir,
    )
    replay = _safe_auto(
        client,
        conversation_id,
        request_id="turn_reload_dispatch_001",
    )

    assert replay.status_code == 200, replay.text
    assert replay_stub.calls == 0
    assert replay.json()["execution"]["replayed"] is True
    conn = app.state.conn_factory()
    try:
        assert len(repos.list_messages(conn, conversation_id)) == 2
        assert repos.list_tasks(conn, conversation_id=conversation_id) == []
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    [
        ("legacy_uploader", 409),
        ("sensitive", 409),
        ("output", 409),
        ("task_owned", 409),
        ("foreign_uploader", 403),
    ],
)
def test_safe_auto_rejects_untrusted_current_attachment_before_model(
    app_env, mutation: str, expected_status: int
) -> None:
    client, app = app_env
    stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = stub
    conversation = _create(client, request_id=f"create_attachment_{mutation}_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]

    task_id = None
    classification = "sensitive" if mutation == "sensitive" else "internal"
    if mutation == "task_owned":
        task = client.post(
            "/api/tasks",
            json={"agent_id": "hello_agent", "inputs": {"name": "owner"}},
        )
        assert task.status_code == 200, task.text
        task_id = task.json()["id"]
    file_id = _upload(client, classification=classification, task_id=task_id)

    conn = app.state.conn_factory()
    try:
        if mutation == "legacy_uploader":
            conn.execute(
                "UPDATE files SET uploaded_by_username = NULL WHERE id = ?", (file_id,)
            )
        elif mutation == "foreign_uploader":
            conn.execute(
                "UPDATE files SET uploaded_by_username = 'other_user' WHERE id = ?",
                (file_id,),
            )
        elif mutation == "output":
            conn.execute("UPDATE files SET kind = 'output' WHERE id = ?", (file_id,))
    finally:
        conn.close()

    response = _safe_auto(
        client,
        conversation_id,
        request_id=f"turn_attachment_{mutation}_001",
        file_ids=[file_id],
    )

    assert response.status_code == expected_status, response.text
    assert stub.calls == 0
    _assert_no_turn_side_effects(app, conversation_id)


def test_safe_auto_duplicate_attachment_ids_are_rejected_before_model(app_env) -> None:
    client, app = app_env
    stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = stub
    conversation = _create(client, request_id="create_attachment_duplicate_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    file_id = _upload(client)

    response = _safe_auto(
        client,
        conversation_id,
        request_id="turn_attachment_duplicate_001",
        file_ids=[file_id, file_id],
    )

    assert response.status_code == 422
    assert stub.calls == 0
    _assert_no_turn_side_effects(app, conversation_id)


def test_safe_auto_passes_only_current_verified_attachment_evidence_to_dispatch(
    app_env,
) -> None:
    client, app = app_env
    stub = _ClarifyingStub()
    capture = _CapturingDispatch()
    app.state.conversation_service.model_gateway = stub
    app.state.conversation_service.guide_plan_dispatch = capture
    conversation = _create(client, request_id="create_attachment_evidence_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    upload = client.post(
        "/api/files/upload",
        files={"file": ("evidence.txt", b"immutable evidence")},
    )
    assert upload.status_code == 200, upload.text
    file_row = upload.json()

    response = _safe_auto(
        client,
        conversation_id,
        request_id="turn_attachment_evidence_001",
        file_ids=[file_row["id"]],
    )

    assert response.status_code == 200, response.text
    assert stub.calls == 1
    assert len(capture.calls) == 1
    assert capture.calls[0]["has_attachments"] is True
    assert capture.calls[0]["has_historical_attachments"] is False
    assert capture.calls[0]["current_file_bindings"] == [
        {
            "file_id": file_row["id"],
            "sha256": file_row["sha256"],
            "classification": "internal",
            "uploaded_by_username": TEST_USERNAME,
        }
    ]


@pytest.mark.parametrize("mutation", ["same_size_tamper", "missing_blob", "malformed_sha"])
def test_safe_auto_rejects_unverified_attachment_blob_before_model(
    app_env, mutation: str
) -> None:
    client, app = app_env
    stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = stub
    conversation = _create(client, request_id=f"create_blob_{mutation}_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    upload = client.post(
        "/api/files/upload",
        files={"file": ("evidence.txt", b"ORIGINAL")},
    )
    assert upload.status_code == 200, upload.text
    file_row = upload.json()

    if mutation == "same_size_tamper":
        Path(file_row["path"]).write_bytes(b"TAMPERED")
    elif mutation == "missing_blob":
        Path(file_row["path"]).unlink()
    else:
        conn = app.state.conn_factory()
        try:
            conn.execute(
                "UPDATE files SET sha256 = 'malformed' WHERE id = ?", (file_row["id"],)
            )
        finally:
            conn.close()

    request_id = f"turn_blob_{mutation}_001"
    response = _safe_auto(
        client,
        conversation_id,
        request_id=request_id,
        file_ids=[file_row["id"]],
    )

    assert response.status_code == 409, response.text
    assert stub.calls == 0
    _assert_no_turn_side_effects(
        app, conversation_id, request_id=request_id
    )


def test_safe_auto_rechecks_attachment_blob_after_model_before_commit(app_env) -> None:
    client, app = app_env
    conversation = _create(client, request_id="create_blob_toc_tou_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    upload = client.post(
        "/api/files/upload",
        files={"file": ("evidence.txt", b"ORIGINAL")},
    )
    assert upload.status_code == 200, upload.text
    file_row = upload.json()
    stub = _TamperDuringChatStub(file_row["path"])
    app.state.conversation_service.model_gateway = stub
    request_id = "turn_blob_toc_tou_001"

    response = _safe_auto(
        client,
        conversation_id,
        request_id=request_id,
        file_ids=[file_row["id"]],
    )

    assert response.status_code == 409, response.text
    assert stub.calls == 1
    _assert_no_turn_side_effects(
        app, conversation_id, request_id=request_id
    )


def test_plan_only_keeps_legacy_attachment_behavior(app_env) -> None:
    client, app = app_env
    stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = stub
    conversation = _create(client, request_id="create_attachment_plan_only_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    file_id = _upload(client)
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE files SET uploaded_by_username = 'other_user' WHERE id = ?", (file_id,)
        )
    finally:
        conn.close()

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "仅生成建议", "file_ids": [file_id]},
    )

    assert response.status_code == 200, response.text
    assert stub.calls == 1


def test_safe_auto_rejects_historical_attachment_before_model(app_env) -> None:
    client, app = app_env
    conversation = _create(client, request_id="create_historical_attachment_001")
    assert conversation.status_code == 200, conversation.text
    conversation_id = conversation.json()["id"]
    file_id = _upload(client)

    app.state.conversation_service.model_gateway = _ClarifyingStub()
    seeded = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "仅保留为历史资料", "file_ids": [file_id]},
    )
    assert seeded.status_code == 200, seeded.text

    safe_auto_stub = _ClarifyingStub()
    app.state.conversation_service.model_gateway = safe_auto_stub
    response = _safe_auto(
        client,
        conversation_id,
        request_id="turn_historical_attachment_001",
    )

    assert response.status_code == 409, response.text
    assert safe_auto_stub.calls == 0
    conn = app.state.conn_factory()
    try:
        assert len(repos.list_messages(conn, conversation_id)) == 2
        assert repos.list_tasks(conn, conversation_id=conversation_id) == []
    finally:
        conn.close()
