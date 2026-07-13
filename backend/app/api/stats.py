"""批B /today 只读聚合（spec docs/superpowers/specs/2026-07-13-today-workbench-batch-b-design.md §三）。
零 schema 变更：SQL 直查既有表 + eval_cases 落盘文件计数。since 必填、必须
offset-aware ISO8601（naive/纯日期 422 fail-closed，不默认兜底窗口）；入 SQL
前归一化为 UTC "+00:00" 表示——库内 repos 写入即该格式，归一化后字典序
比较才恒等于时间序（B-T2 审查实证：'Z' 后缀同秒会因 ASCII 'Z'>'.'/'+'
错序漏计，而 JS toISOString() 默认就是 'Z' 后缀）。"""
from __future__ import annotations

from datetime import datetime, timezone
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
        dt = datetime.fromisoformat(since)
        if dt.tzinfo is None:
            # naive/纯日期没有确定时刻语义，与库内 offset-aware 字符串比较必错序——拒收。
            raise HTTPException(
                status_code=422, detail=f"since 必须带时区偏移（offset-aware）：{since}"
            )
        since = dt.astimezone(timezone.utc).isoformat()  # 归一化 'Z'/任意偏移 → '+00:00' 表示
    except (ValueError, OverflowError) as exc:
        # ValueError=非法 ISO8601；OverflowError=极端年份+大偏移归一化到 UTC 时溢出
        # datetime 可表示范围（如 0001-01-01T00:00:00+23:59），二者同归 422 fail-closed。
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
