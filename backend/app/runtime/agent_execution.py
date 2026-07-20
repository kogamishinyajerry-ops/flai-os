"""Closed Agent-layer execution seam.

FLAi-OS owns task state, classification, artifacts, evidence and human review.
Adapters only execute an already-bound request and return a candidate result.
The binding is frozen on the task row and must still match the registered
Agent manifest at execution time; an unavailable adapter never falls back.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol


NATIVE_ADAPTER_ID = "native_python"
NATIVE_CONTRACT_VERSION = "native.workflow.v1"
JERRY_ADAPTER_ID = "jerryagent_sidecar"
JERRY_CONTRACT_VERSION = "flai.agent-layer.v1"


class AgentExecutionError(RuntimeError):
    """The frozen Agent-layer binding could not be executed exactly."""


@dataclass(frozen=True)
class AgentExecutionRequest:
    """A capability-limited execution request assembled by ``AgentRuntime``."""

    task: Mapping[str, Any]
    agent: Mapping[str, Any]
    package_dir: Path
    output_dir: Path
    context: Mapping[str, Any]


@dataclass(frozen=True)
class ExecutionReceipt:
    """Non-governance provenance returned by an Agent-layer adapter."""

    adapter: str
    contract_version: str
    execution_id: str
    request_sha256: str
    runtime_identity: Mapping[str, Any]
    final_revision: int | None
    model_calls_attested_by_flai: bool


@dataclass(frozen=True)
class AgentExecutionOutcome:
    result: Mapping[str, Any]
    receipt: ExecutionReceipt


class AgentExecutionAdapter(Protocol):
    adapter: str
    contract_version: str

    def execute(self, request: AgentExecutionRequest) -> AgentExecutionOutcome: ...


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentExecutionError("Agent-layer request is not canonical JSON") from exc


def request_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _validate_external_candidate_result(
    request: AgentExecutionRequest,
    outcome: AgentExecutionOutcome,
) -> None:
    """Validate an external adapter's candidate against the locked package schema."""
    result = outcome.result
    if not isinstance(result, Mapping) or set(result) != {"status", "outputs"}:
        raise AgentExecutionError("External Agent-layer result envelope is not exact")
    outputs = result.get("outputs")
    if (
        result.get("status") != "success"
        or not isinstance(outputs, list)
        or len(outputs) != 1
        or not isinstance(outputs[0], dict)
    ):
        raise AgentExecutionError(
            "External Agent-layer must return exactly one successful candidate"
        )
    schema_ref = (request.agent.get("output") or {}).get("schema")
    if not isinstance(schema_ref, str) or not schema_ref:
        raise AgentExecutionError("External Agent-layer output schema is missing")
    try:
        from jsonschema.exceptions import SchemaError, ValidationError
        from jsonschema.validators import validator_for

        from .registry import package_reference_path

        schema_path = package_reference_path(request.package_dir, schema_ref)
        before = schema_path.lstat()
        if stat.S_ISREG(before.st_mode) is not True or schema_path.is_symlink():
            raise ValueError("output schema must be a regular non-symlink file")
        if before.st_size > 512 * 1024:
            raise ValueError("output schema exceeds 512 KiB")
        schema = json.loads(schema_path.read_bytes().decode("utf-8"))
        validator = validator_for(schema)
        validator.check_schema(schema)
        validator(schema).validate(outputs[0])
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError, ValidationError, ValueError, TypeError) as exc:
        raise AgentExecutionError(
            f"External Agent-layer output schema validation failed: {exc.__class__.__name__}"
        ) from exc


