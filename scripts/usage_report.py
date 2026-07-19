#!/usr/bin/env python3
"""使用遥测报告（试点舰队观测件）：只读汇总平台真实使用情况。

定位：灯塔试点的软件缺口——「谁在用、卡在哪、在哪一步放弃」。
纯只读（sqlite URI mode=ro），纯 stdlib，零内核依赖；对表/列做存在性探测，
结构缺失显式标注「未知」，绝不编 0（B1 纪律：token 凑不出=未知绝不记 0）。

用法：
    python3 scripts/usage_report.py [--db data/flai_os.db] [--days 14] [--json]

退出码：0=报告完成；2=DB 不存在/不可读（fail-closed，不产出空报告假绿）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from backend.app.storage.outcome_schema import (  # noqa: E402
    OUTCOME_SCHEMA_WITNESS_KEYS as _OUTCOME_SCHEMA_WITNESS_KEYS,
)
from backend.app.storage.outcome_schema import (  # noqa: E402
    outcome_schema_witnesses as _outcome_schema_witnesses,
)

DEFAULT_DB = Path(os.environ.get("FLAI_DB_PATH", str(REPO / "data" / "flai_os.db")))
STALL_HOURS = 48


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> object:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _parse_ts(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (
            parsed.replace(tzinfo=dt.timezone.utc)
            if parsed.tzinfo is None
            else parsed.astimezone(dt.timezone.utc)
        )
    except ValueError:
        return None


def build_report(db_path: Path, days: int, now: dt.datetime | None = None) -> dict:
    """汇总使用数据。now 可注入（测试确定性）。"""
    now = now or dt.datetime.now(dt.timezone.utc)
    now = (
        now.replace(tzinfo=dt.timezone.utc)
        if now.tzinfo is None
        else now.astimezone(dt.timezone.utc)
    )
    generated_at = now.isoformat(timespec="seconds")
    # Persisted facts commonly carry microseconds.  Keep the human-facing
    # timestamp compact, but compare against the exact injected/current clock;
    # a seconds-truncated upper bound would wrongly drop facts from the same
    # second that happened before ``now``.
    generated_at_bound = now.isoformat(timespec="microseconds")
    since = (now - dt.timedelta(days=days)).isoformat(timespec="seconds")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # sqlite3 的只读 SELECT 默认可能各自打开/关闭事务；显式 BEGIN 让整份报告
        # 固定在第一次读取建立的同一 WAL snapshot 上，避免同份报告跨时点拼接。
        conn.execute("BEGIN")
        report: dict = {
            "generated_at": generated_at,
            "window_days": days,
            "db": str(db_path),
        }

        # ---- 账户 ----
        if {"username", "is_active"} <= _columns(conn, "users"):
            report["accounts"] = {
                "total": _one(conn, "SELECT COUNT(*) FROM users"),
                "active_flag": _one(conn, "SELECT COUNT(*) FROM users WHERE is_active = 1"),
            }
        else:
            report["accounts"] = "未知（users 表结构不含所需列）"

        # ---- 任务面（origin='user' 才算真实使用；eval 跑批不计） ----
        task_cols = _columns(conn, "tasks")
        if {"status", "created_at", "origin"} <= task_cols:
            base = "FROM tasks WHERE origin = 'user' AND created_at >= ?"
            by_status = {
                r["status"]: r["n"]
                for r in conn.execute(f"SELECT status, COUNT(*) AS n {base} GROUP BY status", (since,))
            }
            tasks: dict = {"created": sum(by_status.values()), "by_status": by_status}

            ident = "created_by_username" if "created_by_username" in task_cols else "created_by"
            tasks["distinct_creators"] = _one(
                conn, f"SELECT COUNT(DISTINCT {ident}) {base} AND {ident} IS NOT NULL", (since,)
            )
            tasks["by_creator"] = {
                str(r["who"]): r["n"]
                for r in conn.execute(
                    f"SELECT {ident} AS who, COUNT(*) AS n {base} AND {ident} IS NOT NULL "
                    "GROUP BY who ORDER BY n DESC LIMIT 10",
                    (since,),
                )
            }
            tasks["by_agent"] = {
                str(r["agent_id"]): r["n"]
                for r in conn.execute(
                    f"SELECT agent_id, COUNT(*) AS n {base} GROUP BY agent_id ORDER BY n DESC LIMIT 10",
                    (since,),
                )
            }

            durations: list[float] = []
            for r in conn.execute(
                f"SELECT created_at, finished_at {base} AND status = 'completed' AND finished_at IS NOT NULL",
                (since,),
            ):
                t0, t1 = _parse_ts(r["created_at"]), _parse_ts(r["finished_at"])
                if t0 and t1 and t1 >= t0:
                    durations.append((t1 - t0).total_seconds())
            durations.sort()
            tasks["completed_median_s"] = round(durations[len(durations) // 2], 1) if durations else "未知（窗口内无已完成任务）"

            stall_cutoff = (now - dt.timedelta(hours=STALL_HOURS)).isoformat(timespec="seconds")
            if "updated_at" in task_cols:
                tasks["stalled_waiting_review"] = _one(
                    conn,
                    "SELECT COUNT(*) FROM tasks WHERE origin = 'user' AND status = 'waiting_review' AND updated_at < ?",
                    (stall_cutoff,),
                )
            report["tasks"] = tasks
        else:
            report["tasks"] = "未知（tasks 表结构不含所需列）"

        # ---- 人签活跃度 ----
        event_cols = _columns(conn, "task_events")
        if (
            {"task_id", "event_type", "created_at"} <= event_cols
            and {"id", "origin"} <= task_cols
        ):
            reviews: dict = {
                "approved": _one(
                    conn,
                    "SELECT COUNT(*) FROM task_events AS event "
                    "JOIN tasks AS task ON task.id = event.task_id "
                    "WHERE task.origin = 'user' "
                    "AND event.event_type = 'review_approved' "
                    "AND event.created_at >= ?",
                    (since,),
                ),
                "rejected": _one(
                    conn,
                    "SELECT COUNT(*) FROM task_events AS event "
                    "JOIN tasks AS task ON task.id = event.task_id "
                    "WHERE task.origin = 'user' "
                    "AND event.event_type = 'review_rejected' "
                    "AND event.created_at >= ?",
                    (since,),
                ),
            }
            decision_cols = _columns(conn, "task_human_decisions")
            if {"task_id", "reason_code", "created_at"} <= decision_cols:
                structured = _one(
                    conn,
                    "SELECT COUNT(*) FROM task_events AS event "
                    "JOIN tasks AS task ON task.id = event.task_id "
                    "JOIN task_human_decisions AS decision "
                    "ON decision.task_id = event.task_id "
                    "WHERE task.origin = 'user' "
                    "AND event.event_type IN ('review_approved', 'review_rejected') "
                    "AND event.created_at >= ?",
                    (since,),
                )
                legacy = _one(
                    conn,
                    "SELECT COUNT(*) FROM task_events AS event "
                    "JOIN tasks AS task ON task.id = event.task_id "
                    "LEFT JOIN task_human_decisions AS decision "
                    "ON decision.task_id = event.task_id "
                    "WHERE task.origin = 'user' "
                    "AND event.event_type IN ('review_approved', 'review_rejected') "
                    "AND event.created_at >= ? "
                    "AND decision.task_id IS NULL",
                    (since,),
                )
                denominator = int(structured or 0) + int(legacy or 0)
                reviews["judgment_coverage"] = {
                    "status": (
                        "measured"
                        if denominator > 0
                        else "unknown_no_review_samples"
                    ),
                    "structured": structured,
                    "legacy_unstructured": legacy,
                    "structured_ratio": (
                        round(int(structured or 0) / denominator, 4)
                        if denominator > 0
                        else "未知（窗口内无具名人签样本）"
                    ),
                    "by_reject_reason": {
                        str(row["reason_code"]): row["n"]
                        for row in conn.execute(
                            "SELECT decision.reason_code, COUNT(*) AS n "
                            "FROM task_human_decisions AS decision "
                            "JOIN tasks AS task ON task.id = decision.task_id "
                            "WHERE task.origin = 'user' "
                            "AND decision.created_at >= ? "
                            "AND decision.reason_code IS NOT NULL "
                            "GROUP BY decision.reason_code ORDER BY n DESC",
                            (since,),
                        )
                    },
                    "note": "legacy_unstructured 仅计无结构化 decision 的既有 review event；不反推 reason",
                }
            else:
                reviews["judgment_coverage"] = (
                    "未知（task_human_decisions 结构未在位；不把旧人签冒充结构化样本）"
                )
            report["reviews"] = reviews
        else:
            report["reviews"] = "未知（task_events/tasks 表结构不含所需列）"

        # ---- 对话/漏斗 ----
        conv_ok = {"created_at", "created_by"} <= _columns(conn, "conversations")
        conv_count = _one(conn, "SELECT COUNT(*) FROM conversations WHERE created_at >= ?", (since,)) if conv_ok else None
        if conv_ok and isinstance(report.get("tasks"), dict):
            conv_with_tasks = _one(
                conn,
                "SELECT COUNT(DISTINCT conversation_id) FROM tasks "
                "WHERE origin = 'user' AND conversation_id IS NOT NULL AND created_at >= ?",
                (since,),
            )
            by_status = report["tasks"]["by_status"]
            report["funnel"] = {
                "conversations": conv_count,
                "conversations_with_tasks": conv_with_tasks,
                "tasks_created": report["tasks"]["created"],
                "waiting_review_now": by_status.get("waiting_review", 0),
                "completed": by_status.get("completed", 0),
                "failed": by_status.get("failed", 0),
                "note": "对话数为全量（conversations 无 origin 轴）；任务数仅 origin=user",
            }
        else:
            report["funnel"] = "未知（conversations/tasks 表结构不含所需列）"

        # ---- 模型消耗（token 列动态探测，缺=未知绝不记 0） ----
        mc_cols = _columns(conn, "model_calls")
        if {"status", "created_at"} <= mc_cols:
            calls: dict = {
                "total": _one(conn, "SELECT COUNT(*) FROM model_calls WHERE created_at >= ?", (since,)),
                "failed": _one(
                    conn, "SELECT COUNT(*) FROM model_calls WHERE created_at >= ? AND status != 'success'", (since,)
                ),
            }
            token_col = next((c for c in ("total_tokens", "tokens_total", "usage_total_tokens") if c in mc_cols), None)
            calls["tokens"] = (
                _one(conn, f"SELECT SUM({token_col}) FROM model_calls WHERE created_at >= ?", (since,))
                if token_col
                else "未知（model_calls 无总 token 列）"
            )
            report["model_calls"] = calls
        else:
            report["model_calls"] = "未知（model_calls 表结构不含所需列）"

        # ---- 签发产物流转 lower-bound（ADR-0036） ----
        # capture_started 是逐权威产物 observation cohort 起点，不是 outcome。
        # 无 marker 时无法区分“没有行为”与“还没有可观测产物”，必须报未知而非 0。
        outcome_cols = _columns(conn, "artifact_outcome_events")
        required_outcome_cols = {
            "id", "event_type", "source_task_id", "source_file_id",
            "review_event_id", "actor_username", "downstream_task_id",
            "delivered_bytes", "schema_version", "created_at",
        }
        outcome_schema_witnesses = _outcome_schema_witnesses(conn)
        outcome_schema_ready = all(
            outcome_schema_witnesses.get(key) is True
            for key in _OUTCOME_SCHEMA_WITNESS_KEYS
        )
        if (
            outcome_schema_ready is True
            and required_outcome_cols <= outcome_cols
            and {"id", "origin"} <= task_cols
        ):
            first_capture = _one(
                conn,
                "SELECT MIN(outcome.created_at) "
                "FROM artifact_outcome_events AS outcome "
                "JOIN tasks AS source ON source.id = outcome.source_task_id "
                "WHERE source.origin = 'user' "
                "AND outcome.event_type = 'capture_started'",
            )
            if first_capture is None:
                report["artifact_outcomes"] = {
                    "status": "unknown_no_instrumented_artifacts",
                    "observation_started_at": "未知（尚无逐权威产物 capture_started）",
                    "capture_started": "未知（尚无 instrumentation cohort，不以 0 充数）",
                    "full_download": "未知（尚无 instrumentation cohort，不以 0 充数）",
                    "pipeline_handoff": "未知（尚无 instrumentation cohort，不以 0 充数）",
                    "note": "capture_started 只表示采集生效，不是 outcome；不历史回填",
                }
            else:
                first_capture_dt = _parse_ts(first_capture)
                if first_capture_dt is None:
                    report["artifact_outcomes"] = {
                        "status": "unknown_invalid_capture_timestamp",
                        "observation_started_at": "未知（capture_started 时间戳不可解析）",
                        "capture_started": "未知（采集起点不可验证）",
                        "full_download": "未知（采集起点不可验证）",
                        "pipeline_handoff": "未知（采集起点不可验证）",
                        "note": "拒绝跨不可验证采集起点编造结果计数",
                    }
                elif first_capture_dt > now:
                    report["artifact_outcomes"] = {
                        "status": "unknown_future_capture_timestamp",
                        "observation_started_at": "未知（capture_started 晚于报告生成时点）",
                        "capture_started": "未知（采集起点来自未来，不进入当前快照计数）",
                        "full_download": "未知（采集起点来自未来，不进入当前快照计数）",
                        "pipeline_handoff": "未知（采集起点来自未来，不进入当前快照计数）",
                        "note": "拒绝把报告生成时点之后的采集事实计入当前报告",
                    }
                else:
                    requested_since_dt = now - dt.timedelta(days=days)
                    effective_dt = max(requested_since_dt, first_capture_dt)
                    effective_since = effective_dt.isoformat(timespec="seconds")

                    def outcome_counts(event_type: str, *, require_downstream: bool = False) -> dict:
                        downstream_join = (
                            "JOIN tasks AS downstream "
                            "ON downstream.id = outcome.downstream_task_id "
                            "AND downstream.origin = 'user' "
                            if require_downstream else ""
                        )
                        row = conn.execute(
                            "SELECT COUNT(*) AS events, "
                            "COUNT(DISTINCT outcome.source_file_id) AS artifacts, "
                            "COUNT(DISTINCT outcome.source_task_id) AS source_tasks"
                            + (
                                ", COUNT(DISTINCT outcome.downstream_task_id) AS downstream_tasks "
                                if require_downstream else " "
                            )
                            + "FROM artifact_outcome_events AS outcome "
                            "JOIN tasks AS source ON source.id = outcome.source_task_id "
                            "AND source.origin = 'user' "
                            + downstream_join
                            + "WHERE outcome.event_type = ? "
                            "AND outcome.created_at >= ? "
                            "AND outcome.created_at <= ?",
                            (event_type, effective_since, generated_at_bound),
                        ).fetchone()
                        result = {
                            "events": int(row["events"]),
                            "distinct_artifacts": int(row["artifacts"]),
                            "distinct_source_tasks": int(row["source_tasks"]),
                        }
                        if require_downstream:
                            result["distinct_downstream_tasks"] = int(row["downstream_tasks"])
                        return result

                    capture_counts = outcome_counts("capture_started")
                    download_counts = outcome_counts("full_download")
                    download_counts["distinct_actors"] = int(_one(
                        conn,
                        "SELECT COUNT(DISTINCT outcome.actor_username) "
                        "FROM artifact_outcome_events AS outcome "
                        "JOIN tasks AS source ON source.id = outcome.source_task_id "
                        "AND source.origin = 'user' "
                        "WHERE outcome.event_type = 'full_download' "
                        "AND outcome.created_at >= ? "
                        "AND outcome.created_at <= ? "
                        "AND outcome.actor_username IS NOT NULL",
                        (effective_since, generated_at_bound),
                    ) or 0)
                    handoff_counts = outcome_counts(
                        "pipeline_handoff", require_downstream=True
                    )
                    report["artifact_outcomes"] = {
                        "status": "measured",
                        "schema_witnesses": outcome_schema_witnesses,
                        "observation_started_at": str(first_capture),
                        "requested_window_start": since,
                        "effective_window_start": effective_since,
                        "requested_window_fully_covered": first_capture_dt <= requested_since_dt,
                        "capture_started": capture_counts,
                        "full_download": {
                            "delivered_events_lower_bound": download_counts.pop("events"),
                            **download_counts,
                        },
                        "pipeline_handoff": {
                            "flowed_events_lower_bound": handoff_counts.pop("events"),
                            **handoff_counts,
                        },
                        "note": (
                            "仅统计逐权威产物 capture_started 之后的 user-origin 事件；"
                            "full_download=完整正文已交付，不代表采用（仅 200 GET）；"
                            "pipeline_handoff=产物已流入下游任务，不代表被读取或采用"
                        ),
                    }
        else:
            report["artifact_outcomes"] = (
                "未知（artifact_outcome_events exact schema witness 未通过或 tasks 结构缺失；"
                "拒绝从 loose lookalike/缺 trigger 的库计数）"
            )

        # ---- 反馈 ----
        if {"created_at"} <= _columns(conn, "feedback"):
            report["feedback_count"] = _one(conn, "SELECT COUNT(*) FROM feedback WHERE created_at >= ?", (since,))
        else:
            report["feedback_count"] = "未知（feedback 表结构不含所需列）"

        return report
    finally:
        conn.close()


def render_md(report: dict) -> str:
    lines = [
        f"# FLAi-OS 使用遥测 · 近 {report['window_days']} 天",
        "",
        f"- 生成：{report['generated_at']} · 库：`{report['db']}`",
        f"- 账户：{report['accounts']}",
        "",
    ]
    tasks = report.get("tasks")
    if isinstance(tasks, dict):
        lines += [
            "## 任务（origin=user）",
            f"- 新建 {tasks['created']}，独立发起人 {tasks['distinct_creators']}",
            f"- 状态分布：{tasks['by_status'] or '（窗口内无任务）'}",
            f"- 发起人 Top：{tasks['by_creator'] or '—'}",
            f"- Agent Top：{tasks['by_agent'] or '—'}",
            f"- 完成任务时延中位数：{tasks['completed_median_s']}{'s' if isinstance(tasks['completed_median_s'], (int, float)) else ''}",
            f"- 滞留 waiting_review >{STALL_HOURS}h：{tasks.get('stalled_waiting_review', '未知')}（放弃点信号）",
            "",
        ]
    else:
        lines += [f"## 任务：{tasks}", ""]
    lines += [f"## 人签：{report['reviews']}", "", f"## 漏斗：{report['funnel']}", ""]
    lines += [
        f"## 模型调用：{report['model_calls']}",
        "",
        f"## 签发产物流转（lower-bound）：{report['artifact_outcomes']}",
        "",
        f"## 反馈条数：{report['feedback_count']}",
        "",
    ]
    lines += ["> 只读报告；eval 跑批（origin≠user）不计入使用量；缺失结构显式标注「未知」，绝不以 0 充数。"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--json", action="store_true", help="输出 JSON 而非 markdown")
    args = parser.parse_args()

    if not args.db.is_file():
        print(f"[usage] FAIL：DB 不存在：{args.db}（fail-closed，不产出空报告）", file=sys.stderr)
        return 2
    try:
        report = build_report(args.db, args.days)
    except sqlite3.Error as exc:
        print(f"[usage] FAIL：DB 读取错误：{exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_md(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
