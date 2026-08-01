"""导引会话接口（M6，ADR-0012）：interactive 型 Agent 的多轮对话入口。

与一次性 tasks 端点正交——会话由 ConversationService 驱动（app.state.conversation_service）。
红线：本层只负责开启会话、逐轮转发消息、返回 assistant 回复与推荐草案；**绝不**在
本层创建/签发下游任务。推荐草案（recommendation）交前端带到创建任务页，由人确认提交。

错误映射（fail-closed，绝不把上游失败降级为绿）：
- 会话/agent 不存在 → 404；会话已结束 → 409；对非 interactive Agent 发起会话 → 409；
- 模型上游失败/workflow 诚实抛错 → 502（如实透出「本轮对话失败，可重试」，不伪造回复）。
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import StreamingResponse

from . import classification_gate as cgate
from ..core.errors import (
    ClearanceDeniedError,
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
_STREAM_END = object()


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
    except ClearanceDeniedError as exc:
        # 密级准入不足（ADR-0030，Codex R2 P1）：策略拒绝非报警红——与任务路径
        # 创建门同 400 口径；本轮零落库、零 LLM 调用。
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


def _stream_error_event(
    exc: Exception, *, persisted: bool = False
) -> dict[str, Any]:
    """把同步端点既有错误语义编码进已开始的 NDJSON 响应。"""
    if isinstance(exc, (ConversationNotFoundError, FileNotFoundInStoreError)):
        status, detail, retryable = 404, str(exc), False
    elif isinstance(exc, ConversationConflictError):
        status, detail, retryable = 409, str(exc), True
    elif isinstance(exc, ConversationClosedError):
        status, detail, retryable = 409, str(exc), False
    elif isinstance(exc, ClearanceDeniedError):
        status, detail, retryable = 400, str(exc), False
    elif isinstance(exc, ModelConfigError):
        status = 503
        detail = (
            f"模型网关未配置，导引不可用：{exc}。此为部署配置问题（非临时故障），"
            "请联系管理员设置 FLAI_LLM_* 环境变量后再试。"
        )
        retryable = False
    elif isinstance(exc, (ModelUpstreamError, ValueError)):
        status = 502
        detail = f"导引本轮对话失败（可重试）：{exc}"
        retryable = True
    else:
        # 响应头已经发出，无法再切换为 HTTP 500；仍以显式事件 fail-closed，
        # 且不把内部异常细节暴露给前端。
        status, detail, retryable = 500, "导引本轮对话失败：服务内部错误", False
    return {
        "type": "error",
        "status": status,
        "detail": detail,
        "retryable": retryable,
        # 只有 service 尚未返回（因此确定事务未提交）时才允许 false。若服务已
        # 成功返回而后续封装异常，必须如实标 true，不能诱导前端盲目重试。
        "persisted": persisted,
    }


def _ndjson(event: dict[str, Any]) -> bytes:
    return (
        json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: str, body: PostMessageRequest, request: Request
) -> StreamingResponse:
    """真实分块对话：start → delta* → done；失败则以 error 明示零持久化。

    ConversationService / ModelGateway 仍是同步内核，因此用单个短生命周期线程把
    上游 SSE callback 桥接到响应生成器；不引入任务队列，也不改变旧 /messages。
    """
    service = request.app.state.conversation_service

    async def events() -> AsyncIterator[bytes]:
        pending: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
        closed = threading.Event()
        loop = asyncio.get_running_loop()

        def publish(event: dict[str, Any] | object) -> None:
            if closed.is_set():
                return
            try:
                loop.call_soon_threadsafe(pending.put_nowait, event)
            except RuntimeError:
                # 事件循环已关闭等同客户端已离开；后台轮次会在 callback 或
                # ConversationService 的提交前取消检查处退出。
                closed.set()

        def emit_delta(text: str) -> None:
            if closed.is_set():
                # 让模型调用与 ConversationService 在客户端离开后于落库前失败，
                # 不产生“用户没收到、服务却保存成功”的假完成。
                raise RuntimeError("流式客户端已断开")
            if text:
                publish({"type": "delta", "text": text})

        def run_round() -> None:
            committed = False
            try:
                result = service.post_message(
                    conversation_id=conversation_id,
                    content=body.content,
                    file_ids=body.file_ids,
                    on_delta=emit_delta,
                    is_cancelled=closed.is_set,
                )
                # ConversationService 返回即代表 COMMIT 已完成，且返回值不再做
                # 任何数据库读取。之后若封装 done 失败，error 不能谎报未持久化。
                committed = True
                if not closed.is_set():
                    publish(
                        {
                            "type": "done",
                            "message": result["message"],
                            "conversation": result["conversation"],
                        }
                    )
            except Exception as exc:
                if not closed.is_set():
                    publish(_stream_error_event(exc, persisted=committed))
            finally:
                publish(_STREAM_END)

        worker = threading.Thread(
            target=run_round,
            name=f"conversation-stream-{conversation_id[:24]}",
            daemon=True,
        )
        worker.start()
        try:
            yield _ndjson({"type": "start", "persisted": False})
            while True:
                # ASGI 2.4+ 的 StreamingResponse 只靠 send 抛 OSError 感知断连，
                # 同步 queue.get 又会把生成器困在线程池里。这里用 async 轮询显式
                # 检查 receive channel，使 http.disconnect 能在模型仍生成时及时
                # 设置 closed，继而触发 callback / 提交前检查并保持零落库。
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        pending.get(), timeout=0.05
                    )
                except asyncio.TimeoutError:
                    continue
                if event is _STREAM_END:
                    break
                if await request.is_disconnected():
                    break
                yield _ndjson(event)
        finally:
            closed.set()

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


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
