from __future__ import annotations

from typing import Any

from backend.tests.test_asset_candidates_api import (
    _create_candidate,
    _decision,
    _seed_task,
)
from backend.tests.test_m6_guide_conversation import (
    _CannedStub,
    _agent,
    _fta_inputs,
    _open_conversation,
    _orchestrate,
    _plan_reply,
)


def _accept_and_approve_package(
    client,
    app,
    *,
    task_name: str,
    agent_id: str = "fta_agent",
) -> dict[str, Any]:
    candidate = _create_candidate(
        client,
        _seed_task(
            app,
            agent_id=agent_id,
            task_name=task_name,
            task_inputs=(
                _fta_inputs(task_name)
                if agent_id == "fta_agent"
                else {"name": task_name}
            ),
            user_message=f"请完成{task_name}，并保留核对证据。",
        ),
    ).json()
    accepted = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert accepted.status_code == 200, accepted.text
    package = accepted.json()["skill_package"]
    approved = client.post(
        f"/api/skill-packages/{package['id']}/decision",
        json={
            "schema_version": "skill_package_decision_request.v1",
            "action": "approve",
            "expected_package_digest": package["package_digest"],
        },
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _hello_plan(*, forged_reuse: dict[str, Any] | None = None) -> str:
    plan = _orchestrate(
        [_agent("fta_agent", _fta_inputs("复用方法执行"))],
        analysis="按已经核对的方法完成同类任务",
        goal="完成同类工程任务并保留证据",
        workflow="单执行单元完成并交回工程师核对",
    )
    if forged_reuse is not None:
        plan["skill_reuse"] = forged_reuse
    return _plan_reply("我会沿用已核对的方法组织这次工作。", plan)


def test_pending_package_is_not_reused_or_exposed_to_guide(app_env) -> None:
    client, app = app_env
    candidate = _create_candidate(
        client,
        _seed_task(
            app,
            task_name="起落架控制逻辑核对",
            user_message="请完成起落架控制逻辑核对。",
        ),
    ).json()
    accepted = client.post(
        f"/api/asset-candidates/{candidate['id']}/decision",
        json=_decision(candidate),
    )
    assert accepted.status_code == 200
    assert accepted.json()["skill_package"]["state"] == "pending_review"

    gateway = _CannedStub(_hello_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    recommendation = response.json()["message"]["recommendation"]
    assert "skill_reuse" not in recommendation
    assert "已审核可复用 Skill 方法" not in gateway.calls[0]["messages"][0]["content"]


def test_approved_package_is_uniquely_matched_injected_and_trusted_ref_attached(
    app_env,
) -> None:
    client, app = app_env
    package = _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
    )
    gateway = _CannedStub(_hello_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对，并沿用上次方法。"},
    )

    assert response.status_code == 200, response.text
    recommendation = response.json()["message"]["recommendation"]
    reuse = recommendation["skill_reuse"]
    assert reuse == {
        "schema_version": "skill_reuse_ref.v1",
        "package_id": package["id"],
        "package_version": package["version"],
        "package_digest": package["package_digest"],
        "candidate_digest": package["source"]["candidate_digest"],
        "skill_digest": package["source"]["skill_digest"],
        "skill_name": "起落架控制逻辑核对：可复用方法",
        "matched_agent_id": "fta_agent",
        "review_state": "approved",
        "match_policy_version": "skill_reuse_match.v1",
        "match_basis_digest": reuse["match_basis_digest"],
    }
    assert reuse["match_basis_digest"].startswith("sha256:")
    system_prompt = gateway.calls[0]["messages"][0]["content"]
    assert "已审核可复用 Skill 方法" in system_prompt
    assert "起落架控制逻辑核对" in system_prompt
    assert "核验任务终态、产物摘要与事件证据" in system_prompt


def test_approved_package_for_undeclared_profile_none_agent_is_not_auto_reused(
    app_env,
) -> None:
    client, app = app_env
    _accept_and_approve_package(
        client,
        app,
        task_name="起落架控制逻辑核对",
        agent_id="hello_agent",
    )
    gateway = _CannedStub(_hello_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对，并沿用上次方法。"},
    )

    assert response.status_code == 200, response.text
    assert "skill_reuse" not in response.json()["message"]["recommendation"]
    assert "已审核可复用 Skill 方法" not in gateway.calls[0]["messages"][0]["content"]


def test_llm_forged_skill_reuse_ref_is_stripped_when_no_approved_match(
    app_env,
) -> None:
    client, app = app_env
    gateway = _CannedStub(
        _hello_plan(
            forged_reuse={
                "schema_version": "skill_reuse_ref.v1",
                "package_id": "skill_package_forged",
                "package_digest": "sha256:" + "f" * 64,
                "matched_agent_id": "hello_agent",
            }
        )
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "处理一个从未形成过候选的新目标。"},
    )

    assert response.status_code == 200, response.text
    assert "skill_reuse" not in response.json()["message"]["recommendation"]
