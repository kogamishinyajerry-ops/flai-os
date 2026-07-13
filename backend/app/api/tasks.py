"""Task Center 接口：创建/查询/取消任务 + 事件时间轴查询。

宪法铁律「无事件=没发生」在本层落实：任何状态变化都配一条 task_event。
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import classification_gate as cgate
from ..core.errors import IllegalTransitionError
from ..logging_setup import audit_event
from ..storage import repos

router = APIRouter(prefix="/api", tags=["tasks"])

# 审计 P2（DoS 面）：inputs 此前无大小上限——超大 JSON 会被原样落库并进入
# runtime/事件链路放大。256KB 对 params 型输入绰绰有余；大数据走文件上传通道。
_INPUTS_MAX_BYTES = 256 * 1024


class CreateTaskRequest(BaseModel):
    # ADR-0019 D5：created_by 已从请求体删除，服务端从登录会话派生——身份
    # 不再自报。extra="forbid"：仍发 created_by 的旧客户端得到响亮 422 而非
    # 静默忽略（以为自己设置了身份=更危险）。
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str | None = Field(default=None, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)
    input_file_ids: list[str] = Field(default_factory=list)
    # M8/ADR-0016：可选归属——由导引协作会话产出的任务记会话 id，供协作工作台
    # 按会话分组。仅分组归属，不改执行语义；门户直建任务不带此字段（留 None）。
    conversation_id: str | None = Field(default=None, max_length=100)

    @field_validator("inputs")
    @classmethod
    def inputs_size_capped(cls, v: dict[str, Any]) -> dict[str, Any]:
        import json as _json

        size = len(_json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if size > _INPUTS_MAX_BYTES:
            raise ValueError(
                f"inputs 序列化后 {size} 字节，超过上限 {_INPUTS_MAX_BYTES}——大数据请走附件上传"
            )
        return v

    @field_validator("name")
    @classmethod
    def name_non_blank_if_present(cls, v: str | None) -> str | None:
        # task.schema.json: name 是 ["string","null"] 且 minLength=1——给了就不能空/纯空白
        # （异源 Codex R6-#7：空串 name 会落库并使 GET 响应违契约）。不命名请省略（留 null）。
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("name 若提供则不得为空白——不命名请省略该字段（留 null）")
        return stripped

    @field_validator("input_file_ids")
    @classmethod
    def input_file_ids_sane_and_unique(cls, v: list[str]) -> list[str]:
        # task.schema.json: input_file_ids.items.minLength=1 且 uniqueItems=true
        # （异源 Codex R6-#7：空串/重复 id 会落库并使响应违契约）。与会话附件 id 同口径
        # （非空白、长度 ≤64），另强制唯一——重复即如实拒，不静默去重。
        seen: set[str] = set()
        for fid in v:
            if not fid.strip() or len(fid) > 64:
                raise ValueError(f"非法输入文件 id：{fid!r}")
            if fid in seen:
                raise ValueError(f"输入文件 id 重复：{fid!r}（契约要求 uniqueItems）")
            seen.add(fid)
        return v


class ReviewTaskRequest(BaseModel):
    """人工放行请求体（P1-B）。reviewer 已从请求体删除（ADR-0019 D5）：
    签发者=登录会话身份，服务端派生——「人是唯一的工程签发者」（宪法铁律六）
    的「人」从此是认证的人，不是自报文本。extra="forbid" 同 CreateTaskRequest。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "reject"]
    comment: str | None = None


class SetSimRunRefRequest(BaseModel):
    """关联本任务到一次仿真 run（供 TaskDetail 深链监控视图 #/<mod>@<run_id>）。
    module/run_id 会进前端 URL hash——字符白名单钳死，只允许模块 id 与时间戳型
    run 名的安全字符集，防注入/畸形 hash（不接受空白、路径分隔、hash 元字符）。"""

    model_config = ConfigDict(extra="forbid")

    module: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$")


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
        # ADR-0019 D5：发起人=登录会话身份（中间件已验证注入），非请求体自报
        created_by = request.state.user["display_name"]
        create_kwargs = dict(
            task_id=task_id,
            agent_id=body.agent_id,
            agent_version=agent.get("version"),
            name=body.name,
            created_by=created_by,
            inputs=body.inputs,
            input_file_ids=body.input_file_ids,
            metadata={},
            conversation_id=body.conversation_id,
        )
        if body.conversation_id is not None:
            # 归属某导引会话：会话须真实存在（防悬空引用）**且仍 active**——归档后真只读
            # （异源 Codex R2-#3：「结束协作」= 真结束，不再接受新成员任务）。**复查状态与
            # INSERT 必须原子**（Codex R1 复审 #3：check-then-insert 非原子时，并发 conclude
            # 可抢在二者之间提交、仍把任务挂进已归档会话）→ BEGIN IMMEDIATE 写锁内复查真实
            # 状态再 INSERT，与 conclude 的 BEGIN IMMEDIATE 串行化。set_task_status 自带
            # BEGIN IMMEDIATE，故本事务只包「复查 + create_task」，提交后再迁 queued。
            conn.execute("BEGIN IMMEDIATE")
            try:
                conv = repos.get_conversation(conn, body.conversation_id)
                if conv is None:
                    raise HTTPException(
                        status_code=404, detail=f"归属的导引会话不存在：{body.conversation_id}"
                    )
                if conv["status"] != "active":
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"归属的导引会话已 {conv['status']}，不再接受新任务"
                            f"（结束协作=真只读）：{body.conversation_id}"
                        ),
                    )
                repos.create_task(conn, **create_kwargs)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        else:
            repos.create_task(conn, **create_kwargs)
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
            payload={"created_by": created_by, "status_from": "created", "status_to": "queued"},
        )
        return task
    finally:
        conn.close()


