from __future__ import annotations

import copy
import json

import httpx
import pytest

from conftest import TEST_USERNAME, seed_pre_p23_legacy_conversation, seed_user

from backend.app.runtime.agent_execution import canonical_json_bytes
from backend.app.runtime import agent_fact_projection as fact_projection
from backend.app.runtime.jerryagent_adapter import build_jerryagent_facts_reader
from backend.app.storage import repos


TOKEN = "flai-jerryagent-test-token-00000001"


def _conversation(app, conversation_id: str, *, owner: str = TEST_USERNAME) -> None:
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=conversation_id,
            agent_id="guide_agent",
            created_by="测试工程师",
            created_by_username=owner,
        )
        conn.commit()
    finally:
        conn.close()


def _task(
    app,
    task_id: str,
    conversation_id: str,
    *,
    agent_id: str = "hello_agent",
    depends_on: list[str] | None = None,
    agent_version: str | None = None,
) -> None:
    agent = app.state.agent_registry.get(agent_id)
    assert agent is not None
    execution = agent.get("execution") or {}
    conn = app.state.conn_factory()
    try:
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version=agent_version or agent["version"],
            name=task_id,
            created_by="测试工程师",
            created_by_username=TEST_USERNAME,
            inputs={"name": task_id},
            conversation_id=conversation_id,
            depends_on=depends_on,
            review_requested_from_username=TEST_USERNAME,
            execution_adapter=execution.get("adapter", "native_python"),
            execution_contract_version=execution.get(
                "contract_version", "native.workflow.v1"
            ),
        )
    finally:
        conn.close()


def _drive(app, task_id: str, *states: str) -> None:
    conn = app.state.conn_factory()
    try:
        for state in states:
            repos.set_task_status(conn, task_id, state)
    finally:
        conn.close()


def _settings() -> dict[str, str]:
    return {
        "FLAI_JERRYAGENT_ENABLED": "1",
        "FLAI_JERRYAGENT_URL": "http://127.0.0.1:43117",
        "FLAI_JERRYAGENT_TOKEN": TOKEN,
    }


def _jerry_fact(task_id: str) -> dict:
    return {
        "runtimeTaskId": "runtime-task-a",
        "status": "running",
        "revision": 9,
        "identity": {
            "product": "JerryAgent",
            "schema": "flai.agent-layer.v1",
            "runtimeEventSchemaVersion": 1,
            "instanceId": "instance-a",
            "sessionId": "session-a",
            "runtimeKind": "external",
            "executionId": task_id,
            "externalTaskId": task_id,
            "requestSha256": "a" * 64,
        },
        "wait": {
            "kind": "subagent_completion",
            "since": "2026-07-20T12:00:00+00:00",
            "subjectOrdinal": 1,
            "pendingCount": 1,
            "continueWhen": "subagents_terminal",
        },
        "delegationHold": None,
        "subagentCount": 1,
        "subagentsTruncated": False,
        "subagents": [
            {
                "ordinal": 1,
                "status": "running",
                "retryOfOrdinal": None,
                "createdAt": "2026-07-20T12:00:00+00:00",
                "updatedAt": "2026-07-20T12:00:01+00:00",
            }
        ],
    }


