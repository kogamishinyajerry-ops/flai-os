"""导引会话接口（M6，ADR-0012）：interactive 型 Agent 的多轮对话入口。

与一次性 tasks 端点正交——会话由 ConversationService 驱动（app.state.conversation_service）。
本层负责开启会话、逐轮转发消息，并把认证用户显式请求的 ``safe_auto`` 交给后端
受限派发模块。派发只创建/入队可机械证明安全的任务；人工 review 与正式签发不可代理。

错误映射（fail-closed，绝不把上游失败降级为绿）：
- 会话/agent 不存在 → 404；会话已结束 → 409；对非 interactive Agent 发起会话 → 409；
- 模型上游失败/workflow 诚实抛错 → 502（如实透出「本轮对话失败，可重试」，不伪造回复）。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import classification_gate as cgate
from ..core.errors import (
    ConversationAccessDeniedError,
    ConversationAttachmentBindingError,
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    FileNotFoundInStoreError,
    ModelConfigError,
    ModelUpstreamError,
    NotInteractiveAgentError,
)
from ..storage import repos

router = APIRouter(prefix="/api", tags=["conversations"])


class ExpectedPrincipal(BaseModel):
    """浏览器意图绑定；仅作一致性前置条件，不参与授权。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "agent_developer", "business_user"]


class CreateConversationRequest(BaseModel):
    # ADR-0019 D5：created_by 已删——会话发起人=登录会话身份，服务端派生
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    # 浏览器在收到创建响应前刷新时，可用同一键重放；键只在当前认证用户名下唯一。
    request_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"
    )
    expected_principal: ExpectedPrincipal | None = None

    @model_validator(mode="after")
    def idempotent_create_requires_expected_principal(
        self,
    ) -> "CreateConversationRequest":
        if self.request_id is not None and self.expected_principal is None:
            raise ValueError("带 request_id 的会话创建必须绑定 expected_principal")
        return self


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
    expected_principal: ExpectedPrincipal | None = None

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
        if self.execution_mode == "safe_auto" and self.expected_principal is None:
            raise ValueError("safe_auto 必须绑定 expected_principal")
        if self.execution_mode == "safe_auto" and len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("safe_auto 的 file_ids 必须唯一，拒绝静默去重来源证据")
        return self


def _assert_expected_principal(
    expected: ExpectedPrincipal | None, request: Request
) -> None:
    if expected is None:
        return
    actual = request.state.user
    if (
        expected.username != actual.get("username")
        or expected.role != actual.get("role")
    ):
        # 不回显当前 cookie 对应的身份，避免把一致性门变成主体探测接口。
        raise HTTPException(
            status_code=409,
            detail="认证主体与持久化自动执行意图不一致，已拒绝请求",
        )


@router.post("/conversations")
def create_conversation(body: CreateConversationRequest, request: Request) -> dict[str, Any]:
    _assert_expected_principal(body.expected_principal, request)
    service = request.app.state.conversation_service
    try:
        return service.create(
            agent_id=body.agent_id,
            created_by=request.state.user["display_name"],
            created_by_username=request.state.user["username"],
            actor_role=request.state.user["role"],
            creation_request_id=body.request_id,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotInteractiveAgentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConversationConflictError as exc:
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
    _assert_expected_principal(body.expected_principal, request)
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
    except ConversationAttachmentBindingError as exc:
        # 文件存在但其种类/归属/分级/上传身份不满足自动执行来源契约。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
