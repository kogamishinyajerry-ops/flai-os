from __future__ import annotations

import shutil
from pathlib import Path
from types import MappingProxyType
import json

from backend.app.config import CONTRACTS_DIR, TOOLS_DIR
from backend.app.governance import eval_runner
from backend.app.runtime.agent_execution import (
    AgentExecutionOutcome,
    AgentExecutionRequest,
    AgentExecutionRouter,
    ExecutionReceipt,
    NativeWorkflowAdapter,
)
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.tests.test_runtime import _FakeModelGateway, _RealishToolRegistry


class _FakeJerryAdapter:
    adapter = "jerryagent_sidecar"
    contract_version = "flai.agent-layer.v1"

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def execute(self, request: AgentExecutionRequest) -> AgentExecutionOutcome:
        assert set(request.context) == {"event_logger"}
        assert callable(getattr(request.context["event_logger"], "log", None))
        request.output_dir.mkdir(parents=True, exist_ok=True)
        (request.output_dir / "jerryagent_result.md").write_text(
            "# 待人工复核候选\n", encoding="utf-8"
        )
        return AgentExecutionOutcome(
            result={
                "status": "success",
                "outputs": [
                    {
                        "summary": "待人工复核候选",
                        "runtime_task_id": "runtime-1",
                        "request_sha256": "a" * 64,
                        "candidate_only": True,
                        "human_review_required": True,
                    }
                ],
            },
            receipt=ExecutionReceipt(
                adapter=self.adapter,
                contract_version=self.contract_version,
                execution_id=str(request.task["id"]),
                request_sha256="a" * 64,
                runtime_identity=MappingProxyType(
                    {
                        "product": "JerryAgent",
                        "schema": self.contract_version,
                        "instanceId": "instance-1",
                        "sessionId": "session-1",
                    }
                ),
                final_revision=12,
                model_calls_attested_by_flai=False,
            ),
        )


class _InvalidJerryAdapter(_FakeJerryAdapter):
    def execute(self, request: AgentExecutionRequest) -> AgentExecutionOutcome:
        outcome = super().execute(request)
        invalid = dict(outcome.result["outputs"][0])
        invalid["candidate_only"] = False
        return AgentExecutionOutcome(
            result={"status": "success", "outputs": [invalid]},
            receipt=outcome.receipt,
        )