def _jerry_witness(
    app,
    task_id: str,
    *,
    digest: str = "a" * 64,
    runtime_task_id: str = "runtime-task-a",
    instance_id: str = "instance-a",
    session_id: str = "session-a",
    replayed: bool = False,
    identity_bound: bool = True,
    bound_instance_id: str | None = None,
    bound_session_id: str | None = None,
    bound_runtime_kind: str = "external",
    observed_revisions: list[int] | None = None,
    receipt: bool = False,
    final_revision: int = 9,
) -> None:
    conn = app.state.conn_factory()
    try:
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="jerryagent_research_agent",
            event_type="agent_log",
            level="info",
            message="agent layer started",
            payload={
                "workflow_event_type": "agent_layer_started",
                "adapter": "jerryagent_sidecar",
                "contract_version": "flai.agent-layer.v1",
                "execution_id": task_id,
                "request_sha256": digest,
                "runtime_instance_id": instance_id,
                "runtime_session_id": session_id,
                "model_calls_attested_by_flai": False,
            },
        )
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="jerryagent_research_agent",
            event_type="agent_log",
            level="info",
            message="agent layer submitted",
            payload={
                "workflow_event_type": "agent_layer_submitted",
                "execution_id": task_id,
                "runtime_task_id": runtime_task_id,
                "replayed": replayed,
                "receipt_recovered": False,
                "submission_attempts": 1,
            },
        )
        if identity_bound:
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id="jerryagent_research_agent",
                event_type="agent_log",
                level="info",
                message="agent layer identity bound",
                payload={
                    "workflow_event_type": "agent_layer_identity_bound",
                    "execution_id": task_id,
                    "runtime_task_id": runtime_task_id,
                    "request_sha256": digest,
                    "runtime_identity": {
                        "product": "JerryAgent",
                        "schema": "flai.agent-layer.v1",
                        "runtimeEventSchemaVersion": 1,
                        "instanceId": bound_instance_id or instance_id,
                        "sessionId": bound_session_id or session_id,
                        "runtimeKind": bound_runtime_kind,
                    },
                },
            )
        for revision in observed_revisions or []:
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id="jerryagent_research_agent",
                event_type="agent_log",
                level="info",
                message="agent layer observed",
                payload={
                    "workflow_event_type": "agent_layer_observed",
                    "execution_id": task_id,
                    "runtime_task_id": runtime_task_id,
                    "status": "running",
                    "revision": revision,
                },
            )
        if receipt:
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id="jerryagent_research_agent",
                event_type="agent_log",
                level="info",
                message="agent layer receipt",
                payload={
                    "workflow_event_type": "agent_layer_receipt",
                    "execution_adapter": "jerryagent_sidecar",
                    "execution_contract_version": "flai.agent-layer.v1",
                    "execution_id": task_id,
                    "request_sha256": digest,
                    "runtime_identity": {
                        "product": "JerryAgent",
                        "schema": "flai.agent-layer.v1",
                        "runtimeEventSchemaVersion": 1,
                        "instanceId": instance_id,
                        "sessionId": session_id,
                        "runtimeKind": "external",
                    },
                    "final_revision": final_revision,
                    "model_calls_attested_by_flai": False,
                },
            )
    finally:
        conn.close()


def _append_identity_bound_event(
    app,
    task_id: str,
    *,
    digest: str = "a" * 64,
    runtime_task_id: str = "runtime-task-a",
    instance_id: str = "instance-a",
    session_id: str = "session-a",
) -> None:
    conn = app.state.conn_factory()
    try:
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="jerryagent_research_agent",
            event_type="agent_log",
            level="info",
            message="agent layer identity bound",
            payload={
                "workflow_event_type": "agent_layer_identity_bound",
                "execution_id": task_id,
                "runtime_task_id": runtime_task_id,
                "request_sha256": digest,
                "runtime_identity": {
                    "product": "JerryAgent",
                    "schema": "flai.agent-layer.v1",
                    "runtimeEventSchemaVersion": 1,
                    "instanceId": instance_id,
                    "sessionId": session_id,
                    "runtimeKind": "external",
                },
            },
        )
    finally:
        conn.close()


def _json(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        stream=httpx.ByteStream(canonical_json_bytes(payload)),
        headers={"content-type": "application/json", "cache-control": "no-store"},
    )


