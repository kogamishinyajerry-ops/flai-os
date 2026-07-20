from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.runtime.agent_execution import (
    AgentExecutionError,
    AgentExecutionRequest,
    AgentExecutionRouter,
    NativeWorkflowAdapter,
)


def _request(tmp_path: Path, *, task_binding: tuple[str, str] | None = None,
             agent_binding: tuple[str, str] | None = None) -> AgentExecutionRequest:
    package_dir = tmp_path / "agent"
    package_dir.mkdir()
    (package_dir / "workflow.py").write_text(
        "def run(context):\n"
        "    return {'status': 'success', 'outputs': "
        "[{'echo': context['inputs']['objective']}]}\n",
        encoding="utf-8",
    )
    task = {
        "id": "task-1",
        "agent_id": "research_agent",
        "agent_version": "0.1.0",
        "inputs": {"objective": "inspect"},
    }
    if task_binding is not None:
        task["execution_adapter"], task["execution_contract_version"] = task_binding
    agent = {"id": "research_agent", "version": "0.1.0"}
    if agent_binding is not None:
        agent["execution"] = {
            "adapter": agent_binding[0],
            "contract_version": agent_binding[1],
        }
    return AgentExecutionRequest(
        task=task,
        agent=agent,
        package_dir=package_dir,
        output_dir=tmp_path / "output",
        context={"inputs": task["inputs"]},
    )


def test_native_adapter_preserves_the_existing_workflow_contract(tmp_path: Path) -> None:
    outcome = AgentExecutionRouter().execute(_request(tmp_path))

    assert outcome.result == {
        "status": "success",
        "outputs": [{"echo": "inspect"}],
    }
    assert outcome.receipt.adapter == "native_python"
    assert outcome.receipt.contract_version == "native.workflow.v1"
    assert outcome.receipt.model_calls_attested_by_flai is True
    assert len(outcome.receipt.request_sha256) == 64


def test_router_rejects_manifest_drift_before_execution(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        task_binding=("native_python", "native.workflow.v1"),
        agent_binding=("jerryagent_sidecar", "flai.agent-layer.v1"),
    )

    with pytest.raises(AgentExecutionError, match="binding drift"):
        AgentExecutionRouter().execute(request)


def test_unavailable_jerry_binding_fails_without_native_fallback(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        task_binding=("jerryagent_sidecar", "flai.agent-layer.v1"),
        agent_binding=("jerryagent_sidecar", "flai.agent-layer.v1"),
    )

    with pytest.raises(AgentExecutionError, match="no fallback was attempted"):
        AgentExecutionRouter((NativeWorkflowAdapter(),)).execute(request)
