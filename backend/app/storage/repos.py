"""任务/事件/文件/工具运行/模型调用/样本的仓储函数层（stdlib sqlite3，ADR-0008）。

约定：
- 每个函数第一参数是已打开的 `sqlite3.Connection`（调用方负责生命周期）。
- 返回值一律是 dict，且把 `_json` 后缀的存储列解码为去掉后缀的 Python 对象
  （如 `inputs_json` 列 -> 返回 dict 里的 `inputs` 键），方便上层直接消费。
- 所有时间戳字段一律 `datetime.now(timezone.utc).isoformat()`（UTC ISO 8601）。
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jsonschema import ValidationError, validate

from ..config import CONTRACTS_DIR
from ..core.errors import TaskNotFoundError
from ..core.statemachine import assert_transition, is_terminal

_EVENT_SCHEMA_PATH = CONTRACTS_DIR / "event.schema.json"
_event_schema_cache: dict[str, Any] | None = None
_QUESTION_ID_RE = re.compile(r"^q_[a-f0-9]{32}$")
_MESSAGE_ID_RE = re.compile(r"^msg_[a-f0-9]{32}$")
_REVIEW_REASON_CODES = frozenset({
    "source_doubt",
    "method_error",
    "conclusion_overreach",
    "insufficient_evidence",
    "classification_issue",
    "other",
})
_ADVISORY_OUTCOMES = frozenset({"clear", "concerns", "abstain"})
_ARTIFACT_OUTCOME_EVENT_TYPES = frozenset({
    "capture_started",
    "full_download",
    "pipeline_handoff",
})


class InvalidReviewError(ValueError):
    """人工终裁请求违反判断账本合同；API 层可安全映射为显式 422。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_event_schema() -> dict[str, Any]:
    global _event_schema_cache
    if _event_schema_cache is None:
        _event_schema_cache = json.loads(_EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _event_schema_cache


def _decode_json(d: dict[str, Any], json_key: str, out_key: str | None = None, default: Any = None) -> None:
    """把 d[json_key]（JSON 文本或 None）原地解码进 d[out_key]，并弹出原始列。"""
    out_key = out_key or json_key.removesuffix("_json")
    raw = d.pop(json_key, None)
    if raw is None:
        d[out_key] = default
    else:
        d[out_key] = json.loads(raw)


# ── tasks ──────────────────────────────────────────────────────────────

def _decode_task(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "input_file_ids", default=[])
    _decode_json(d, "output_file_ids", default=[])
    _decode_json(d, "inputs_json", "inputs", default={})
    _decode_json(d, "metadata_json", "metadata", default={})
    # 迁移 #9（协作运行时）：depends_on 缺省 []（存量 NULL / 无依赖）；input_binding
    # 缺省 None（默认拷全部上游 output）。存量库无此列时 dict(row) 无该键，兜默认。
    d["depends_on"] = json.loads(d["depends_on"]) if d.get("depends_on") else []
    d["input_binding"] = json.loads(d["input_binding"]) if d.get("input_binding") else None
    # 迁移 #12：retry_of 血缘注记——存量库尚未迁移时 row 无该键，兜 None
    # （投影键恒在，契约 parity 才稳定）。
    d["retry_of"] = d.get("retry_of")
    return d


def _decode_review_advice(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    _decode_json(result, "doubts_json", "doubts", default=[])
    _decode_json(
        result,
        "evidence_file_ids_json",
        "evidence_file_ids",
        default=[],
    )
    return result


def record_review_advice(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    model_call_id: int,
    advisor_id: str,
    advisor_version: str,
    model_profile: str,
    model_name: str | None,
    advisory_outcome: str,
    doubts: list[dict[str, Any]],
    evidence_file_ids: list[str] | None = None,
) -> dict[str, Any]:
    """写入一条机器顾问候选；本接口没有任何任务状态迁移能力。

    advisor_id/model_profile/model_name 必须与 model_calls 原始 provenance
    null-safe 精确一致。model_calls 当前没有 agent version 列，故
    advisor_version 仍是调用方从冻结 Agent manifest 提供的快照，不能被本表反推。
    """
    if advisory_outcome not in _ADVISORY_OUTCOMES:
        raise ValueError(f"未知机器顾问结论：{advisory_outcome}")
    if not all(isinstance(value, str) and value.strip() for value in (
        task_id, advisor_id, advisor_version, model_profile
    )):
        raise ValueError("顾问记录的任务、顾问与模型标识必须非空")
    if not isinstance(doubts, list) or len(doubts) > 20:
        raise ValueError("机器疑点必须是至多 20 条的列表")
    normalized_doubts: list[dict[str, str]] = []
    for doubt in doubts:
        if not isinstance(doubt, dict) or set(doubt) != {"code", "detail"}:
            raise ValueError("每条机器疑点必须且只能包含 code/detail")
        code = doubt.get("code")
        detail = doubt.get("detail")
        if code not in _REVIEW_REASON_CODES:
            raise ValueError(f"未知机器疑点代码：{code}")
        if not isinstance(detail, str) or not detail.strip() or len(detail) > 2000:
            raise ValueError("机器疑点说明必须为 1-2000 字符的非空文本")
        normalized_doubts.append({"code": code, "detail": detail})
    if advisory_outcome == "clear" and normalized_doubts:
        raise ValueError("clear 顾问结论不得携带疑点")
    if advisory_outcome == "concerns" and not normalized_doubts:
        raise ValueError("concerns 顾问结论至少需要一条疑点")
    if evidence_file_ids is None:
        evidence_file_ids = []
    if not isinstance(evidence_file_ids, list) or len(evidence_file_ids) > 50:
        raise ValueError("证据指针必须是至多 50 个 file_id 的列表")
    if len(set(evidence_file_ids)) != len(evidence_file_ids) or not all(
        isinstance(file_id, str)
        and bool(file_id.strip())
        and len(file_id) <= 100
        for file_id in evidence_file_ids
    ):
        raise ValueError("证据 file_id 必须非空、唯一且不超过 100 字符")

    task = get_task(conn, task_id)
    if task is None:
        raise TaskNotFoundError(f"任务不存在：{task_id}")
    authoritative_file_ids = set(task["input_file_ids"]) | set(
        task["output_file_ids"]
    )
    if not set(evidence_file_ids).issubset(authoritative_file_ids):
        raise ValueError("证据 file_id 必须属于同任务的冻结输入或权威输出")
    persisted_file_ids = {
        row["id"] for row in list_files_by_ids(conn, evidence_file_ids)
    }
    if persisted_file_ids != set(evidence_file_ids):
        raise ValueError("证据 file_id 必须引用真实文件记录")
    model_call = conn.execute(
        """
        SELECT task_id, agent_id, model_profile, model_name, status
        FROM model_calls
        WHERE id = ?
        """,
        (model_call_id,),
    ).fetchone()
    if model_call is None or model_call["task_id"] != task_id or model_call["status"] != "success":
        raise ValueError("顾问记录必须绑定同任务的一次成功模型调用")
    if (
        model_call["agent_id"] != advisor_id
        or model_call["model_profile"] != model_profile
        or model_call["model_name"] != model_name
    ):
        raise ValueError(
            "顾问记录的 advisor/model 快照必须与模型调用 exact provenance 一致"
        )

    advice_id = f"advice_{uuid.uuid4().hex}"
    created_at = _now_iso()
    conn.execute(
        """
        INSERT INTO task_review_advice
            (id, task_id, model_call_id, advisor_id, advisor_version,
             model_profile, model_name, advisory_outcome, doubts_json,
             evidence_file_ids_json, schema_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            advice_id,
            task_id,
            model_call_id,
            advisor_id,
            advisor_version,
            model_profile,
            model_name,
            advisory_outcome,
            json.dumps(normalized_doubts, ensure_ascii=False, sort_keys=True),
            json.dumps(evidence_file_ids, ensure_ascii=False),
            created_at,
        ),
    )
    row = conn.execute(
        "SELECT * FROM task_review_advice WHERE id = ?", (advice_id,)
    ).fetchone()
    return _decode_review_advice(row)


def get_human_decision(
    conn: sqlite3.Connection, task_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM task_human_decisions WHERE task_id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def create_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str,
    agent_version: str,
    name: str | None,
    created_by: str,
    inputs: dict[str, Any] | None = None,
    input_file_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    conversation_id: str | None = None,
    origin: str = "user",
    created_by_username: str | None = None,
    depends_on: list[str] | None = None,
    input_binding: dict[str, Any] | None = None,
    retry_of: str | None = None,
) -> dict[str, Any]:
    """建任务：初始态永远是 created（未入队）。

    depends_on / input_binding（迁移 #10/协作运行时 §3.5）：声明式依赖。depends_on
    非空时任务滞留 created 由 resolver 在全部上游 completed 后拷产物入 input_file_ids
    并入队（API 层负责"depends_on 非空则不自动入队"的短路，本函数只忠实落列）。

    conversation_id（M8/ADR-0016）：若本任务由导引协作会话产出，记会话 id 以便
    协作工作台按会话分组；门户直建任务留 None。仅作分组归属，不改任何执行语义。

    origin（M10/ADR-0018）：'user'=用户任务（worker 候选集）/'eval'=评测跑批
    任务（仅 eval runner 经 claim_task 驱动）。两候选集不相交，双跑竞态在
    结构上不存在。白名单校验：拼写错误的 origin 会造永久无主孤儿，进门即拒。

    created_by_username（迁移 #9）：发起人不可变唯一 username。created_by 存
    display_name（可变、可撞名，仅展示），本列存身份主键（批C 个人贡献按此归
    因绝不撞名）。省略=None，绝不用 created_by 冒充（自报时代不冒充追溯）。
    """
    if origin not in ("user", "eval"):
        raise ValueError(f"origin 只认 'user'/'eval'：{origin!r}")
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO tasks
            (id, agent_id, agent_version, name, status, created_by,
             created_at, updated_at, started_at, finished_at,
             input_file_ids, output_file_ids, inputs_json, error_message, metadata_json,
             conversation_id, origin, created_by_username, depends_on, input_binding,
             retry_of)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, agent_id, agent_version, name, "created", created_by,
            now, now, None, None,
            json.dumps(input_file_ids or [], ensure_ascii=False),
            json.dumps([], ensure_ascii=False),
            json.dumps(inputs or {}, ensure_ascii=False),
            None,
            json.dumps(metadata or {}, ensure_ascii=False),
            conversation_id,
            origin,
            created_by_username,
            json.dumps(depends_on, ensure_ascii=False) if depends_on else None,
            json.dumps(input_binding, ensure_ascii=False) if input_binding else None,
            retry_of,
        ),
    )
    return get_task(conn, task_id)  # type: ignore[return-value]


def list_created_dependent_tasks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """resolver 候选集：status='created' 且 depends_on 非空的 user 任务（不含 eval）。

    只读，不参与拾取裁决——resolver 拿到候选后逐个在写锁内复查状态再推进。
    depends_on 列 NULL/空 JSON 的存量任务天然不入候选（IS NOT NULL 且非 '[]'）。

    **列投影（Codex 增量2审 R4 P2）**：只取 resolver 实际消费的 4 列
    （id/agent_id/depends_on/input_binding），绝不 `SELECT *`。上游卡 waiting_review
    时其全部下游每个 resolve tick 都重现于此候选集；若拉全行，`_decode_task` 会 JSON
    解码每个下游至多 256KB 的 `inputs`（resolver 根本不读），大依赖批下累积可拖垮内存
    或阻塞唯一 worker 及其心跳。projected 后单候选负载只剩 depends_on(≤32 id)+小
    input_binding，与 `inputs` 体量彻底解耦。created_at 仅用于 ORDER BY 无需入选择列。
    """
    rows = conn.execute(
        "SELECT id, agent_id, depends_on, input_binding FROM tasks "
        "WHERE status = 'created' AND origin = 'user' "
        "AND depends_on IS NOT NULL AND depends_on != '[]' "
        "ORDER BY created_at ASC, id ASC"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["depends_on"] = json.loads(d["depends_on"]) if d.get("depends_on") else []
        d["input_binding"] = json.loads(d["input_binding"]) if d.get("input_binding") else None
        out.append(d)
    return out


def enqueue_dependent_task(
    conn: sqlite3.Connection,
    task_id: str,
    piped_input_file_ids: list[str],
    *,
    event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """resolver 把依赖满足的任务原子推进 created→queued 并落管道产物入 input_file_ids。

    BEGIN IMMEDIATE 写锁内**复查 status=='created'**（防并发：另一 resolver tick 或
    人工 cancel 可能已推进本任务）——非 created 返回 None（本次放弃，幂等）。
    **绝不写 data_classification**（F2：分级 100% 交执行期既有派生，避免抢写 CAS 冻结
    列挤掉下游自身污点）。input_file_ids = 原有 + 管道产物（去重保序）。
    event（Codex 增量2审 R2 P2）：lifecycle 事件与状态迁移**同事务原子写**——「无事件=
    没发生」宪法铁律，crash 窗口绝不留下 queued 却无 dependency_resolved 事件的任务。
    event 校验失败（append_event 抛）连状态迁移一并 ROLLBACK（原子）。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT status, input_file_ids FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None or row["status"] != "created":
            conn.execute("COMMIT")
            return None
        existing = json.loads(row["input_file_ids"]) if row["input_file_ids"] else []
        merged = list(existing)
        newly_piped: list[str] = []
        for fid in piped_input_file_ids:
            if fid not in merged:
                merged.append(fid)
                newly_piped.append(fid)
        assert_transition("created", "queued")
        now = _now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'queued', input_file_ids = ?, updated_at = ? "
            "WHERE id = ? AND status = 'created'",
            (json.dumps(merged, ensure_ascii=False), now, task_id),
        )
        # ADR-0036：管道 flow signal 与 created→queued、精确 input_file_ids 写入
        # 共用本事务。仅对新 instrumentation cohort（已有 capture_started）的
        # 人签产物记账；legacy/确定性无 capture 的合法管道照常运行但不冒充可观测。
        # 任一 telemetry insert 失败会走本函数统一 ROLLBACK，绝不留下已入队却无
        # handoff witness 的半态。full_download 可重复；这里则由 downstream 状态
        # 复查 + DB 精确唯一键共同保证 source file→downstream 幂等。
        for file_id in newly_piped:
            capture = get_artifact_capture_witness(conn, file_id)
            if capture is not None:
                append_artifact_outcome_event(
                    conn,
                    event_type="pipeline_handoff",
                    source_task_id=capture["source_task_id"],
                    source_file_id=file_id,
                    review_event_id=capture["review_event_id"],
                    downstream_task_id=task_id,
                )
        if event is not None:
            append_event(conn, task_id=task_id, **event)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def cancel_dependent_task(
    conn: sqlite3.Connection,
    task_id: str,
    error_message: str,
    *,
    event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """resolver 级联取消：**仅当仍 created** 时 created→cancelled（上游失败/取消）。

    BEGIN IMMEDIATE 复查 status=='created'——非 created（已被人工/并发推进）返回 None
    幂等放弃。刻意不走 set_task_status：后者的 assert_transition 允许 queued→cancelled，
    会误伤已入队任务（虽本分支上游失败下不该已入队，仍以结构守卫杜绝）。
    event（Codex 增量2审 R2 P2）：task_cancelled 事件与状态迁移**同事务原子写**（同
    enqueue，「无事件=没发生」，crash 窗口不留无事件的取消）。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None or row["status"] != "created":
            conn.execute("COMMIT")
            return None
        assert_transition("created", "cancelled")
        now = _now_iso()
        conn.execute(
            # data_classification=COALESCE(…, 'internal')（Codex 增量2审 R3 P2）：级联取消
            # 任务从未执行故 data_classification=NULL，而 error_message 一置，classification_gate
            # 会因「NULL 分级 + 有内容」fail-closed 判 sensitive 遮蔽掉系统取消诊断（reason/
            # message/payload），客户端无法区分级联取消。取消原因是**固定系统消息、非敏感
            # 用户内容**，CAS-on-NULL 落 internal 使诊断可见（ADR-0025：仅 NULL 时首写、
            # 不覆盖既有分级，保不可变语义；created 任务本恒 NULL 故等价落 internal）。
            "UPDATE tasks SET status = 'cancelled', error_message = ?, finished_at = ?, "
            "data_classification = COALESCE(data_classification, 'internal'), "
            "updated_at = ? WHERE id = ? AND status = 'created'",
            (error_message, now, now, task_id),
        )
        if event is not None:
            append_event(conn, task_id=task_id, **event)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def get_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _decode_task(row) if row is not None else None


def list_tasks(
    conn: sqlite3.Connection,
    *,
    agent_id: str | None = None,
    status: str | None = None,
    conversation_id: str | None = None,
    origin: str | None = None,
    created_by_username: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """最近任务流（created_at 降序）分页切片；同刻并列以 id 降序稳定去歧，
    保证 limit/offset 翻页不重不漏（P2-B：此前硬 LIMIT 100 静默截断）。

    conversation_id（M8）：按导引协作会话过滤——协作工作台取某次会话的成员任务。
    origin（M10）：仓储层 None=不过滤保持中立；API 层默认 'user'——工程师任务流
    不混入 eval 跑批任务（可显式查询，诚实可追溯，但不进默认工作流视图）。
    created_by_username（批C）：仓储层 None=不过滤中立；API 的 /me 端点按登录会话
    username 精确归因「我发起的任务」，NULL 存量行不被任何 username 误计。
    """
    clauses: list[str] = []
    params: list[Any] = []
    if agent_id is not None:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if conversation_id is not None:
        clauses.append("conversation_id = ?")
        params.append(conversation_id)
    if origin is not None:
        clauses.append("origin = ?")
        params.append(origin)
    if created_by_username is not None:
        clauses.append("created_by_username = ?")
        params.append(created_by_username)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = conn.execute(
        f"SELECT * FROM tasks {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", params
    ).fetchall()
    return [_decode_task(r) for r in rows]


def set_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    *,
    error_message: str | None = None,
) -> dict[str, Any]:
    """状态迁移入口：读-验-写整体包进 BEGIN IMMEDIATE 事务（P2-5：与 claim_next_queued
    同一防 TOCTOU 手法）——否则两个调用方可能并发读到同一 current 状态、都通过
    assert_transition、都写入，产生非法的"双写"竞态。据新态自动填 started_at/finished_at。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = get_task(conn, task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在：{task_id}")
        assert_transition(task["status"], new_status)

        now = _now_iso()
        updates: dict[str, Any] = {"status": new_status, "updated_at": now}
        if new_status == "running" and task.get("started_at") is None:
            updates["started_at"] = now
        if is_terminal(new_status):
            updates["finished_at"] = now
        if error_message is not None:
            updates["error_message"] = error_message

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)  # type: ignore[return-value]


def apply_human_review(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    action: str,
    reviewer: str,
    reviewer_username: str,
    reason_code: str | None,
    comment: str | None,
    paired_advice_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    """人工签发（approve/reject）的原子落库（Codex 增量2审 R4 P1）。

    waiting_review→completed/failed 状态迁移、样本标签回填、signer 事件
    （review_approved / review_rejected）三者包进**同一 BEGIN IMMEDIATE** 原子提交。
    此前 review_task 依次调 set_task_status（自带独立 COMMIT）+ set_sample_review_outcome
    + append_event 三次**分离提交**：crash 窗口可留下 status=completed 却无 signer 事件、
    样本仍 NULL 的任务——resolver 只看 status=='completed' 即放行下游，「无事件=没发生」
    铁律在最承重的人签路径失守（R2-3 已给次要的 resolver enqueue/cancel 上原子事件，
    此处补齐人签路径本身）。诚实边界：签名本体是人工触发、状态机门控且已持久提交的
    状态迁移**本身**（人确实签了，非未签发放行）；本修补的是审计事件与样本标签同迁移的
    **原子性**——防审计轨/样本标签在 crash 窗口丢失、与迁移脱节。event 契约校验失败 /
    非法转换 → 连状态迁移一并 ROLLBACK。

    返回 (最终任务行, 回填样本行数)。非 waiting_review 由 assert_transition 抛
    IllegalTransitionError（调用方按并发竞态转 409；含另一 review 已并发转出的场景）。
    """
    if action not in {"approve", "reject"}:
        raise InvalidReviewError(f"未知人工终裁动作：{action}")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise InvalidReviewError("人工终裁显示名必须非空")
    if not isinstance(reviewer_username, str) or not reviewer_username.strip():
        raise InvalidReviewError("人工终裁 username 必须非空")
    if comment is not None and len(comment) > 2000:
        raise InvalidReviewError("人工终裁说明不得超过 2000 字符")
    if action == "approve" and reason_code is not None:
        raise InvalidReviewError("批准不得携带驳回原因")
    if action == "reject" and reason_code not in _REVIEW_REASON_CODES:
        raise InvalidReviewError("驳回必须携带受支持的结构化原因")
    if reason_code == "other" and (comment is None or not comment.strip()):
        raise InvalidReviewError("驳回原因为 other 时必须填写非空说明")

    approve = action == "approve"
    new_status = "completed" if approve else "failed"
    decision_id = f"decision_{uuid.uuid4().hex}"
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = get_task(conn, task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在：{task_id}")
        # waiting_review→completed/failed 是人签唯一合法出口；terminal→terminal 非法
        # （并发二次 review 命中已转出任务时在此抛 IllegalTransitionError）。
        assert_transition(task["status"], new_status)
        now = _now_iso()
        if paired_advice_id is not None:
            paired = conn.execute(
                "SELECT 1 FROM task_review_advice WHERE id = ? AND task_id = ?",
                (paired_advice_id, task_id),
            ).fetchone()
            if paired is None:
                raise InvalidReviewError(
                    "paired_advice_id 必须引用同任务的机器顾问记录"
                )
        conn.execute(
            """
            INSERT INTO task_human_decisions
                (id, task_id, paired_advice_id, action, reason_code, comment,
                 reviewer_username, reviewer_display_name, schema_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                decision_id,
                task_id,
                paired_advice_id,
                action,
                reason_code,
                comment,
                reviewer_username,
                reviewer,
                now,
            ),
        )
        updates: dict[str, Any] = {
            "status": new_status,
            "updated_at": now,
            "finished_at": now,  # completed/failed 均 terminal
        }
        if not approve:
            updates["error_message"] = (
                f"人工拒绝（reviewer={reviewer}；reason={reason_code}）"
            ) + (
                f"：{comment}" if comment else ""
            )
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        # 样本标签回填（approve→1 / reject→0）——复用 set_sample_review_outcome
        # primitive（其裸 UPDATE 不自开事务，参与本 BEGIN IMMEDIATE，故与迁移同事务原子）。
        sample_rows = set_sample_review_outcome(conn, task_id, accepted=approve)
        # signer 事件，与迁移同事务（「无事件=没发生」在人签路径落地）。
        payload = {
            "reviewer": reviewer,
            "comment": comment,
            "decision_id": decision_id,
            "reason_code": reason_code,
            "paired_advice_id": paired_advice_id,
        }
        if approve:
            review_event = append_event(
                conn,
                task_id=task_id,
                agent_id=task.get("agent_id"),
                event_type="review_approved",
                level="info",
                message=f"人工批准放行（reviewer={reviewer}），任务转 completed"
                + (f"；{sample_rows} 条样本标记为工程师认可" if sample_rows else ""),
                payload=payload,
            )
            # ADR-0036 cohort 起点：只在**新** user-origin 人工批准事务里，按当时
            # 冻结的权威 output 清单逐件落 capture_started。它只表示 instrumentation
            # active，不是 outcome；绝不扫描旧 review event 反向回填。插入与人签同
            # 事务，故 marker 必绑定 exact review_approved event_id，任一坏 provenance
            # 会让本次批准整体 fail-closed 回滚。
            if task.get("origin") == "user":
                for output_file_id in dict.fromkeys(task.get("output_file_ids") or []):
                    append_artifact_outcome_event(
                        conn,
                        event_type="capture_started",
                        source_task_id=task_id,
                        source_file_id=output_file_id,
                        review_event_id=review_event["event_id"],
                    )
        else:
            append_event(
                conn,
                task_id=task_id,
                agent_id=task.get("agent_id"),
                event_type="review_rejected",
                level="warning",
                message=f"人工拒绝（reviewer={reviewer}），任务转 failed"
                + (f"；{sample_rows} 条样本标记为未认可" if sample_rows else ""),
                payload=payload,
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id), sample_rows  # type: ignore[return-value]


def get_agent_version_manifest(
    conn: sqlite3.Connection, agent_id: str, version: str
) -> dict[str, Any] | None:
    """读该 (agent_id, version) **锁定版本**的历史 manifest（agent_versions.yaml_json=
    registry 注册期落库的 json.dumps(data)）。键于任务自身锁定的 agent_version 而非当前
    registry——正确处理**版本翻转**（当前 v2=profile:none 但历史任务跑在 v1=reasoning）。
    行缺失 / yaml 损坏 / 非 dict → None（=版本 provenance 无法确立，调用方 fail-closed）。"""
    row = conn.execute(
        "SELECT yaml_json FROM agent_versions WHERE agent_id = ? AND version = ?",
        (agent_id, version),
    ).fetchone()
    if row is None:
        return None
    try:
        manifest = json.loads(row["yaml_json"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def has_review_approved_event(conn: sqlite3.Connection, task_id: str) -> bool:
    """该任务是否有持久 review_approved 事件=人工签发见证（apply_human_review 是唯一写入
    方，见其实现）。K1 签发维 provenance 用：`status=='completed'` 只证时序、不证人签。"""
    row = conn.execute(
        "SELECT 1 FROM task_events WHERE task_id = ? AND event_type = 'review_approved' LIMIT 1",
        (task_id,),
    ).fetchone()
    return row is not None


# ── artifact outcome telemetry（ADR-0036）──────────────────────────────

def _decode_artifact_outcome(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def append_artifact_outcome_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    source_task_id: str,
    source_file_id: str,
    review_event_id: str,
    actor_username: str | None = None,
    downstream_task_id: str | None = None,
    delivered_bytes: int | None = None,
) -> dict[str, Any]:
    """Append one physically witnessed artifact-flow fact.

    Python validates the public repository call shape; SQLite independently
    re-witnesses the user-origin source, authoritative output manifest, exact
    review event, capture cohort, byte count, and downstream dependency.  The
    table remains append-only even for ``INSERT OR REPLACE`` / explicit rowid.
    """
    if event_type not in _ARTIFACT_OUTCOME_EVENT_TYPES:
        raise ValueError(f"未知产物结果事件：{event_type}")
    if not all(
        isinstance(value, str) and bool(value.strip())
        for value in (source_task_id, source_file_id, review_event_id)
    ):
        raise ValueError("结果事件必须绑定非空 source task/file/review event")
    if event_type == "capture_started":
        if actor_username is not None or downstream_task_id is not None or delivered_bytes is not None:
            raise ValueError("capture_started 只能表示 instrumentation active")
    elif event_type == "full_download":
        if (
            not isinstance(actor_username, str)
            or not actor_username.strip()
            or downstream_task_id is not None
            or not isinstance(delivered_bytes, int)
            or isinstance(delivered_bytes, bool)
            or delivered_bytes < 0
        ):
            raise ValueError("full_download 需要具名 actor 与非负完整交付字节数")
    elif (
        actor_username is not None
        or not isinstance(downstream_task_id, str)
        or not downstream_task_id.strip()
        or delivered_bytes is not None
    ):
        raise ValueError("pipeline_handoff 需要 exact downstream task，且不得携带 actor/bytes")

    outcome_id = f"outcome_{uuid.uuid4().hex}"
    created_at = _now_iso()
    conn.execute(
        """
        INSERT INTO artifact_outcome_events
            (id, event_type, source_task_id, source_file_id, review_event_id,
             actor_username, downstream_task_id, delivered_bytes,
             schema_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            outcome_id,
            event_type,
            source_task_id,
            source_file_id,
            review_event_id,
            actor_username,
            downstream_task_id,
            delivered_bytes,
            created_at,
        ),
    )
    row = conn.execute(
        "SELECT * FROM artifact_outcome_events WHERE id = ?", (outcome_id,)
    ).fetchone()
    if row is None:  # defensive: INSERT success must have produced one row
        raise sqlite3.IntegrityError("artifact outcome insert produced no row")
    return _decode_artifact_outcome(row)


def get_artifact_capture_witness(
    conn: sqlite3.Connection, source_file_id: str
) -> dict[str, Any] | None:
    """Return the unique per-artifact cohort marker, never infer/backfill one."""
    row = conn.execute(
        """
        SELECT * FROM artifact_outcome_events
        WHERE event_type = 'capture_started' AND source_file_id = ?
        LIMIT 1
        """,
        (source_file_id,),
    ).fetchone()
    return _decode_artifact_outcome(row) if row is not None else None


def record_full_download_outcome(
    conn: sqlite3.Connection,
    *,
    source_task_id: str,
    source_file_id: str,
    review_event_id: str,
    actor_username: str,
    delivered_bytes: int,
) -> dict[str, Any]:
    """Record a completed 200 body against a pre-stream cohort snapshot.

    The caller must snapshot the exact source task/file/review witness before
    streaming begins.  This function deliberately does not discover a newer
    capture marker after delivery; SQLite independently revalidates that exact
    witness during INSERT.  Repeated real deliveries intentionally append
    repeated events.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        outcome = append_artifact_outcome_event(
            conn,
            event_type="full_download",
            source_task_id=source_task_id,
            source_file_id=source_file_id,
            review_event_id=review_event_id,
            actor_username=actor_username,
            delivered_bytes=delivered_bytes,
        )
        conn.execute("COMMIT")
        return outcome
    except Exception:
        conn.execute("ROLLBACK")
        raise


def task_output_is_signed_off(conn: sqlite3.Connection, task: dict[str, Any]) -> bool:
    """K1 签发维 provenance（Codex 增量2审 R5-1 + loop-auditor 巡查）：一个 completed 任务的
    产物**可否越依赖边界流入下游**。`status=='completed'` 只是时序代理——review-gated 上游
    经人签转出 completed 才带 review_approved 事件；但 pre-§3.6（或曾发过 profile≠none+rhr:
    false 版本后修正）的 legacy 任务可能已 analyzing→completed **自动放行、无人签**=未签
    LLM 判决，注册期 §3.6 只拒当前加载包、改不动历史行。

    fail-closed 双见证（皆持久、皆键于任务自身锁定的 agent_version）：
      ① 存在持久 review_approved 事件（人工签发）→ 放行；或
      ② 该任务 agent_version 的历史 manifest **显式** model.profile=='none' **且** workflow
         .requires_human_review is False（确定性零-LLM Agent 且显式非 review-gated，合法自动
         完成无需人签；与 §3.6 注册期判据同源——真实 agent 均显式声明二字段）→ 放行。
    **命中即审 R1 收紧**：原判据 `profile in (None,'none')` 会把空/退化 manifest（`{}`、
    `model.profile:null`、profile 缺失）当 none 放行=**fail-open**；且忽略 requires_human_review
    （profile=none+rhr:true 的 agent 其任务仍应人签，不该自动放行）。收紧为**二字段皆显式**：
    profile 必显式字符串 'none'（缺失/null→拒）+ rhr 必显式 False（缺失/None/True→拒）→ 退化/
    损坏/半 manifest 一律 fail-closed。manifest 缺失/损坏（get_agent_version_manifest 返 None）
    亦拒。二者皆不成立 → False（拒）。"""
    if has_review_approved_event(conn, task["id"]):
        return True
    manifest = get_agent_version_manifest(conn, task["agent_id"], task["agent_version"])
    if manifest is None:
        return False  # 版本 provenance 无法确立 → fail-closed，绝不 fail-open 放行
    model = manifest.get("model") or {}
    workflow = manifest.get("workflow") or {}
    # 显式确定性（profile=='none'）且显式非 review-gated（rhr is False）——皆显式杜绝退化 manifest
    # fail-open（空 dict/缺字段→None，非 'none'/非 False→拒）。
    return model.get("profile") == "none" and workflow.get("requires_human_review") is False


def set_task_data_classification(
    conn: sqlite3.Connection, task_id: str, classification: str
) -> str:
    """执行期把任务级派生分级落库为**真不可变**列（ADR-0025）：runtime.execute 在 agent
    加载成功后、产出任何内容前调一次。

    **CAS 首写语义（Codex R0 P1-2 闭合）**：只在列为 NULL 时写入——已落库值不可变。
    此前为无条件 `UPDATE ... SET`，二次 `runtime.execute()` 会在状态机拒绝重跑前按**当前
    注册表**重算并覆盖（工具降级后把历史 sensitive 改 internal），正是 R1-B 漂移换个入口
    复现。CAS-on-NULL 结构性杜绝：首写定终身，后续 execute 一律 no-op。

    返回**最终持久值**（首写=传入值；已存在=既有落库值）——runtime 必须用返回值而非
    新算值定后续产物/样本分级，确保「产物分级 == 落库任务级分级」即便二次 execute。
    read 期仍一律读此列不重派生。"""
    conn.execute(
        "UPDATE tasks SET data_classification = ? WHERE id = ? AND data_classification IS NULL",
        (classification, task_id),
    )
    row = conn.execute(
        "SELECT data_classification FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()
    # 行必存在（runtime 已确认任务加载）；列在首写后非 NULL。防御性回退到传入值。
    return row[0] if row is not None and row[0] is not None else classification


_BACKFILL_TERMINAL_STATES = ("completed", "failed", "cancelled", "waiting_review")


def backfill_task_data_classification(
    conn: sqlite3.Connection,
    sensitive_tool_ids: list[str],
    known_tool_ids: list[str] | None = None,
) -> int:
    """一次性回填存量任务的不可变分级（ADR-0025 D4，在 bootstrap.assemble 调，registry
    可用处）：只碰**终态** NULL 任务（created/queued/running 留 NULL，执行期由 runtime
    落库），按**持久证据**定分级 → sensitive，否则 internal。sensitive 证据：
      1. 非 internal 的 files/samples 行；
      2. tool_runs 引用当前判 sensitive 的工具；
      3. tool_runs 引用当前注册表**不认识**的工具（已卸载/scan 被拒/改名——历史分级
         不可考，fail-closed 判 sensitive，绝不把「当前无命中」当「已证明 internal」，
         Codex R0 P1-3）。

    `known_tool_ids`=当前注册表全部工具 id（sensitive+internal）；缺省 None 表示调用方
    未提供已知集 → 跳过第 3 类（保持旧行为，仅测试/兼容用）。`sensitive_tool_ids` 由调用
    方从当前注册表算（非显式 internal 一律计入，含坏值/未知）。

    **诚实残差（非本函数漏洞，见 ADR-0025 §五）**：输入文件/知识轴的历史 sensitive 不由
    本函数直接对账——但 ADR-0021 执行期已按文件∨知识轴给这些任务的**产物**落 sensitive
    分级（→第 1 类命中），且 sensitive 输入文件本身的下载受其自身 classification 保护
    （files.py 下载门检子行，非父任务列），故无泄漏面。

    幂等：NULL 终态集清空后每次启动重跑均为 no-op。全程 BEGIN IMMEDIATE 写锁内（双进程
    启动竞态安全，与迁移同手法）。返回本次回填的任务数。"""
    term_ph = ", ".join("?" for _ in _BACKFILL_TERMINAL_STATES)
    conn.execute("BEGIN IMMEDIATE")
    try:
        backfilled = conn.execute(
            f"SELECT COUNT(*) FROM tasks WHERE data_classification IS NULL"
            f" AND status IN ({term_ph})",
            _BACKFILL_TERMINAL_STATES,
        ).fetchone()[0]
        # 1) sensitive：非 internal 的 files/samples 行（持久、执行期已定）。
        conn.execute(
            f"""UPDATE tasks SET data_classification = 'sensitive'
                WHERE data_classification IS NULL AND status IN ({term_ph}) AND (
                  id IN (SELECT task_id FROM files
                         WHERE classification IS NOT NULL AND classification != 'internal')
                  OR id IN (SELECT task_id FROM samples
                            WHERE classification IS NOT NULL AND classification != 'internal'))""",
            _BACKFILL_TERMINAL_STATES,
        )
        # 2) sensitive：tool_runs 引用了 (a) 当前判 sensitive 的工具，或 (b) 当前注册表
        #    不认识的工具（fail-closed，Codex R0 P1-3）。覆盖无 files/samples 行的 sensitive
        #    任务（Codex R1-B 点名的 eval/collect_samples=false/早失败）+ 卸载工具历史任务。
        taint_clauses: list[str] = []
        taint_params: list[str] = []
        if sensitive_tool_ids:
            taint_clauses.append(
                f"tool_id IN ({', '.join('?' for _ in sensitive_tool_ids)})"
            )
            taint_params.extend(sensitive_tool_ids)
        if known_tool_ids is not None:
            if known_tool_ids:
                taint_clauses.append(
                    f"tool_id NOT IN ({', '.join('?' for _ in known_tool_ids)})"
                )
                taint_params.extend(known_tool_ids)
            else:
                # 注册表为空（退化启动）：一切历史工具不可考 → 全 fail-closed sensitive。
                taint_clauses.append("1 = 1")
        if taint_clauses:
            conn.execute(
                f"""UPDATE tasks SET data_classification = 'sensitive'
                    WHERE data_classification IS NULL AND status IN ({term_ph})
                    AND id IN (SELECT task_id FROM tool_runs
                               WHERE {' OR '.join(taint_clauses)})""",
                (*_BACKFILL_TERMINAL_STATES, *taint_params),
            )
        # 3) 剩余终态 NULL → internal（无 sensitive 证据）。
        conn.execute(
            f"UPDATE tasks SET data_classification = 'internal'"
            f" WHERE data_classification IS NULL AND status IN ({term_ph})",
            _BACKFILL_TERMINAL_STATES,
        )
        # 4) 子行一致化（Codex R0 P1）：**下载门（files.py:277）与固化/复用门（curation）
        #    检的是 files/samples 自身的 classification 子行，不是父任务列**。步骤 1-2 把父
        #    任务升 sensitive 后，历史 internal 子行（0.1.0 期 monitor 草案：工具轴当时不存在
        #    →产物误落 internal）仍会过下载 403（不触发）与 eval-cases 原样固化=半闭合假绿。
        #    故把**终态 sensitive 任务**的非 sensitive 子行一并升 sensitive——与执行期
        #    _register_outputs/_record_failure_sample 对新任务「产物/样本继承任务级派生分级」
        #    同口径，兑现「一个任务 sensitive 则其全部产出一致 sensitive」不变式。NULL 亦升
        #    （fail-closed）。幂等（已 sensitive 子行不动）。锁内，与父行同事务。
        term_sensitive = (
            f"(SELECT id FROM tasks WHERE data_classification = 'sensitive'"
            f" AND status IN ({term_ph}))"
        )
        for _child_table in ("files", "samples"):
            conn.execute(
                f"UPDATE {_child_table} SET classification = 'sensitive'"
                f" WHERE (classification IS NULL OR classification != 'sensitive')"
                f" AND task_id IN {term_sensitive}",
                _BACKFILL_TERMINAL_STATES,
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return backfilled


def fail_task_from_execution(
    conn: sqlite3.Connection,
    task_id: str,
    error_message: str,
) -> dict[str, Any] | None:
    """仅允许 Runner 从执行态把任务置 failed，审核态与终态一律拒绝自动迁移。

    状态读取、执行态白名单判断与更新全部位于同一个 BEGIN IMMEDIATE 事务内，
    防止检查后到更新前任务已被并发推进到 waiting_review 的 TOCTOU 旁路。
    """
    execution_states = frozenset({"validating", "running", "parsing", "analyzing"})
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = get_task(conn, task_id)
        if task is None or task["status"] not in execution_states:
            conn.execute("COMMIT")
            return None

        assert_transition(task["status"], "failed")
        now = _now_iso()
        updates: dict[str, Any] = {"status": "failed", "updated_at": now}
        if is_terminal("failed"):
            updates["finished_at"] = now
        if error_message is not None:
            updates["error_message"] = error_message

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?",
            (*updates.values(), task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def claim_next_queued(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """原子拾取一条 queued **用户**任务并转 validating（BEGIN IMMEDIATE 独占写锁，先来先服务）。

    无 queued 任务返回 None。两个调用方并发调用本函数时，sqlite 的
    IMMEDIATE 锁保证同一行只会被其中一次调用拾取（另一次要么看不到该行
    已被更新前的状态，要么被阻塞到第一次提交后重新读到 validating 而非
    queued，从而拿不到同一任务）。

    M10/ADR-0018：候选集限定 origin='user'——eval 跑批任务由 eval runner 经
    claim_task 自驱，worker 永远看不到它们（隔离是集合不相交，不是时序侥幸）。
    """
    # 空队列是高频空跑路径：先做普通读，只有探测到候选才申请写锁。探测结果
    # 绝不参与拾取裁决；拿锁后仍须重新 SELECT，以锁内读到的状态为唯一真相。
    if conn.execute(
        "SELECT 1 FROM tasks WHERE status = 'queued' AND origin = 'user' LIMIT 1"
    ).fetchone() is None:
        return None

    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT id FROM tasks WHERE status = 'queued' AND origin = 'user' "
            "ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        task_id = row["id"]
        assert_transition("queued", "validating")
        now = _now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'validating', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now, task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def claim_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    """原子认领**指定** queued 的 eval 任务并转 validating（eval runner 专用，M10）。

    与 claim_next_queued 同一 BEGIN IMMEDIATE 手法；目标任务不存在、不在
    queued 态、或 origin 不是 'eval'（本函数绝不许被误用来抢用户任务——与
    worker 的 origin='user' 过滤互为镜像）都返回 None（调用方 fail-closed）。
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT status, origin FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None or row["status"] != "queued" or row["origin"] != "eval":
            conn.execute("COMMIT")
            return None
        assert_transition("queued", "validating")
        now = _now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'validating', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now, task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


def set_task_outputs(conn: sqlite3.Connection, task_id: str, output_file_ids: list[str]) -> dict[str, Any]:
    now = _now_iso()
    conn.execute(
        "UPDATE tasks SET output_file_ids = ?, updated_at = ? WHERE id = ?",
        (json.dumps(output_file_ids, ensure_ascii=False), now, task_id),
    )
    return get_task(conn, task_id)  # type: ignore[return-value]


def set_task_sim_run_ref(
    conn: sqlite3.Connection, task_id: str, *, module: str, run_id: str
) -> dict[str, Any] | None:
    """把「本任务关联的仿真 run」写进 metadata.sim_run_ref（复用现有 metadata 袋，
    不加列不迁移）——供 TaskDetail 深链到该 run 的监控视图（#/<mod>@<run_id>）。
    真实时序：run_id 在任务跑起来后才知道，故必须支持创建后写入。read-modify-write
    metadata 整体包 BEGIN IMMEDIATE（与 set_task_status 同手法，防同任务并发写竞态
    互相吞掉 metadata 其他键）。任务不存在返回 None（API 转 404）。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        task = get_task(conn, task_id)
        if task is None:
            conn.execute("ROLLBACK")
            return None
        metadata = dict(task.get("metadata") or {})
        metadata["sim_run_ref"] = {"module": module, "run_id": run_id, "set_at": _now_iso()}
        # 绝不 bump updated_at（Codex 治理审 P2）：sim_run_ref 是 metadata 标注不是
        # 状态迁移——终态未读信号（taskHasUnseen/hasUnseen 依 updated_at 判新鲜度）
        # 与「最近更新」排序都不该被一次关联/更正扰动。同理不 append_event。
        conn.execute(
            "UPDATE tasks SET metadata_json = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), task_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_task(conn, task_id)


# ── task_events ────────────────────────────────────────────────────────

def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d.pop("id", None)  # sqlite 自增主键仅内部用；对外唯一键=event_id（P1-2/P1-3 契约对账）。
    # 无 Agent 上下文的系统事件（如 Job Runner 兜底 task_failed）以 NULL 存 agent_id；
    # event.schema.json 的 agent_id 只允许 string 或**省略**，绝不允许 null——写入口
    # 校验的是"省略 agent_id 的对象"（append_event 仅 agent_id 非空才入 event_obj），
    # 读出口却把 NULL 列还原成 null 会破契约。此处对齐：NULL → 省略（异源 Codex R6-#8）。
    if d.get("agent_id") is None:
        d.pop("agent_id", None)
    _decode_json(d, "payload_json", "payload", default={})
    return d


def append_event(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str | None = None,
    event_type: str,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """写事件：先对 contracts/event.schema.json 做整对象校验，非法即抛 ValueError。

    这是「事件枚举在写入口强制」的咬合点——event_type/level 若不在契约枚举内，
    jsonschema 校验必炸，不允许绕过 API 层校验直接写库产生脏事件。
    """
    payload = payload or {}
    event_id = str(uuid.uuid4())
    created_at = _now_iso()
    event_obj: dict[str, Any] = {
        "event_id": event_id,
        "task_id": task_id,
        "event_type": event_type,
        "level": level,
        "message": message,
        "payload": payload,
        "created_at": created_at,
    }
    if agent_id is not None:
        event_obj["agent_id"] = agent_id

    try:
        validate(event_obj, _load_event_schema())
    except ValidationError as exc:
        raise ValueError(f"事件契约校验失败：{exc.message}") from exc

    cur = conn.execute(
        """
        INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (event_id, task_id, agent_id, event_type, level, message,
         json.dumps(payload, ensure_ascii=False), created_at),
    )
    row = conn.execute("SELECT * FROM task_events WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_event(row)


def list_events(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    limit: int = 2000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """任务事件时间轴分页切片（ORDER BY id ASC 不变——自增主键即写入序，
    翻页天然不重不漏）。默认 limit=2000 覆盖 V0.1 全部正常任务。"""
    rows = conn.execute(
        "SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC LIMIT ? OFFSET ?",
        (task_id, limit, offset),
    ).fetchall()
    return [_decode_event(r) for r in rows]


def get_task_event_snapshot(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    after_sequence: int = 0,
    anchor_event_id: str | None = None,
) -> dict[str, Any]:
    """Return an anchored, per-task sequenced view of the append-only event log.

    ``task_events.id`` remains internal.  The public sequence is the stable
    one-based ordinal inside one task's append-only log; ``event_id`` is the
    exact anchor that detects deletion, compaction, or a stale client cursor.
    Existing event rows and their public schema are not changed.
    """
    count_row = conn.execute(
        "SELECT COUNT(*) AS n FROM task_events WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    sequence = int(count_row["n"])
    last_row = conn.execute(
        "SELECT event_id FROM task_events WHERE task_id = ? ORDER BY id DESC LIMIT 1",
        (task_id,),
    ).fetchone()
    cursor_event_id = str(last_row["event_id"]) if last_row is not None else None
    cursor = {"sequence": sequence, "event_id": cursor_event_id}
    base = {"sequence": after_sequence, "event_id": anchor_event_id}

    if after_sequence > sequence:
        return {
            "base": base,
            "cursor": cursor,
            "events": [],
            "resync_required": True,
            "resync_reason": "cursor_ahead",
        }

    if after_sequence > 0:
        anchor_row = conn.execute(
            """
            SELECT event_id FROM task_events
            WHERE task_id = ? ORDER BY id ASC LIMIT 1 OFFSET ?
            """,
            (task_id, after_sequence - 1),
        ).fetchone()
        if anchor_row is None or str(anchor_row["event_id"]) != anchor_event_id:
            return {
                "base": base,
                "cursor": cursor,
                "events": [],
                "resync_required": True,
                "resync_reason": "anchor_mismatch",
            }

    rows = conn.execute(
        """
        SELECT * FROM task_events
        WHERE task_id = ? ORDER BY id ASC LIMIT -1 OFFSET ?
        """,
        (task_id, after_sequence),
    ).fetchall()
    events = [
        {"sequence": after_sequence + index, "event": _decode_event(row)}
        for index, row in enumerate(rows, start=1)
    ]
    return {
        "base": base,
        "cursor": cursor,
        "events": events,
        "resync_required": False,
        "resync_reason": None,
    }


# ── files ──────────────────────────────────────────────────────────────

def create_file(
    conn: sqlite3.Connection,
    *,
    file_id: str,
    task_id: str | None = None,
    kind: str,
    filename: str,
    path: str,
    size_bytes: int,
    sha256: str,
    classification: str,
    uploaded_by: str | None = None,
) -> dict[str, Any]:
    """classification 必填无默认值（ADR-0021 D1/设计审 F4）：调用点漏传=TypeError
    当场炸，绝不静默吃 DDL DEFAULT 把派生 sensitive 洗白成 internal。"""
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO files
            (id, task_id, kind, filename, path, size_bytes, sha256, created_at,
             classification, uploaded_by)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (file_id, task_id, kind, filename, path, size_bytes, sha256, now,
         classification, uploaded_by),
    )
    return get_file(conn, file_id)  # type: ignore[return-value]


def get_file(conn: sqlite3.Connection, file_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    return dict(row) if row is not None else None


# IN 子句分批上限（Codex R1 审 P2）：SQLite 绑定变量默认上限 32766，超长
# input_file_ids 一把梭会炸 OperationalError——在失败样本路径上炸掉的是
# 分级派生本身。500 一批远离上限且单批开销可忽略。
_IN_CLAUSE_CHUNK = 500


def list_files_by_ids(conn: sqlite3.Connection, file_ids: list[str]) -> list[dict[str, Any]]:
    """按 id 列表批量取文件行，**保持入参顺序**；不存在的 id 静默缺位（调用方
    自行对账缺失——会话附件校验/渲染都要求显式处理缺文件，不做兜底伪造）。
    超长列表分批查询（Codex R1 审 P2），语义与单发等价。"""
    if not file_ids:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for i in range(0, len(file_ids), _IN_CLAUSE_CHUNK):
        chunk = file_ids[i : i + _IN_CLAUSE_CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT * FROM files WHERE id IN ({placeholders})", tuple(chunk)
        ).fetchall()
        by_id.update({r["id"]: dict(r) for r in rows})
    return [by_id[fid] for fid in file_ids if fid in by_id]


# ── feedback ───────────────────────────────────────────────────────────

def create_feedback(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str | None,
    agent_version: str | None,
    rating: str,
    category: str,
    message: str | None,
    created_by: str,
) -> dict[str, Any]:
    """插一条任务反馈（任务书 §7.8）。rating/category 枚举由 API 层 Literal 锁定，
    本层不重复校验（与 tasks 层"状态枚举在 statemachine 锁、repos 只执行"同一分层）。
    """
    now = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO feedback
            (task_id, agent_id, agent_version, rating, category, message, created_by, created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (task_id, agent_id, agent_version, rating, category, message, created_by, now),
    )
    row = conn.execute("SELECT * FROM feedback WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def list_feedback(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    """按 created_at 升序返回任务的全部反馈；同刻并列以自增 id 升序稳定去歧
    （id 单调递增与写入顺序一致，排序语义不变，只是消除同一微秒内的不确定序）。
    """
    rows = conn.execute(
        "SELECT * FROM feedback WHERE task_id = ? ORDER BY created_at ASC, id ASC", (task_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── tool_runs ──────────────────────────────────────────────────────────

def _decode_tool_run(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["mock"] = bool(d["mock"])
    _decode_json(d, "input_json", "input", default=None)
    _decode_json(d, "output_json", "output", default=None)
    return d


def record_tool_run(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    tool_id: str,
    tool_version: str,
    mock: bool,
    status: str,
    input_json: dict[str, Any],
    output_json: dict[str, Any] | None = None,
    raw_input_path: str | None = None,
    raw_output_path: str | None = None,
    error_message: str | None = None,
    started_at: str,
    finished_at: str | None = None,
) -> dict[str, Any]:
    cur = conn.execute(
        """
        INSERT INTO tool_runs
            (task_id, tool_id, tool_version, mock, status, input_json, output_json,
             raw_input_path, raw_output_path, error_message, started_at, finished_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, tool_id, tool_version, int(bool(mock)), status,
            json.dumps(input_json, ensure_ascii=False),
            json.dumps(output_json, ensure_ascii=False) if output_json is not None else None,
            raw_input_path, raw_output_path, error_message, started_at, finished_at,
        ),
    )
    row = conn.execute("SELECT * FROM tool_runs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_tool_run(row)


def list_tool_runs(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM tool_runs WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_tool_run(r) for r in rows]


# ── model_calls ────────────────────────────────────────────────────────

def _decode_model_call(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "token_usage_json", "token_usage", default=None)
    return d


def record_model_call(
    conn: sqlite3.Connection,
    *,
    task_id: str | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    model_profile: str,
    model_name: str | None = None,
    status: str,
    request_summary: str | None = None,
    response_summary: str | None = None,
    error_message: str | None = None,
    token_usage_json: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or _now_iso()
    cur = conn.execute(
        """
        INSERT INTO model_calls
            (task_id, conversation_id, agent_id, model_profile, model_name, status,
             request_summary, response_summary, error_message, token_usage_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, conversation_id, agent_id, model_profile, model_name, status,
            request_summary, response_summary, error_message,
            json.dumps(token_usage_json, ensure_ascii=False) if token_usage_json is not None else None,
            created_at,
        ),
    )
    row = conn.execute("SELECT * FROM model_calls WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_model_call(row)


def list_model_calls(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM model_calls WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_model_call(r) for r in rows]


def list_model_calls_for_conversation(
    conn: sqlite3.Connection, conversation_id: str
) -> list[dict[str, Any]]:
    """导引会话的模型调用留痕（ADR-0013：会话路径的 Q5 可追溯性）。"""
    rows = conn.execute(
        "SELECT * FROM model_calls WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    return [_decode_model_call(r) for r in rows]


# ── samples ────────────────────────────────────────────────────────────

def _decode_sample(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "input_json", "input", default=None)
    _decode_json(d, "output_json", "output", default=None)
    if d.get("accepted_by_engineer") is not None:
        d["accepted_by_engineer"] = bool(d["accepted_by_engineer"])
    return d


def record_sample(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    agent_id: str,
    agent_version: str,
    tool_id: str | None = None,
    tool_version: str | None = None,
    case_id: str | None = None,
    input_json: dict[str, Any],
    output_json: dict[str, Any] | None = None,
    raw_input_path: str | None = None,
    raw_output_path: str | None = None,
    validation_status: str | None = None,
    accepted_by_engineer: bool | None = None,
    created_at: str | None = None,
    classification: str,
) -> dict[str, Any]:
    """classification 必填无默认值（ADR-0021 D1/设计审 F4），口径同 create_file。"""
    created_at = created_at or _now_iso()
    accepted_int = None if accepted_by_engineer is None else int(bool(accepted_by_engineer))
    cur = conn.execute(
        """
        INSERT INTO samples
            (task_id, agent_id, agent_version, tool_id, tool_version, case_id,
             input_json, output_json, raw_input_path, raw_output_path,
             validation_status, accepted_by_engineer, created_at, classification)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id, agent_id, agent_version, tool_id, tool_version, case_id,
            json.dumps(input_json, ensure_ascii=False),
            json.dumps(output_json, ensure_ascii=False) if output_json is not None else None,
            raw_input_path, raw_output_path, validation_status, accepted_int, created_at,
            classification,
        ),
    )
    row = conn.execute("SELECT * FROM samples WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _decode_sample(row)


def get_sample(conn: sqlite3.Connection, sample_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
    return _decode_sample(row) if row is not None else None


def list_samples(conn: sqlite3.Connection, task_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM samples WHERE task_id = ? ORDER BY id ASC", (task_id,)
    ).fetchall()
    return [_decode_sample(r) for r in rows]


def set_sample_review_outcome(
    conn: sqlite3.Connection, task_id: str, accepted: bool
) -> int:
    """人工放行/拒绝时回填该任务全部样本的 accepted_by_engineer 标签。

    requires_human_review 型 Agent 的样本在执行阶段落库时 accepted_by_engineer
    留 NULL（结果未定），直到人工审核动作发生：approve→1、reject→0。这样下游
    eval/复用管道能按「工程师确认」筛样本，而不会把待审/被拒草案混入已认可数据。
    返回被回填的样本行数（无样本返回 0，不报错）。
    """
    accepted_int = int(bool(accepted))
    cur = conn.execute(
        "UPDATE samples SET accepted_by_engineer = ? WHERE task_id = ?",
        (accepted_int, task_id),
    )
    return cur.rowcount


# ── conversations（M6 导引 Agent，interactive 会话运行时，ADR-0012）──────

def _decode_conversation(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "recommendation_json", "recommendation", default=None)
    return d


def _decode_message(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d.pop("id", None)  # 自增主键仅内部排序用，对外不暴露
    _decode_json(d, "recommendation_json", "recommendation", default=None)
    _decode_json(d, "file_ids", "file_ids", default=[])
    return d


def create_conversation(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    agent_id: str,
    created_by: str,
    created_by_username: str,
) -> dict[str, Any]:
    """建会话：初始态 active，无推荐（recommendation 留 NULL 待对话产出）。

    ``created_by`` 是展示名；``created_by_username`` 是 P2.3 稳定 owner。运行时
    新建必须携带非空认证 username；legacy NULL 只能作为迁移前已经存在的事实，
    不得再经当前仓储入口制造。本仓储层不提供 owner 更新函数：非 NULL owner
    另由 DB trigger 锁死不可变。
    """
    if not isinstance(created_by_username, str) or not created_by_username.strip():
        raise ValueError("created_by_username must be a non-blank string")
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO conversations
            (id, agent_id, status, created_by, created_by_username,
             recommendation_json, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            conversation_id,
            agent_id,
            "active",
            created_by,
            created_by_username,
            None,
            now,
            now,
        ),
    )
    return get_conversation(conn, conversation_id)  # type: ignore[return-value]


def get_conversation(conn: sqlite3.Connection, conversation_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    return _decode_conversation(row) if row is not None else None


def get_conversation_for_owner(
    conn: sqlite3.Connection, conversation_id: str, created_by_username: str
) -> dict[str, Any] | None:
    """按 id + exact username 取会话；foreign 与 legacy NULL 都返回 None。

    这是所有普通用户 conversation_id 引用的单一仓储判据。刻意不用
    ``created_by``（display_name 可撞名），也不为 NULL 猜测/回填 owner。
    """
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ? AND created_by_username = ?",
        (conversation_id, created_by_username),
    ).fetchone()
    return _decode_conversation(row) if row is not None else None


def list_conversations(
    conn: sqlite3.Connection,
    *,
    created_by_username: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """列当前 exact username 的会话；无“不过滤”普通用户路径。

    ``created_by_username = ?`` 天然排除 legacy NULL。调用者不能用 display_name
    或客户端 owner 参数扩张结果集。
    """
    rows = conn.execute(
        "SELECT * FROM conversations WHERE created_by_username = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        (created_by_username, limit, offset),
    ).fetchall()
    return [_decode_conversation(r) for r in rows]


def append_message(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    role: str,
    content: str,
    recommendation: dict[str, Any] | None = None,
    file_ids: list[str] | None = None,
) -> dict[str, Any]:
    """追加一条会话消息（role∈user|assistant），并顺带把会话 updated_at 推进。

    recommendation 仅 assistant 轮可能非空（导引提议的预填任务草案）——原样存这一
    轮的推荐快照，便于回看「哪一轮给出了推荐」。
    file_ids 仅 user 轮可能非空（M7 会话附件）：存 File Service 的文件 id 列表，
    附件内容本身不进消息文本（渲染是运行时按窗口预算做的事，见 attachments.py）。
    """
    now = _now_iso()
    rec_json = json.dumps(recommendation, ensure_ascii=False) if recommendation is not None else None
    message_id = f"msg_{uuid.uuid4().hex}"
    cur = conn.execute(
        """
        INSERT INTO conversation_messages
            (message_id, conversation_id, role, content,
             recommendation_json, file_ids, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            message_id,
            conversation_id,
            role,
            content,
            rec_json,
            json.dumps(file_ids or [], ensure_ascii=False),
            now,
        ),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
    )
    row = conn.execute(
        "SELECT * FROM conversation_messages WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _decode_message(row)


def list_messages(conn: sqlite3.Connection, conversation_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY id ASC",
        (conversation_id,),
    ).fetchall()
    return [_decode_message(r) for r in rows]


def get_message_by_public_id(
    conn: sqlite3.Connection, conversation_id: str, message_id: str
) -> dict[str, Any] | None:
    """按 conversation + public message id 精确取消息，路径错配统一不可见。"""
    row = conn.execute(
        "SELECT * FROM conversation_messages "
        "WHERE conversation_id = ? AND message_id = ?",
        (conversation_id, message_id),
    ).fetchone()
    return _decode_message(row) if row is not None else None


def count_messages(conn: sqlite3.Connection, conversation_id: str) -> int:
    """会话消息计数——post_message 乐观并发检查用（ADR-0013）。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    return int(row[0])


# ── structured conversation questions（P2.3）────────────────────────

def _question_timestamp(
    value: str | datetime | None, *, field: str
) -> tuple[str, datetime]:
    """Validate an aware ISO timestamp and return canonical fixed-microsecond UTC."""
    if value is None:
        value = _now_iso()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parseable = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(parseable)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO 8601 timestamp") from exc
    else:
        raise ValueError(f"{field} must be an ISO 8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds"), utc


def _question_text(
    value: Any, *, field: str, maximum: int, nullable: bool = False
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"invalid question {field}")
    return value


def _normalize_question_spec(question_spec: dict[str, Any]) -> dict[str, Any]:
    """Freeze the parser output without relying on SQLite JSON1 validation."""
    if not isinstance(question_spec, dict):
        raise ValueError("question_spec must be an object")
    allowed = {"kind", "prompt", "description", "options"}
    if set(question_spec) - allowed or not {"kind", "prompt"} <= set(question_spec):
        raise ValueError("invalid question spec fields")

    kind = question_spec["kind"]
    if kind not in ("single_choice", "free_text"):
        raise ValueError("invalid question kind")
    prompt = _question_text(question_spec["prompt"], field="prompt", maximum=500)
    description = _question_text(
        question_spec.get("description"),
        field="description",
        maximum=1000,
        nullable=True,
    )
    raw_options = question_spec.get("options", [])
    if not isinstance(raw_options, list):
        raise ValueError("question options must be an array")
    if kind == "single_choice" and not 2 <= len(raw_options) <= 6:
        raise ValueError("single-choice questions require 2-6 frozen options")
    if kind == "free_text" and raw_options:
        raise ValueError("free-text questions cannot carry options")

    options: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for index, raw_option in enumerate(raw_options, start=1):
        if not isinstance(raw_option, dict):
            raise ValueError("question option must be an object")
        if set(raw_option) - {"id", "label", "description"}:
            raise ValueError("invalid question option fields")
        expected_id = f"option_{index}"
        if raw_option.get("id") != expected_id:
            raise ValueError("question option ids must be deterministic")
        label = _question_text(raw_option.get("label"), field="option label", maximum=200)
        label_key = label.strip().casefold()
        if label_key in seen_labels:
            raise ValueError("question option labels must be unique")
        seen_labels.add(label_key)
        option_description = _question_text(
            raw_option.get("description"),
            field="option description",
            maximum=500,
            nullable=True,
        )
        options.append(
            {
                "id": expected_id,
                "label": label,
                "description": option_description,
            }
        )
    return {
        "kind": kind,
        "prompt": prompt,
        "description": description,
        "options": options,
    }


def validate_question_answer(
    question: dict[str, Any], answer: dict[str, Any]
) -> dict[str, Any]:
    """Validate an answer against the exact frozen option set and return a copy."""
    if not isinstance(answer, dict):
        raise ValueError("question answer must be an object")
    answer_kind = answer.get("kind")
    if answer_kind == "option":
        if set(answer) != {"kind", "option_id"}:
            raise ValueError("invalid option answer fields")
        option_id = answer.get("option_id")
        frozen_ids = {
            option.get("id")
            for option in question.get("options", [])
            if isinstance(option, dict)
        }
        if question.get("kind") != "single_choice" or option_id not in frozen_ids:
            raise ValueError("answer option is not in the frozen question")
        return {"kind": "option", "option_id": option_id}
    if answer_kind == "text":
        if set(answer) != {"kind", "text"}:
            raise ValueError("invalid text answer fields")
        text = answer.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("invalid text answer")
        if question.get("kind") not in ("single_choice", "free_text"):
            raise ValueError("question does not accept text")
        return {"kind": "text", "text": text}
    raise ValueError("invalid question answer kind")


def _begin_question_write(conn: sqlite3.Connection) -> str | None:
    """Acquire a write lock, or isolate this primitive inside a caller transaction."""
    if conn.in_transaction:
        savepoint = f"question_{uuid.uuid4().hex}"
        conn.execute(f"SAVEPOINT {savepoint}")
        return savepoint
    conn.execute("BEGIN IMMEDIATE")
    return None


def _commit_question_write(conn: sqlite3.Connection, savepoint: str | None) -> None:
    if savepoint is None:
        conn.execute("COMMIT")
    else:
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")


def _rollback_question_write(conn: sqlite3.Connection, savepoint: str | None) -> None:
    if savepoint is None:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        return
    conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
    conn.execute(f"RELEASE SAVEPOINT {savepoint}")


def _project_question(
    row: sqlite3.Row, *, now: str | datetime | None = None
) -> dict[str, Any]:
    now_iso, now_utc = _question_timestamp(now, field="now")
    del now_iso  # only the exact instant is needed for the derived status
    created_iso, _ = _question_timestamp(row["created_at"], field="created_at")
    expires_iso, expires_utc = _question_timestamp(row["expires_at"], field="expires_at")
    options = json.loads(row["options_json"])
    closed_reason = row["closed_reason"]

    answer_projection: dict[str, Any] | None = None
    if closed_reason == "answered":
        payload = json.loads(row["answer_json"])
        closed_iso, _ = _question_timestamp(row["closed_at"], field="closed_at")
        # There is intentionally no second answered_at column: closed_at is the
        # immutable resolution instant and is projected as public answered_at.
        answer_projection = {
            "schema_version": "conversation-answer/v1",
            "question_id": row["id"],
            "question_revision": row["revision"],
            "submission_id": row["submission_id"],
            "payload": payload,
            "answered_by_username": row["answered_by_username"],
            "answered_at": closed_iso,
            "answer_message_id": row["answer_message_id"],
            "response_message_id": row["response_message_id"],
        }
        status = "answered"
        closed_at = closed_iso
    elif closed_reason in ("expired", "superseded"):
        status = closed_reason
        closed_at, _ = _question_timestamp(row["closed_at"], field="closed_at")
    elif now_utc >= expires_utc:
        # Natural expiry is projected without a mutable persisted status. Until
        # the next write closes it, expires_at is also the truthful close instant.
        status = "expired"
        closed_at = expires_iso
    else:
        status = "pending"
        closed_at = None

    return {
        "schema_version": "conversation-question/v1",
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "prompt_message_id": row["prompt_message_id"],
        "revision": row["revision"],
        "kind": row["kind"],
        "prompt": row["prompt"],
        "description": row["description"],
        "options": options,
        "asked_to_username": row["asked_to_username"],
        "status": status,
        "created_at": created_iso,
        "expires_at": expires_iso,
        "answer": answer_projection,
        "closed_at": closed_at,
    }


def get_question(
    conn: sqlite3.Connection,
    question_id: str,
    *,
    conversation_id: str | None = None,
    asked_to_username: str | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any] | None:
    clauses = ["id = ?"]
    params: list[Any] = [question_id]
    if conversation_id is not None:
        clauses.append("conversation_id = ?")
        params.append(conversation_id)
    if asked_to_username is not None:
        clauses.append("asked_to_username = ?")
        params.append(asked_to_username)
    row = conn.execute(
        f"SELECT * FROM conversation_questions WHERE {' AND '.join(clauses)}",
        params,
    ).fetchone()
    return _project_question(row, now=now) if row is not None else None


def list_questions(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    now: str | datetime | None = None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM conversation_questions WHERE conversation_id = ? "
        "ORDER BY created_at ASC, id ASC",
        (conversation_id,),
    ).fetchall()
    return [_project_question(row, now=now) for row in rows]


def get_unresolved_question(
    conn: sqlite3.Connection,
    conversation_id: str,
    asked_to_username: str,
    *,
    now: str | datetime | None = None,
) -> dict[str, Any] | None:
    """Return the persisted unresolved row; projection may already be expired."""
    row = conn.execute(
        "SELECT * FROM conversation_questions "
        "WHERE conversation_id = ? AND asked_to_username = ? "
        "AND closed_reason IS NULL ORDER BY created_at DESC, id DESC LIMIT 1",
        (conversation_id, asked_to_username),
    ).fetchone()
    return _project_question(row, now=now) if row is not None else None


def _close_unresolved_question_rows(
    conn: sqlite3.Connection,
    conversation_id: str,
    asked_to_username: str,
    *,
    now_iso: str,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM conversation_questions "
        "WHERE conversation_id = ? AND asked_to_username = ? "
        "AND closed_reason IS NULL ORDER BY created_at ASC, id ASC",
        (conversation_id, asked_to_username),
    ).fetchall()
    closed_ids: list[str] = []
    for row in rows:
        expires_iso, expires_utc = _question_timestamp(
            row["expires_at"], field="expires_at"
        )
        reason = "expired" if now_utc >= expires_utc else "superseded"
        closed_at = expires_iso if reason == "expired" else now_iso
        cur = conn.execute(
            "UPDATE conversation_questions SET closed_reason = ?, closed_at = ? "
            "WHERE id = ? AND closed_reason IS NULL",
            (reason, closed_at, row["id"]),
        )
        if cur.rowcount == 1:
            closed_ids.append(row["id"])
    projections: list[dict[str, Any]] = []
    for question_id in closed_ids:
        row = conn.execute(
            "SELECT * FROM conversation_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if row is not None:
            projections.append(_project_question(row, now=now_iso))
    return projections


def close_unresolved_questions(
    conn: sqlite3.Connection,
    conversation_id: str,
    asked_to_username: str,
    *,
    now: str | datetime,
) -> list[dict[str, Any]]:
    """Atomically close the prior unresolved Question at its truthful instant."""
    now_iso, now_utc = _question_timestamp(now, field="now")
    savepoint = _begin_question_write(conn)
    try:
        result = _close_unresolved_question_rows(
            conn,
            conversation_id,
            asked_to_username,
            now_iso=now_iso,
            now_utc=now_utc,
        )
        _commit_question_write(conn, savepoint)
        return result
    except Exception:
        _rollback_question_write(conn, savepoint)
        raise


def create_question(
    conn: sqlite3.Connection,
    *,
    question_id: str,
    conversation_id: str,
    prompt_message_id: str,
    asked_to_username: str,
    question_spec: dict[str, Any],
    created_at: str | datetime,
    expires_at: str | datetime,
) -> dict[str, Any]:
    """Close any prior unresolved Question and atomically insert revision 1."""
    if not _QUESTION_ID_RE.fullmatch(question_id):
        raise ValueError("invalid public question id")
    if not _MESSAGE_ID_RE.fullmatch(prompt_message_id):
        raise ValueError("invalid public prompt message id")
    if (
        not isinstance(asked_to_username, str)
        or not asked_to_username.strip()
        or len(asked_to_username) > 100
    ):
        raise ValueError("invalid asked_to_username")
    spec = _normalize_question_spec(question_spec)
    created_iso, created_utc = _question_timestamp(created_at, field="created_at")
    expires_iso, expires_utc = _question_timestamp(expires_at, field="expires_at")
    if expires_utc - created_utc != timedelta(hours=24):
        raise ValueError("question TTL must be exactly 24 hours")
    options_json = json.dumps(
        spec["options"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    savepoint = _begin_question_write(conn)
    try:
        _close_unresolved_question_rows(
            conn,
            conversation_id,
            asked_to_username,
            now_iso=created_iso,
            now_utc=created_utc,
        )
        conn.execute(
            """
            INSERT INTO conversation_questions
                (id, conversation_id, prompt_message_id, asked_to_username,
                 revision, kind, prompt, description, options_json,
                 created_at, expires_at, closed_reason, closed_at,
                 submission_id, answer_json, answered_by_username,
                 answer_message_id, response_message_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                question_id,
                conversation_id,
                prompt_message_id,
                asked_to_username,
                1,
                spec["kind"],
                spec["prompt"],
                spec["description"],
                options_json,
                created_iso,
                expires_iso,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )
        row = conn.execute(
            "SELECT * FROM conversation_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - INSERT success makes this impossible
            raise RuntimeError("question insert was not observable")
        result = _project_question(row, now=created_iso)
        _commit_question_write(conn, savepoint)
        return result
    except Exception:
        _rollback_question_write(conn, savepoint)
        raise


def resolve_question(
    conn: sqlite3.Connection,
    *,
    question_id: str,
    conversation_id: str,
    asked_to_username: str,
    submission_id: str,
    answer: dict[str, Any],
    answered_at: str | datetime,
    answer_message_id: str,
    response_message_id: str,
) -> dict[str, Any] | None:
    """CAS the first complete answer; exact same submission+payload replays."""
    answered_iso, answered_utc = _question_timestamp(answered_at, field="answered_at")
    savepoint = _begin_question_write(conn)
    try:
        row = conn.execute(
            "SELECT * FROM conversation_questions "
            "WHERE id = ? AND conversation_id = ? AND asked_to_username = ?",
            (question_id, conversation_id, asked_to_username),
        ).fetchone()
        if row is None:
            _commit_question_write(conn, savepoint)
            return None

        question = _project_question(row, now=answered_iso)
        if row["closed_reason"] == "answered":
            normalized_answer = validate_question_answer(question, answer)
            existing_answer = json.loads(row["answer_json"])
            result = (
                question
                if row["submission_id"] == submission_id
                and existing_answer == normalized_answer
                else None
            )
            _commit_question_write(conn, savepoint)
            return result
        if row["closed_reason"] is not None:
            _commit_question_write(conn, savepoint)
            return None

        _, expires_utc = _question_timestamp(row["expires_at"], field="expires_at")
        if answered_utc >= expires_utc:
            conn.execute(
                "UPDATE conversation_questions "
                "SET closed_reason = 'expired', closed_at = expires_at "
                "WHERE id = ? AND closed_reason IS NULL",
                (question_id,),
            )
            _commit_question_write(conn, savepoint)
            return None

        normalized_answer = validate_question_answer(question, answer)
        if (
            not isinstance(submission_id, str)
            or not 8 <= len(submission_id) <= 128
        ):
            raise ValueError("invalid submission_id")
        if not _MESSAGE_ID_RE.fullmatch(answer_message_id):
            raise ValueError("invalid answer_message_id")
        if not _MESSAGE_ID_RE.fullmatch(response_message_id):
            raise ValueError("invalid response_message_id")
        answer_json = json.dumps(
            normalized_answer,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        cur = conn.execute(
            """
            UPDATE conversation_questions
            SET closed_reason = 'answered', closed_at = ?, submission_id = ?,
                answer_json = ?, answered_by_username = ?,
                answer_message_id = ?, response_message_id = ?
            WHERE id = ? AND conversation_id = ? AND asked_to_username = ?
              AND closed_reason IS NULL
            """,
            (
                answered_iso,
                submission_id,
                answer_json,
                asked_to_username,
                answer_message_id,
                response_message_id,
                question_id,
                conversation_id,
                asked_to_username,
            ),
        )
        if cur.rowcount != 1:
            _commit_question_write(conn, savepoint)
            return None
        resolved_row = conn.execute(
            "SELECT * FROM conversation_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if resolved_row is None:  # pragma: no cover - immutable row cannot vanish
            raise RuntimeError("resolved question was not observable")
        result = _project_question(resolved_row, now=answered_iso)
        _commit_question_write(conn, savepoint)
        return result
    except Exception:
        _rollback_question_write(conn, savepoint)
        raise


def set_conversation_recommendation(
    conn: sqlite3.Connection,
    conversation_id: str,
    recommendation: dict[str, Any] | None,
    *,
    status: str | None = None,
) -> dict[str, Any]:
    """回填会话的最新推荐（预填任务草案），可选同时推进 status（如 concluded）。

    recommendation 是「导引当前给出的预填草案」快照——会话可多轮刷新推荐，
    以最后一次为准；人确认提交任务的动作在 tasks 端点，与此处解耦。
    """
    now = _now_iso()
    rec_json = json.dumps(recommendation, ensure_ascii=False) if recommendation is not None else None
    if status is not None:
        conn.execute(
            "UPDATE conversations SET recommendation_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (rec_json, status, now, conversation_id),
        )
    else:
        conn.execute(
            "UPDATE conversations SET recommendation_json = ?, updated_at = ? WHERE id = ?",
            (rec_json, now, conversation_id),
        )
    return get_conversation(conn, conversation_id)  # type: ignore[return-value]


def set_conversation_status(
    conn: sqlite3.Connection, conversation_id: str, status: str
) -> dict[str, Any]:
    now = _now_iso()
    conn.execute(
        "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, conversation_id),
    )
    return get_conversation(conn, conversation_id)  # type: ignore[return-value]


# ── eval_runs / promotions（M10 治理闭环，ADR-0018） ────────────────────

def _decode_eval_run(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    _decode_json(d, "case_results_json", "case_results", default=[])
    _decode_json(d, "draft_cases_json", "draft_cases", default=[])
    return d


def create_eval_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    agent_id: str,
    agent_version: str,
    triggered_by: str,
    status: str = "running",
    snapshot_handle: str | None = None,
) -> dict[str, Any]:
    """建 eval_run 行。status 默认 'running'（既有同步路径向后兼容）；异步队列
    入队传 status='queued'（T1，GH #2）。started_at 记建行时刻——同步路径下建行
    即开跑二者同一瞬间；异步队列下 started_at 语义即「入队时刻」，worker 认领
    （queued→running）不另立时间戳（配额门与状态机只看 status，不看时间戳）。

    INSERT 与回查快照包在单个 BEGIN IMMEDIATE 事务里（P2，Codex R1 审）：连接为
    isolation_level=None（autocommit），裸 INSERT 即刻可见，live worker 可能在下一条
    get_eval_run 之前就认领/收口本行，令本应返回 queued 的入队响应变成 running/终态
    （违反 POST 202+queued 契约与 e2e 断言）。写锁内 INSERT 再回查，worker 的 claim
    （同样 BEGIN IMMEDIATE）被写锁挡到 COMMIT 之后，快照必是入队瞬时态。"""
    now = _now_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            INSERT INTO eval_runs
                (id, agent_id, agent_version, triggered_by, status, started_at, snapshot_handle)
            VALUES (?,?,?,?,?,?,?)
            """,
            (run_id, agent_id, agent_version, triggered_by, status, now, snapshot_handle),
        )
        snapshot = get_eval_run(conn, run_id)
        conn.execute("COMMIT")
        return snapshot  # type: ignore[return-value]
    except Exception:
        conn.execute("ROLLBACK")
        raise


def insert_eval_snapshot(
    conn: sqlite3.Connection,
    *,
    handle: str,
    agent_id: str,
    agent_version: str,
    eval_cases_digest: str | None,
    content_json: str,
) -> None:
    """写入不可变评测快照（T2/#5）。handle=内容 sha256（内容派生）。**insert-once**：
    `INSERT OR IGNORE`——handle 为 PK 且内容派生，同 handle 必同内容，二次写入静默忽略、
    绝不覆盖（M12 monitor 教训：不可变行绝不无条件 UPDATE/REPLACE）。多 run 引用同一
    冻结内容自然去重到一行。"""
    conn.execute(
        """
        INSERT OR IGNORE INTO eval_snapshots
            (handle, agent_id, agent_version, eval_cases_digest, content_json, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (handle, agent_id, agent_version, eval_cases_digest, content_json, _now_iso()),
    )


def get_eval_snapshot(conn: sqlite3.Connection, handle: str) -> dict[str, Any] | None:
    """取快照行（含 content_json 原文）。不存在返回 None。"""
    row = conn.execute(
        "SELECT * FROM eval_snapshots WHERE handle = ?", (handle,)
    ).fetchone()
    return dict(row) if row is not None else None


def claim_next_queued_eval_run(
    conn: sqlite3.Connection, *, quota: int
) -> dict[str, Any] | None:
    """配额门 + 认领的原子原语（T1 异步评测队列，GH #2）。

    单个 BEGIN IMMEDIATE 写锁内完成「统计 running → 配额判断 → 挑最旧 queued →
    CAS 置 running」：running 已达配额则返回 None（超配额排队不拒，非 409）；否则
    FIFO（started_at, id）挑一条 queued，`WHERE id=? AND status='queued'` CAS 翻
    running 并回该行。配额判断与 CAS 同锁原子——即使多 poller 也不会超额放行。
    worker 单实例锁保证同库唯一 poller，此原子性是纵深防御。

    只读预检（P2，Codex R1 复审）：无 queued 时 worker 每 poll 都 BEGIN IMMEDIATE 抢
    SQLite 唯一写锁只为发现无活可干，空转期阻塞 JobRunner/API 的无关写。先用 WAL 下不
    上写锁的只读 SELECT 探一眼，无 queued 直接返回 None（不进写事务）。TOCTOU：预检后
    才入队的 run 顺延一个 poll 周期被认领——非正确性问题（配额门仍在写锁内权威判定），
    idx_eval_runs_status_started 支撑这条与内部 FIFO 查询避免全表扫。
    """
    if conn.execute(
        "SELECT 1 FROM eval_runs WHERE status = 'queued' LIMIT 1"
    ).fetchone() is None:
        return None
    conn.execute("BEGIN IMMEDIATE")
    try:
        running = conn.execute(
            "SELECT COUNT(*) FROM eval_runs WHERE status = 'running'"
        ).fetchone()[0]
        if running >= quota:
            conn.execute("COMMIT")
            return None
        row = conn.execute(
            "SELECT id FROM eval_runs WHERE status = 'queued' "
            "ORDER BY started_at ASC, id ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        run_id = row["id"]
        cur = conn.execute(
            "UPDATE eval_runs SET status = 'running' WHERE id = ? AND status = 'queued'",
            (run_id,),
        )
        if cur.rowcount != 1:
            # 理论不可能（同锁内独占）；防御性 fail-closed：不认领畸形态
            conn.execute("ROLLBACK")
            return None
        claimed = get_eval_run(conn, run_id)
        conn.execute("COMMIT")
        return claimed
    except Exception:
        conn.execute("ROLLBACK")
        raise


def finish_eval_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    status: str,
    total: int,
    passed: int,
    failed: int,
    skipped: int,
    case_results: list[dict[str, Any]],
    draft_cases: list[dict[str, Any]],
    eval_cases_digest: str | None,
) -> dict[str, Any]:
    now = _now_iso()
    conn.execute(
        """
        UPDATE eval_runs
           SET status = ?, finished_at = ?, total = ?, passed = ?, failed = ?, skipped = ?,
               case_results_json = ?, draft_cases_json = ?, eval_cases_digest = ?
         WHERE id = ?
        """,
        (
            status, now, total, passed, failed, skipped,
            json.dumps(case_results, ensure_ascii=False),
            json.dumps(draft_cases, ensure_ascii=False),
            eval_cases_digest,
            run_id,
        ),
    )
    return get_eval_run(conn, run_id)  # type: ignore[return-value]


def get_eval_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
    return _decode_eval_run(row) if row is not None else None


def list_eval_runs(
    conn: sqlite3.Connection, agent_id: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM eval_runs WHERE agent_id = ? ORDER BY started_at DESC, id DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    return [_decode_eval_run(r) for r in rows]


def record_promotion(
    conn: sqlite3.Connection,
    *,
    agent_id: str,
    agent_version: str,
    from_maturity: str,
    to_maturity: str,
    eval_run_id: str,
    checks: dict[str, Any],
    confirmations: dict[str, Any],
    confirmed_by: str,
) -> dict[str, Any]:
    now = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO promotions
            (agent_id, agent_version, from_maturity, to_maturity, eval_run_id,
             checks_json, confirmations_json, confirmed_by, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            agent_id, agent_version, from_maturity, to_maturity, eval_run_id,
            json.dumps(checks, ensure_ascii=False),
            json.dumps(confirmations, ensure_ascii=False),
            confirmed_by, now,
        ),
    )
    row = conn.execute("SELECT * FROM promotions WHERE id = ?", (cur.lastrowid,)).fetchone()
    d = dict(row)
    _decode_json(d, "checks_json", "checks", default={})
    _decode_json(d, "confirmations_json", "confirmations", default={})
    return d


def list_promotions(conn: sqlite3.Connection, agent_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM promotions WHERE agent_id = ? ORDER BY id DESC", (agent_id,)
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        _decode_json(d, "checks_json", "checks", default={})
        _decode_json(d, "confirmations_json", "confirmations", default={})
        out.append(d)
    return out


def list_promotions_all(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """全局最近晋升（批B /today Agent 动态）。与单 agent 版同解码，最近优先。
    排序按 created_at 主键（Codex R2-P2 verbatim）：恢复/回填的行可能乱插入序，
    自增 id 只是并列决胜，「最近」以时间戳为准。"""
    rows = conn.execute(
        "SELECT * FROM promotions ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        _decode_json(d, "checks_json", "checks", default={})
        _decode_json(d, "confirmations_json", "confirmations", default={})
        out.append(d)
    return out


# ── worker heartbeats（迁移 #7，ADR-0021/Codex R1 审 P1）────────────────

def beat_worker_heartbeat(conn: sqlite3.Connection, *, generation: str, detail: str | None = None) -> None:
    """worker 心跳 upsert：单实例锁保证同库唯一 worker，固定主键单行不增长。

    generation 每次心跳覆写——worker 升级重启后旧代际字符串不会残留误导
    部署自检门；started_at 保留首次值供诊断。
    """
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO worker_heartbeats (worker_id, generation, detail, started_at, last_beat_at)
        VALUES ('default', ?, ?, ?, ?)
        ON CONFLICT(worker_id) DO UPDATE SET
            generation = excluded.generation,
            detail = excluded.detail,
            last_beat_at = excluded.last_beat_at
        """,
        (generation, detail, now, now),
    )


def get_worker_heartbeat(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM worker_heartbeats WHERE worker_id = 'default'"
    ).fetchone()
    return dict(row) if row is not None else None


# ── 专家团队模板（批八/ADR-0031，迁移 #13）─────────────────────────────────


def create_team(
    conn: sqlite3.Connection,
    *,
    team_id: str,
    name: str,
    owner_user: str,
    members: list[dict[str, Any]],
    goal_template: str | None = None,
    created_from_conversation_id: str | None = None,
) -> dict[str, Any]:
    """建团队蓝本 + 席位（单事务由调用方持有；本函数只执行 INSERT，不自 BEGIN——
    与 create_task 同口径，事务边界归 API 层）。members 每项 =
    {agent_id, agent_version_at_save, role, seq, after(list[int] 前序 seq)}；
    合法性（agent 在场/非 interactive/after 仅引更小 seq/≤5 席）由 API 层对账后
    传入，此处忠实落库。"""
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO teams (id, name, goal_template, owner_user,
                           created_from_conversation_id, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (team_id, name, goal_template, owner_user, created_from_conversation_id, now),
    )
    for m in members:
        conn.execute(
            """
            INSERT INTO team_members (team_id, agent_id, agent_version_at_save,
                                      role, seq, after_json)
            VALUES (?,?,?,?,?,?)
            """,
            (
                team_id,
                m["agent_id"],
                m["agent_version_at_save"],
                m.get("role"),
                m["seq"],
                json.dumps(m.get("after") or [], ensure_ascii=False),
            ),
        )
    return get_team(conn, team_id)  # type: ignore[return-value]


def get_team(conn: sqlite3.Connection, team_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if row is None:
        return None
    team = dict(row)
    team["members"] = list_team_members(conn, team_id)
    return team


def list_team_members(conn: sqlite3.Connection, team_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM team_members WHERE team_id = ? ORDER BY seq", (team_id,)
    ).fetchall()
    members: list[dict[str, Any]] = []
    for r in rows:
        m = dict(r)
        raw_after = m.pop("after_json", None)
        try:
            decoded = json.loads(raw_after) if raw_after else []
        except json.JSONDecodeError:
            decoded = []
        m["after"] = decoded if isinstance(decoded, list) else []
        members.append(m)
    return members


def list_teams(
    conn: sqlite3.Connection,
    *,
    owner_user: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if owner_user is not None:
        clauses.append("owner_user = ?")
        params.append(owner_user)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = conn.execute(
        f"SELECT * FROM teams {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        params,
    ).fetchall()
    teams = [dict(r) for r in rows]
    for t in teams:
        t["members"] = list_team_members(conn, t["id"])
    return teams
