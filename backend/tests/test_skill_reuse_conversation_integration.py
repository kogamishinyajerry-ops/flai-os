from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from backend.app.runtime.conversation import ConversationConflictError
from backend.app.storage import repos
from backend.tests.test_m6_guide_conversation import (
    _agent,
    _CannedStub,
    _fta_inputs,
    _open_conversation,
    _orchestrate,
    _plan_reply,
    _refuse,
    _SequenceStub,
    _StreamingStub,
)


class _RecordingMatcher:
    def __init__(self, matched: dict[str, Any] | None) -> None:
        self.matched = matched
        self.calls: list[dict[str, Any]] = []

    def match(self, conn: Any, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append(kwargs)
        return self.matched


def _trusted_match() -> dict[str, Any]:
    return {
        "ref": {
            "schema_version": "skill_reuse_ref.v1",
            "package_id": "skill_package_0123456789abcdef01234567",
            "package_version": "0.1.0",
            "package_digest": "sha256:" + "a" * 64,
            "candidate_digest": "sha256:" + "b" * 64,
            "skill_digest": "sha256:" + "c" * 64,
            "skill_name": "起落架控制逻辑核对：可复用方法",
            "matched_agent_id": "fta_agent",
            "review_state": "approved",
            "match_policy_version": "skill_reuse_match.v1",
            "match_basis_digest": "sha256:" + "d" * 64,
        },
        "method": {
            "skill_revision": {
                "schema_version": "skill_draft.v1",
                "status": "draft",
                "name": "起落架控制逻辑核对：可复用方法",
                "instructions": ["核验任务终态、产物摘要与事件证据"],
                "content_digest": "sha256:" + "c" * 64,
            },
            "skill_markdown": "先核对输入，再核验任务终态、产物摘要与事件证据。",
        },
    }


def _guide_plan() -> str:
    plan = _orchestrate(
        [_agent("fta_agent", _fta_inputs("复用方法执行"))],
        analysis="按已审核的方法完成同类任务",
        goal="完成同类工程任务并保留证据",
        workflow="单执行单元完成并交回工程师核对",
    )
    # 模型伪造的引用必须被 canonical plan 剥离，最终引用只能来自 matcher。
    plan["skill_reuse"] = {"package_id": "model-forged"}
    return _plan_reply("我会沿用已核对的方法组织这次工作。", plan)


def test_http_guide_round_injects_reviewed_method_and_attaches_only_trusted_ref(
    app_env,
) -> None:
    client, app = app_env
    matcher = _RecordingMatcher(_trusted_match())
    app.state.conversation_service.skill_reuse_matcher = matcher
    gateway = _CannedStub(_guide_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    assert matcher.calls == [
        {
            "username": "test_engineer",
            "segment_messages": [
                {"role": "user", "content": "请再次完成起落架控制逻辑核对。"}
            ],
            "attachment_filenames": [],
        }
    ]
    system_prompt = gateway.calls[0]["messages"][0]["content"]
    assert "已审核可复用 Skill 方法" in system_prompt
    assert "核验任务终态、产物摘要与事件证据" in system_prompt
    assert "skill_package_0123456789abcdef01234567" not in system_prompt
    recommendation = response.json()["message"]["recommendation"]
    assert recommendation["skill_reuse"] == _trusted_match()["ref"]


def test_matcher_failure_keeps_guide_round_available_without_reuse_claim(
    app_env,
) -> None:
    client, app = app_env

    class _BrokenMatcher:
        def match(self, conn: Any, **kwargs: Any) -> dict[str, Any] | None:
            raise RuntimeError("package store unavailable")

    app.state.conversation_service.skill_reuse_matcher = _BrokenMatcher()
    gateway = _CannedStub(_guide_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "处理一个新的工程目标。"},
    )

    assert response.status_code == 200, response.text
    assert "skill_reuse" not in response.json()["message"]["recommendation"]
    assert "已审核可复用 Skill 方法" not in gateway.calls[0]["messages"][0]["content"]
    assistant_message = response.json()["message"]["content"]
    assert "沿用已核对的方法" not in assistant_message
    assert "方法匹配与实际应用状态" in assistant_message
    assert "开工后的任务事件" in assistant_message


def test_agent_mismatch_removes_ref_and_neutralizes_positive_reuse_claim(
    app_env,
) -> None:
    client, app = app_env
    mismatched_match = _trusted_match()
    mismatched_match["ref"]["matched_agent_id"] = "control_logic_agent"
    matcher = _RecordingMatcher(mismatched_match)
    app.state.conversation_service.skill_reuse_matcher = matcher
    gateway = _CannedStub(_guide_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请处理控制逻辑检查。"},
    )

    assert response.status_code == 200, response.text
    recommendation = response.json()["message"]["recommendation"]
    assert isinstance(recommendation, dict)
    assert "skill_reuse" not in recommendation
    assistant_message = response.json()["message"]["content"]
    assert "沿用已核对的方法" not in assistant_message
    assert "方法匹配与实际应用状态" in assistant_message
    assert "开工后的任务事件" in assistant_message


@pytest.mark.parametrize(
    "mutate",
    [
        lambda match: match["ref"].__setitem__("unexpected", "model-data"),
        lambda match: match["ref"].__setitem__("package_version", "01.0.0"),
        lambda match: match["ref"].__setitem__("package_digest", "SHA256:" + "a" * 64),
        lambda match: match["ref"].__setitem__("review_state", "pending_review"),
        lambda match: match["method"].__setitem__("unexpected", "model-data"),
        lambda match: match["method"]["skill_revision"].__setitem__(
            "content_digest", "sha256:" + "e" * 64
        ),
        lambda match: match["method"]["skill_revision"].__setitem__(
            "name", "另一个方法"
        ),
    ],
    ids=[
        "extra-ref-key",
        "noncanonical-semver",
        "noncanonical-digest",
        "not-approved",
        "extra-method-key",
        "revision-digest-mismatch",
        "revision-name-mismatch",
    ],
)
def test_malformed_match_envelope_is_not_injected_or_attached(app_env, mutate) -> None:
    client, app = app_env
    malformed = copy.deepcopy(_trusted_match())
    mutate(malformed)
    matcher = _RecordingMatcher(malformed)
    app.state.conversation_service.skill_reuse_matcher = matcher
    gateway = _CannedStub(_guide_plan())
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    assert "已审核可复用 Skill 方法" not in gateway.calls[0]["messages"][0]["content"]
    assert "skill_reuse" not in response.json()["message"]["recommendation"]
    assert "沿用已核对的方法" not in response.json()["message"]["content"]


def test_request_user_skill_is_not_injected_into_unproven_other_owner_conversation(
    app_env,
) -> None:
    client, app = app_env
    matcher = _RecordingMatcher(_trusted_match())
    service = app.state.conversation_service
    service.skill_reuse_matcher = matcher
    gateway = _CannedStub(_guide_plan())
    service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    result = service.post_message(
        conversation_id=conversation_id,
        content="请完成起落架控制逻辑核对。",
        actor_username="another_engineer",
    )

    assert matcher.calls == []
    assert "已审核可复用 Skill 方法" not in gateway.calls[0]["messages"][0]["content"]
    assert "skill_reuse" not in result["message"]["recommendation"]
    assert "沿用已核对的方法" not in result["message"]["content"]
    # 既有会话共享语义保持不变：跨用户直调仍可完成普通对话，只是绝不复用
    # owner 的私有 Skill。此切片不顺手引入新的会话 ACL。
    assert len(service.get(conversation_id)["messages"]) == 2


def test_recreated_service_uses_persisted_owner_proof_for_skill_match(app_env) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    old_service = app.state.conversation_service
    matcher = _RecordingMatcher(_trusted_match())
    gateway = _CannedStub(_guide_plan())
    app.state.conversation_service = type(old_service)(
        old_service.agent_registry,
        gateway,
        old_service.conn_factory,
        uploads_dir=old_service.uploads_dir,
        skill_reuse_matcher=matcher,
    )

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    assert matcher.calls[0]["username"] == "test_engineer"
    assert (
        response.json()["message"]["recommendation"]["skill_reuse"]
        == _trusted_match()["ref"]
    )


def test_legacy_conversation_without_username_proof_fails_closed_before_reuse(
    app_env,
) -> None:
    client, app = app_env
    matcher = _RecordingMatcher(_trusted_match())
    service = app.state.conversation_service
    service.skill_reuse_matcher = matcher
    gateway = _CannedStub(_guide_plan())
    service.model_gateway = gateway
    conversation_id = "conv_legacy_without_owner_proof"
    conn = service.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by="测试工程师",
        )
    finally:
        conn.close()

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "资源不存在或不可访问"}
    assert matcher.calls == []
    assert gateway.calls == []
    conn = service.conn_factory()
    try:
        assert repos.list_messages(conn, conversation_id) == []
    finally:
        conn.close()


