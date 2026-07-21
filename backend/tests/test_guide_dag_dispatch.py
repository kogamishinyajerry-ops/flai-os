"""Guide versioned DAG dispatch contracts, exercised through the public dispatch seam."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from agents.guide_agent import workflow as guide_workflow
from backend.app.jobs.runner import resolve_dependencies_once
from backend.app.storage import repos


REPO_ROOT = Path(__file__).resolve().parents[2]


CONTROL_INPUTS = {
    "system_name": "双通道供电控制",
    "states": ["OFF", "ON"],
    "transitions": [{"from": "OFF", "to": "ON", "condition": "收到启动指令"}],
}
FTA_INPUTS = {
    "top_event": "供电完全丧失",
    "system_description": "双通道供电控制系统",
    "components": ["主汇流条", "备用汇流条"],
}


def _valid_dag() -> dict[str, Any]:
    return {
        "decision": "orchestrate",
        "contract": "guide_dag.v1",
        "analysis": "先确定性整理控制结构，再形成 FTA 人审草案",
        "goal": "形成可审阅的供电失效分析草案",
        "workflow": "control 节点产物定向传给唯一 FTA 叶节点",
        "nodes": [
            {
                "node_id": "control",
                "agent_id": "control_logic_agent",
                "agent_version": "0.2.0",
                "prefilled_inputs": CONTROL_INPUTS,
                "stripped_fields": [],
                "depends_on": [],
                "artifact_binding": {"mode": "none", "from_nodes": []},
                "attachment_binding": {"mode": "none"},
            },
            {
                "node_id": "fta",
                "agent_id": "fta_agent",
                "agent_version": "0.2.0",
                "prefilled_inputs": FTA_INPUTS,
                "stripped_fields": [],
                "depends_on": ["control"],
                "artifact_binding": {"mode": "selected", "from_nodes": ["control"]},
                "attachment_binding": {"mode": "none"},
            },
        ],
        "dropped_agents": [],
        "capped": False,
    }


def _explicit_dag_inputs() -> str:
    return json.dumps(
        {
            "inputs_by_agent": {
                "control_logic_agent": CONTROL_INPUTS,
                "fta_agent": FTA_INPUTS,
            }
        },
        ensure_ascii=False,
    )


def _dispatch(
    app: Any,
    recommendation: dict[str, Any],
    *,
    current_user_content: str = "{}",
    has_attachments: bool = False,
    current_file_bindings: tuple[dict[str, Any], ...] = (),
    has_historical_attachments: bool = False,
) -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        execution = app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
            conn,
            conversation_id="conv_dag_contract",
            recommendation=recommendation,
            request_id="turn_dag_contract_001",
            actor_display_name="测试工程师",
            actor_username="test_engineer",
            actor_role="admin",
            current_user_content=current_user_content,
            has_attachments=has_attachments,
            current_file_bindings=current_file_bindings,
            has_historical_attachments=has_historical_attachments,
        )
        assert repos.list_tasks(conn, conversation_id="conv_dag_contract") == []
        conn.execute("ROLLBACK")
        return execution
    finally:
        conn.close()


def test_unknown_dag_contract_fails_closed_before_task_creation(app_env) -> None:
    _client, app = app_env

    execution = _dispatch(
        app,
        {
            "decision": "orchestrate",
            "contract": "guide_dag.v2",
            "nodes": [],
            "dropped_agents": [],
            "capped": False,
        },
    )

    assert execution["status"] == "blocked_conflict"
    assert execution["issues"][0]["code"] == "GRAPH_CONTRACT_UNSUPPORTED"


def test_dag_dependency_must_reference_an_earlier_node(app_env) -> None:
    _client, app = app_env
    recommendation = _valid_dag()
    recommendation["nodes"][0]["depends_on"] = ["fta"]

    execution = _dispatch(app, recommendation)

    assert execution["status"] == "blocked_conflict"
    assert execution["issues"][0]["code"] == "GRAPH_DEPENDENCY_ORDER_INVALID"


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("duplicate_agent", "GRAPH_AGENT_DUPLICATE"),
        ("multiple_leaves", "GRAPH_LEAF_COUNT_INVALID"),
        ("artifact_outside_edge", "ARTIFACT_BINDING_INVALID"),
        ("dependent_none", "ARTIFACT_BINDING_INVALID"),
    ],
)
def test_dag_shape_rejects_ambiguous_or_unauthorized_edges(
    app_env, case: str, expected_code: str
) -> None:
    _client, app = app_env
    recommendation = copy.deepcopy(_valid_dag())
    if case == "duplicate_agent":
        recommendation["nodes"][1]["agent_id"] = "control_logic_agent"
    elif case == "multiple_leaves":
        recommendation["nodes"][1]["depends_on"] = []
        recommendation["nodes"][1]["artifact_binding"] = {
            "mode": "none",
            "from_nodes": [],
        }
    elif case == "artifact_outside_edge":
        recommendation["nodes"][1]["artifact_binding"] = {
            "mode": "selected",
            "from_nodes": ["not_a_dependency"],
        }
    else:
        recommendation["nodes"][1]["artifact_binding"] = {
            "mode": "none",
            "from_nodes": [],
        }

    execution = _dispatch(app, recommendation)

    assert execution["status"] == "blocked_conflict"
    assert execution["issues"][0]["code"] == expected_code


def test_dag_rejects_model_or_review_gated_intermediate_node(app_env) -> None:
    _client, app = app_env
    recommendation = copy.deepcopy(_valid_dag())
    recommendation["nodes"] = [
        {
            **recommendation["nodes"][1],
            "depends_on": [],
            "artifact_binding": {"mode": "none", "from_nodes": []},
        },
        {
            **recommendation["nodes"][0],
            "depends_on": ["fta"],
            "artifact_binding": {"mode": "selected", "from_nodes": ["fta"]},
        },
    ]

    execution = _dispatch(app, recommendation)

    assert execution["status"] == "blocked_policy"
    assert execution["issues"][0]["code"] == "PROVISIONAL_EDGE_UNSUPPORTED"


def test_dag_requires_the_only_leaf_to_stop_for_human_review(app_env) -> None:
    _client, app = app_env
    recommendation = copy.deepcopy(_valid_dag())
    recommendation["nodes"] = [recommendation["nodes"][0]]

    execution = _dispatch(app, recommendation)

    assert execution["status"] == "blocked_policy"
    assert execution["issues"][0]["code"] == "FINAL_REVIEW_REQUIRED"


def test_dag_requires_exact_current_turn_inputs_by_agent_mapping(app_env) -> None:
    _client, app = app_env

    execution = _dispatch(
        app,
        _valid_dag(),
        current_user_content=json.dumps(CONTROL_INPUTS, ensure_ascii=False),
    )

    assert execution["status"] == "blocked_source"
    assert execution["issues"][0]["code"] == "UNVERIFIED_INPUT_SOURCE"


def test_dag_rejects_historical_attachment_as_current_authority(app_env) -> None:
    _client, app = app_env

    execution = _dispatch(
        app,
        _valid_dag(),
        current_user_content=_explicit_dag_inputs(),
        has_historical_attachments=True,
    )

    assert execution["status"] == "blocked_source"
    assert execution["issues"][0]["code"] == "HISTORICAL_ATTACHMENT_SOURCE_UNBOUND"


def test_dag_attachment_declaration_must_match_current_turn_evidence(app_env) -> None:
    _client, app = app_env
    recommendation = _valid_dag()
    recommendation["nodes"][1]["attachment_binding"] = {"mode": "current_turn"}

    execution = _dispatch(
        app,
        recommendation,
        current_user_content=_explicit_dag_inputs(),
    )

    assert execution["status"] == "blocked_source"
    assert execution["issues"][0]["code"] == "ATTACHMENT_BINDING_MISMATCH"


def test_dag_current_attachments_require_exactly_one_target_node(app_env) -> None:
    _client, app = app_env
    file_binding = {
        "file_id": "file_current_turn_001",
        "sha256": "a" * 64,
        "classification": "internal",
        "uploaded_by_username": "test_engineer",
    }

    execution = _dispatch(
        app,
        _valid_dag(),
        current_user_content=_explicit_dag_inputs(),
        has_attachments=True,
        current_file_bindings=(file_binding,),
    )

    assert execution["status"] == "blocked_source"
    assert execution["issues"][0]["code"] == "ATTACHMENT_TARGET_AMBIGUOUS"


def test_dag_dispatch_materializes_versioned_task_graph_in_one_transaction(app_env) -> None:
    _client, app = app_env
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        execution = app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
            conn,
            conversation_id="conv_dag_positive",
            recommendation=_valid_dag(),
            request_id="turn_dag_positive_001",
            actor_display_name="测试工程师",
            actor_username="test_engineer",
            actor_role="admin",
            current_user_content=_explicit_dag_inputs(),
            current_file_bindings=(),
            has_historical_attachments=False,
        )
        tasks = {
            task["agent_id"]: task
            for task in repos.list_tasks(conn, conversation_id="conv_dag_positive")
        }

        assert execution["status"] == "dispatched"
        assert execution["graph_version"] == "guide_dag.v1"
        assert len(execution["graph_digest"]) == 64
        assert [item["node_id"] for item in execution["node_tasks"]] == ["control", "fta"]
        assert execution["task_ids"] == [
            item["task_id"] for item in execution["node_tasks"]
        ]
        control = tasks["control_logic_agent"]
        fta = tasks["fta_agent"]
        assert control["status"] == "queued"
        assert fta["status"] == "created"
        assert fta["depends_on"] == [control["id"]]
        assert control["input_binding"] == {"from_tasks": []}
        assert fta["input_binding"] == {"from_tasks": [control["id"]]}
        assert control["source_binding"]["params"] == {
            "kind": "current_turn_json",
            "json_pointer": "/inputs_by_agent/control_logic_agent",
            "value_digest": hashlib.sha256(
                json.dumps(
                    CONTROL_INPUTS,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }
        assert control["source_binding"]["attachments"] == []
        assert fta["source_binding"]["graph_digest"] == execution["graph_digest"]
        assert [event["event_type"] for event in repos.list_events(conn, control["id"])] == [
            "task_created"
        ]
        assert [event["event_type"] for event in repos.list_events(conn, fta["id"])] == [
            "task_created"
        ]
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_dag_dispatch_binds_all_current_attachments_to_exactly_one_node(app_env) -> None:
    _client, app = app_env
    recommendation = _valid_dag()
    recommendation["nodes"][1]["attachment_binding"] = {"mode": "current_turn"}
    binding = {
        "file_id": "file_current_turn_bound_001",
        "sha256": "b" * 64,
        "classification": "internal",
        "uploaded_by_username": "test_engineer",
    }
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        execution = app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
            conn,
            conversation_id="conv_dag_attachment_positive",
            recommendation=recommendation,
            request_id="turn_dag_attachment_positive_001",
            actor_display_name="测试工程师",
            actor_username="test_engineer",
            actor_role="admin",
            current_user_content=_explicit_dag_inputs(),
            current_file_bindings=(binding,),
            has_historical_attachments=False,
        )
        tasks = {
            task["agent_id"]: task
            for task in repos.list_tasks(
                conn, conversation_id="conv_dag_attachment_positive"
            )
        }

        assert execution["status"] == "dispatched"
        assert tasks["control_logic_agent"]["input_file_ids"] == []
        assert tasks["control_logic_agent"]["source_binding"]["attachments"] == []
        assert tasks["fta_agent"]["input_file_ids"] == [binding["file_id"]]
        assert tasks["fta_agent"]["source_binding"]["attachments"] == [
            {
                "slot": "input_file_ids",
                "file_id": binding["file_id"],
                "conversation_id": "conv_dag_attachment_positive",
                "uploaded_by_username": "test_engineer",
                "sha256": binding["sha256"],
                "classification": "internal",
                "kind": "input",
                "task_id": None,
            }
        ]
        assert tasks["fta_agent"]["source_binding"]["graph_digest"] == execution[
            "graph_digest"
        ]
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_single_review_leaf_dag_accepts_current_turn_attachment(app_env) -> None:
    _client, app = app_env
    recommendation = _valid_dag()
    recommendation["nodes"] = [
        {
            **recommendation["nodes"][1],
            "depends_on": [],
            "artifact_binding": {"mode": "none", "from_nodes": []},
            "attachment_binding": {"mode": "current_turn"},
        }
    ]
    binding = {
        "file_id": "file_single_review_leaf_001",
        "sha256": "d" * 64,
        "classification": "internal",
        "uploaded_by_username": "test_engineer",
    }
    current_content = json.dumps(
        {"inputs_by_agent": {"fta_agent": FTA_INPUTS}},
        ensure_ascii=False,
    )
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        execution = app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
            conn,
            conversation_id="conv_dag_single_review_leaf",
            recommendation=recommendation,
            request_id="turn_dag_single_review_leaf_001",
            actor_display_name="测试工程师",
            actor_username="test_engineer",
            actor_role="admin",
            current_user_content=current_content,
            has_attachments=True,
            current_file_bindings=(binding,),
            has_historical_attachments=False,
        )
        tasks = repos.list_tasks(
            conn, conversation_id="conv_dag_single_review_leaf"
        )

        assert execution["status"] == "dispatched"
        assert execution["graph_version"] == "guide_dag.v1"
        assert len(tasks) == 1
        assert execution["node_tasks"] == [
            {
                "node_id": "fta",
                "agent_id": "fta_agent",
                "task_id": tasks[0]["id"],
                "initial_status": "queued",
            }
        ]
        assert tasks[0]["input_file_ids"] == [binding["file_id"]]
        assert tasks[0]["source_binding"]["attachments"][0]["file_id"] == binding[
            "file_id"
        ]
        assert app.state.agent_registry.get("fta_agent")["workflow"][
            "requires_human_review"
        ] is True
        assert "review_approved" not in {
            event["event_type"] for event in repos.list_events(conn, tasks[0]["id"])
        }
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_materialized_dag_advances_through_existing_resolver(app_env) -> None:
    _client, app = app_env
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
            conn,
            conversation_id="conv_dag_resolver",
            recommendation=_valid_dag(),
            request_id="turn_dag_resolver_001",
            actor_display_name="测试工程师",
            actor_username="test_engineer",
            actor_role="admin",
            current_user_content=_explicit_dag_inputs(),
        )
        conn.execute("COMMIT")
        tasks = {
            task["agent_id"]: task
            for task in repos.list_tasks(conn, conversation_id="conv_dag_resolver")
        }
        root = tasks["control_logic_agent"]
        leaf = tasks["fta_agent"]
        for status in ("validating", "running", "analyzing", "completed"):
            repos.set_task_status(conn, root["id"], status)
        output_id = "file_dag_resolver_output_001"
        repos.create_file(
            conn,
            file_id=output_id,
            task_id=root["id"],
            kind="output",
            filename="control_logic.json",
            path="/tmp/control_logic.json",
            size_bytes=1,
            sha256="c" * 64,
            classification="internal",
        )
        repos.set_task_outputs(conn, root["id"], [output_id])
        assert repos.get_task(conn, leaf["id"])["status"] == "created"
    finally:
        conn.close()

    assert resolve_dependencies_once(app.state.conn_factory) == 1
    conn = app.state.conn_factory()
    try:
        advanced_leaf = repos.get_task(conn, leaf["id"])
        assert advanced_leaf["status"] == "queued"
        assert advanced_leaf["input_file_ids"] == [output_id]
    finally:
        conn.close()


def test_dag_second_node_event_failure_leaves_no_partial_graph(
    app_env, monkeypatch
) -> None:
    _client, app = app_env
    original_append_event = repos.append_event
    calls = 0
    attempted_task_ids: list[str] = []

    def _fail_second_event(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        attempted_task_ids.append(kwargs["task_id"])
        if calls == 2:
            raise RuntimeError("injected second DAG event failure")
        return original_append_event(*args, **kwargs)

    monkeypatch.setattr(repos, "append_event", _fail_second_event)
    conn = app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(RuntimeError, match="second DAG event failure"):
            app.state.conversation_service.guide_plan_dispatch.dispatch_in_transaction(
                conn,
                conversation_id="conv_dag_atomic_failure",
                recommendation=_valid_dag(),
                request_id="turn_dag_atomic_failure_001",
                actor_display_name="测试工程师",
                actor_username="test_engineer",
                actor_role="admin",
                current_user_content=_explicit_dag_inputs(),
            )
        conn.execute("ROLLBACK")
    finally:
        conn.close()

    conn = app.state.conn_factory()
    try:
        assert repos.list_tasks(conn, conversation_id="conv_dag_atomic_failure") == []
        assert all(repos.list_events(conn, task_id) == [] for task_id in attempted_task_ids)
    finally:
        conn.close()


def test_guide_workflow_normalizes_only_explicit_versioned_dag(app_env) -> None:
    _client, app = app_env
    proposed = _valid_dag()

    class _DagStub:
        def chat(self, profile: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "content": "DAG 已明确。\n<<PLAN>>\n"
                + json.dumps(proposed, ensure_ascii=False)
                + "\n<<END>>",
            }

    result = guide_workflow.run(
        {
            "messages": [{"role": "user", "content": _explicit_dag_inputs()}],
            "model_gateway": _DagStub(),
            "agent_registry": app.state.agent_registry,
            "agent_config": app.state.agent_registry.get("guide_agent"),
            "safe_auto_agent_ids": {"control_logic_agent", "fta_agent"},
        }
    )
    recommendation = result["recommendation"]

    assert recommendation["contract"] == "guide_dag.v1"
    assert [node["node_id"] for node in recommendation["nodes"]] == ["control", "fta"]
    assert [node["agent_version"] for node in recommendation["nodes"]] == [
        "0.2.0",
        "0.2.0",
    ]
    assert all(node["stripped_fields"] == [] for node in recommendation["nodes"])
    validate(
        recommendation,
        json.loads(
            (REPO_ROOT / "agents" / "guide_agent" / "output_schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def test_guide_workflow_rejects_unknown_graph_contract_instead_of_falling_back(
    app_env,
) -> None:
    _client, app = app_env
    proposed = _valid_dag()
    proposed["contract"] = "guide_dag.v2"
    proposed["agents"] = [
        {
            "agent_id": "control_logic_agent",
            "prefilled_inputs": CONTROL_INPUTS,
        }
    ]

    class _UnknownContractStub:
        def chat(self, profile: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "content": "<<PLAN>>\n"
                + json.dumps(proposed, ensure_ascii=False)
                + "\n<<END>>"
            }

    result = guide_workflow.run(
        {
            "messages": [{"role": "user", "content": _explicit_dag_inputs()}],
            "model_gateway": _UnknownContractStub(),
            "agent_registry": app.state.agent_registry,
            "agent_config": app.state.agent_registry.get("guide_agent"),
            "safe_auto_agent_ids": {"control_logic_agent", "fta_agent"},
        }
    )

    assert result["recommendation"] is None


def test_safe_auto_http_turn_dispatches_explicit_dag_and_persists_receipt(app_env) -> None:
    client, app = app_env
    proposed = _valid_dag()

    class _DagStub:
        def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
            return {
                "content": "DAG 已明确。\n<<PLAN>>\n"
                + json.dumps(proposed, ensure_ascii=False)
                + "\n<<END>>",
                "model_name": "stub",
                "token_usage": None,
                "finish_reason": "stop",
            }

    app.state.conversation_service.model_gateway = _DagStub()
    opened = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert opened.status_code == 200, opened.text
    conversation_id = opened.json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "content": _explicit_dag_inputs(),
            "execution_mode": "safe_auto",
            "request_id": "turn_dag_http_positive_001",
        },
    )

    assert response.status_code == 200, response.text
    execution = response.json()["execution"]
    assert execution["status"] == "dispatched"
    assert execution["graph_version"] == "guide_dag.v1"
    assert [item["initial_status"] for item in execution["node_tasks"]] == [
        "queued",
        "created",
    ]
    validate(
        response.json()["message"]["recommendation"],
        json.loads(
            (REPO_ROOT / "agents" / "guide_agent" / "output_schema.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    conn = app.state.conn_factory()
    try:
        tasks = repos.list_tasks(conn, conversation_id=conversation_id)
        receipt = repos.get_conversation_dispatch(
            conn, conversation_id, "turn_dag_http_positive_001"
        )
        assert len(tasks) == 2
        assert receipt is not None
        assert receipt["result"]["execution"]["task_ids"] == execution["task_ids"]
    finally:
        conn.close()


def test_dag_schema_requires_graph_projection_when_execution_is_dispatched(app_env) -> None:
    _client, app = app_env
    proposed = _valid_dag()

    class _DagStub:
        def chat(self, profile: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "content": "<<PLAN>>\n"
                + json.dumps(proposed, ensure_ascii=False)
                + "\n<<END>>"
            }

    recommendation = guide_workflow.run(
        {
            "messages": [{"role": "user", "content": _explicit_dag_inputs()}],
            "model_gateway": _DagStub(),
            "agent_registry": app.state.agent_registry,
            "agent_config": app.state.agent_registry.get("guide_agent"),
            "safe_auto_agent_ids": {"control_logic_agent", "fta_agent"},
        }
    )["recommendation"]
    recommendation["execution"] = {
        "mode": "safe_auto",
        "request_id": "turn_dag_schema_probe_001",
        "status": "dispatched",
        "plan_digest": "sha256:" + "a" * 64,
        "task_ids": ["task_a", "task_b"],
        "issues": [],
        "replayed": False,
    }
    schema = json.loads(
        (REPO_ROOT / "agents" / "guide_agent" / "output_schema.json").read_text(
            encoding="utf-8"
        )
    )

    with pytest.raises(ValidationError):
        validate(recommendation, schema)
