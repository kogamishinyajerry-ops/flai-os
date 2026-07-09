"""Task Center 接口：创建/查询/取消任务 + 事件时间轴查询。

宪法铁律「无事件=没发生」在本层落实：任何状态变化都配一条 task_event。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..storage import repos

router = APIRouter(prefix="/api", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    agent_id: str
    name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    input_file_ids: list[str] = Field(default_factory=list)
    created_by: str = "anonymous"


def _get_agent_or_none(registry: Any, agent_id: str) -> dict[str, Any] | None:
    try:
        agent = registry.get(agent_id)
    except KeyError:
        return None
    return agent


@router.post("/tasks")
def create_task(body: CreateTaskRequest, request: Request) -> dict[str, Any]:
    agent_registry = request.app.state.agent_registry
    agent = _get_agent_or_none(agent_registry, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{body.agent_id}")
    if agent.get("status") == "disabled":
        raise HTTPException(status_code=409, detail=f"agent 已下线，禁止调用：{body.agent_id}")

    conn = request.app.state.conn_factory()
    try:
        task_id = f"task_{uuid.uuid4().hex}"
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id=body.agent_id,
            agent_version=agent.get("version"),
            name=body.name,
            created_by=body.created_by,
            inputs=body.inputs,
            input_file_ids=body.input_file_ids,
            metadata={},
        )
        # P2-4：created->queued 由本创建动作原子完成（docs/05 §6「两处文档化原子例外」
        # 之一）——先把状态迁到 queued，再发 task_created 事件，事件 payload 显式携带
        # status_from/status_to 双态见证，而不是只见证 created 这一态就消失。
        task = repos.set_task_status(conn, task_id, "queued")
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id=body.agent_id,
            event_type="task_created",
            level="info",
            message=f"任务已创建：agent={body.agent_id}",
            payload={"created_by": body.created_by, "status_from": "created", "status_to": "queued"},
        )
        return task
    finally:
        conn.close()


@router.get("/tasks")
def list_tasks(
    request: Request,
    status: str | None = None,
    agent_id: str | None = None,
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        return repos.list_tasks(conn, agent_id=agent_id, status=status)
    finally:
        conn.close()


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return task
    finally:
        conn.close()


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        current = task["status"]

        if current in ("created", "queued"):
            task = repos.set_task_status(conn, task_id, "cancelled")
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=task.get("agent_id"),
                event_type="task_cancelled",
                level="info",
                message="任务被用户取消",
                payload={"previous_status": current},
            )
            return task

        if current == "running":
            raise HTTPException(
                status_code=409,
                detail="V0.1 不支持取消运行中任务（ADR-0008 取消语义裁决）",
            )

        # waiting_review：docs/05 强制规则——只能人工放行（review_approved/
        # review_rejected）转出，禁止任何自动化路径（含 cancel）转出；
        # 其余终态（completed/failed/cancelled）本身禁止再迁移。
        raise HTTPException(
            status_code=409,
            detail=f"任务处于 {current}，不可取消",
        )
    finally:
        conn.close()


@router.get("/tasks/{task_id}/events")
def list_events(task_id: str, request: Request) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return repos.list_events(conn, task_id)
    finally:
        conn.close()