class _TaskBoundaryInterloper(_CannedStub):
    def __init__(self, reply: str, app: Any, conversation_id: str) -> None:
        super().__init__(reply)
        self._app = app
        self._conversation_id = conversation_id

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any):
        conn = self._app.state.conn_factory()
        try:
            repos.create_task(
                conn,
                task_id="task_boundary_changed_during_llm",
                agent_id="hello_agent",
                agent_version="1.0.0",
                name="并发签发的任务",
                created_by="测试工程师",
                created_by_username="test_engineer",
                conversation_id=self._conversation_id,
            )
        finally:
            conn.close()
        return super().chat(profile, messages, **kwargs)


class _StreamingTaskBoundaryInterloper(_TaskBoundaryInterloper):
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any):
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            on_delta("我已经复用了审核方法。")
        return super().chat(profile, messages, **kwargs)


def test_task_boundary_change_during_llm_returns_409_and_persists_zero_messages(
    app_env,
) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    app.state.conversation_service.model_gateway = _TaskBoundaryInterloper(
        _guide_plan(), app, conversation_id
    )

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 409, response.text
    assert "工作段" in response.json()["detail"]
    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_guide_stream_flushes_only_after_atomic_persistence(app_env) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    service = app.state.conversation_service
    service.model_gateway = _StreamingTaskBoundaryInterloper(
        _guide_plan(), app, conversation_id
    )
    visible: list[str] = []

    with pytest.raises(ConversationConflictError, match="工作段"):
        service.post_message(
            conversation_id=conversation_id,
            content="请完成起落架控制逻辑核对。",
            actor_username="test_engineer",
            on_delta=visible.append,
        )

    assert visible == []
    assert client.get(f"/api/conversations/{conversation_id}").json()["messages"] == []