def test_agent_facts_is_owner_scoped_no_store_full_snapshot(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_agent_facts")

    response = client.get("/api/conversations/conv_agent_facts/agent-facts")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {
        "schemaVersion",
        "conversationId",
        "generatedAt",
        "taskCount",
        "tasksTruncated",
        "tasks",
    }
    assert body["schemaVersion"] == "agent_fact_projection.v1"
    assert body["conversationId"] == "conv_agent_facts"
    assert body["taskCount"] == 0
    assert body["tasksTruncated"] is False
    assert body["tasks"] == []

    seed_user(
        app.state.db_path,
        username="other_engineer",
        display_name="其他工程师",
    )
    _conversation(app, "foreign", owner="other_engineer")
    foreign = client.get("/api/conversations/foreign/agent-facts")
    assert foreign.status_code == 404
    assert foreign.headers["cache-control"] == "no-store"
    conn = app.state.conn_factory()
    try:
        seed_pre_p23_legacy_conversation(
            conn,
            conversation_id="conv_legacy_agent_facts",
            agent_id="guide_agent",
            created_by="legacy",
        )
        conn.commit()
    finally:
        conn.close()
    legacy = client.get("/api/conversations/conv_legacy_agent_facts/agent-facts")
    assert legacy.status_code == 404
    assert legacy.headers["cache-control"] == "no-store"


def test_dependency_wait_handoff_and_deterministic_gate_are_flai_authority(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_dependencies")
    _task(app, "upstream", "conv_dependencies")
    _drive(app, "upstream", "queued", "validating", "running", "analyzing", "completed")
    _task(app, "downstream", "conv_dependencies", depends_on=["upstream"])

    waiting = client.get("/api/conversations/conv_dependencies/agent-facts").json()
    downstream = next(item for item in waiting["tasks"] if item["taskId"] == "downstream")
    assert downstream["phase"] == "waiting_upstream"
    assert downstream["dependencies"] == [
        {
            "taskId": "upstream",
            "agentId": "hello_agent",
            "status": "completed",
            "gate": "deterministic_provenance",
        }
    ]
    assert downstream["wait"] is None
    assert downstream["signoff"]["state"] == "not_required"
    assert downstream["runtime"] == {
        "adapter": "native_python",
        "reported": False,
        "reason": "not_applicable",
        "sourceEpoch": None,
        "revision": None,
        "status": None,
        "wait": None,
        "delegationHold": None,
        "subagentCount": 0,
        "subagentsTruncated": False,
        "subagents": [],
    }

    conn = app.state.conn_factory()
    try:
        repos.enqueue_dependent_task(
            conn,
            "downstream",
            [],
            event={
                "agent_id": "hello_agent",
                "event_type": "agent_log",
                "level": "info",
                "message": "dependency details that must not leak",
                "payload": {
                    "workflow_event_type": "dependency_resolved",
                    "upstream_task_ids": ["upstream"],
                    "secret": "must-not-leak",
                },
            },
        )
    finally:
        conn.close()
    resolved_response = client.get("/api/conversations/conv_dependencies/agent-facts")
    assert "must-not-leak" not in resolved_response.text
    resolved = next(
        item for item in resolved_response.json()["tasks"] if item["taskId"] == "downstream"
    )
    assert resolved["phase"] == "queued"
    assert resolved["wait"] is None
    assert resolved["handoffs"] == [
        {
            "fromTaskId": "upstream",
            "toTaskId": "downstream",
            "at": resolved["handoffs"][0]["at"],
        }
    ]


def test_dependency_gate_uses_frozen_version_and_missing_profile_fails_closed(
    app_env,
) -> None:
    client, app = app_env
    _conversation(app, "conv_frozen_gate")
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "INSERT INTO agent_versions (agent_id, version, yaml_json, created_at) "
            "VALUES ('hello_agent', '9.9.9', ?, '2026-07-20T00:00:00+00:00')",
            (
                json.dumps(
                    {
                        "model": {},
                        "workflow": {"requires_human_review": False},
                    }
                ),
            ),
        )
        conn.execute(
            "INSERT INTO agent_versions (agent_id, version, yaml_json, created_at) "
            "VALUES ('hello_agent', '9.9.8', ?, '2026-07-20T00:00:00+00:00')",
            (json.dumps({"model": {"profile": "none"}, "workflow": {}}),),
        )
    finally:
        conn.close()
    _task(app, "frozen-good", "conv_frozen_gate")
    _task(
        app,
        "frozen-missing-profile",
        "conv_frozen_gate",
        agent_version="9.9.9",
    )
    _task(
        app,
        "frozen-missing-review-mode",
        "conv_frozen_gate",
        agent_version="9.9.8",
    )
    for task_id in ("frozen-good", "frozen-missing-profile"):
        _drive(app, task_id, "queued", "validating", "running", "analyzing", "completed")
    _task(
        app,
        "frozen-consumer",
        "conv_frozen_gate",
        depends_on=["frozen-good", "frozen-missing-profile"],
    )

    # Current-package drift must not rewrite a historical dependency gate.
    current = app.state.agent_registry.get("hello_agent")
    current["model"]["profile"] = "reasoning"
    current["workflow"]["requires_human_review"] = True
    snapshot_tasks = client.get(
        "/api/conversations/conv_frozen_gate/agent-facts"
    ).json()["tasks"]
    consumer = next(
        item
        for item in snapshot_tasks
        if item["taskId"] == "frozen-consumer"
    )
    assert [item["gate"] for item in consumer["dependencies"]] == [
        "deterministic_provenance",
        "unknown",
    ]
    assert consumer["signoff"]["state"] == "not_required"
    assert next(
        item for item in snapshot_tasks if item["taskId"] == "frozen-missing-profile"
    )["signoff"]["state"] == "not_required"
    assert next(
        item
        for item in snapshot_tasks
        if item["taskId"] == "frozen-missing-review-mode"
    )["signoff"]["state"] == "unknown"


@pytest.mark.parametrize("corruption", ["missing", "cross_conversation"])
def test_corrupt_dependency_scope_fails_the_snapshot_closed(
    app_env, corruption: str
) -> None:
    client, app = app_env
    conversation_id = f"conv_dependency_scope_{corruption}"
    dependency_id = f"private-dependency-{corruption}"
    _conversation(app, conversation_id)
    if corruption == "cross_conversation":
        _conversation(app, "conv_dependency_scope_foreign")
        _task(app, dependency_id, "conv_dependency_scope_foreign")
    _task(
        app,
        f"dependent-{corruption}",
        conversation_id,
        depends_on=[dependency_id],
    )

    response = client.get(f"/api/conversations/{conversation_id}/agent-facts")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert dependency_id not in response.text


@pytest.mark.parametrize(
    ("action", "reason_code", "expected"),
    [("approve", None, "approved"), ("reject", "source_doubt", "rejected")],
)
def test_structured_human_decision_is_the_only_signoff_authority(
    app_env, action: str, reason_code: str | None, expected: str
) -> None:
    client, app = app_env
    _conversation(app, f"conv_{action}")
    _task(app, f"review_{action}", f"conv_{action}", agent_id="fta_agent")
    _drive(
        app,
        f"review_{action}",
        "queued",
        "validating",
        "running",
        "waiting_review",
    )
    before = client.get(f"/api/conversations/conv_{action}/agent-facts").json()["tasks"][0]
    assert before["phase"] == "awaiting_signoff"
    assert before["signoff"] == {
        "state": "awaiting_human",
        "requestedFrom": TEST_USERNAME,
        "reviewer": None,
        "decidedAt": None,
    }

    conn = app.state.conn_factory()
    try:
        repos.apply_human_review(
            conn,
            f"review_{action}",
            action=action,
            reviewer="王工",
            reviewer_username="wang.gong",
            reason_code=reason_code,
            comment=None,
        )
    finally:
        conn.close()
    after = client.get(f"/api/conversations/conv_{action}/agent-facts").json()["tasks"][0]
    assert after["signoff"]["state"] == expected
    assert after["signoff"]["reviewer"] == "王工"
    assert after["signoff"]["decidedAt"] is not None


@pytest.mark.parametrize("tamper", ["missing_witness", "decision_status", "task_time"])
def test_signoff_fails_closed_without_exact_witness_and_terminal_coherence(
    app_env, tamper: str
) -> None:
    client, app = app_env
    conversation_id = f"conv_signoff_tamper_{tamper}"
    task_id = f"review-tamper-{tamper}"
    _conversation(app, conversation_id)
    _task(app, task_id, conversation_id, agent_id="fta_agent")
    _drive(app, task_id, "queued", "validating", "running", "waiting_review")
    conn = app.state.conn_factory()
    try:
        repos.apply_human_review(
            conn,
            task_id,
            action="approve",
            reviewer="王工",
            reviewer_username="wang.gong",
            reason_code=None,
            comment=None,
        )
        if tamper == "missing_witness":
            conn.execute("DROP TRIGGER trg_task_review_event_witnesses_no_delete")
            conn.execute(
                "DELETE FROM task_review_event_witnesses WHERE task_id = ?",
                (task_id,),
            )
        elif tamper == "decision_status":
            conn.execute("DROP TRIGGER trg_task_human_decisions_no_update")
            conn.execute(
                "UPDATE task_human_decisions "
                "SET action = 'reject', reason_code = 'source_doubt' "
                "WHERE task_id = ?",
                (task_id,),
            )
        else:
            conn.execute("DROP TRIGGER trg_review_package_tasks_provenance_immutable")
            conn.execute(
                "UPDATE tasks SET updated_at = '2099-01-01T00:00:00+00:00' "
                "WHERE id = ?",
                (task_id,),
            )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/conversations/{conversation_id}/agent-facts")
    assert response.status_code == 200
    assert response.json()["tasks"][0]["signoff"] == {
        "state": "unknown",
        "requestedFrom": TEST_USERNAME,
        "reviewer": None,
        "decidedAt": None,
    }


@pytest.mark.parametrize("agent_id", ["fta_agent", "hello_agent"])
def test_untrusted_review_event_cannot_release_a_dependency(
    app_env, agent_id: str
) -> None:
    client, app = app_env
    conversation_id = f"conv_untrusted_review_dependency_{agent_id}"
    _conversation(app, conversation_id)
    _task(
        app,
        "reviewed-upstream",
        conversation_id,
        agent_id=agent_id,
    )
    _drive(
        app,
        "reviewed-upstream",
        "queued",
        "validating",
        "running",
        "waiting_review",
    )
    conn = app.state.conn_factory()
    try:
        repos.apply_human_review(
            conn,
            "reviewed-upstream",
            action="approve",
            reviewer="王工",
            reviewer_username="wang.gong",
            reason_code=None,
            comment=None,
        )
        conn.execute("DROP TRIGGER trg_task_human_decisions_no_update")
        conn.execute(
            "UPDATE task_human_decisions "
            "SET action = 'reject', reason_code = 'source_doubt' "
            "WHERE task_id = 'reviewed-upstream'"
        )
        conn.commit()
    finally:
        conn.close()
    _task(
        app,
        "dependent-on-untrusted-review",
        conversation_id,
        depends_on=["reviewed-upstream"],
    )

    tasks = client.get(
        f"/api/conversations/{conversation_id}/agent-facts"
    ).json()["tasks"]
    dependent = next(
        task for task in tasks if task["taskId"] == "dependent-on-untrusted-review"
    )
    assert dependent["dependencies"][0]["gate"] == "unknown"
    assert dependent["wait"]["kind"] == "dependency"


def test_valid_jerry_facts_are_sanitized_and_runtime_wait_is_secondary(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_jerry")
    _task(app, "jerry-task", "conv_jerry", agent_id="jerryagent_research_agent")
    _jerry_witness(app, "jerry-task")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/executions/jerry-task/facts")
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        return _json(_jerry_fact("jerry-task"))

    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(handler)
    )
    response = client.get("/api/conversations/conv_jerry/agent-facts")
    assert response.status_code == 200
    task = response.json()["tasks"][0]
    assert task["wait"] == {
        "kind": "subagent_completion",
        "since": "2026-07-20T12:00:00Z",
        "subjectTaskId": None,
        "subjectAgentId": None,
        "subjectOrdinal": 1,
        "pendingCount": 1,
        "continueWhen": "subagents_terminal",
    }
    assert set(task["runtime"]) == {
        "adapter",
        "reported",
        "reason",
        "sourceEpoch",
        "revision",
        "status",
        "wait",
        "delegationHold",
        "subagentCount",
        "subagentsTruncated",
        "subagents",
    }
    assert task["runtime"]["reported"] is True
    assert task["runtime"]["reason"] == "reported"
    assert len(task["runtime"]["sourceEpoch"]) == 64
    assert "identity" not in task["runtime"]
    assert "requestSha256" not in response.text
    assert task["signoff"]["state"] == "pending_result"


def test_historical_replay_facts_bind_to_the_durable_projection_identity(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_replay_identity")
    task_id = "jerry-replay-identity"
    _task(app, task_id, "conv_replay_identity", agent_id="jerryagent_research_agent")
    _jerry_witness(
        app,
        task_id,
        instance_id="replacement-instance",
        session_id="replacement-session",
        replayed=True,
        bound_instance_id="historical-instance",
        bound_session_id="historical-session",
    )
    payload = _jerry_fact(task_id)
    payload["identity"]["instanceId"] = "historical-instance"
    payload["identity"]["sessionId"] = "historical-session"
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    matched = client.get(
        "/api/conversations/conv_replay_identity/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert matched["reported"] is True

    app.state.jerryagent_facts_reader.close()
    drifted = copy.deepcopy(payload)
    drifted["identity"]["instanceId"] = "replacement-instance"
    drifted["identity"]["sessionId"] = "replacement-session"
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(drifted))
    )
    rejected = client.get(
        "/api/conversations/conv_replay_identity/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert rejected["reported"] is False
    assert rejected["reason"] == "malformed"


def test_legacy_replay_without_identity_bound_witness_is_not_reportable(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_replay_without_identity")
    task_id = "jerry-replay-without-identity"
    _task(
        app,
        task_id,
        "conv_replay_without_identity",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(app, task_id, replayed=True, identity_bound=False)
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(),
        transport=httpx.MockTransport(lambda _request: _json(_jerry_fact(task_id))),
    )

    runtime = client.get(
        "/api/conversations/conv_replay_without_identity/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


@pytest.mark.parametrize("tamper", ["after_observed", "digest", "duplicate"])
def test_identity_bound_witness_order_and_content_are_immutable(
    app_env, tamper: str
) -> None:
    client, app = app_env
    conversation_id = f"conv_identity_bound_{tamper}"
    task_id = f"jerry-identity-bound-{tamper}"
    _conversation(app, conversation_id)
    _task(app, task_id, conversation_id, agent_id="jerryagent_research_agent")
    if tamper == "after_observed":
        _jerry_witness(
            app,
            task_id,
            identity_bound=False,
            observed_revisions=[8],
        )
        _append_identity_bound_event(app, task_id)
    elif tamper == "digest":
        _jerry_witness(app, task_id, identity_bound=False)
        _append_identity_bound_event(app, task_id, digest="b" * 64)
    else:
        _jerry_witness(app, task_id)
        _append_identity_bound_event(app, task_id)
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(),
        transport=httpx.MockTransport(lambda _request: _json(_jerry_fact(task_id))),
    )

    runtime = client.get(
        f"/api/conversations/{conversation_id}/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


@pytest.mark.parametrize(
    "malformation",
    [
        "zero_pending",
        "terminal_wait",
        "terminal_active_child",
        "awaiting_without_approval",
        "approval_while_running",
        "approval_with_ordinal",
        "armed_hold_mismatch",
    ],
)
def test_jerry_wait_semantics_fail_closed_at_the_flai_boundary(
    app_env, malformation: str
) -> None:
    client, app = app_env
    conversation_id = f"conv_wait_semantics_{malformation}"
    task_id = f"jerry-wait-{malformation}"
    _conversation(app, conversation_id)
    _task(app, task_id, conversation_id, agent_id="jerryagent_research_agent")
    _jerry_witness(app, task_id)
    payload = _jerry_fact(task_id)
    if malformation == "zero_pending":
        payload["wait"]["pendingCount"] = 0
    elif malformation == "terminal_wait":
        payload["status"] = "completed"
        payload["subagents"][0]["status"] = "completed"
    elif malformation == "terminal_active_child":
        payload["status"] = "completed"
        payload["wait"] = None
    elif malformation == "awaiting_without_approval":
        payload["status"] = "awaiting_approval"
    elif malformation in {"approval_while_running", "approval_with_ordinal"}:
        payload["wait"] = {
            "kind": "runtime_approval",
            "since": "2026-07-20T12:00:00Z",
            "subjectOrdinal": 1 if malformation == "approval_with_ordinal" else None,
            "pendingCount": 1,
            "continueWhen": "approval_resolved",
        }
        if malformation == "approval_with_ordinal":
            payload["status"] = "awaiting_approval"
    else:
        payload["delegationHold"] = {
            "phase": "armed",
            "requestedAt": "2026-07-20T12:00:00Z",
            "resolvedAt": None,
            "satisfiedByOrdinal": None,
        }
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    runtime = client.get(
        f"/api/conversations/{conversation_id}/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


def test_valid_jerry_subagent_truncation_remains_truthful(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_jerry_truncated")
    _task(
        app,
        "jerry-truncated",
        "conv_jerry_truncated",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(app, "jerry-truncated")
    payload = _jerry_fact("jerry-truncated")
    payload["subagentCount"] = 65
    payload["subagentsTruncated"] = True
    payload["wait"]["pendingCount"] = 65
    payload["subagents"] = [
        {
            "ordinal": ordinal,
            "status": "running",
            "retryOfOrdinal": None,
            "createdAt": "2026-07-20T12:00:00Z",
            "updatedAt": "2026-07-20T12:00:01Z",
        }
        for ordinal in range(1, 65)
    ]
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    runtime = client.get(
        "/api/conversations/conv_jerry_truncated/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is True
    assert runtime["subagentCount"] == 65
    assert runtime["subagentsTruncated"] is True
    assert len(runtime["subagents"]) == 64


def test_jerry_facts_must_match_the_durable_started_request_digest(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_digest_mismatch")
    _task(
        app,
        "jerry-digest-mismatch",
        "conv_digest_mismatch",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(app, "jerry-digest-mismatch", digest="b" * 64)
    payload = _jerry_fact("jerry-digest-mismatch")
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    runtime = client.get(
        "/api/conversations/conv_digest_mismatch/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


def test_jerry_facts_must_match_the_durable_submitted_runtime_task_id(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_runtime_task_mismatch")
    _task(
        app,
        "jerry-runtime-task-mismatch",
        "conv_runtime_task_mismatch",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(
        app,
        "jerry-runtime-task-mismatch",
        runtime_task_id="durable-runtime-task",
    )
    payload = _jerry_fact("jerry-runtime-task-mismatch")
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    runtime = client.get(
        "/api/conversations/conv_runtime_task_mismatch/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


def test_jerry_fact_revision_cannot_regress_below_the_maximum_durable_observation(
    app_env,
) -> None:
    client, app = app_env
    _conversation(app, "conv_observed_revision")
    _task(
        app,
        "jerry-observed-revision",
        "conv_observed_revision",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(
        app,
        "jerry-observed-revision",
        observed_revisions=[7, 12],
    )
    payload = _jerry_fact("jerry-observed-revision")
    payload["revision"] = 12
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )
    current = client.get(
        "/api/conversations/conv_observed_revision/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert current["reported"] is True

    app.state.jerryagent_facts_reader.close()
    regressed = copy.deepcopy(payload)
    regressed["revision"] = 11
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(regressed))
    )
    runtime = client.get(
        "/api/conversations/conv_observed_revision/agent-facts"
    ).json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


def test_terminal_jerry_facts_must_match_the_durable_receipt(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_receipt")
    _task(
        app,
        "jerry-receipt",
        "conv_receipt",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(app, "jerry-receipt", receipt=True, final_revision=9)
    _drive(
        app,
        "jerry-receipt",
        "queued",
        "validating",
        "running",
        "waiting_review",
    )
    payload = _jerry_fact("jerry-receipt")
    payload["status"] = "completed"
    payload["wait"] = None
    payload["delegationHold"] = None
    payload["subagents"][0]["status"] = "completed"
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )
    matched = client.get("/api/conversations/conv_receipt/agent-facts").json()[
        "tasks"
    ][0]
    assert matched["runtime"]["reported"] is True
    assert matched["runtime"]["revision"] == 9
    assert matched["signoff"]["state"] == "awaiting_human"

    app.state.jerryagent_facts_reader.close()
    drifted = copy.deepcopy(payload)
    drifted["identity"]["instanceId"] = "different-instance"
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(drifted))
    )
    runtime = client.get("/api/conversations/conv_receipt/agent-facts").json()[
        "tasks"
    ][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"


def test_jerry_runtime_approval_never_becomes_flai_signoff(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_jerry_approval")
    _task(
        app,
        "jerry-approval",
        "conv_jerry_approval",
        agent_id="jerryagent_research_agent",
    )
    _jerry_witness(app, "jerry-approval")
    payload = _jerry_fact("jerry-approval")
    payload["status"] = "awaiting_approval"
    payload["wait"] = {
        "kind": "runtime_approval",
        "since": "2026-07-20T12:00:00Z",
        "subjectOrdinal": None,
        "pendingCount": 1,
        "continueWhen": "approval_resolved",
    }
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )

    task = client.get("/api/conversations/conv_jerry_approval/agent-facts").json()[
        "tasks"
    ][0]
    assert task["runtime"]["status"] == "awaiting_approval"
    assert task["wait"]["kind"] == "runtime_approval"
    assert task["signoff"] == {
        "state": "pending_result",
        "requestedFrom": TEST_USERNAME,
        "reviewer": None,
        "decidedAt": None,
    }


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("disabled", "disabled"), ("404", "not_found"), ("503", "malformed")],
)
def test_jerry_disabled_and_exact_404_are_closed_nonfatal_reasons(
    app_env, mode: str, expected: str
) -> None:
    client, app = app_env
    _conversation(app, f"conv_jerry_{mode}")
    _task(
        app,
        f"jerry-{mode}",
        f"conv_jerry_{mode}",
        agent_id="jerryagent_research_agent",
    )
    if mode != "disabled":
        _jerry_witness(app, f"jerry-{mode}")
        status = int(mode)
        app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
            _settings(),
            transport=httpx.MockTransport(
                lambda _request: _json(
                    {
                        "error": (
                            "not found"
                            if status == 404
                            else "PRIVATE-PERSISTED-CORRUPTION"
                        )
                    },
                    status=status,
                )
            ),
        )
    response = client.get(f"/api/conversations/conv_jerry_{mode}/agent-facts")
    assert response.status_code == 200
    runtime = response.json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == expected
    assert "PRIVATE-PERSISTED-CORRUPTION" not in response.text


@pytest.mark.parametrize(
    "malformation",
    ["free_text", "identity", "identity_type", "ordinal", "revision"],
)
def test_malformed_jerry_facts_fail_closed_without_leaking_error_text(
    app_env, malformation: str
) -> None:
    client, app = app_env
    _conversation(app, f"conv_bad_{malformation}")
    task_id = f"jerry-bad-{malformation}"
    _task(app, task_id, f"conv_bad_{malformation}", agent_id="jerryagent_research_agent")
    _jerry_witness(app, task_id)
    payload = copy.deepcopy(_jerry_fact(task_id))
    if malformation == "free_text":
        payload["privateThought"] = "INTERNAL-ERROR-SECRET"
    elif malformation == "identity":
        payload["identity"]["executionId"] = "other-task"
    elif malformation == "identity_type":
        payload["identity"]["runtimeEventSchemaVersion"] = True
    elif malformation == "ordinal":
        payload["subagents"][0]["ordinal"] = 2
    else:
        payload["revision"] = True

    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(lambda _request: _json(payload))
    )
    response = client.get(f"/api/conversations/conv_bad_{malformation}/agent-facts")
    assert response.status_code == 200
    runtime = response.json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "malformed"
    assert runtime["subagents"] == []
    assert "INTERNAL-ERROR-SECRET" not in response.text


def test_unreachable_jerry_does_not_fail_the_flai_snapshot(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_unreachable")
    _task(app, "jerry-unreachable", "conv_unreachable", agent_id="jerryagent_research_agent")
    _jerry_witness(app, "jerry-unreachable")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PRIVATE-UPSTREAM-DETAIL", request=request)

    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(handler)
    )
    response = client.get("/api/conversations/conv_unreachable/agent-facts")
    assert response.status_code == 200
    runtime = response.json()["tasks"][0]["runtime"]
    assert runtime["reported"] is False
    assert runtime["reason"] == "unreachable"
    assert "PRIVATE-UPSTREAM-DETAIL" not in response.text


def test_unreachable_jerry_is_circuit_broken_once_per_snapshot(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_circuit")
    for index in range(5):
        _task(
            app,
            f"jerry-circuit-{index}",
            "conv_circuit",
            agent_id="jerryagent_research_agent",
        )
        _jerry_witness(app, f"jerry-circuit-{index}")
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("offline", request=request)

    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(handler)
    )
    response = client.get("/api/conversations/conv_circuit/agent-facts")
    assert response.status_code == 200
    assert attempts == 1
    assert {
        task["runtime"]["reason"] for task in response.json()["tasks"]
    } == {"unreachable"}


def test_jerry_reads_share_one_bounded_snapshot_deadline(
    app_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, app = app_env
    _conversation(app, "conv_snapshot_deadline")
    for index in range(5):
        task_id = f"jerry-deadline-{index}"
        _task(
            app,
            task_id,
            "conv_snapshot_deadline",
            agent_id="jerryagent_research_agent",
        )
        _jerry_witness(app, task_id)

    clock = 0.0
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts, clock
        attempts += 1
        clock += 1.1
        task_id = request.url.path.split("/")[-2]
        return _json(_jerry_fact(task_id))

    monkeypatch.setattr(fact_projection, "_monotonic", lambda: clock, raising=False)
    app.state.jerryagent_facts_reader = build_jerryagent_facts_reader(
        _settings(), transport=httpx.MockTransport(handler)
    )

    response = client.get("/api/conversations/conv_snapshot_deadline/agent-facts")

    assert response.status_code == 200
    assert attempts == 2
    reasons = [task["runtime"]["reason"] for task in response.json()["tasks"]]
    assert reasons.count("reported") == 2
    assert reasons.count("unreachable") == 3


def test_event_projection_filters_noise_and_fails_closed_at_its_hard_limit(
    app_env,
) -> None:
    client, app = app_env
    _conversation(app, "conv_event_limit")
    _task(app, "event-limit-task", "conv_event_limit")
    conn = app.state.conn_factory()
    try:
        def rows(kind: str, count: int):
            payload = json.dumps(
                {
                    "workflow_event_type": kind,
                    "upstream_task_ids": [],
                }
            )
            return [
                (
                    f"event-{kind}-{index}",
                    "event-limit-task",
                    "hello_agent",
                    "agent_log",
                    "info",
                    "bounded projection event",
                    payload,
                    "2026-07-20T00:00:00+00:00",
                )
                for index in range(4097)
            ]

        insert_sql = (
            "INSERT INTO task_events "
            "(event_id, task_id, agent_id, event_type, level, message, "
            "payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        conn.executemany(insert_sql, rows("noise", 4097))
        conn.commit()
    finally:
        conn.close()

    noise_only = client.get("/api/conversations/conv_event_limit/agent-facts")
    assert noise_only.status_code == 200

    conn = app.state.conn_factory()
    try:
        conn.executemany(insert_sql, rows("dependency_resolved", 4097))
        conn.commit()
    finally:
        conn.close()
    capped = client.get("/api/conversations/conv_event_limit/agent-facts")
    assert capped.status_code == 503
    assert capped.headers["cache-control"] == "no-store"


def test_snapshot_truthfully_truncates_to_latest_one_hundred_tasks(app_env) -> None:
    client, app = app_env
    _conversation(app, "conv_many")
    for index in range(101):
        _task(app, f"many-{index:03d}", "conv_many")

    body = client.get("/api/conversations/conv_many/agent-facts").json()
    assert body["taskCount"] == 101
    assert body["tasksTruncated"] is True
    assert len(body["tasks"]) == 100
    assert "many-100" in {task["taskId"] for task in body["tasks"]}
    assert "many-000" not in {task["taskId"] for task in body["tasks"]}
    assert set(body["tasks"][0]) == {
        "taskId",
        "agentId",
        "status",
        "createdAt",
        "updatedAt",
        "phase",
        "dependencies",
        "wait",
        "handoffs",
        "signoff",
        "runtime",
    }
