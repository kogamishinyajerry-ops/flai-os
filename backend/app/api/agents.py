"""Agent 只读查询接口（GET /api/agents、GET /api/agents/{id}）。

列表投影提供门户只读卡片所需的最小字段，不透出 owner/permissions 等治理细节；
详情额外提供输入 schema 与附件后缀契约，供自动路由在展示开工按钮前做确定性核对。
mode（job/interactive）是运行方式事实，不是让工程师手工选择执行路径的控件信号。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["agents"])


def _get_package_snapshot_or_none(registry: Any, agent_id: str) -> Any | None:
    """兼容 package_snapshot() 的两种可能约定：抛 KeyError 或返回 None。"""
    try:
        snapshot = registry.package_snapshot(agent_id)
    except KeyError:
        return None
    return snapshot


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


def _read_input_schema(package_snapshot: Any) -> dict[str, Any] | None:
    """从已发布包快照读 manifest 指定的输入 schema，供自动路由确定性核对。

    只在详情端点解析（列表端点不读，省带宽）；缺文件/解析失败一律返回 None，
    消费端据此 fail-closed 并继续对话追问。禁止读取可变 authoring 目录，避免
    manifest/version 与 schema 跨发布代际拼接。
    """
    try:
        manifest = package_snapshot.manifest
        input_decl = manifest.get("input") if isinstance(manifest, dict) else None
        schema_name = input_decl.get("schema") if isinstance(input_decl, dict) else None
        if not isinstance(schema_name, str) or not schema_name:
            return None
        schema_bytes = dict(package_snapshot.files).get(schema_name)
    except (AttributeError, TypeError, ValueError, RecursionError):
        return None
    if schema_bytes is None:
        return None
    try:
        parsed = json.loads(schema_bytes.decode("utf-8"))
    except (AttributeError, UnicodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _input_allowed_extensions(agent: dict[str, Any]) -> list[str] | None:
    """投影附件契约；畸形声明返回 None，供消费端 fail-closed。"""
    input_decl = agent.get("input", {}) or {}
    raw = input_decl.get("allowed_extensions")
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 32:
        return None
    cleaned: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        extension = item.strip().lower()
        if not extension.startswith(".") or not 2 <= len(extension) <= 16:
            return None
        if extension not in cleaned:
            cleaned.append(extension)
    return cleaned


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    registry = request.app.state.agent_registry
    package_snapshot = _get_package_snapshot_or_none(registry, agent_id)
    if package_snapshot is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{agent_id}")
    agent = package_snapshot.manifest
    projected = _project(agent)
    projected["input_schema"] = _read_input_schema(package_snapshot)
    projected["package_snapshot_digest"] = package_snapshot.digest
    # 详情端点才带附件后缀契约：自动路由据此判断文件型 Agent 是否真正可开工；
    # 列表保持轻量，畸形契约投影为 None 而非猜测放行。
    projected["input_allowed_extensions"] = _input_allowed_extensions(agent)
    return projected
