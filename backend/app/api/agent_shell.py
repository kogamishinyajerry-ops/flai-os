"""Authenticated read-only Agent Shell semantic catalog endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..ontology import AgentShellProjectionError

router = APIRouter(prefix="/api", tags=["agent-shell"])


@router.get("/agent-shell")
def get_agent_shell(request: Request) -> dict[str, Any]:
    try:
        return request.app.state.agent_shell_catalog.snapshot()
    except AgentShellProjectionError as exc:
        raise HTTPException(status_code=503, detail="Agent 本体投影不可用") from exc
