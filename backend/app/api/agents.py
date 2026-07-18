"""Agent 只读查询接口（GET /api/agents、GET /api/agents/{id}）。

投影字段：id/name/version/status/maturity/category/summary/limitations/mode
（门户卡片文案所需的最小字段集，不透出 owner/permissions 等治理细节）。mode
（job/interactive）是前端路由信号：interactive 型 Agent 走对话入口而非创建任务
（M6/ADR-0012——否则用户在创建任务页选中导引只会撞 409 死路）。
"""

from __future__ import annotations

import json
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
        "mode": (agent.get("workflow", {}) or {}).get("mode"),
        # 输入模式（params / file_upload / none）：前端「原地召集」就绪门需要它区分
        # 纯参数型与文件型——file_upload 的 params schema 可为空 required，若只看
        # required 会空洞通过（异源 Codex R1-P1）。additive 字段，创建页不依赖。
        "input_mode": (agent.get("input", {}) or {}).get("type"),
        # 批七 ADR-0030：专长身份轴与密级上限投影（additive，通用包两者皆缺省）。
        # clearance 缺省语义=internal fail-closed——投影层如实回 None，缺省最严
        # 的解释由消费方（密级 gate/前端 pill）按 ADR-0030 统一执行，不在此拍死。
        "expertise": agent.get("expertise"),
        "clearance": (agent.get("clearance", {}) or {}).get("max_data_classification"),
        # 批七 §1.6：签发面「未提供依据请谨慎签发」警示行需要此旗标（additive；
        # 判定 is True——非布尔坏值不当 required）。
        "evidence_policy_required": (agent.get("evidence_policy", {}) or {}).get("required") is True,
    }


@router.get("/agents")
def list_agents(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.agent_registry
    return [_project(a) for a in registry.list()]


def _read_input_schema(registry: Any, agent_id: str) -> dict[str, Any] | None:
    """从 Agent 包目录读 input_schema.json，供前端按契约动态渲染创建表单。

    只在详情端点读盘（列表端点不读，省带宽）；缺文件/解析失败一律返回 None，
    前端据此降级回 JSON 手填模式，绝不因 schema 缺失阻断建任务。
    """
    package_dir = getattr(registry, "package_dir", lambda _id: None)(agent_id)
    if package_dir is None:
        return None
    schema_path = package_dir / "input_schema.json"
    try:
        parsed = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    registry = request.app.state.agent_registry
    agent = _get_agent_or_none(registry, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{agent_id}")
    projected = _project(agent)
    projected["input_schema"] = _read_input_schema(registry, agent_id)
    return projected
