"""导引会话接口（M6，ADR-0012）：interactive 型 Agent 的多轮对话入口。

与一次性 tasks 端点正交——会话由 ConversationService 驱动（app.state.conversation_service）。
红线：本层只负责开启会话、逐轮转发消息、返回 assistant 回复与推荐草案；**绝不**在
本层创建/签发下游任务。推荐草案（recommendation）交前端带到创建任务页，由人确认提交。

错误映射（fail-closed，绝不把上游失败降级为绿）：
- 会话/agent 不存在 → 404；会话已结束 → 409；对非 interactive Agent 发起会话 → 409；
- 模型上游失败/workflow 诚实抛错 → 502（如实透出「本轮对话失败，可重试」，不伪造回复）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from ..core.errors import (
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    ModelUpstreamError,
    NotInteractiveAgentError,
)
from ..storage import repos

router = APIRouter(prefix="/api", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    agent_id: str
    created_by: str = Field(min_length=1, max_length=100)

    @field_validator("created_by")
    @classmethod
    def created_by_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("created_by 不得为空白字符——会话必须具名")
        return stripped


class PostMessageRequest(BaseModel):
    # max_length：审计 P2（DoS 面）——content 此前无上限，超大文本会被落库并
    # 全量转发模型。16000 字符对需求描述/追问回答绰绰有余；更大材料走附件通道
    # （V0.1 会话不接附件，附件在创建任务页上传，见 guide_agent limitations）。
    content: str = Field(min_length=1, max_length=16000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content 不得为空白——请输入你的需求或对追问的回答")
        return stripped


@router.post("/conversations")
def create_conversation(body: CreateConversationRequest, request: Request) -> dict[str, Any]:
    service = request.app.state.conversation_service
    try:
        return service.create(agent_id=body.agent_id, created_by=body.created_by)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotInteractiveAgentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/conversations")
def list_conversations(
    request: Request,
    created_by: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        return repos.list_conversations(conn, created_by=created_by, limit=limit, offset=offset)
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    service = request.app.state.conversation_service
    try:
        return service.get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/conversations/{conversation_id}/messages")
def post_message(
    conversation_id: str, body: PostMessageRequest, request: Request
) -> dict[str, Any]:
    service = request.app.state.conversation_service
    try:
        return service.post_message(conversation_id=conversation_id, content=body.content)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationClosedError, ConversationConflictError) as exc:
        # 已结束 / 被并发轮抢先：如实 409。冲突轮零落库，可基于最新历史重试。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ModelUpstreamError, ValueError) as exc:
        # 上游失败或 workflow 诚实抛错：本轮零落库（事务性单轮），可幂等重试。
        raise HTTPException(
            status_code=502, detail=f"导引本轮对话失败（可重试）：{exc}"
        ) from exc


@router.post("/conversations/{conversation_id}/conclude")
def conclude_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    """结束会话（active → concluded）。「确认草案去创建任务」时前端调用本端点
    归档会话（ADR-0013：补上 V0.1 会话不落终态的债）。"""
    service = request.app.state.conversation_service
    try:
        return service.conclude(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/model_calls")
def list_conversation_model_calls(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    """会话的模型调用留痕（ADR-0013：导引路径的 Q5 可追溯，成败全量）。"""
    conn = request.app.state.conn_factory()
    try:
        if repos.get_conversation(conn, conversation_id) is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{conversation_id}")
        return repos.list_model_calls_for_conversation(conn, conversation_id)
    finally:
        conn.close()
