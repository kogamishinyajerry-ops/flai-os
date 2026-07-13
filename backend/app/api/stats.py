"""批B /today 只读聚合（spec docs/superpowers/specs/2026-07-13-today-workbench-batch-b-design.md §三）。
零 schema 变更：SQL 直查既有表 + eval_cases 落盘文件计数。since 必填合法
ISO8601（fail-closed 422，不默认兜底窗口）；ISO8601 UTC 字符串字典序可比，
与 repos 写入格式一致，SQL 直接 >= 比较。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["stats"])


def count_curated_cases(agents_dir: Path) -> int:
    """累计固化 case 数=agents/*/eval_cases/case_*.json 落盘文件（治理产物的
    真实存在形式，ADR-0018 固化即落盘无 DB 行）。目录缺失=0，不抛。"""
    if not agents_dir.is_dir():
        return 0
    return sum(1 for _ in agents_dir.glob("*/eval_cases/case_*.json"))


@router.get("/stats/overview")
def stats_overview(request: Request, since: str | None = None) -> dict[str, Any]:
    if not since:
        raise HTTPException(status_code=422, detail="since 必填（ISO8601）")
    try:
        datetime.fromisoformat(since)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"since 不是合法 ISO8601：{since}") from exc
    conn = request.app.state.conn_factory()
    try:
        tasks_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'completed'"
            " AND origin = 'user' AND finished_at IS NOT NULL AND finished_at >= ?",
            (since,),
        ).fetchone()[0]
        reviews_approved = conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE event_type = 'review_approved'"
            " AND created_at >= ?",
            (since,),
        ).fetchone()[0]
        promotions = conn.execute(
            "SELECT COUNT(*) FROM promotions WHERE created_at >= ?", (since,)
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "since": since,
        "tasks_completed": tasks_completed,
        "reviews_approved": reviews_approved,
        "curated_cases_total": count_curated_cases(request.app.state.agents_dir),
        "promotions": promotions,
    }