def test_matcher_receives_only_user_text_after_latest_guide_boundary(app_env) -> None:
    client, app = app_env
    conversation_id = _open_conversation(client)
    app.state.conversation_service.model_gateway = _CannedStub(
        _plan_reply(
            "这段工作先在这里收束。",
            _refuse(residual=["需重新定义目标"], reframe=["换一个可执行目标"]),
        )
    )
    first = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "旧工作段：分析一个完全不同的目标。"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["message"]["recommendation"]["decision"] == "refuse"

    matcher = _RecordingMatcher(_trusted_match())
    app.state.conversation_service.skill_reuse_matcher = matcher
    app.state.conversation_service.model_gateway = _CannedStub(_guide_plan())
    second = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "新工作段：请再次完成起落架控制逻辑核对。"},
    )

    assert second.status_code == 200, second.text
    assert matcher.calls[0]["segment_messages"] == [
        {"role": "user", "content": "新工作段：请再次完成起落架控制逻辑核对。"}
    ]


def test_authenticated_stream_route_passes_username_to_matcher(app_env) -> None:
    client, app = app_env
    matcher = _RecordingMatcher(_trusted_match())
    app.state.conversation_service.skill_reuse_matcher = matcher
    app.state.conversation_service.model_gateway = _CannedStub(_guide_plan())
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["start", "done"]
    assert matcher.calls[0]["username"] == "test_engineer"
    assert (
        events[-1]["message"]["recommendation"]["skill_reuse"]
        == _trusted_match()["ref"]
    )


@pytest.mark.parametrize(
    "model_claim",
    [
        "我会按照刚才审核通过的方法执行。",
        "采用已审定的 Skill 处理这项任务。",
        "I will apply the previously vetted method.",
    ],
)
def test_sync_plan_reply_uses_kernel_owned_planned_language_even_with_trusted_match(
    app_env, model_claim: str
) -> None:
    client, app = app_env
    app.state.conversation_service.skill_reuse_matcher = _RecordingMatcher(
        _trusted_match()
    )
    plan = _orchestrate([_agent("fta_agent", _fta_inputs("复用方法执行"))])
    app.state.conversation_service.model_gateway = _CannedStub(
        _plan_reply(model_claim, plan)
    )
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    message = response.json()["message"]
    assert message["recommendation"]["skill_reuse"] == _trusted_match()["ref"]
    assert message["content"] != model_claim
    assert "已复用" not in message["content"]
    assert "按照刚才审核通过的方法执行" not in message["content"]
    assert "采用已审定" not in message["content"]
    assert "apply the previously vetted" not in message["content"].lower()
    assert "计划复用" in message["content"]
    assert "开工后的任务事件" in message["content"]