@router.get("/tasks")
def list_tasks(
    request: Request,
    status: str | None = None,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    origin: str = Query(
        default="user",
        description="任务来源：user（默认，工程师任务流）/eval（评测跑批）/all（不过滤）"
        "——M10/ADR-0018：eval 任务可查（诚实可追溯）但不混入默认工作流视图",
    ),
    limit: int = Query(default=100, ge=1, le=500, description="每页条数（1-500）"),
    offset: int = Query(default=0, ge=0, description="跳过条数（最近任务流分页语义，无总数计数）"),
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        rows = repos.list_tasks(
            conn, agent_id=agent_id, status=status, conversation_id=conversation_id,
            origin=None if origin == "all" else origin,
            limit=limit, offset=offset,
        )
        # ADR-0025 单 chokepoint：sensitive 任务的 error_message（承载工具内容）遮蔽。
        return [cgate.redact_task_row_if_sensitive(conn, t) for t in rows]
    finally:
        conn.close()


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        task = repos.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        # ADR-0025：sensitive→遮蔽 error_message（工具内容）；task.inputs 是用户自报
        # 输入不在门内（ADR-0024 D5 边界：封「工具产出」不封「用户提交」）。
        return cgate.redact_task_row_if_sensitive(conn, task)
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
            # ADR-0025 一致封闭：sensitive 任务的**任一**出场面（含变更响应回显的
            # 任务行 error_message）都过 chokepoint，绝不「GET 封、mutation 漏」。
            return cgate.redact_task_row_if_sensitive(conn, task)

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

        reviewer = request.state.user["display_name"]  # ADR-0019 D5：签发者=认证身份
        payload = {"reviewer": reviewer, "comment": body.comment}
        try:
            if body.action == "approve":
                task = repos.set_task_status(conn, task_id, "completed")
            else:
                # action == "reject"（Literal 已锁定只有两值）
                reject_reason = f"人工拒绝（reviewer={reviewer}）" + (
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

        # 治理签发审计（M12-2c）：人工放行/拒绝是「人是唯一签发者」红线的落点，
        # 是平台最安全承重的动作——此前只落 task_event（应用数据），无篡改抗性的
        # audit.log 轨。此处补审计轴：actor=签发者唯一 username（P2-4 唯一身份纪律），
        # 记录被签发任务、创建者、及**近似自审标记**（签发者与创建者显示名相同）。
        # 诚实边界：self_review 基于 display_name 比对（created_by 存的是显示名，非
        # username）——显示名非唯一故为可见性提示非强制；硬性职责分离（禁自审 403）
        # 需先补 created_by_username 身份列 + owner 定策略（角色轴，task #17 递延）。
        created_by = task.get("created_by")
        audit_event(
            "task_review",
            actor=request.state.user["username"],
            outcome=("approved" if body.action == "approve" else "rejected"),
            task_id=task_id,
            created_by=created_by if created_by is not None else "(unknown)",
            self_review=bool(created_by is not None and reviewer == created_by),
        )

        if body.action == "approve":
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=task.get("agent_id"),
                event_type="review_approved",
                level="info",
                message=f"人工批准放行（reviewer={reviewer}），任务转 completed"
                + (f"；{sample_rows} 条样本标记为工程师认可" if sample_rows else ""),
                payload=payload,
            )
            return cgate.redact_task_row_if_sensitive(conn, task)  # ADR-0025 一致封闭

        repos.append_event(
            conn,
            task_id=task_id,
            agent_id=task.get("agent_id"),
            event_type="review_rejected",
            level="warning",
            message=f"人工拒绝（reviewer={reviewer}），任务转 failed"
            + (f"；{sample_rows} 条样本标记为未认可" if sample_rows else ""),
            payload=payload,
        )
        return cgate.redact_task_row_if_sensitive(conn, task)  # ADR-0025 一致封闭
    finally:
        conn.close()


@router.post("/tasks/{task_id}/sim-run-ref")
def set_sim_run_ref(task_id: str, body: SetSimRunRefRequest, request: Request) -> dict[str, Any]:
    """把任务关联到一次仿真 run（写 metadata.sim_run_ref，不改执行语义/不改状态机）。
    真实时序：run_id 在任务跑起来后才知道，故独立于 create。鉴权由 default-deny
    中间件覆盖（非 allowlist）。任务不存在→404。"""
    conn = request.app.state.conn_factory()
    try:
        # 注：设 run 关联是 metadata 标注、非任务状态迁移——「无事件=没发生」约束的是
        # 状态变化；metadata.sim_run_ref.set_at 本身即记录，不为此扩冻结的事件枚举。
        task = repos.set_task_sim_run_ref(conn, task_id, module=body.module, run_id=body.run_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
        # ADR-0025：失败任务的 error_message 经此响应回；sensitive→遮蔽（Codex R1-A 三漏端点之一）。
        return cgate.redact_task_row_if_sensitive(conn, task)
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
        events = repos.list_events(conn, task_id, limit=limit, offset=offset)
        # ADR-0025：tool_started 事件 payload 带工具 input、tool_failed message 带外部
        # grounding_failures（event.schema:74 本就要求敏感 payload 脱敏）——sensitive→
        # 遮蔽 message+payload，只留 type/level/时间戳等元数据。
        if cgate.is_sensitive_task(conn, task):
            return cgate.redact_rows(events, cgate.EVENT_CONTENT_KEYS)
        return events
    finally:
        conn.close()


# ── 追溯读 API（ADR-0013，§18-Q5 收口）────────────────────────────────────
# tool_runs/model_calls/samples 自 M1 起就成败全量落库，但此前无任何读端点——
# 「输出可追溯到工具版本/模型版本」的数据存而不可达。三端点均为只读投影。


def _get_task_or_404(conn: Any, task_id: str) -> dict[str, Any]:
    task = repos.get_task(conn, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
    return task


@router.get("/tasks/{task_id}/tool_runs")
def list_task_tool_runs(task_id: str, request: Request) -> list[dict[str, Any]]:
    """任务的工具调用留痕（含 tool_version/mock 标记/原始输入输出路径）。"""
    conn = request.app.state.conn_factory()
    try:
        task = _get_task_or_404(conn, task_id)
        rows = repos.list_tool_runs(conn, task_id)
        # ADR-0025：sensitive→遮蔽 input/output/raw_path + error_message（Codex R1-A：
        # 工具错误文本承载外部 grounding_failures），只留元数据。
        if cgate.is_sensitive_task(conn, task):
            return cgate.redact_rows(rows, cgate.TOOL_RUN_CONTENT_KEYS)
        return rows
    finally:
        conn.close()


@router.get("/tasks/{task_id}/model_calls")
def list_task_model_calls(task_id: str, request: Request) -> list[dict[str, Any]]:
    """任务的模型调用留痕（含 model_profile/model_name/token 用量，成败全量）。"""
    conn = request.app.state.conn_factory()
    try:
        task = _get_task_or_404(conn, task_id)
        rows = repos.list_model_calls(conn, task_id)
        # ADR-0025：sensitive→遮蔽 request/response_summary + error_message；保留
        # token 计数/model_name 等元数据（非内容）。
        if cgate.is_sensitive_task(conn, task):
            return cgate.redact_rows(rows, cgate.MODEL_CALL_CONTENT_KEYS)
        return rows
    finally:
        conn.close()


@router.get("/tasks/{task_id}/samples")
def list_task_samples(task_id: str, request: Request) -> list[dict[str, Any]]:
    """任务沉淀的数据样本（validation_status=success|failed；accepted_by_engineer
    为人工审核结论回填，NULL=待定）。"""
    conn = request.app.state.conn_factory()
    try:
        task = _get_task_or_404(conn, task_id)
        rows = repos.list_samples(conn, task_id)
        # ADR-0025：sensitive→遮蔽 input/output/raw_path；保留 validation_status/
        # accepted_by_engineer/classification 等元数据。
        if cgate.is_sensitive_task(conn, task):
            return cgate.redact_rows(rows, cgate.SAMPLE_CONTENT_KEYS)
        return rows
    finally:
        conn.close()
