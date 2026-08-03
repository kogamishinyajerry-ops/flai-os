"""Owner-scoped authorization at the conversation and file HTTP seams.

The platform has no role axis in V1, so stable authenticated usernames are the
only ownership proof.  Missing, legacy NULL, and other-user resources share the
same generic 404 response; callers cannot use these APIs as existence oracles.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.api import object_authorization as oauth
from backend.app.storage import repos
from backend.app.storage.db import init_db
from backend.tests.test_asset_candidates_api import (
    _create_candidate,
    _decision,
    _seed_task,
)
from backend.tests.test_m6_guide_conversation import _CannedStub, _StreamingStub
from conftest import TEST_DISPLAY_NAME, TEST_USERNAME, login, seed_user

BOB_USERNAME = "owner_scope_bob"
BOB_PASSWORD = "owner-scope-bob-password"


@pytest.fixture()
def owner_clients(app_env) -> Iterator[tuple[TestClient, TestClient, object]]:
    alice_client, app = app_env
    seed_user(
        app.state.db_path,
        username=BOB_USERNAME,
        # Deliberately collide display names: authorization must use username.
        display_name=TEST_DISPLAY_NAME,
        password=BOB_PASSWORD,
    )
    bob_client = TestClient(app)
    login(bob_client, username=BOB_USERNAME, password=BOB_PASSWORD)
    try:
        yield alice_client, bob_client, app
    finally:
        bob_client.close()


def _open_conversation(client: TestClient) -> str:
    response = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _asset_preview_request() -> dict:
    return {
        "schema_version": "asset_draft_preview_request.v1",
        "generalization": {
            "title": "入口边界复核",
            "trigger": "收到待复核输入",
            "desired_outcome": "形成复核清单",
            "inputs": ["输入文件"],
            "outputs": ["复核清单"],
            "steps": ["核对输入"],
            "evidence_requirements": ["保留来源"],
            "human_decision_points": ["工程师确认冲突"],
            "limitations": ["不替代工程师签发"],
        },
    }


class _RecordingGateway:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *_args, **_kwargs) -> dict:
        self.calls += 1
        return {
            "content": "这条回复不应被跨 owner 请求触发。",
            "token_usage": None,
            "model_name": "authorization-test-stub",
            "finish_reason": "stop",
        }


def test_conversation_list_and_detail_hide_other_and_unproven_owners(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    alice_conversation_id = _open_conversation(alice_client)

    bob_rows = bob_client.get("/api/conversations")
    assert bob_rows.status_code == 200
    assert alice_conversation_id not in {row["id"] for row in bob_rows.json()}

    hidden = bob_client.get(f"/api/conversations/{alice_conversation_id}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "资源不存在或不可访问"}

    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id="conv_legacy_owner_null",
            agent_id="guide_agent",
            created_by=TEST_DISPLAY_NAME,
        )
    finally:
        conn.close()

    legacy = alice_client.get("/api/conversations/conv_legacy_owner_null")
    assert legacy.status_code == 404
    assert legacy.json() == {"detail": "资源不存在或不可访问"}

    alice_rows = alice_client.get("/api/conversations")
    assert alice_rows.status_code == 200
    assert alice_conversation_id in {row["id"] for row in alice_rows.json()}
    assert "conv_legacy_owner_null" not in {row["id"] for row in alice_rows.json()}
    assert TEST_USERNAME != BOB_USERNAME


def test_conversation_list_excludes_lineage_overflow_before_pagination(
    owner_clients,
    monkeypatch,
) -> None:
    alice_client, _bob_client, app = owner_clients
    monkeypatch.setattr(oauth, "_MAX_LINEAGE_CONVERSATION_MESSAGES", 4)
    monkeypatch.setattr(
        repos,
        "CONVERSATION_LINEAGE_MAX_MESSAGES",
        4,
        raising=False,
    )
    readable_id = _open_conversation(alice_client)
    overflow_id = _open_conversation(alice_client)
    conn = app.state.conn_factory()
    try:
        for index in range(5):
            repos.append_message(
                conn,
                conversation_id=overflow_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"overflow witness {index}",
                file_ids=[],
            )
    finally:
        conn.close()

    hidden = alice_client.get(f"/api/conversations/{overflow_id}")
    assert hidden.status_code == 404, hidden.text
    assert hidden.json() == {"detail": "资源不存在或不可访问"}

    first_page = alice_client.get(
        "/api/conversations",
        params={"limit": 1, "offset": 0},
    )
    assert first_page.status_code == 200, first_page.text
    assert [row["id"] for row in first_page.json()] == [readable_id]


def test_other_owner_conversation_endpoints_are_generic_404_with_zero_side_effects(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    gateway = _RecordingGateway()
    app.state.conversation_service.model_gateway = gateway

    probes = [
        bob_client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "越权消息不得触发模型"},
        ),
        bob_client.post(
            f"/api/conversations/{conversation_id}/messages/stream",
            json={"content": "越权流式消息不得启动"},
        ),
        bob_client.post(f"/api/conversations/{conversation_id}/conclude"),
        bob_client.get(f"/api/conversations/{conversation_id}/model_calls"),
        bob_client.get(f"/api/conversations/{conversation_id}/tasks"),
        bob_client.post(
            f"/api/conversations/{conversation_id}/asset-draft-preview",
            json=_asset_preview_request(),
        ),
    ]

    for response in probes:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}

    unchanged = alice_client.get(f"/api/conversations/{conversation_id}")
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "active"
    assert unchanged.json()["messages"] == []
    assert gateway.calls == 0


def test_file_download_and_direct_attachment_require_exact_owner(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    internal_upload = alice_client.post(
        "/api/files/upload",
        files={"file": ("alice.txt", b"alice internal payload", "text/plain")},
        data={"classification": "internal"},
    )
    assert internal_upload.status_code == 200, internal_upload.text
    internal_id = internal_upload.json()["id"]

    assert alice_client.get(f"/api/files/{internal_id}/download").content == (
        b"alice internal payload"
    )
    hidden_download = bob_client.get(f"/api/files/{internal_id}/download")
    assert hidden_download.status_code == 404
    assert hidden_download.json() == {"detail": "资源不存在或不可访问"}

    bob_conversation_id = _open_conversation(bob_client)
    gateway = _RecordingGateway()
    app.state.conversation_service.model_gateway = gateway
    hidden_attachment = bob_client.post(
        f"/api/conversations/{bob_conversation_id}/messages",
        json={"content": "尝试附加他人文件", "file_ids": [internal_id]},
    )
    assert hidden_attachment.status_code == 404
    assert hidden_attachment.json() == {"detail": "资源不存在或不可访问"}
    bob_conversation = bob_client.get(
        f"/api/conversations/{bob_conversation_id}"
    ).json()
    assert bob_conversation["messages"] == []
    assert gateway.calls == 0

    sensitive_upload = alice_client.post(
        "/api/files/upload",
        files={"file": ("sensitive.txt", b"sensitive payload", "text/plain")},
        data={"classification": "sensitive"},
    )
    assert sensitive_upload.status_code == 200, sensitive_upload.text
    sensitive_id = sensitive_upload.json()["id"]
    sensitive_download = alice_client.get(
        f"/api/files/{sensitive_id}/download"
    )
    assert sensitive_download.status_code == 403

    legacy_path = app.state.uploads_dir / "legacy-null-owner.txt"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_payload = b"legacy owner is unknown"
    legacy_path.write_bytes(legacy_payload)

    output_task_id = "task_owner_scoped_output"
    output_path = app.state.task_runs_dir / output_task_id / "output" / "result.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_payload = b"owned task output"
    output_path.write_bytes(output_payload)

    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn,
            file_id="file_legacy_owner_null",
            task_id=None,
            kind="input",
            filename=legacy_path.name,
            path=str(legacy_path),
            size_bytes=len(legacy_payload),
            sha256=hashlib.sha256(legacy_payload).hexdigest(),
            classification="internal",
        )
        repos.create_task(
            conn,
            task_id=output_task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="owner-scoped output",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=TEST_USERNAME,
        )
        repos.create_file(
            conn,
            file_id="file_owned_task_output",
            task_id=output_task_id,
            kind="output",
            filename=output_path.name,
            path=str(output_path),
            size_bytes=len(output_payload),
            sha256=hashlib.sha256(output_payload).hexdigest(),
            classification="internal",
        )
        repos.set_task_outputs(
            conn, output_task_id, ["file_owned_task_output"]
        )
    finally:
        conn.close()

    legacy = alice_client.get("/api/files/file_legacy_owner_null/download")
    assert legacy.status_code == 404
    assert legacy.json() == {"detail": "资源不存在或不可访问"}
    assert (
        alice_client.get("/api/files/file_owned_task_output/download").content
        == output_payload
    )
    hidden_output = bob_client.get("/api/files/file_owned_task_output/download")
    assert hidden_output.status_code == 404
    assert hidden_output.json() == {"detail": "资源不存在或不可访问"}


def test_output_download_rejects_cross_owner_task_directory_as_generic_404(
    owner_clients,
) -> None:
    alice_client, _bob_client, app = owner_clients
    alice_task_id = "task_alice_output_path_owner"
    bob_task_id = "task_bob_output_path_owner"

    alice_path = app.state.task_runs_dir / alice_task_id / "output" / "result.txt"
    alice_path.parent.mkdir(parents=True, exist_ok=True)
    alice_payload = b"alice authoritative output"
    alice_path.write_bytes(alice_payload)

    bob_path = app.state.task_runs_dir / bob_task_id / "output" / "private.txt"
    bob_path.parent.mkdir(parents=True, exist_ok=True)
    bob_payload = b"bob private output"
    bob_path.write_bytes(bob_payload)

    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id=alice_task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="alice output path owner",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=TEST_USERNAME,
        )
        repos.create_task(
            conn,
            task_id=bob_task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="bob output path owner",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=BOB_USERNAME,
        )
        repos.create_file(
            conn,
            file_id="file_alice_authoritative_output",
            task_id=alice_task_id,
            kind="output",
            filename=alice_path.name,
            path=str(alice_path),
            size_bytes=len(alice_payload),
            sha256=hashlib.sha256(alice_payload).hexdigest(),
            classification="internal",
        )
        # Simulate a poisoned legacy row: its logical relation names Alice's task,
        # while its physical path escapes into Bob's task directory.
        repos.create_file(
            conn,
            file_id="file_alice_row_bob_path",
            task_id=alice_task_id,
            kind="output",
            filename=bob_path.name,
            path=str(bob_path),
            size_bytes=len(bob_payload),
            sha256=hashlib.sha256(bob_payload).hexdigest(),
            classification="internal",
        )
        repos.create_file(
            conn,
            file_id="file_alice_sensitive_row_bob_path",
            task_id=alice_task_id,
            kind="output",
            filename=bob_path.name,
            path=str(bob_path),
            size_bytes=len(bob_payload),
            sha256=hashlib.sha256(bob_payload).hexdigest(),
            classification="sensitive",
        )
        repos.set_task_outputs(
            conn,
            alice_task_id,
            [
                "file_alice_authoritative_output",
                "file_alice_row_bob_path",
                "file_alice_sensitive_row_bob_path",
            ],
        )
    finally:
        conn.close()

    legitimate = alice_client.get("/api/files/file_alice_authoritative_output/download")
    assert legitimate.status_code == 200, legitimate.text
    assert legitimate.content == alice_payload

    missing = alice_client.get("/api/files/file_missing_output/download")
    for poisoned_id in (
        "file_alice_row_bob_path",
        "file_alice_sensitive_row_bob_path",
    ):
        poisoned = alice_client.get(f"/api/files/{poisoned_id}/download")
        assert poisoned.status_code == missing.status_code == 404
        assert poisoned.json() == missing.json() == {"detail": "资源不存在或不可访问"}
        assert poisoned.content != bob_payload


def test_historical_cross_owner_attachment_blocks_new_round_before_model_or_write(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    bob_upload = bob_client.post(
        "/api/files/upload",
        files={"file": ("bob.txt", b"bob private input", "text/plain")},
        data={"classification": "internal"},
    )
    assert bob_upload.status_code == 200, bob_upload.text
    bob_file_id = bob_upload.json()["id"]

    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="模拟旧版本残留的跨 owner 附件",
            file_ids=[bob_file_id],
        )
        before_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    gateway = _RecordingGateway()
    app.state.conversation_service.model_gateway = gateway
    probes = [
        alice_client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "不得把历史越权附件带入模型"},
        ),
        alice_client.post(
            f"/api/conversations/{conversation_id}/messages/stream",
            json={"content": "流式也必须在启动前拒绝"},
        ),
        alice_client.post(
            f"/api/conversations/{conversation_id}/asset-draft-preview",
            json=_asset_preview_request(),
        ),
        alice_client.get(f"/api/conversations/{conversation_id}/model_calls"),
        alice_client.get(f"/api/conversations/{conversation_id}/tasks"),
    ]
    for response in probes:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}

    conn = app.state.conn_factory()
    try:
        after_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
        status = conn.execute(
            "SELECT status FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert after_count == before_count
    assert status == "active"
    assert gateway.calls == 0


def test_conversation_owner_filter_is_applied_before_sql_pagination(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    alice_first = _open_conversation(alice_client)
    bob_first = _open_conversation(bob_client)
    alice_tainted = _open_conversation(alice_client)
    bob_second = _open_conversation(bob_client)
    bob_upload = bob_client.post(
        "/api/files/upload",
        files={"file": ("pagination.txt", b"must stay with bob", "text/plain")},
        data={"classification": "internal"},
    )
    assert bob_upload.status_code == 200, bob_upload.text
    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=alice_tainted,
            role="user",
            content="legacy tainted row must be removed before pagination",
            file_ids=[bob_upload.json()["id"]],
        )
    finally:
        conn.close()
    alice_latest = _open_conversation(alice_client)

    alice_page_1 = alice_client.get(
        "/api/conversations", params={"limit": 1, "offset": 0}
    ).json()
    alice_page_2 = alice_client.get(
        "/api/conversations", params={"limit": 1, "offset": 1}
    ).json()
    bob_page_1 = bob_client.get(
        "/api/conversations", params={"limit": 1, "offset": 0}
    ).json()
    bob_page_2 = bob_client.get(
        "/api/conversations", params={"limit": 1, "offset": 1}
    ).json()

    assert [row["id"] for row in alice_page_1] == [alice_latest]
    assert [row["id"] for row in alice_page_2] == [alice_first]
    assert alice_tainted not in {
        row["id"]
        for row in alice_client.get(
            "/api/conversations", params={"limit": 500}
        ).json()
    }
    assert [row["id"] for row in bob_page_1] == [bob_second]
    assert [row["id"] for row in bob_page_2] == [bob_first]


@pytest.mark.parametrize(
    "stored_file_ids",
    [
        "{not-json",
        json.dumps({}, ensure_ascii=False),
        json.dumps("not-an-array", ensure_ascii=False),
        json.dumps([42]),
        json.dumps([""]),
        json.dumps([" padded-id "]),
        json.dumps(["x" * 65]),
        json.dumps(["file_missing"]),
    ],
)
def test_conversation_list_excludes_malformed_or_unproven_attachment_lineage(
    owner_clients,
    stored_file_ids: str,
) -> None:
    alice_client, _bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="malformed lineage must not enter list projection",
            file_ids=[],
        )
        conn.execute(
            "UPDATE conversation_messages SET file_ids = ? "
            "WHERE conversation_id = ?",
            (stored_file_ids, conversation_id),
        )
    finally:
        conn.close()

    listed = alice_client.get("/api/conversations", params={"limit": 500})
    assert listed.status_code == 200, listed.text
    assert conversation_id not in {row["id"] for row in listed.json()}
    hidden = alice_client.get(f"/api/conversations/{conversation_id}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "资源不存在或不可访问"}


def test_upload_cannot_link_blob_to_another_owners_task(owner_clients) -> None:
    alice_client, bob_client, app = owner_clients
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task_alice_upload_target",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="Alice upload target",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=TEST_USERNAME,
        )
        before_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        conn.close()
    before_paths = set(app.state.uploads_dir.glob("**/*"))

    hidden = bob_client.post(
        "/api/files/upload",
        files={"file": ("bob.txt", b"must not land", "text/plain")},
        data={"task_id": "task_alice_upload_target", "classification": "internal"},
    )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "资源不存在或不可访问"}

    conn = app.state.conn_factory()
    try:
        after_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        conn.close()
    assert after_files == before_files
    assert set(app.state.uploads_dir.glob("**/*")) == before_paths

    allowed = alice_client.post(
        "/api/files/upload",
        files={"file": ("alice.txt", b"allowed", "text/plain")},
        data={"task_id": "task_alice_upload_target", "classification": "internal"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["task_id"] == "task_alice_upload_target"


def test_conversation_task_projections_fail_closed_on_foreign_nested_task(
    owner_clients,
) -> None:
    alice_client, _bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id="task_bob_nested_in_alice_conversation",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="foreign nested task",
            created_by=TEST_DISPLAY_NAME,
            created_by_username=BOB_USERNAME,
            conversation_id=conversation_id,
        )
        repos.record_model_call(
            conn,
            task_id="task_bob_nested_in_alice_conversation",
            conversation_id=conversation_id,
            model_profile="reasoning",
            model_name="authorization-test",
            status="success",
            request_summary="Bob private request summary",
            response_summary="Bob private response summary",
        )
    finally:
        conn.close()

    for suffix in ("tasks", "model_calls"):
        response = alice_client.get(
            f"/api/conversations/{conversation_id}/{suffix}"
        )
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}


def test_malformed_historical_attachment_projection_is_generic_404(
    owner_clients,
) -> None:
    alice_client, _bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="corrupt attachment projection witness",
            file_ids=[],
        )
        conn.execute(
            "UPDATE conversation_messages SET file_ids = ? "
            "WHERE conversation_id = ?",
            ("{not-json", conversation_id),
        )
    finally:
        conn.close()

    gateway = _RecordingGateway()
    app.state.conversation_service.model_gateway = gateway
    response = alice_client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "corrupt history must stop before model"},
    )
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "资源不存在或不可访问"}
    assert gateway.calls == 0


def test_asset_candidate_endpoints_hide_foreign_legacy_and_drifted_owners(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    task_id = _seed_task(app)
    candidate_response = _create_candidate(alice_client, task_id)
    assert candidate_response.status_code == 200, candidate_response.text
    candidate = candidate_response.json()

    before = _counts_for_candidate_auth(app)
    probes = [
        _create_candidate(bob_client, task_id),
        bob_client.get(f"/api/tasks/{task_id}/asset-candidate"),
        bob_client.post(
            f"/api/asset-candidates/{candidate['id']}/decision",
            json={
                **_decision(candidate),
                # A foreign caller must not learn that these digests are stale.
                "expected_candidate_digest": "sha256:" + "1" * 64,
                "expected_bundle_digest": "sha256:" + "2" * 64,
            },
        ),
    ]
    for response in probes:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
    assert _counts_for_candidate_auth(app) == before

    legacy_task_id = _seed_task(app, owner_username=None)
    for response in (
        _create_candidate(alice_client, legacy_task_id),
        alice_client.get(f"/api/tasks/{legacy_task_id}/asset-candidate"),
    ):
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}

    conn = app.state.conn_factory()
    try:
        # Reproduce a legacy row written before owner immutability existed;
        # current direct UPDATEs are rejected by SQLite and covered separately.
        conn.execute("DROP TRIGGER trg_asset_candidates_initiator_immutable")
        conn.execute(
            "UPDATE asset_candidates SET initiated_by_username = ? WHERE id = ?",
            (BOB_USERNAME, candidate["id"]),
        )
    finally:
        conn.close()
    init_db(app.state.db_path)
    for response in (
        _create_candidate(alice_client, task_id),
        alice_client.get(f"/api/tasks/{task_id}/asset-candidate"),
        alice_client.post(
            f"/api/asset-candidates/{candidate['id']}/decision",
            json=_decision(candidate),
        ),
    ):
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
    assert _counts_for_candidate_auth(app) == before


def test_asset_candidate_derivation_rejects_foreign_historical_input(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    bob_upload = bob_client.post(
        "/api/files/upload",
        files={"file": ("bob-candidate.txt", b"bob candidate secret", "text/plain")},
        data={"classification": "internal"},
    )
    assert bob_upload.status_code == 200, bob_upload.text
    bob_file_id = bob_upload.json()["id"]

    task_id = _seed_task(
        app,
        existing_conversation_id=conversation_id,
        message_file_ids=[bob_file_id],
    )
    before = _counts_for_candidate_auth(app)
    for response in (
        _create_candidate(alice_client, task_id),
        alice_client.get(f"/api/tasks/{task_id}/asset-candidate"),
    ):
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
    assert _counts_for_candidate_auth(app) == before


def _counts_for_candidate_auth(app) -> tuple[int, int]:
    conn = app.state.conn_factory()
    try:
        return (
            conn.execute("SELECT COUNT(*) FROM asset_candidates").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM asset_candidate_events").fetchone()[0],
        )
    finally:
        conn.close()


@pytest.mark.parametrize("stream", [False, True], ids=["post", "stream"])
@pytest.mark.parametrize("existing_messages", [2, 3], ids=["exact", "overflow"])
def test_conversation_round_reserves_message_lineage_budget_before_model(
    owner_clients,
    monkeypatch,
    stream: bool,
    existing_messages: int,
) -> None:
    alice_client, _bob_client, app = owner_clients
    monkeypatch.setattr(oauth, "_MAX_LINEAGE_CONVERSATION_MESSAGES", 4)
    monkeypatch.setattr(
        repos,
        "CONVERSATION_LINEAGE_MAX_MESSAGES",
        4,
        raising=False,
    )
    conversation_id = _open_conversation(alice_client)
    conn = app.state.conn_factory()
    try:
        for index in range(existing_messages):
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"existing message {index}",
                file_ids=[],
            )
    finally:
        conn.close()

    gateway = (
        _StreamingStub("边界内回复", ["边界内", "回复"])
        if stream
        else _CannedStub("边界内回复")
    )
    app.state.conversation_service.model_gateway = gateway
    response = alice_client.post(
        f"/api/conversations/{conversation_id}/messages"
        + ("/stream" if stream else ""),
        json={"content": "本轮必须先预留两条消息"},
    )

    conn = app.state.conn_factory()
    try:
        persisted_count = repos.count_messages(conn, conversation_id)
    finally:
        conn.close()
    if existing_messages == 2:
        assert response.status_code == 200, response.text
        if stream:
            events = [json.loads(line) for line in response.text.splitlines() if line]
            assert events[-1]["type"] == "done"
        assert len(gateway.calls) == 1
        assert persisted_count == 4
    else:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
        assert gateway.calls == []
        assert persisted_count == 3

    visible = alice_client.get(f"/api/conversations/{conversation_id}")
    assert visible.status_code == 200, visible.text
    listed = alice_client.get("/api/conversations", params={"limit": 500})
    assert conversation_id in {row["id"] for row in listed.json()}


@pytest.mark.parametrize("stream", [False, True], ids=["post", "stream"])
@pytest.mark.parametrize("existing_files", [0, 1], ids=["exact", "overflow"])
def test_conversation_round_reserves_attachment_lineage_budget_before_model(
    owner_clients,
    monkeypatch,
    stream: bool,
    existing_files: int,
) -> None:
    alice_client, _bob_client, app = owner_clients
    monkeypatch.setattr(oauth, "_MAX_LINEAGE_FILE_IDS", 1)
    monkeypatch.setattr(
        repos,
        "CONVERSATION_LINEAGE_MAX_FILE_IDS",
        1,
        raising=False,
    )
    conversation_id = _open_conversation(alice_client)
    uploaded_ids: list[str] = []
    for index in range(2):
        uploaded = alice_client.post(
            "/api/files/upload",
            files={
                "file": (
                    f"budget-{index}.txt",
                    f"owned payload {index}".encode(),
                    "text/plain",
                )
            },
            data={"classification": "internal"},
        )
        assert uploaded.status_code == 200, uploaded.text
        uploaded_ids.append(uploaded.json()["id"])
    if existing_files:
        conn = app.state.conn_factory()
        try:
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="user",
                content="existing owned attachment",
                file_ids=[uploaded_ids[0]],
            )
        finally:
            conn.close()

    gateway = (
        _StreamingStub("附件边界回复", ["附件边界", "回复"])
        if stream
        else _CannedStub("附件边界回复")
    )
    app.state.conversation_service.model_gateway = gateway
    response = alice_client.post(
        f"/api/conversations/{conversation_id}/messages"
        + ("/stream" if stream else ""),
        json={"content": "附加新文件", "file_ids": [uploaded_ids[1]]},
    )

    conn = app.state.conn_factory()
    try:
        persisted_count = repos.count_messages(conn, conversation_id)
    finally:
        conn.close()
    if existing_files == 0:
        assert response.status_code == 200, response.text
        if stream:
            events = [json.loads(line) for line in response.text.splitlines() if line]
            assert events[-1]["type"] == "done"
        assert len(gateway.calls) == 1
        assert persisted_count == 2
    else:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
        assert gateway.calls == []
        assert persisted_count == 1

    visible = alice_client.get(f"/api/conversations/{conversation_id}")
    assert visible.status_code == 200, visible.text


@pytest.mark.parametrize("stream", [False, True], ids=["post", "stream"])
def test_conversation_round_reserves_canonical_duplicate_attachment_delta(
    owner_clients,
    monkeypatch,
    stream: bool,
) -> None:
    alice_client, _bob_client, app = owner_clients
    monkeypatch.setattr(oauth, "_MAX_LINEAGE_FILE_IDS", 2)
    monkeypatch.setattr(
        repos,
        "CONVERSATION_LINEAGE_MAX_FILE_IDS",
        2,
        raising=False,
    )
    conversation_id = _open_conversation(alice_client)
    uploaded = alice_client.post(
        "/api/files/upload",
        files={
            "file": (
                "duplicate-budget.txt",
                b"owned duplicate budget payload",
                "text/plain",
            )
        },
        data={"classification": "internal"},
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["id"]
    conn = app.state.conn_factory()
    try:
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="one remaining lineage attachment slot",
            file_ids=[file_id],
        )
    finally:
        conn.close()

    gateway = (
        _StreamingStub("规范化回复", ["规范化", "回复"])
        if stream
        else _CannedStub("规范化回复")
    )
    app.state.conversation_service.model_gateway = gateway
    response = alice_client.post(
        f"/api/conversations/{conversation_id}/messages"
        + ("/stream" if stream else ""),
        json={
            "content": "重复附件按实际持久化列表预算",
            "file_ids": [file_id, file_id],
        },
    )

    assert response.status_code == 200, response.text
    if stream:
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert events[-1]["type"] == "done"
    assert len(gateway.calls) == 1
    conn = app.state.conn_factory()
    try:
        messages = repos.list_messages(conn, conversation_id)
    finally:
        conn.close()
    assert len(messages) == 3
    assert messages[0]["file_ids"] == [file_id]
    assert messages[1]["file_ids"] == [file_id]
    assert messages[2]["file_ids"] == []
    detail = alice_client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200, detail.text
    listed = alice_client.get("/api/conversations", params={"limit": 500})
    assert conversation_id in {row["id"] for row in listed.json()}


def test_feature_asset_map_rejects_legacy_candidate_with_foreign_history(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    bob_upload = bob_client.post(
        "/api/files/upload",
        files={"file": ("bob-map.txt", b"bob map secret", "text/plain")},
        data={"classification": "internal"},
    )
    assert bob_upload.status_code == 200, bob_upload.text
    task_id = _seed_task(
        app,
        existing_conversation_id=conversation_id,
        message_file_ids=[bob_upload.json()["id"]],
    )

    conn = app.state.conn_factory()
    try:
        user_id = conn.execute(
            "SELECT id FROM users WHERE username = ?", (TEST_USERNAME,)
        ).fetchone()["id"]
        legacy_candidate = (
            app.state.asset_candidate_ledger.create_for_completed_task(
                conn,
                task_id=task_id,
                initiated_by_user_id=user_id,
                initiated_by_username=TEST_USERNAME,
            )
        )
    finally:
        conn.close()

    direct = alice_client.get(f"/api/tasks/{task_id}/asset-candidate")
    assert direct.status_code == 404
    assert direct.json() == {"detail": "资源不存在或不可访问"}
    feature_map = alice_client.get("/api/feature-asset-map")
    assert feature_map.status_code == 503, feature_map.text
    assert feature_map.json() == {"detail": "功能/资产地图暂不可用"}
    assert legacy_candidate["id"] not in feature_map.text


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_skill_package_endpoints_revalidate_complete_candidate_lineage(
    owner_clients,
    action: str,
) -> None:
    """A package must disappear when its accepted source lineage is poisoned.

    Package ownership alone is not authority: reads and the human decision must
    revalidate Candidate -> task -> conversation -> every historical attachment
    in one authoritative database snapshot, with no decision write on failure.
    """

    alice_client, bob_client, app = owner_clients
    conversation_id = _open_conversation(alice_client)
    task_id = _seed_task(app, existing_conversation_id=conversation_id)
    candidate = _create_candidate(alice_client, task_id).json()
    accepted = alice_client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert accepted.status_code == 200, accepted.text
    package = accepted.json()["skill_package"]

    foreign_upload = bob_client.post(
        "/api/files/upload",
        files={"file": ("foreign-package-source.txt", b"foreign lineage", "text/plain")},
        data={"classification": "internal"},
    )
    assert foreign_upload.status_code == 200, foreign_upload.text

    conn = app.state.conn_factory()
    try:
        before = conn.execute(
            "SELECT state, review_event_id FROM skill_packages WHERE id = ?",
            (package["id"],),
        ).fetchone()
        before_event_count = conn.execute(
            "SELECT COUNT(*) FROM skill_package_events WHERE package_id = ?",
            (package["id"],),
        ).fetchone()[0]
        repos.append_message(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="legacy poisoned history",
            file_ids=[foreign_upload.json()["id"]],
        )
        conn.commit()
    finally:
        conn.close()

    hidden_candidate = alice_client.get(f"/api/tasks/{task_id}/asset-candidate")
    responses = [
        alice_client.get(f"/api/skill-packages/{package['id']}"),
        alice_client.get(f"/api/skill-packages/{package['id']}/review-content"),
        alice_client.post(
            f"/api/skill-packages/{package['id']}/decision",
            json={
                "schema_version": "skill_package_decision_request.v1",
                "action": action,
                "expected_package_digest": package["package_digest"],
            },
        ),
    ]
    for response in [hidden_candidate, *responses]:
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": "资源不存在或不可访问"}
        assert package["package_digest"] not in response.text

    conn = app.state.conn_factory()
    try:
        after = conn.execute(
            "SELECT state, review_event_id FROM skill_packages WHERE id = ?",
            (package["id"],),
        ).fetchone()
        after_event_count = conn.execute(
            "SELECT COUNT(*) FROM skill_package_events WHERE package_id = ?",
            (package["id"],),
        ).fetchone()[0]
    finally:
        conn.close()
    assert tuple(after) == tuple(before)
    assert after_event_count == before_event_count


@pytest.mark.parametrize("tamper", ["package_owner", "package_source_task"])
def test_feature_asset_map_rejects_package_owner_or_source_lineage_drift(
    owner_clients,
    tamper: str,
) -> None:
    alice_client, _bob_client, app = owner_clients
    task_id = _seed_task(app)
    candidate = _create_candidate(alice_client, task_id).json()
    accepted = alice_client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert accepted.status_code == 200, accepted.text
    package_id = accepted.json()["skill_package"]["id"]

    conn = app.state.conn_factory()
    try:
        if tamper == "package_owner":
            # Reproduce pre-trigger legacy corruption, then restore the current
            # insert-once owner boundary before exercising fail-closed reads.
            conn.execute(
                "DROP TRIGGER trg_skill_packages_owner_username_immutable"
            )
            conn.execute(
                "UPDATE skill_packages SET owner_username = ? WHERE id = ?",
                (BOB_USERNAME, package_id),
            )
        else:
            foreign_task_id = _seed_task(app, owner_username=BOB_USERNAME)
            conn.execute(
                "UPDATE skill_packages SET source_task_id = ? WHERE id = ?",
                (foreign_task_id, package_id),
            )
    finally:
        conn.close()
    if tamper == "package_owner":
        init_db(app.state.db_path)

    feature_map = alice_client.get("/api/feature-asset-map")
    assert feature_map.status_code == 503, feature_map.text
    assert feature_map.json() == {"detail": "功能/资产地图暂不可用"}
    assert package_id not in feature_map.text


def test_feature_asset_map_rejects_owned_package_with_foreign_candidate_lineage(
    owner_clients,
) -> None:
    alice_client, bob_client, app = owner_clients
    foreign_task_id = _seed_task(app, owner_username=BOB_USERNAME)
    foreign_candidate_response = _create_candidate(bob_client, foreign_task_id)
    assert (
        foreign_candidate_response.status_code == 200
    ), foreign_candidate_response.text
    foreign_candidate = foreign_candidate_response.json()
    accepted = bob_client.post(
        f"/api/asset-candidates/{foreign_candidate['id']}/decision",
        json=_decision(foreign_candidate),
    )
    assert accepted.status_code == 200, accepted.text
    package_id = accepted.json()["skill_package"]["id"]

    conn = app.state.conn_factory()
    try:
        # Historical/direct persistence contamination: the package now claims
        # Alice while its immutable Candidate and task still belong to Bob.
        conn.execute("DROP TRIGGER trg_skill_packages_owner_username_immutable")
        conn.execute(
            "UPDATE skill_packages SET owner_username = ? WHERE id = ?",
            (TEST_USERNAME, package_id),
        )
        conn.commit()
    finally:
        conn.close()
    init_db(app.state.db_path)

    feature_map = alice_client.get("/api/feature-asset-map")
    assert feature_map.status_code == 503, feature_map.text
    assert feature_map.json() == {"detail": "功能/资产地图暂不可用"}
    assert package_id not in feature_map.text
