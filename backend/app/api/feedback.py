"""Feedback 接口（任务书 §7.8）：任务反馈提交与查询。

反馈是数据资产闭环的入口（宪法铁律八：线上失败沉淀为评测用例或经验记录），
提交成功必发 `feedback_received` 事件——无事件=没发生。

- rating/category 枚举在本层用 Literal 锁死（repos 层不重复校验，分层与
  tasks/statemachine 一致）。
- created_by 必填非空且 strip 后非空白（与 review reviewer 同手法）——
  反馈也是具名的，匿名反馈无法回访核实。
- agent_id/agent_version 一律服务端从 task 记录自填，不信客户端传入。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from ..storage import repos

router = APIRouter(prefix="/api", tags=["feedback"])

_MESSAGE_SUMMARY_LIMIT = 200


class CreateFeedbackRequest(BaseModel):
    task_id: str
    rating: Literal["good", "bad"]
    category: Literal[
        "result_wrong", "result_incomplete", "tool_error", "usability", "suggestion", "other"
    ]
    message: str | None = None
    created_by: str = Field(min_length=1)

    @field_validator("created_by")
    @classmethod
    def created_by_must_not_be_blank(cls, v: str) -> str:
        """全空白 created_by = 事实匿名反馈：strip 后为空一律 422，
        入库/入事件统一存 strip 后的名字（与 tasks.py reviewer 校验同手法）。"""
        stripped = v.strip()
        if not stripped:
            raise ValueError("created_by 不得为空白字符——反馈必须具名，匿名反馈无法回访核实")
        return stripped


@router.post("/feedback")
def create_feedback(body: CreateFeedbackRequest, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, body.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{body.task_id}")

        record = repos.create_feedback(
            conn,
            task_id=body.task_id,
            # 服务端自填：来源=task 记录（任务创建时锁定的 agent 口径），不信客户端。
            agent_id=task.get("agent_id"),
            agent_version=task.get("agent_version"),
            rating=body.rating,
            category=body.category,
            message=body.message,
            created_by=body.created_by,
        )
        message_summary = (
            body.message[:_MESSAGE_SUMMARY_LIMIT] if body.message is not None else None
        )
        repos.append_event(
            conn,
            task_id=body.task_id,
            agent_id=task.get("agent_id"),
            event_type="feedback_received",
            level="info",
            message=f"收到任务反馈：rating={body.rating}, category={body.category}",
            payload={
                "rating": body.rating,
                "category": body.category,
                "created_by": body.created_by,
                "message_summary": message_summary,
            },
        )
        return record
    finally:
        conn.close()


@router.get("/tasks/{task_id}/feedback")
def list_task_feedback(task_id: str, request: Request) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        return repos.list_feedback(conn, task_id)
    finally:
        conn.close()
