from __future__ import annotations

import json
from typing import Any

from backend.app.ontology.asset_builder import AssetDraftProjectionError
from backend.app.storage import repos


def _request() -> dict:
    return {
        "schema_version": "asset_draft_preview_request.v1",
        "generalization": {
            "title": "入口边界复核",
            "trigger": "收到待计算的稳态算例",
            "desired_outcome": "形成可签认的复核清单",
            "inputs": ["边界条件表"],
            "outputs": ["复核清单"],
            "steps": ["核对输入", "标出缺口"],
            "evidence_requirements": ["保留原始位置"],
            "human_decision_points": ["冲突值由工程师确认"],
            "limitations": ["不适用于瞬态工况"],
        },
    }


def _create_conversation(app, *, with_user_message: bool = True) -> str:
    conversation_id = "conv_asset_api"
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by="测试工程师",
        )
        if with_user_message:
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="user",
                content="SECRET_SOURCE_ONLY：核对入口边界。",
                file_ids=[],
            )
            repos.append_message(
                conn,
                conversation_id=conversation_id,
                role="assistant",
                content="先核输入，再核缺口。",
            )
        return conversation_id
    finally:
        conn.close()


def _database_dump(app) -> str:
    conn = app.state.conn_factory()
    try:
        return "\n".join(conn.iterdump())
    finally:
        conn.close()


def test_authenticated_preview_resolves_work_case_without_writes_or_source_echo(app_env) -> None:
    client, app = app_env
    conversation_id = _create_conversation(app)
    before = _database_dump(app)

    response = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=_request(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["work_case"]["source_id"] == conversation_id
    assert body["work_case"]["source_state"] == "platform_resolved"
    assert body["validation"]["state"] == "ready_for_human_review"
    assert body["review"]["decision_state"] == "not_recorded"
    assert "SECRET_SOURCE_ONLY" not in response.text
    assert _database_dump(app) == before


def test_semantic_gaps_return_200_with_blockers(app_env) -> None:
    client, app = app_env
    conversation_id = _create_conversation(app)
    request = _request()
    request["generalization"].update(
        {
            "outputs": [],
            "steps": [],
            "evidence_requirements": [],
            "human_decision_points": [],
            "limitations": [],
        }
    )

    response = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=request,
    )

    assert response.status_code == 200
    assert response.json()["validation"]["state"] == "needs_revision"
    assert response.json()["review"]["ready"] is False


def test_preview_is_authenticated_and_source_errors_are_honest(app_env) -> None:
    client, app = app_env
    conversation_id = _create_conversation(app, with_user_message=False)

    missing = client.post(
        "/api/conversations/conv_missing/asset-draft-preview", json=_request()
    )
    assert missing.status_code == 404

    empty = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=_request(),
    )
    assert empty.status_code == 409
    assert "Work Case" in empty.json()["detail"]

    client.cookies.clear()
    anonymous = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=_request(),
    )
    assert anonymous.status_code == 401


def test_unknown_fields_and_projection_failures_fail_closed(app_env) -> None:
    client, app = app_env
    conversation_id = _create_conversation(app)
    invalid = _request()
    invalid["approved"] = True

    response = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=invalid,
    )
    assert response.status_code == 422

    missing = _request()
    del missing["generalization"]["limitations"]
    response = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=missing,
    )
    assert response.status_code == 422

    class BrokenBuilder:
        def preview(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssetDraftProjectionError("SECRET_INTERNAL_SOURCE_ERROR")

    app.state.asset_draft_builder = BrokenBuilder()
    broken = client.post(
        f"/api/conversations/{conversation_id}/asset-draft-preview",
        json=_request(),
    )
    assert broken.status_code == 503
    assert broken.json() == {"detail": "资产草稿投影不可用"}
    assert "SECRET_INTERNAL_SOURCE_ERROR" not in broken.text


def test_malformed_persisted_source_is_a_generic_503(app_env) -> None:
    client, app = app_env

    class BrokenConversationService:
        def get(self, _conversation_id: str) -> dict[str, Any]:
            raise json.JSONDecodeError("SECRET_BROKEN_JSON", "{", 1)

    app.state.conversation_service = BrokenConversationService()
    response = client.post(
        "/api/conversations/conv_corrupt/asset-draft-preview",
        json=_request(),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "资产草稿来源不可用"}
    assert "SECRET_BROKEN_JSON" not in response.text
