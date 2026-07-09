"""Task Center 接口：创建/查询/取消任务 + 事件时间轴查询。

宪法铁律「无事件=没发生」在本层落实：任何状态变化都配一条 task_event。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from ..core.errors import IllegalTransitionError
from ..storage import repos

router = APIRouter(prefix="/api", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    agent_id: str
    name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    input_file_ids: list[str] = Field(default_factory=list)
    created_by: str = "anonymous"


class ReviewTaskRequest(BaseModel):
    """人工放行请求体（P1-B）。reviewer 必填非空——人是唯一的工程签发者
    （宪法铁律六），匿名放行等于没有签发者，pydantic 层直接 422 拒收。"""

    action: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)
    comment: str | None = None

    @field_validator("reviewer")
    @classmethod
    def reviewer_must_not_be_blank(cls, v: str) -> str:
        """全空白 reviewer = 事实匿名签发（R1 复审 P3）：strip 后为空一律 422。
        入库/入事件统一存 strip 后的名字。"""
        stripped = v.strip()
        if not stripped:
            raise ValueError("reviewer 不得为空白字符——人工放行必须有具名签发者")
        return stripped


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
    if (agent.get("workflow", {}) or {}).get("mode") == "interactive":
        # ADR-0012 决策 6：interactive 型 Agent（导引）不作为一次性任务运行，
        # 两条运行时语义正交——请走 /api/conversations 对话，绝不混用。
        raise HTTPException(
            status_code=409,
            detail=f"agent {body.agent_id} 是导引类（interactive）Agent，请走 /api/conversations 对话，不作为一次性任务运行",
        )

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
    limit: int = Query(default=100, ge=1, le=500, description="每页条数（1-500）"),
    offset: int = Query(default=0, ge=0, description="跳过条数（最近任务流分页语义，无总数计数）"),
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        return repos.list_tasks(conn, agent_id=agent_id, status=status, limit=limit, offset=offset)
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


@router.post("/tasks/{task_id}/review")
def review_task(task_id: str, body: ReviewTaskRequest, request: Request) -> dict[str, Any]:
    """人工放行/拒绝 waiting_review 任务（P1-B：waiting_review 的唯一合法出口）。

    docs/05 §2：waiting_review 只能由人工放行动作转出——approve→completed
    （review_approved 事件），reject→failed（review_rejected 事件）；本端点即
    该「人工放行动作」的 API 落点。任务不处于 waiting_review 一律 409 如实拒绝。
    """
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        if task["status"] != "waiting_review":
            raise HTTPException(
                status_code=409,
                detail=f"任务处于 {task['status']}，不在 waiting_review，无法人工放行/拒绝",
            )

        payload = {"reviewer": body.reviewer, "comment": body.comment}
        try:
            if body.action == "approve":
                task = repos.set_task_status(conn, task_id, "completed")
            else:
                # action == "reject"（Literal 已锁定只有两值）
                reject_reason = f"人工拒绝（reviewer={body.reviewer}）" + (
                    f"：{body.comment}" if body.comment else ""
                )
                task = repos.set_task_status(conn, task_id, "failed", error_message=reject_reason)
        except IllegalTransitionError as exc:
            # R1 复审 P2：两个 review 请求并发命中同一 waiting_review 任务时，
            # 后到者可通过预检但在状态机层被拒——这是正常并发竞态，
            # 与预检失败同口径返回 409，绝不让 500 逃逸。
            raise HTTPException(
                status_code=409,
                detail=f"任务已被并发的人工审核动作转出 waiting_review，本次不生效：{exc}",
            ) from exc

        # 回填该任务全部样本的工程师确认标签（approve→1 / reject→0）。
        # collect_samples 型 Agent 执行时留 NULL（结果未定），此处按人工审核结论
        # 定标，确保下游只把工程师认可的草案当作可复用数据。
        sample_rows = repos.set_sample_review_outcome(
            conn, task_id, accepted=(body.action == "approve")
        )

        if body.action == "approve":
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=task.get("agent_id"),
                event_type="review_approved",
                level="info",
                message=f"人工批准放行（reviewer={body.reviewer}），任务转 completed"
                + (f"；{sample_rows} 条样本标记为工程师认可" if sample_rows else ""),
                payload=payload,
            )
            return task

        repos.append_event(
            conn,
            task_id=task_id,
            agent_id=task.get("agent_id"),
            event_type="review_rejected",
            level="warning",
            message=f"人工拒绝（reviewer={body.reviewer}），任务转 failed"
            + (f"；{sample_rows} 条样本标记为未认可" if sample_rows else ""),
            payload=payload,
        )
        return task
    finally:
        conn.close()


@router.get("/tasks/{task_id}/events")
def list_events(
    task_id: str,
    request: Request,
    limit: int = Query(default=2000, ge=1, le=5000, description="每页事件条数（1-5000）"),
    offset: int = Query(default=0, ge=0, description="跳过条数（id 升序写入序分页）"),
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return repos.list_events(conn, task_id, limit=limit, offset=offset)
    finally:
        conn.close()
