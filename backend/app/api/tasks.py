"""Task Center 接口：创建/查询/取消任务 + 事件时间轴查询。

宪法铁律「无事件=没发生」在本层落实：任何状态变化都配一条 task_event。
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import classification_gate as cgate
from ..auth.authorization import agent_is_callable, current_actor_matches, role_can_access_agent
from ..core.errors import IllegalTransitionError
from ..logging_setup import audit_event
from ..storage import repos

router = APIRouter(prefix="/api", tags=["tasks"])

# 审计 P2（DoS 面）：inputs 此前无大小上限——超大 JSON 会被原样落库并进入
# runtime/事件链路放大。256KB 对 params 型输入绰绰有余；大数据走文件上传通道。
_INPUTS_MAX_BYTES = 256 * 1024


class InputBinding(BaseModel):
    """artifact→input 绑定（协作运行时 §3.1）：声明只从哪些上游拷产物入 input_file_ids。

    from_tasks 空=默认拷全部上游 output（等价 input_binding=null）；非空=只拷这些上游
    的 output，其余上游仍参与依赖等待但产物不注入下游。**typed + extra=forbid + 有界列表**
    （Codex 增量2审 P2-4/P2-5）：任意 dict 会让 `{"from_tasks":1}` 过 Pydantic 后在服务端
    迭代抛 TypeError→500，且无大小上限可提交 MB 级嵌套对象绕过 inputs 的 256KB 放大闸；
    收成 str 列表模型后畸形入参得响亮 422、载荷天然有界。"""

    model_config = ConfigDict(extra="forbid")

    from_tasks: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("from_tasks")
    @classmethod
    def _from_tasks_sane_and_unique(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        for tid in v:
            if not tid.strip() or len(tid) > 64:
                raise ValueError(f"非法上游 task_id：{tid!r}")
            if tid in seen:
                raise ValueError(f"input_binding.from_tasks 重复：{tid!r}")
            seen.add(tid)
        return v


class CreateTaskRequest(BaseModel):
    # ADR-0019 D5：created_by 已从请求体删除，服务端从登录会话派生——身份
    # 不再自报。extra="forbid"：仍发 created_by 的旧客户端得到响亮 422 而非
    # 静默忽略（以为自己设置了身份=更危险）。
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str | None = Field(default=None, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)
    # max_length（Codex 增量2审 R3 P2）：仅 minLength/唯一不够——无数量上限时可提交数万
    # 个唯一 id，create_task 的 kind-allowlist 逐 id 查库=数万次 round trip 绕 256KB inputs
    # 闸的 authenticated DoS。64 对直提交输入绰绰有余（resolver 管道注入是内部写、不过本闸）。
    input_file_ids: list[str] = Field(default_factory=list, max_length=64)
    # M8/ADR-0016：可选归属——由导引协作会话产出的任务记会话 id，供协作工作台
    # 按会话分组。仅分组归属，不改执行语义；门户直建任务不带此字段（留 None）。
    conversation_id: str | None = Field(default=None, max_length=100)
    # 协作运行时 §3.5：声明式依赖。depends_on 非空 → 任务滞留 created 由 resolver
    # 在全部上游 completed 后管道产物入 input_file_ids 并入队（人是唯一签发者不变：
    # 人建整图、人签每个 review 环节；resolver 只排序执行，绝不建/签任务）。
    # input_binding：None=默认拷全部上游 output_file_ids；非 null 见 InputBinding（typed）。
    depends_on: list[str] = Field(default_factory=list, max_length=32)
    input_binding: InputBinding | None = Field(default=None)

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

    @field_validator("depends_on")
    @classmethod
    def depends_on_sane_and_unique(cls, v: list[str]) -> list[str]:
        # Codex 增量2审 R1 P2：max_length=32 只限条数，单个 ID 无长度上限时可提交 MB 级
        # 字符串绕 inputs 256KB 放大闸 + 404 detail 回显放大（authenticated DoS）。与
        # input_file_ids 同口径钳每项（非空白、≤64、唯一），把 task_id 收成有界标识符。
        seen: set[str] = set()
        for tid in v:
            if not tid.strip() or len(tid) > 64:
                raise ValueError(f"非法依赖 task_id：{tid!r}")
            if tid in seen:
                raise ValueError(f"依赖 task_id 重复：{tid!r}")
            seen.add(tid)
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


def _require_current_agent_access(
    conn: Any, request: Request, agent_registry: Any, agent_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """写事务内重读账户与当前 manifest；任一授权/可用性变化都默认拒绝。"""
    snapshot = request.state.user
    actor = current_actor_matches(
        conn,
        username=snapshot["username"],
        expected_role=snapshot["role"],
    )
    if actor is None:
        raise HTTPException(
            status_code=403,
            detail="认证账户已停用或角色发生变化，请重新登录后重试",
        )
    agent = _get_agent_or_none(agent_registry, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=409,
            detail=f"agent 在提交期间已不可用，拒绝运行或签发：{agent_id}",
        )
    if not agent_is_callable(agent, mode="job"):
        raise HTTPException(
            status_code=409,
            detail=f"agent 在提交期间已下线或不再是 job 型，拒绝运行或签发：{agent_id}",
        )
    if not role_can_access_agent(agent, actor["role"]):
        raise HTTPException(
            status_code=403,
            detail=(
                f"当前角色 {actor['role']} 无权运行或签发 agent {agent.get('id')}"
                "（permissions.visibility/allowed_roles 默认拒绝）"
            ),
        )
    return actor, copy.deepcopy(agent)


@router.post("/tasks")
def create_task(body: CreateTaskRequest, request: Request) -> dict[str, Any]:
    agent_registry = request.app.state.agent_registry
    agent = _get_agent_or_none(agent_registry, body.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{body.agent_id}")
    if not agent_is_callable(agent):
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
        # 角色复核、会话/依赖复查、创建、初始迁移与事件同一写事务：并发降权、
        # conclude 或事件失败均不能留下已入队的越权/半成品任务。
        conn.execute("BEGIN IMMEDIATE")
        actor, agent = _require_current_agent_access(
            conn, request, agent_registry, body.agent_id
        )
        task_id = f"task_{uuid.uuid4().hex}"
        # ADR-0019 D5：发起人=登录会话身份（中间件已验证注入），非请求体自报。
        # created_by 存 display_name（展示用，可撞名）；created_by_username（迁移 #9）
        # 存不可变唯一 username——批C 个人贡献归因按 username 绝不撞名；自审会被
        # 精确标记进审计，是否硬性职责分离仍由 owner 后续策略决定。
        created_by = actor["display_name"]
        created_by_username = actor["username"]
        # 协作运行时 §3.4/§3.5：depends_on 只能引用**已存在**任务（→图按构造即 DAG，
        # 无法建回边指向未来任务，无需运行时环检测）；缺失即 404 fail-closed。
        # input_binding 引用的上游必在 depends_on 内（越权引用拒，T6）。
        for dep_id in body.depends_on:
            upstream = repos.get_task(conn, dep_id)
            if upstream is None:
                raise HTTPException(
                    status_code=404, detail=f"依赖的上游任务不存在：{dep_id}"
                )
            # Codex 增量2审 R1 P1：依赖必须同 conversation 作用域（设计明列「不做跨
            # conversation 依赖」）。conversation_id 是分组归属、机密由 classification/taint
            # 独立管，但声明的排除须 fail-closed 强制——否则 C2 任务 depends_on C1 任务时
            # resolver 会把 C1 产物管道漏进 C2 协作会话。None==None（门户直建）/C==C 放行，
            # 不等即跨作用域 422 拒。
            if upstream.get("conversation_id") != body.conversation_id:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"依赖跨协作会话作用域：上游 {dep_id} 归属会话 "
                        f"{upstream.get('conversation_id')!r}，本任务归属 {body.conversation_id!r}"
                        "——不支持跨 conversation 依赖（产物不得跨会话管道）"
                    ),
                )
            # Codex 增量2审 R2 P1：依赖不得跨 eval/user 执行方隔离轴（ADR-0018）。用户
            # 任务（本 API 建的一律 origin=user）depends_on 一个 origin=eval 跑批任务时，
            # resolver 会把 eval 产物管道进 user 任务→user-origin sample gate 落库 samples，
            # 污染真实用户样本库、违 M10 隔离。上游须 origin=user 否则 422 fail-closed。
            if upstream.get("origin") != "user":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"依赖跨执行方隔离轴：上游 {dep_id} origin={upstream.get('origin')!r} 非 user"
                        "——不得依赖 eval 跑批任务（ADR-0018 eval/user 隔离，防 eval 产物污染样本库）"
                    ),
                )
        # 协作运行时安全边界（与 _open_input_files 按 kind 选权威根的放宽配对成闭）：
        # 直接提交的 input_file_ids 只允许上传件（allowlist：kind=input）。上游产物
        # （kind=output）唯一合法入口是 review-gated resolver 的管道注入
        # （enqueue_dependent_task 合并写 input_file_ids）——绝不许绕过 depends_on/人签闸
        # 直引他人 output，否则 _open_input_files 的 task_runs_dir 放宽会沦为直读任意
        # 任务产物的旁路。allowlist 而非 denylist：未来新增 kind 默认拒（fail-closed）。
        # 缺失文件（get_file=None）留执行期 _open_input_files 兜底，不在创建期拒。
        for fid in body.input_file_ids:
            rec = repos.get_file(conn, fid)
            if rec is not None and rec.get("kind") != "input":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"input_file_ids 只接受上传件（kind=input）：{fid} 的 kind="
                        f"{rec.get('kind')!r}——上游产物须经依赖 resolver 管道注入，不得直引"
                    ),
                )
        if body.input_binding is not None:
            stray = [t for t in body.input_binding.from_tasks if t not in body.depends_on]
            if stray:
                raise HTTPException(
                    status_code=422,
                    detail=f"input_binding 引用了 depends_on 之外的任务（越权）：{stray}",
                )
        create_kwargs = dict(
            task_id=task_id,
            agent_id=body.agent_id,
            agent_version=agent.get("version"),
            name=body.name,
            created_by=created_by,
            created_by_username=created_by_username,
            inputs=body.inputs,
            input_file_ids=body.input_file_ids,
            metadata={},
            depends_on=body.depends_on or None,
            # 持久化为普通 dict（repos.create_task json.dumps 落库）；None 保持 None。
            input_binding=body.input_binding.model_dump() if body.input_binding is not None else None,
            conversation_id=body.conversation_id,
        )
        if body.conversation_id is not None:
            # 归属某导引会话：会话须真实存在（防悬空引用）**且仍 active**——归档后真只读
            # （异源 Codex R2-#3：「结束协作」= 真结束，不再接受新成员任务）。**复查状态与
            # INSERT 必须原子**（Codex R1 复审 #3：check-then-insert 非原子时，并发 conclude
            # 可抢在二者之间提交、仍把任务挂进已归档会话）→ BEGIN IMMEDIATE 写锁内复查真实
            # 状态再 INSERT，与 conclude 的 BEGIN IMMEDIATE 串行化。本外层事务同时包
            # create_task、初始状态迁移与事件，任一步失败都不留半成品。
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
        latest_agent = _get_agent_or_none(agent_registry, body.agent_id)
        if latest_agent != agent:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"agent {body.agent_id} 的 manifest 在任务校验期间发生变化；"
                    "请基于当前版本重新提交"
                ),
            )
        repos.create_task(conn, **create_kwargs)
        # 协作运行时 §3.5 条件短路（F4 命门修复）：depends_on 非空的任务**不自动入队**，
        # 滞留 created 由 resolver 在全部上游 completed 后管道产物入 input 并入队——否则
        # 带依赖任务会在此被 P2-4 无条件推进到 queued，resolver 永远看不到 created 态、
        # 且 input_file_ids 尚无上游产物（"滞留 created"整机制静默失效）。
        # 无依赖任务保持 P2-4 原子 created->queued（docs/05 §6 文档化原子例外）。
        if body.depends_on:
            task = repos.get_task(conn, task_id)
            status_to = "created"
            message = f"任务已创建（等待 {len(body.depends_on)} 个前置任务）：agent={body.agent_id}"
        else:
            task = repos.set_task_status_in_transaction(conn, task_id, "queued")
            status_to = "queued"
            message = f"任务已创建：agent={body.agent_id}"
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id=body.agent_id,
            event_type="task_created",
            level="info",
            message=message,
            payload={
                "created_by": created_by,
                "status_from": "created",
                "status_to": status_to,
                "depends_on": body.depends_on or [],
            },
        )
        conn.execute("COMMIT")
        return task
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
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
        conn.execute("BEGIN IMMEDIATE")
        try:
            task = repos.get_task(conn, task_id)
            if task is None:
                raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
            if task["status"] != "waiting_review":
                raise HTTPException(
                    status_code=409,
                    detail=f"任务处于 {task['status']}，不在 waiting_review，无法人工放行/拒绝",
                )
            actor, _agent = _require_current_agent_access(
                conn,
                request,
                request.app.state.agent_registry,
                task["agent_id"],
            )
            if _get_agent_or_none(request.app.state.agent_registry, task["agent_id"]) != _agent:
                raise HTTPException(
                    status_code=409,
                    detail="任务所属 Agent manifest 在签发校验期间发生变化；请重新审核",
                )
            reviewer = actor["display_name"]  # ADR-0019 D5：签发者=当前认证身份
            # Codex 增量2审 R4 P1：状态迁移 + 样本标签回填 + signer 事件三者**同一事务
            # 原子落库**（此前三次分离提交，crash 窗口可留下 status=completed 却无
            # review_approved 事件的任务，resolver 见 status 即放行下游）。approve→completed
            # + review_approved / reject→failed + review_rejected；样本 approve→1/reject→0。
            task, _sample_rows = repos.apply_human_review(
                conn, task_id, action=body.action, reviewer=reviewer, comment=body.comment
            )
            conn.execute("COMMIT")
        except IllegalTransitionError as exc:
            # R1 复审 P2：两个 review 请求并发命中同一 waiting_review 任务时，
            # 后到者可通过预检但在状态机层被拒——这是正常并发竞态，
            # 与预检失败同口径返回 409，绝不让 500 逃逸。
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise HTTPException(
                status_code=409,
                detail=f"任务已被并发的人工审核动作转出 waiting_review，本次不生效：{exc}",
            ) from exc
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        # 治理签发审计（M12-2c）：人工放行/拒绝是「人是唯一签发者」红线的落点，
        # 是平台最安全承重的动作——此前只落 task_event（应用数据），无篡改抗性的
        # audit.log 轨。此处补审计轴：actor=签发者唯一 username（P2-4 唯一身份纪律），
        # 记录被签发任务、创建者、及自审标记。audit.log 独立于 DB（不同持久化域，无法
        # 互相原子），故置于原子 DB 提交**之后**——只为已提交的签发决策落审计。
        # 自审判定（迁移 #9 后升级）：created_by_username 存在（新任务）时按唯一
        # username 精确比对——绝不因显示名撞名误判；legacy 行（该列 NULL）回退
        # display_name 近似比对，并标 self_review_basis 说明证据等级。仍**只标记
        # 不拦截**（硬性职责分离 403 是 owner 待定的角色轴策略，task #17）。
        created_by = task.get("created_by")
        created_by_username = task.get("created_by_username")
        reviewer_username = actor["username"]
        if created_by_username is not None:
            self_review = bool(reviewer_username == created_by_username)
            self_review_basis = "username"  # 精确身份，不撞名
        else:
            self_review = bool(created_by is not None and reviewer == created_by)
            self_review_basis = "display_name"  # legacy 近似，可撞名
        audit_event(
            "task_review",
            actor=reviewer_username,
            outcome=("approved" if body.action == "approve" else "rejected"),
            task_id=task_id,
            created_by=created_by if created_by is not None else "(unknown)",
            created_by_username=created_by_username if created_by_username is not None else "(legacy-null)",
            self_review=self_review,
            self_review_basis=self_review_basis,
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
        # ADR-0025：普通 tool_started 事件 payload 可带工具 input（sensitive 工具只留
        # keys）；tool_failed message 可带外部 grounding_failures（event.schema:74
        # 要求敏感 payload 脱敏）——sensitive→
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


@router.get("/tasks/{task_id}/output_files")
def list_task_output_files(task_id: str, request: Request) -> list[dict[str, Any]]:
    """任务产物文件的只读元数据投影（批B P1 治理修复）：DeliveryCard 产物条此前
    逐个调用 /files/{id}/download 只为取文件名——纯展示需求却全量拖 blob，且对
    非 internal 分级文件触发 sensitive_download_denied 假阳性审计（用户根本没
    有下载意图）。本端点只投影 [{id, filename, size_bytes, data_classification}]，
    绝不含 path/sha256/uploaded_by 等敏感或内容字段——前端据此渲染 chip，真实下载
    仍走 /files/{id}/download 原有分级门（该端点自身的审计语义不受影响）。"""
    conn = request.app.state.conn_factory()
    try:
        task = _get_task_or_404(conn, task_id)
        rows = repos.list_files_by_ids(conn, task.get("output_file_ids") or [])
        return [
            {
                "id": r["id"],
                "filename": r["filename"],
                "size_bytes": r["size_bytes"],
                "data_classification": r["classification"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def _model_call_token_total(usage: Any) -> int | float | None:
    """与 DeliveryCard.vue/TaskDetail.vue modelCallTokenTotal() 同源口径：
    total_tokens 优先；否则 prompt_tokens+completion_tokens 均为数字才计入；
    两者皆无算未知，绝不记 0（bool 是 int 子类，显式排除避免 True 被当 1 计入）。"""
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return total
    p = usage.get("prompt_tokens")
    c = usage.get("completion_tokens")
    if (
        isinstance(p, (int, float)) and not isinstance(p, bool)
        and isinstance(c, (int, float)) and not isinstance(c, bool)
    ):
        return p + c
    return None


@router.get("/tasks/{task_id}/delivery_summary")
def get_task_delivery_summary(task_id: str, request: Request) -> dict[str, Any]:
    """今日交付卡（DeliveryCard）的有界服务端聚合（批B 治理审 R1 P1 修复）：
    此前单卡自带 listModelCalls+listTaskEvents 两个无界只读请求，交付量大时
    今日工作台=无界扇出。本端点一次聚合返回：

    - model_calls：只读 status/token_usage_json 两列（不 SELECT *，避免拖
      request/response_summary 等内容字段），token 口径与 DeliveryCard/TaskDetail
      的 tokenTotal 完全同源。
    - 批量摘要（batch_ok/batch_failed）：只看最近 50 条 agent_log 事件（DESC
      LIMIT 50，有界）——summary_generated 是批量 Agent 收尾事件，正常态必在
      事件尾部；若真被 50 条后续日志淹没，诚实返回 null（宁缺毋错，卡片就不
      显示批量行），不做无界扫描换取「万一漏了」的假完整。
    """
    conn = request.app.state.conn_factory()
    try:
        task = _get_task_or_404(conn, task_id)

        mc_rows = conn.execute(
            "SELECT status, token_usage_json FROM model_calls WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        mc_total = len(mc_rows)
        mc_ok = 0
        mc_failed = 0
        token_sum: int | float = 0
        token_known = 0
        for row in mc_rows:
            if row["status"] == "success":
                mc_ok += 1
            elif row["status"] == "failed":
                mc_failed += 1
            usage = None
            if row["token_usage_json"]:
                try:
                    usage = json.loads(row["token_usage_json"])
                except (TypeError, ValueError):
                    usage = None
            total = _model_call_token_total(usage)
            if total is not None:
                token_sum += total
                token_known += 1

        batch_ok: int | None = None
        batch_failed: int | None = None
        # ADR-0025 一致封闭（Codex R2-P1 verbatim）：/tasks/{id}/events 对 sensitive
        # 任务遮蔽 payload（含 summary_generated 的 ok/failed_count），本聚合若照读
        # payload 即重开被封的任务派生数据面——sensitive 一律不做事件扫描，批量字段
        # 保持 null（卡片不显示批量行）。model_calls 聚合只含计数/token 元数据，
        # 与 MODEL_CALL_CONTENT_KEYS 遮蔽面正交，保留。
        event_rows = [] if cgate.is_sensitive_task(conn, task) else conn.execute(
            "SELECT payload_json FROM task_events WHERE task_id = ? AND event_type = 'agent_log'"
            " ORDER BY id DESC LIMIT 50",
            (task_id,),
        ).fetchall()
        for row in event_rows:
            try:
                payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            except (TypeError, ValueError):
                payload = {}
            if (
                payload.get("workflow_event_type") == "summary_generated"
                and payload.get("ok_count") is not None
                and payload.get("failed_count") is not None
            ):
                batch_ok = payload["ok_count"]
                batch_failed = payload["failed_count"]
                break
    finally:
        conn.close()

    return {
        "mc_total": mc_total,
        "mc_ok": mc_ok,
        "mc_failed": mc_failed,
        "token_sum": token_sum,
        "token_known": token_known,
        "token_missing": mc_total - token_known,
        "batch_ok": batch_ok,
        "batch_failed": batch_failed,
    }
