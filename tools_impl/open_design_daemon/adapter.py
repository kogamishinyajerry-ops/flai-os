"""ToolRegistry entrypoint for the narrow Open Design loopback trial."""

from __future__ import annotations

from typing import Any

from tools_impl.open_design_fixture.design_reference import build_design_reference_package

from .client import OpenDesignHttpClient
from .service import DaemonGenerationError, failed_tool_output, run_generation_sequence
from .settings import load_settings


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    failure_stage = "runtime_context"
    try:
        if not isinstance(context, dict) or not isinstance(context.get("task_id"), str):
            raise RuntimeError("verified runtime task identity is required")
        failure_stage = "payload_validation"
        if not isinstance(payload, dict) or "task_id" in payload:
            raise RuntimeError("tool payload must not carry task_id; runtime owns that identity")
        request = {**payload, "task_id": context["task_id"]}
        failure_stage = "adapter_settings"
        settings = load_settings()
        if settings.enabled is not True:
            failure_stage = "adapter_disabled"
            raise RuntimeError("Open Design daemon adapter is disabled by default")
        failure_stage = "design_reference"
        design_package = build_design_reference_package()
        failure_stage = "daemon_connection"
        with OpenDesignHttpClient(settings) as client:
            failure_stage = "daemon_sequence"
            return run_generation_sequence(client, request, design_package)
    except Exception as exc:  # noqa: BLE001 - tool boundary returns a schema-valid honest failure
        sequence_error = exc if isinstance(exc, DaemonGenerationError) else None
        return failed_tool_output(
            f"{exc.__class__.__name__}: {exc}",
            asset_slot=payload.get("asset_slot") if isinstance(payload, dict) else None,
            failure_stage=(
                sequence_error.failure_stage
                if sequence_error is not None and sequence_error.failure_stage is not None
                else failure_stage
            ),
            project_id=sequence_error.project_id if sequence_error is not None else None,
            run_id=sequence_error.run_id if sequence_error is not None else None,
            unreconciled_upstream_side_effects_may_exist=(
                sequence_error.unreconciled_upstream_side_effects_may_exist
                if sequence_error is not None
                else False
            ),
        )
