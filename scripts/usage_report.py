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
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_report(db_path: Path, days: int, now: dt.datetime | None = None) -> dict:
    """汇总使用数据。now 可注入（测试确定性）。"""
    now = now or dt.datetime.now()
    since = (now - dt.timedelta(days=days)).isoformat(timespec="seconds")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        report: dict = {
            "generated_at": now.isoformat(timespec="seconds"),
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
        if {"event_type", "created_at"} <= _columns(conn, "task_events"):
            report["reviews"] = {
                "approved": _one(
                    conn, "SELECT COUNT(*) FROM task_events WHERE event_type = 'review_approved' AND created_at >= ?", (since,)
                ),
                "rejected": _one(
                    conn, "SELECT COUNT(*) FROM task_events WHERE event_type = 'review_rejected' AND created_at >= ?", (since,)
                ),
            }
        else:
            report["reviews"] = "未知（task_events 表结构不含所需列）"

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
                    conn, "SELECT COUNT(*) FROM model_calls WHERE created_at >= ? AND status != 'succeeded'", (since,)
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
    lines += [f"## 模型调用：{report['model_calls']}", "", f"## 反馈条数：{report['feedback_count']}", ""]
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
