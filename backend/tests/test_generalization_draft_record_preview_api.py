from __future__ import annotations

from backend.app.auth import service as auth_service
from backend.app.runtime.generalization_draft_record import (
    create_generalization_draft_record,
)
from backend.app.storage import repos
from conftest import TEST_PASSWORD, TEST_USERNAME, login


RECORD_ID = "gdr_0123456789abcdef0123456789abcdef"
CONTENT_DIGEST = "sha256:" + "1" * 64
GENERALIZATION = {
    "title": "入口边界复核",
    "trigger": "收到待计算的稳态算例",
    "desired_outcome": "形成可签认的复核清单",
    "inputs": ["边界条件表"],
    "outputs": ["复核清单"],
    "steps": ["核对输入", "标出缺口"],
    "evidence_requirements": ["保留原始位置"],
    "human_decision_points": ["冲突值由工程师确认"],
    "limitations": ["不适用于瞬态工况"],
}


def _request(*, expected_content_digest: str = CONTENT_DIGEST) -> dict[str, str]:
    return {
        "schema_version": "generalization_draft_record_preview_request.v1",
        "expected_content_digest": expected_content_digest,
    }


def _create_conversation(app, conversation_id: str = "conv_record_preview") -> str:
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="life_guide_agent",
            created_by="测试工程师",
            created_by_username=TEST_USERNAME,
        )
    finally:
        conn.close()
    return conversation_id


