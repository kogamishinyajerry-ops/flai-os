"""导引会话接口（M6，ADR-0012）：interactive 型 Agent 的多轮对话入口。

与一次性 tasks 端点正交——会话由 ConversationService 驱动（app.state.conversation_service）。
本层负责开启会话、逐轮转发消息，并把认证用户显式请求的 ``safe_auto`` 交给后端
受限派发模块。派发只创建/入队可机械证明安全的任务；人工 review 与正式签发不可代理。

错误映射（fail-closed，绝不把上游失败降级为绿）：
- 会话/agent 不存在 → 404；会话已结束 → 409；对非 interactive Agent 发起会话 → 409；
- 模型能力尚未接入 → 501（非临时故障，不误导用户重试）；
- 模型上游失败/workflow 诚实抛错 → 502（如实透出「本轮对话失败，可重试」，不伪造回复）。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import classification_gate as cgate
from ..core.errors import (
    ConversationAccessDeniedError,
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    FileNotFoundInStoreError,
    ModelCapabilityUnavailableError,
    ModelConfigError,
    ModelUpstreamError,
    NotInteractiveAgentError,
)
from ..storage import repos

router = APIRouter(prefix="/api", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    # ADR-0019 D5：created_by 已删——会话发起人=登录会话身份，服务端派生
    model_config = ConfigDict(extra="forbid")

    agent_id: str


class PostMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # max_length：审计 P2（DoS 面）——content 此前无上限，超大文本会被落库并
    # 全量转发模型。16000 字符对需求描述/追问回答绰绰有余；更大材料走附件通道。
    content: str = Field(min_length=1, max_length=16000)
    # M7（ADR-0014）：会话附件——File Service 的文件 id 列表（先上传后引用）。
    # 上限 5 个/条与运行时防御纵深同值；内容渲染进模型上下文由内核统一做
    # （防注入规则行 + 预算硬顶），本层只收 id。
    file_ids: list[str] = Field(default_factory=list, max_length=5)
    # 默认保留 API 兼容的 plan_only；产品 GuidePage 对每次发送显式带 safe_auto。
    # 授权来自认证用户这一轮请求，绝不由 LLM 的 plan 文本推断。
    execution_mode: Literal["plan_only", "safe_auto"] = "plan_only"
    request_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content 不得为空白——请输入你的需求或对追问的回答")
        return stripped

    @field_validator("file_ids")
    @classmethod
    def file_ids_must_be_sane(cls, v: list[str]) -> list[str]:
        for fid in v:
            if not fid.strip() or len(fid) > 64:
                raise ValueError(f"非法附件 id：{fid!r}")
        return v

    @model_validator(mode="after")
    def safe_auto_requires_request_id(self) -> "PostMessageRequest":
        if self.execution_mode == "safe_auto" and self.request_id is None:
            raise ValueError("safe_auto 必须提供 request_id 以保证重试不重复创建任务")
        return self


@router.post("/conversations")
def create_conversation(body: CreateConversationRequest, request: Request) -> dict[str, Any]:
    service = request.app.state.conversation_service
    try:
        return service.create(
            agent_id=body.agent_id,
            created_by=request.state.user["display_name"],
            created_by_username=request.state.user["username"],
            actor_role=request.state.user["role"],
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotInteractiveAgentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


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
        return service.post_message(
            conversation_id=conversation_id,
            content=body.content,
            file_ids=body.file_ids,
            execution_mode=body.execution_mode,
            request_id=body.request_id,
            actor_display_name=request.state.user["display_name"],
            actor_username=request.state.user["username"],
            actor_role=request.state.user["role"],
        )
    except (ConversationNotFoundError, FileNotFoundInStoreError) as exc:
        # 会话不存在 / 引用了不存在的附件 id：404，且本轮零落库。
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationClosedError, ConversationConflictError) as exc:
        # 已结束 / 被并发轮抢先：如实 409。冲突轮零落库，可基于最新历史重试。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationAccessDeniedError as exc:
        # 自动执行会产生真实任务；会话所有者不匹配时必须在模型调用前 fail-closed。
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ModelCapabilityUnavailableError as exc:
        # 能力尚未接入是实现/部署边界，不是临时上游故障；同一请求重试不会恢复。
        raise HTTPException(
            status_code=501,
            detail=f"模型能力未接入，导引当前不可用：{exc}。此为能力接入问题（非临时故障），"
            "请联系管理员确认当前支持范围。",
        ) from exc
    except ModelConfigError as exc:
        # 模型网关未配置（缺 FLAI_LLM_*）=永久性错误：重试无效，需运维配置后恢复。
        # 与临时上游故障分流，绝不谎报「可重试」误导用户反复点发送（PM 战略审 top）。
        raise HTTPException(
            status_code=503,
            detail=f"模型网关未配置，导引不可用：{exc}。此为部署配置问题（非临时故障），"
            "请联系管理员设置 FLAI_LLM_* 环境变量后再试。",
        ) from exc
    except (ModelUpstreamError, ValueError) as exc:
        # 临时上游失败或 workflow 诚实抛错：本轮零落库（事务性单轮），可幂等重试。
        raise HTTPException(
            status_code=502, detail=f"导引本轮对话失败（可重试）：{exc}"
        ) from exc


@router.post("/conversations/{conversation_id}/conclude")
def conclude_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    """结束会话（active → concluded）。「确认草案去创建任务」时前端调用本端点
    归档会话（ADR-0013：补上 V0.1 会话不落终态的债）。"""
    service = request.app.state.conversation_service
    try:
        return service.conclude(
            conversation_id, actor_username=request.state.user["username"]
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConversationClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/conversations/{conversation_id}/model_calls")
def list_conversation_model_calls(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    """会话的模型调用留痕（ADR-0013：导引路径的 Q5 可追溯，成败全量）。"""
    conn = request.app.state.conn_factory()
    try:
        if repos.get_conversation(conn, conversation_id) is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{conversation_id}")
        # ADR-0025 单 chokepoint（R1-A 补漏）：会话聚合 model_calls 跨成员任务，
        # sensitive 任务的 summary/error 承载工具产出——逐行按归属任务分级遮蔽。
        rows = repos.list_model_calls_for_conversation(conn, conversation_id)
        return cgate.redact_model_calls_by_task(conn, rows)
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}/tasks")
def list_conversation_tasks(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    """协作会话的成员任务（M8/ADR-0016/ADR-0031）：任务按 conversation_id
    聚合展示。任务可由人手工创建，也可由受限 safe_auto 原子物化；本端点始终仅读，
    最终工程签发仍只能由认证真人完成。
    """
    conn = request.app.state.conn_factory()
    try:
        if repos.get_conversation(conn, conversation_id) is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{conversation_id}")
        # 会话成员是「完整分组视图」而非「最近流」——分页取尽，绝不静默截断
        # （异源 Codex M8-P3：硬编码 limit=500 会让 >500 成员的会话丢最旧任务，
        # 「完整成员视图」名不副实）。单会话成员受 Guide 上限与自动派发安全门约束，
        # 实际远少于一页；循环通常一次即止，边界正确性靠取尽保证。
        _PAGE = 500
        tasks: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = repos.list_tasks(conn, conversation_id=conversation_id, limit=_PAGE, offset=offset)
            tasks.extend(page)
            if len(page) < _PAGE:
                break
            offset += _PAGE
        # ADR-0025 单 chokepoint（Codex R1-A 漏堵端点之一）：sensitive 任务的
        # error_message 承载工具内容——逐行过门遮蔽。
        return [cgate.redact_task_row_if_sensitive(conn, t) for t in tasks]
    finally:
        conn.close()
