"""Agent 只读查询接口（GET /api/agents、GET /api/agents/{id}）。

投影字段：id/name/version/status/maturity/category/summary/limitations
（门户卡片文案所需的最小字段集，不透出 owner/permissions 等治理细节）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["agents"])


def _get_agent_or_none(registry: Any, agent_id: str) -> dict[str, Any] | None:
    """兼容 AgentRegistry.get() 的两种可能约定：抛 KeyError 或返回 None。"""
    try:
        agent = registry.get(agent_id)
    except KeyError:
        return None
    return agent


def _project(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "version": agent.get("version"),
        "status": agent.get("status"),
        "maturity": agent.get("maturity"),
        "category": agent.get("category"),
        "summary": agent.get("summary"),
        "limitations": agent.get("limitations", []),
    }


@router.get("/agents")
def list_agents(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.agent_registry
    return [_project(a) for a in registry.list()]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    registry = request.app.state.agent_registry
    agent = _get_agent_or_none(registry, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{agent_id}")
    return _project(agent)