def _append_message_id(conn, *, conversation_id: str, role: str, content: str) -> int:
    message = repos.append_message(
        conn,
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    return int(message["id"])


def _create_record(app, conversation_id: str = "conv_record_preview") -> dict:
    _create_conversation(app, conversation_id)
    conn = app.state.conn_factory()
    try:
        user_message_id = _append_message_id(
            conn,
            conversation_id=conversation_id,
            role="user",
            content="SECRET_PREFIX_SOURCE：请核对入口边界。",
        )
        assistant_message_id = _append_message_id(
            conn,
            conversation_id=conversation_id,
            role="assistant",
            content="先核输入，再核缺口。",
        )
        stored_model_call = repos.record_model_call(
            conn,
            conversation_id=conversation_id,
            agent_id="life_guide_agent",
            model_profile="life_guide",
            model_name="fixture-model",
            status="success",
        )
        receipt = {
            "model_call_id": stored_model_call["id"],
            "kind": "chat",
            "status": stored_model_call["status"],
            "task_id": stored_model_call["task_id"],
            "conversation_id": stored_model_call["conversation_id"],
            "agent_id": stored_model_call["agent_id"],
            "model_profile": stored_model_call["model_profile"],
            "model_name": stored_model_call["model_name"],
        }
        conn.execute("BEGIN IMMEDIATE")
        try:
            record = create_generalization_draft_record(
                conn,
                payload=GENERALIZATION,
                conversation_id=conversation_id,
                owner_username=TEST_USERNAME,
                source_user_message_id=user_message_id,
                source_assistant_message_id=assistant_message_id,
                model_call_receipt=receipt,
                agent_version="1.0.0",
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return record
    finally:
        conn.close()


def _url(conversation_id: str, record_id: str = RECORD_ID) -> str:
    return (
        f"/api/conversations/{conversation_id}/generalization-draft-records/"
        f"{record_id}/asset-draft-preview"
    )


def test_record_bound_preview_rejects_client_payload(app_env) -> None:
    client, _app = app_env

    response = client.post(
        _url("conv_any"),
        json={
            **_request(),
            "payload": {"title": "客户端不得覆盖 canonical payload"},
        },
    )

    assert response.status_code == 422


def test_record_bound_preview_hides_missing_record(app_env) -> None:
    client, app = app_env
    conversation_id = _create_conversation(app)

    response = client.post(_url(conversation_id), json=_request())

    assert response.status_code == 404
    assert response.json() == {"detail": "资源不存在或不可访问"}


def test_record_bound_preview_returns_bundle_with_exact_source_bindings(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)

    response = client.post(
        _url("conv_record_preview", public_record["id"]),
        json=_request(expected_content_digest=public_record["content_digest"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "generalization_draft_record_preview_response.v1"
    assert body["source_record"] == {
        "id": public_record["id"],
        "content_digest": public_record["content_digest"],
        "record_digest": public_record["record_digest"],
        "source_context_digest": public_record["source_context_digest"],
    }
    assert body["asset_draft"]["schema_version"] == "asset_draft_bundle.v1"
    assert body["asset_draft"]["work_case"]["source_id"] == "conv_record_preview"
    assert body["asset_draft"]["work_case"]["message_count"] == 2
    assert "SECRET_PREFIX_SOURCE" not in response.text


def test_record_bound_preview_rejects_content_digest_drift(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)

    response = client.post(
        _url("conv_record_preview", public_record["id"]),
        json=_request(expected_content_digest="sha256:" + "2" * 64),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "泛化草稿记录内容摘要已变化"}


def test_record_bound_preview_hides_cross_conversation_record(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app, "conv_record_owner")
    _create_conversation(app, "conv_other_owned")

    response = client.post(
        _url("conv_other_owned", public_record["id"]),
        json=_request(expected_content_digest=public_record["content_digest"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "资源不存在或不可访问"}


def test_record_bound_preview_hides_foreign_owner_record(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app, "conv_record_owner")
    conn = app.state.conn_factory()
    try:
        auth_service.create_user(
            conn,
            username="other_engineer",
            display_name="其他工程师",
            password=TEST_PASSWORD,
        )
    finally:
        conn.close()
    client.cookies.clear()
    login(client, username="other_engineer", password=TEST_PASSWORD)

    response = client.post(
        _url("conv_record_owner", public_record["id"]),
        json=_request(expected_content_digest=public_record["content_digest"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "资源不存在或不可访问"}


def test_record_bound_preview_maps_corrupt_parent_evidence_to_generic_503(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE model_calls SET status = 'failed', "
            "error_message = 'SECRET_CORRUPTION_DETAIL' WHERE id = ?",
            (public_record["model_attribution"]["model_call_id"],),
        )
    finally:
        conn.close()

    response = client.post(
        _url("conv_record_preview", public_record["id"]),
        json=_request(expected_content_digest=public_record["content_digest"]),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "泛化草稿记录来源或证据不可用"}
    assert "SECRET_CORRUPTION_DETAIL" not in response.text


def test_record_bound_preview_is_stable_after_later_conversation_turns(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)
    url = _url("conv_record_preview", public_record["id"])
    request = _request(expected_content_digest=public_record["content_digest"])
    before = client.post(url, json=request)
    assert before.status_code == 200

    conn = app.state.conn_factory()
    try:
        _append_message_id(
            conn,
            conversation_id="conv_record_preview",
            role="user",
            content="这是记录形成后的新一轮问题。",
        )
        _append_message_id(
            conn,
            conversation_id="conv_record_preview",
            role="assistant",
            content="这是记录形成后的新一轮回答。",
        )
    finally:
        conn.close()

    after = client.post(url, json=request)

    assert after.status_code == 200
    assert after.json() == before.json()
    assert after.json()["asset_draft"]["work_case"]["message_count"] == 2


def test_record_bound_preview_never_decodes_later_corrupt_rows(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)
    url = _url("conv_record_preview", public_record["id"])
    request = _request(expected_content_digest=public_record["content_digest"])
    before = client.post(url, json=request)
    assert before.status_code == 200

    conn = app.state.conn_factory()
    try:
        later_message_id = _append_message_id(
            conn,
            conversation_id="conv_record_preview",
            role="user",
            content="这条后续消息不属于 frozen source prefix。",
        )
        conn.execute(
            "UPDATE conversation_messages SET file_ids = '{' WHERE id = ?",
            (later_message_id,),
        )
    finally:
        conn.close()

    after = client.post(url, json=request)

    assert after.status_code == 200
    assert after.json() == before.json()


def test_record_bound_preview_maps_corrupt_frozen_prefix_to_generic_503(app_env) -> None:
    client, app = app_env
    public_record = _create_record(app)
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE conversation_messages SET file_ids = '{' WHERE id = ?",
            (public_record["lineage"]["user_message_id"],),
        )
    finally:
        conn.close()

    response = client.post(
        _url("conv_record_preview", public_record["id"]),
        json=_request(expected_content_digest=public_record["content_digest"]),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "泛化草稿记录来源或证据不可用"}
