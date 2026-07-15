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
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import classification_gate as cgate
from ..core.errors import (
    ConversationClosedError,
    ConversationConflictError,
    ConversationNotFoundError,
    FileNotFoundInStoreError,
    InteractiveToolAdmissionError,
    KnowledgeIngestError,
    KnowledgeScopeDeniedError,
    KnowledgeScopeNotRegisteredError,
    KnowledgeSourceUnavailableError,
    ModelConfigError,
    ModelUpstreamError,
    NotInteractiveAgentError,
    RegistryError,
    ToolExecutionError,
    ToolInputInvalidError,
    ToolNotAllowedError,
    ToolNotRegisteredError,
    ToolOutputInvalidError,
)

# 交互工具/知识资源失败的 HTTP 映射（Codex R2-P2）：会话 workflow 里的工具/知识调用会冒泡这些
# FlaiError 子类（wrapper 显式不吞、fail-closed 冒泡），而 post_message 此前只 catch Model* + ValueError
# → 这些**预期**失败逃逸成裸 HTTP 500（"服务器 bug"语义），误导用户/掩盖真实配置问题。按语义分两桶：
#
# ①永久性（config/部署缺陷，重试无效须运维修复）→ 503，与 ModelConfigError 同语义（绝不谎报「可重试」
# 误导用户反复点发送，PM 战略审 top）：工具未注册/未白名单/包 entrypoint 加载失败/注册表包完整性、
# 知识 scope 未注册/被拒/源未接入/语料摄取失败。
_CONV_RESOURCE_PERMANENT: tuple[type[BaseException], ...] = (
    InteractiveToolAdmissionError,  # 交互面工具安全门拒（Codex R3-P2：typed 后不再裸 500）
    ToolNotRegisteredError,
    ToolNotAllowedError,
    ToolExecutionError,        # errors.py：工具包 entrypoint 无法解析/加载=包配置错（永久）
    RegistryError,             # 含 Duplicate*/Invalid*Package/InvalidScopePackage
    KnowledgeScopeNotRegisteredError,
    KnowledgeScopeDeniedError,
    KnowledgeSourceUnavailableError,
    KnowledgeIngestError,
)
# ②临时/契约（可幂等重试、本轮零落库）→ 502，与 ModelUpstreamError/ValueError 同桶：入/出参 schema
# 不过（模型生成 payload 会变）、工具执行超时（builtin TimeoutError，非 FlaiError）。
_CONV_RESOURCE_TRANSIENT: tuple[type[BaseException], ...] = (
    ToolInputInvalidError,
    ToolOutputInvalidError,
    TimeoutError,
)
from ..storage import repos

router = APIRouter(prefix="/api", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    # ADR-0019 D5：created_by 已删——会话发起人=登录会话身份，服务端派生
    model_config = ConfigDict(extra="forbid")

    agent_id: str


class PostMessageRequest(BaseModel):
    # max_length：审计 P2（DoS 面）——content 此前无上限，超大文本会被落库并
    # 全量转发模型。16000 字符对需求描述/追问回答绰绰有余；更大材料走附件通道。
    content: str = Field(min_length=1, max_length=16000)
    # M7（ADR-0014）：会话附件——File Service 的文件 id 列表（先上传后引用）。
    # 上限 5 个/条与运行时防御纵深同值；内容渲染进模型上下文由内核统一做
    # （防注入规则行 + 预算硬顶），本层只收 id。
    file_ids: list[str] = Field(default_factory=list, max_length=5)

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


@router.post("/conversations")
def create_conversation(body: CreateConversationRequest, request: Request) -> dict[str, Any]:
    service = request.app.state.conversation_service
    try:
        return service.create(
            agent_id=body.agent_id, created_by=request.state.user["display_name"]
        )
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
        return service.post_message(
            conversation_id=conversation_id, content=body.content, file_ids=body.file_ids
        )
    except (ConversationNotFoundError, FileNotFoundInStoreError) as exc:
        # 会话不存在 / 引用了不存在的附件 id：404，且本轮零落库。
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ConversationClosedError, ConversationConflictError) as exc:
        # 已结束 / 被并发轮抢先：如实 409。冲突轮零落库，可基于最新历史重试。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except _CONV_RESOURCE_PERMANENT as exc:
        # 交互工具/知识资源**永久性**失败（未注册/未白名单/源未接入/包或语料配置错，Codex R2-P2）：
        # 与 ModelConfigError 同语义——重试无效，须运维修复配置，绝不谎报「可重试」。此前逃逸成裸 500。
        raise HTTPException(
            status_code=503,
            detail=f"会话所需的工具/知识资源不可用：{type(exc).__name__}：{exc}。"
            "此为部署/配置问题（非临时故障），请联系管理员核对工具注册/知识源接入后再试。",
        ) from exc
    except ModelConfigError as exc:
        # 模型网关未配置（缺 FLAI_LLM_*）=永久性错误：重试无效，需运维配置后恢复。
        # 与临时上游故障分流，绝不谎报「可重试」误导用户反复点发送（PM 战略审 top）。
        raise HTTPException(
            status_code=503,
            detail=f"模型网关未配置，导引不可用：{exc}。此为部署配置问题（非临时故障），"
            "请联系管理员设置 FLAI_LLM_* 环境变量后再试。",
        ) from exc
    except _CONV_RESOURCE_TRANSIENT as exc:
        # 交互工具/知识资源**临时/契约**失败（入出参 schema 不过/工具超时，Codex R2-P2）：本轮零落库，
        # 可幂等重试。与 ModelUpstreamError 同桶，但先于其显式捕获（TimeoutError 非 FlaiError 需单列）。
        raise HTTPException(
            status_code=502,
            detail=f"会话工具/知识调用本轮失败（可重试）：{type(exc).__name__}：{exc}",
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
        # ADR-0025 单 chokepoint（R1-A 补漏）：会话聚合 model_calls 跨成员任务，
        # sensitive 任务的 summary/error 承载工具产出——逐行按归属任务分级遮蔽。
        rows = repos.list_model_calls_for_conversation(conn, conversation_id)
        return cgate.redact_model_calls_by_task(conn, rows)
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}/tasks")
def list_conversation_tasks(conversation_id: str, request: Request) -> list[dict[str, Any]]:
    """协作会话的成员任务（M8/ADR-0016）：导引把一次会话的计划分流成 N 个人签发
    任务，各任务记 conversation_id 归到此会话下；协作工作台据此聚合展示进度与产物。
    仅读——每个任务仍由人在创建页亲手签发（人是唯一签发者，本端点不创建任何任务）。
    """
    conn = request.app.state.conn_factory()
    try:
        if repos.get_conversation(conn, conversation_id) is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{conversation_id}")
        # 会话成员是「完整分组视图」而非「最近流」——分页取尽，绝不静默截断
        # （异源 Codex M8-P3：硬编码 limit=500 会让 >500 成员的会话丢最旧任务，
        # 「完整成员视图」名不副实）。成员任务受人工逐个签发约束，实际远少于一页，
        # 循环通常一次即止；边界正确性靠取尽保证。
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