def load_workflow_module(agent_id: str, workflow_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(
        f"flai_agent_{agent_id}_workflow", workflow_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 workflow.py：{workflow_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def effective_agent_binding(agent: Mapping[str, Any]) -> tuple[str, str]:
    execution = agent.get("execution")
    if execution is None:
        return NATIVE_ADAPTER_ID, NATIVE_CONTRACT_VERSION
    if not isinstance(execution, Mapping):
        raise AgentExecutionError("Agent execution binding is not an object")
    adapter = execution.get("adapter")
    contract_version = execution.get("contract_version")
    if not isinstance(adapter, str) or not isinstance(contract_version, str):
        raise AgentExecutionError("Agent execution binding is incomplete")
    return adapter, contract_version


def effective_task_binding(task: Mapping[str, Any]) -> tuple[str, str]:
    # Compatibility for pre-migration in-memory fixtures. Persisted rows are
    # normalized by the repository migration and creation path.
    adapter = task.get("execution_adapter", NATIVE_ADAPTER_ID)
    contract_version = task.get(
        "execution_contract_version", NATIVE_CONTRACT_VERSION
    )
    if not isinstance(adapter, str) or not isinstance(contract_version, str):
        raise AgentExecutionError("Task execution binding is incomplete")
    return adapter, contract_version


class NativeWorkflowAdapter:
    adapter = NATIVE_ADAPTER_ID
    contract_version = NATIVE_CONTRACT_VERSION

    def __init__(
        self,
        workflow_loader: Callable[[str, Path], Any] = load_workflow_module,
    ) -> None:
        self._workflow_loader = workflow_loader

    def execute(self, request: AgentExecutionRequest) -> AgentExecutionOutcome:
        agent_id = str(request.task.get("agent_id", ""))
        task_id = str(request.task.get("id", ""))
        digest = request_sha256(
            {
                "contractVersion": self.contract_version,
                "taskId": task_id,
                "agentId": agent_id,
                "agentVersion": request.task.get("agent_version"),
                "inputs": request.task.get("inputs"),
            }
        )
        workflow = self._workflow_loader(agent_id, request.package_dir / "workflow.py")
        result = workflow.run(dict(request.context))
        return AgentExecutionOutcome(
            result=result,
            receipt=ExecutionReceipt(
                adapter=self.adapter,
                contract_version=self.contract_version,
                execution_id=task_id,
                request_sha256=digest,
                runtime_identity=MappingProxyType(
                    {
                        "product": "FLAi-OS",
                        "runtimeKind": "in-process",
                        "schema": self.contract_version,
                    }
                ),
                final_revision=None,
                model_calls_attested_by_flai=True,
            ),
        )


class AgentExecutionRouter:
    """Resolve one exact frozen binding; never perform adapter fallback."""

    def __init__(self, adapters: tuple[AgentExecutionAdapter, ...] | None = None) -> None:
        selected = adapters if adapters is not None else (NativeWorkflowAdapter(),)
        by_binding: dict[tuple[str, str], AgentExecutionAdapter] = {}
        for adapter in selected:
            key = (adapter.adapter, adapter.contract_version)
            if key in by_binding:
                raise ValueError(f"duplicate Agent-layer adapter binding: {key!r}")
            by_binding[key] = adapter
        native_key = (NATIVE_ADAPTER_ID, NATIVE_CONTRACT_VERSION)
        if native_key not in by_binding:
            raise ValueError("native Agent-layer adapter is mandatory")
        self._adapters = MappingProxyType(by_binding)

    @property
    def bindings(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._adapters)

    def close(self) -> None:
        """Release optional adapter transports without coupling callers to types."""

        for adapter in self._adapters.values():
            close = getattr(adapter, "close", None)
            if callable(close):
                close()

    def execute(self, request: AgentExecutionRequest) -> AgentExecutionOutcome:
        task_binding = effective_task_binding(request.task)
        manifest_binding = effective_agent_binding(request.agent)
        if task_binding != manifest_binding:
            raise AgentExecutionError(
                "Agent execution binding drift: "
                f"task locked {task_binding!r}, registry declares {manifest_binding!r}"
            )
        adapter = self._adapters.get(task_binding)
        if adapter is None:
            raise AgentExecutionError(
                "Frozen Agent-layer adapter is unavailable: "
                f"{task_binding[0]}@{task_binding[1]}; no fallback was attempted"
            )
        outcome = adapter.execute(request)
        if (
            outcome.receipt.adapter != task_binding[0]
            or outcome.receipt.contract_version != task_binding[1]
        ):
            raise AgentExecutionError("Agent-layer adapter returned mismatched provenance")
        if task_binding != (NATIVE_ADAPTER_ID, NATIVE_CONTRACT_VERSION):
            _validate_external_candidate_result(request, outcome)
        return outcome