def _runtime(tmp_path: Path, router: AgentExecutionRouter) -> tuple[AgentRuntime, Path]:
    agents_dir = tmp_path / "agents"
    package = agents_dir / "jerryagent_research_agent"
    source_agents_dir = Path(__file__).resolve().parents[2] / "agents"
    shutil.copytree(
        source_agents_dir / "jerryagent_research_agent",
        package,
    )
    shutil.copytree(source_agents_dir / "hello_agent", agents_dir / "hello_agent")
    manifest = package / "agent.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "status: disabled", "status: draft"
        ),
        encoding="utf-8",
    )
    registry = AgentRegistry(agents_dir, CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    assert registry.errors == []
    db_path = tmp_path / "flai.db"
    init_db(db_path)
    runtime = AgentRuntime(
        registry,
        _RealishToolRegistry(TOOLS_DIR),
        _FakeModelGateway(),
        lambda: get_conn(db_path),
        tmp_path / "task_runs",
        uploads_dir=tmp_path / "uploads",
        execution_router=router,
    )
    return runtime, db_path


def _create(
    db_path: Path,
    *,
    task_id: str = "jerry-task-1",
    agent_id: str = "jerryagent_research_agent",
    execution_adapter: str = "jerryagent_sidecar",
    execution_contract_version: str = "flai.agent-layer.v1",
) -> str:
    conn = get_conn(db_path)
    try:
        task = repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version="0.1.0",
            name="研究复利候选",
            created_by="tester",
            inputs={"objective": "比较两项已签发结论并列出下一轮未知项"},
            execution_adapter=execution_adapter,
            execution_contract_version=execution_contract_version,
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
        return task["id"]
    finally:
        conn.close()


def test_external_version_drift_early_failure_is_statically_sensitive(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(tmp_path, AgentExecutionRouter())
    external_task_id = _create(db_path, task_id="external-version-drift")
    native_task_id = _create(
        db_path,
        task_id="native-version-drift",
        agent_id="hello_agent",
        execution_adapter="native_python",
        execution_contract_version="native.workflow.v1",
    )
    external_agent = runtime.agent_registry.get("jerryagent_research_agent")
    native_agent = runtime.agent_registry.get("hello_agent")
    assert external_agent is not None
    assert native_agent is not None
    external_agent["version"] = "0.2.0"
    native_agent["version"] = "0.2.0"

    external_result = runtime.execute(external_task_id)
    native_result = runtime.execute(native_task_id)

    assert external_result["status"] == "failed"
    assert "版本漂移" in external_result["task"]["error_message"]
    assert external_result["task"]["data_classification"] == "sensitive"
    assert native_result["status"] == "failed"
    assert native_result["task"]["data_classification"] == "internal"


def test_external_disabled_agent_early_failure_is_statically_sensitive(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(tmp_path, AgentExecutionRouter())
    external_task_id = _create(db_path, task_id="external-disabled")
    native_task_id = _create(
        db_path,
        task_id="native-disabled",
        agent_id="hello_agent",
        execution_adapter="native_python",
        execution_contract_version="native.workflow.v1",
    )
    external_agent = runtime.agent_registry.get("jerryagent_research_agent")
    native_agent = runtime.agent_registry.get("hello_agent")
    assert external_agent is not None
    assert native_agent is not None
    external_agent["status"] = "disabled"
    native_agent["status"] = "disabled"

    external_result = runtime.execute(external_task_id)
    native_result = runtime.execute(native_task_id)

    assert external_result["status"] == "failed"
    assert "已下线" in external_result["task"]["error_message"]
    assert external_result["task"]["data_classification"] == "sensitive"
    assert native_result["status"] == "failed"
    assert native_result["task"]["data_classification"] == "internal"


def test_unregistered_external_agent_preserves_the_static_sensitive_axis(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(tmp_path, AgentExecutionRouter())
    external_task_id = _create(db_path, task_id="external-unregistered")
    native_task_id = _create(
        db_path,
        task_id="native-unregistered",
        agent_id="hello_agent",
        execution_adapter="native_python",
        execution_contract_version="native.workflow.v1",
    )
    runtime.agent_registry.deregister("jerryagent_research_agent", "test removal")
    runtime.agent_registry.deregister("hello_agent", "test removal")

    external_result = runtime.execute(external_task_id)
    native_result = runtime.execute(native_task_id)

    assert external_result["status"] == "failed"
    assert "未注册" in external_result["task"]["error_message"]
    assert external_result["task"]["data_classification"] == "sensitive"
    assert native_result["status"] == "failed"
    assert native_result["task"]["data_classification"] is None


def test_external_agent_layer_is_sensitive_and_stops_at_human_review(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(
        tmp_path,
        AgentExecutionRouter((NativeWorkflowAdapter(), _FakeJerryAdapter())),
    )
    task_id = _create(db_path)

    result = runtime.execute(task_id)

    assert result["status"] == "waiting_review"
    assert result["task"]["data_classification"] == "sensitive"
    assert result["task"]["execution_adapter"] == "jerryagent_sidecar"
    conn = get_conn(db_path)
    try:
        events = repos.list_events(conn, task_id)
        files = [repos.get_file(conn, file_id) for file_id in result["task"]["output_file_ids"]]
    finally:
        conn.close()
    receipt = next(
        event
        for event in events
        if event["payload"].get("workflow_event_type") == "agent_layer_receipt"
    )
    assert receipt["payload"]["model_calls_attested_by_flai"] is False
    assert receipt["payload"]["runtime_identity"]["sessionId"] == "session-1"
    assert [file["classification"] for file in files] == ["sensitive"]


def test_runtime_never_executes_sidecar_sentinel_when_adapter_is_unavailable(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(tmp_path, AgentExecutionRouter())
    task_id = _create(db_path)

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "no fallback was attempted" in result["task"]["error_message"]
    assert "must execute through" not in result["task"]["error_message"]
    assert not (tmp_path / "task_runs" / task_id / "output" / "jerryagent_result.md").exists()


def test_agent_runtime_close_releases_the_execution_router(tmp_path: Path) -> None:
    adapter = _FakeJerryAdapter()
    runtime, _db_path = _runtime(
        tmp_path,
        AgentExecutionRouter((NativeWorkflowAdapter(), adapter)),
    )

    runtime.close()

    assert adapter.closed is True


def test_external_result_must_pass_the_locked_agent_output_schema(
    tmp_path: Path,
) -> None:
    runtime, db_path = _runtime(
        tmp_path,
        AgentExecutionRouter((NativeWorkflowAdapter(), _InvalidJerryAdapter())),
    )
    task_id = _create(db_path)

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    assert "output schema" in result["task"]["error_message"]
    assert result["task"]["output_file_ids"] == []


def test_jerry_eval_checks_every_declared_governance_expectation(
    tmp_path: Path,
) -> None:
    case_path = (
        Path(__file__).resolve().parents[2]
        / "agents"
        / "jerryagent_research_agent"
        / "eval_cases"
        / "case_001_contract.json"
    )
    case = json.loads(case_path.read_text(encoding="utf-8"))
    checks = case["checks"]
    assert {
        "kind": "task_field",
        "path": "data_classification",
        "op": "eq",
        "value": "sensitive",
    } in checks
    assert {
        "kind": "artifact_contains",
        "file": "jerryagent_result.md",
        "value": "Candidate only: `true`",
    } in checks

    ok, _detail = eval_runner._eval_one_check(
        checks[1],
        final_task={"data_classification": "sensitive"},
        output_files=[],
        task_runs_dir=tmp_path,
    )
    assert ok is True
