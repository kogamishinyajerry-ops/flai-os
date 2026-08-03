"""Feedback 接口（任务书 §7.8）：任务反馈提交与查询。

反馈是数据资产闭环的入口（宪法铁律八：线上失败沉淀为评测用例或经验记录），
提交成功必发 `feedback_received` 事件——无事件=没发生。

- rating/category 枚举在本层用 Literal 锁死（repos 层不重复校验，分层与
  tasks/statemachine 一致）。
- created_by 已从请求体删除（ADR-0019 D5）：反馈人=登录会话身份，服务端
  派生——反馈仍是具名的，且名字从此可信。
- agent_id/agent_version 一律服务端从 task 记录自填，不信客户端传入。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from . import object_authorization as oauth
from ..storage import repos

router = APIRouter(prefix="/api", tags=["feedback"])

_MESSAGE_SUMMARY_LIMIT = 200


class CreateFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 旧客户端仍发 created_by → 响亮 422

    task_id: str
    rating: Literal["good", "bad"]
    category: Literal[
        "result_wrong", "result_incomplete", "tool_error", "usability", "suggestion", "other"
    ]
    message: str | None = None


@router.post("/feedback")
def create_feedback(body: CreateFeedbackRequest, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        task = oauth.require_owned_task(
            conn, body.task_id, oauth.authenticated_username(request)
        )

        created_by = request.state.user["display_name"]  # ADR-0019 D5：认证身份
        record = repos.create_feedback(
            conn,
            task_id=body.task_id,
            # 服务端自填：来源=task 记录（任务创建时锁定的 agent 口径），不信客户端。
            agent_id=task.get("agent_id"),
            agent_version=task.get("agent_version"),
            rating=body.rating,
            category=body.category,
            message=body.message,
            created_by=created_by,
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
                "created_by": created_by,
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
        oauth.require_readable_task(
            conn, task_id, oauth.authenticated_username(request)
        )
        return repos.list_feedback(conn, task_id)
    finally:
        conn.close()
