"""ToolRegistry adapter for the local Open Design fixture (mock=true)."""

from __future__ import annotations

from typing import Any

from .client import FixtureOpenDesignClient, failed_tool_output


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    try:
        return FixtureOpenDesignClient().generate(payload)
    except Exception as exc:  # noqa: BLE001 - adapter boundary must return an honest failed contract
        return failed_tool_output(f"{exc.__class__.__name__}: {exc}")
