"""任务分级内容门（ADR-0025）——sensitive 任务一切派生内容出场面的**唯一遮蔽 chokepoint**。

分级取自执行期落库的不可变 `tasks.data_classification`（read 期**只读该列不重派生**，
抗工具卸载/降级的配置漂移，Codex R1-B）。本模块被 api/tasks.py 与 api/conversations.py
共用——**所有**返回任务派生数据的端点必须过此门，绝不「只堵文件、漏堵详情」（Codex
R1-A 的 whack-a-mole 教训：同一批外部数据经多个端点/多个字段出场，只堵一处=假绿）。

判定一律 is/== 语义，绝不 truthiness（安全 gate 铁律）。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Sequence

# 各详情行「内容承载键」（repos 解码后的字段名）。**含错误文本列**——Codex R1-A：
# sensitive 工具把外部 grounding_failures 写进 error_message / event.message，那是任务
# 派生内容不是元数据，必须一并遮蔽。
TOOL_RUN_CONTENT_KEYS = ("input", "output", "raw_input_path", "raw_output_path", "error_message")
MODEL_CALL_CONTENT_KEYS = ("request_summary", "response_summary", "error_message")
SAMPLE_CONTENT_KEYS = ("input", "output", "raw_input_path", "raw_output_path")
EVENT_CONTENT_KEYS = ("message", "payload")
# 任务行本身承载内容的字段：error_message（workflow/tool 错误经此列，runtime.set_task_status）。
TASK_ROW_CONTENT_KEYS = ("error_message",)

# NULL 兜底判定用：这些表任一有本任务的行，即代表已有需保护的派生内容落库。
# **刻意不含 task_events**（Codex R0 P1-4 复核后的正确口径）：外部数据事件是**内容行的
# 派生轨迹**而非独立内容源——tool_failed↔tool_runs 行、model_call↔model_calls 行、
# workflow 错误↔tasks.error_message，三者本 tuple/错误列已覆盖，故承载外部数据的事件必有
# 对应内容行被查到。反之 feedback_received / 创建期等**良性事件**会落在未执行(NULL)任务上，
# 若把「有任一事件」当「有内容」→ 误封良性 NULL 任务（内部任务的用户反馈被遮），实测打回
# 4 例（test_feedback/test_m8）。故兜底只认权威内容行，不认派生事件轨迹。
_CONTENT_TABLES = ("tool_runs", "model_calls", "samples", "files")


def is_sensitive_task(conn: sqlite3.Connection, task: dict[str, Any]) -> bool:
    """任务是否 sensitive——读执行期落库的不可变 `data_classification`，绝不重派生。

    - `'sensitive'` → True（封）
    - `'internal'`  → False（放）
    - `NULL`（存量未回填 / 部署代际竞态 / 未跑任务）→ **fail-closed 兜底**：该任务已有
      任何派生内容行（tool_runs/model_calls/samples/files）或非空 error_message 即封，
      否则放。兜底**不看工具注册表**（不重派生），只看「有没有已落库的内容需要保护」——
      故不受工具卸载漂移影响，与 D1 的不重派生原则一致。
    """
    dc = task.get("data_classification")
    if dc == "sensitive":
        return True
    if dc == "internal":
        return False
    return _has_protectable_content(conn, task)


def _has_protectable_content(conn: sqlite3.Connection, task: dict[str, Any]) -> bool:
    task_id = task.get("id")
    if task_id is None:
        return True  # 无从判定 = fail-closed
    for table in _CONTENT_TABLES:
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE task_id = ? LIMIT 1", (task_id,)
        ).fetchone()
        if row is not None:
            return True
    return task.get("error_message") is not None  # 非 truthiness（安全 gate 铁律，Codex R0 P1-4）


def redact_task_row(task: dict[str, Any]) -> dict[str, Any]:
    """遮蔽任务行的内容承载字段（error_message→None），保留全部元数据。返回新 dict。"""
    out = dict(task)
    for key in TASK_ROW_CONTENT_KEYS:
        if key in out:
            out[key] = None
    out["content_withheld"] = True
    return out


def redact_rows(
    rows: Sequence[dict[str, Any]], content_keys: Sequence[str]
) -> list[dict[str, Any]]:
    """遮蔽详情行序列的内容键→None + `content_withheld` 标记；保留元数据（谁/何时/
    成败/工具版本/token 计数/分级等）。返回新 list（不改原行）。"""
    redacted: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        for key in content_keys:
            if key in out:
                out[key] = None
        out["content_withheld"] = True
        redacted.append(out)
    return redacted


def redact_task_row_if_sensitive(conn: sqlite3.Connection, task: dict[str, Any]) -> dict[str, Any]:
    """便捷组合：sensitive→遮蔽任务行；否则原样返回。列表端点逐行调用。"""
    if is_sensitive_task(conn, task):
        return redact_task_row(task)
    return task


def redact_model_calls_by_task(
    conn: sqlite3.Connection, rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """会话聚合 model_calls 逐行按**归属任务**分级遮蔽（ADR-0025 补漏）。

    `GET /conversations/{id}/model_calls` 跨该会话全部成员任务聚合 model_calls——
    sensitive 任务的 request/response_summary/error_message 承载工具从外部真源读进的
    产出，与 `GET /tasks/{id}/model_calls` 同属工具派生内容出场面，必须一致遮蔽（否则
    正是 R1-A 的 whack-a-mole：只堵任务级端点、漏堵会话聚合端点=假绿泄漏）。

    - 逐行取 `task_id`，按其任务分级判定；**task_id 为 NULL 的会话级编排调用**（导引
      路由官自身的 LLM 摘要，非任一工具产出）不遮蔽——与 D5「只封工具产出不封编排/
      用户提交」边界一致。
    - 归属任务查无（异常）→ **fail-closed 遮蔽**。
    - 同任务分级按 task_id 缓存，避免逐行重查（会话可含多 model_call 同任务）。
    """
    cache: dict[str, bool] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        task_id = row.get("task_id")
        if task_id is None:
            out.append(row)  # 会话级编排调用：非工具派生，放行
            continue
        sensitive = cache.get(task_id)
        if sensitive is None:
            trow = conn.execute(
                "SELECT id, data_classification, error_message FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if trow is None:
                sensitive = True  # 归属任务查无 → fail-closed
            else:
                sensitive = is_sensitive_task(
                    conn,
                    {"id": trow[0], "data_classification": trow[1], "error_message": trow[2]},
                )
            cache[task_id] = sensitive
        out.append(redact_rows([row], MODEL_CALL_CONTENT_KEYS)[0] if sensitive else row)
    return out


# ── 批七 ADR-0030：创建时点密级准入 gate ─────────────────────────────────────
# 与上面的「运行中/出场面遮蔽」正交：本 gate 管「这个 Agent 有没有资格接这批
# 材料」，在任务创建时点判定（四路复用：create_task / tasks:batch / 手建路径
# 同走 create_task / 未来 teams summon）；执行期派生分级与出场遮蔽照旧归
# ADR-0025 各函数，互不越权。

_CLEARANCE_RANK = {"public": 0, "internal": 1, "sensitive": 2}


def derive_input_material_level(
    conn: sqlite3.Connection, input_file_ids: Sequence[str] | None
) -> str:
    """输入材料密级（创建时点）：无文件 → public（不携带任何受控材料）；
    文件记录缺失 → sensitive（出处不可考，宁严勿洗白，与 runtime
    _task_input_classification 同哲学）；全 internal → internal；
    任一非 internal（含未知坏值，allowlist 判定）→ sensitive。"""
    file_ids = list(input_file_ids or [])
    if not file_ids:
        return "public"
    placeholders = ",".join("?" for _ in file_ids)
    rows = conn.execute(
        f"SELECT id, classification FROM files WHERE id IN ({placeholders})",
        file_ids,
    ).fetchall()
    if len(rows) != len(file_ids):
        return "sensitive"
    if all(r[1] == "internal" for r in rows) is True:
        return "internal"
    if all(r[1] in ("internal", "public") for r in rows) is True:
        return "internal"
    return "sensitive"


def agent_clearance_allows(
    conn: sqlite3.Connection, agent: dict[str, Any], input_file_ids: Sequence[str] | None
) -> tuple[bool, str, str]:
    """ADR-0030 判定：max(输入材料密级) ≤ agent.clearance.max_data_classification。

    clearance 整块缺省 = internal（fail-closed 取最严的向后兼容解释——存量包
    默认拿不到 sensitive 材料）。未知坏值上限按 public（最低权限）兜底。
    返回 (allowed, material_level, agent_max)；调用方判定必须 `is True/is False`。
    """
    agent_max = ((agent.get("clearance") or {}).get("max_data_classification")) or "internal"
    material_level = derive_input_material_level(conn, input_file_ids)
    allowed = (
        _CLEARANCE_RANK.get(material_level, 2)
        <= _CLEARANCE_RANK.get(agent_max, 0)
    )
    return allowed, material_level, agent_max