@pytest.mark.parametrize(
    "model_claim",
    [
        "我会按照刚才审核通过的方法执行。",
        "采用已审定的 Skill 继续。",
        "I will apply the previously vetted method.",
        "We are using the approved skill.",
    ],
)
def test_sync_no_plan_reply_neutralizes_broad_reuse_claim_even_when_match_exists(
    app_env, model_claim: str
) -> None:
    client, app = app_env
    app.state.conversation_service.skill_reuse_matcher = _RecordingMatcher(
        _trusted_match()
    )
    app.state.conversation_service.model_gateway = _CannedStub(model_claim)
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    message = response.json()["message"]
    assert message["recommendation"] is None
    assert message["content"] != model_claim
    assert "已复用" not in message["content"]
    assert "apply the previously vetted" not in message["content"].lower()
    assert "只以系统方案卡和开工后的任务事件为准" in message["content"]


def test_stream_buffers_model_reuse_claim_until_plan_and_ref_are_reconciled(
    app_env,
) -> None:
    client, app = app_env
    app.state.conversation_service.skill_reuse_matcher = _RecordingMatcher(
        _trusted_match()
    )
    plan = _orchestrate([_agent("fta_agent", _fta_inputs("复用方法执行"))])
    raw_reply = _plan_reply("采用已审定的 Skill 处理。", plan)
    app.state.conversation_service.model_gateway = _StreamingStub(
        raw_reply,
        [
            "采用已审定",
            "的 Skill 处理。<<PL",
            f"AN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>",
        ],
    )
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "请再次完成起落架控制逻辑核对。"},
    )

    assert response.status_code == 200, response.text
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["start", "delta", "done"]
    streamed = "".join(event["text"] for event in events if event["type"] == "delta")
    assert streamed == events[-1]["message"]["content"]
    assert "采用已审定" not in streamed
    assert "已复用" not in streamed
    assert "计划复用" in streamed
    assert (
        events[-1]["message"]["recommendation"]["skill_reuse"]
        == (_trusted_match()["ref"])
    )


def test_stream_discards_partial_false_claim_when_guide_round_fails(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _StreamingStub(
        "不会完整返回",
        ["I will apply the previously vetted method."],
        RuntimeError("upstream exploded after an unsafe delta"),
    )
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "请分析。"},
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["start", "error"]
    assert "previously vetted" not in response.text.lower()
    assert events[-1]["persisted"] is False


class _StreamingSequenceStub(_SequenceStub):
    """Emit the Guide routing lead as an upstream delta before delegation."""

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        if len(self.calls) == 0:
            on_delta = kwargs.get("on_delta")
            if callable(on_delta):
                on_delta("我会按照刚才审核通过的方法执行，然后自动转交。")
        return super().chat(profile, messages, **kwargs)


def test_stream_buffers_guide_lead_across_interactive_delegation(app_env) -> None:
    client, app = app_env
    delegated_answer = "当前合成目录没有足够依据，本轮不提供制度结论。"
    specialist_payload = {
        "answer": delegated_answer,
        "findings": [],
        "refusals": [
            {
                "question": "保密材料应该如何流转？",
                "reason": "当前合成目录未收录足够依据。",
                "suggestion": "请转正式制度库或保密职能窗口查询。",
            }
        ],
    }
    gateway = _StreamingSequenceStub(
        [
            _plan_reply(
                "我会按照刚才审核通过的方法执行，然后自动转交。",
                {
                    "decision": "delegate",
                    "agent_id": "policy_qa_agent",
                    "rationale": "问题匹配制度问答能力。",
                },
            ),
            json.dumps(specialist_payload, ensure_ascii=False),
        ]
    )
    app.state.conversation_service.model_gateway = gateway
    conversation_id = _open_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation_id}/messages/stream",
        json={"content": "保密材料应该如何流转？"},
    )

    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["type"] for event in events] == ["start", "delta", "done"]
    streamed = "".join(event["text"] for event in events if event["type"] == "delta")
    assert streamed == delegated_answer
    assert "审核通过的方法执行" not in response.text
    assert events[-1]["message"]["content"] == delegated_answer
