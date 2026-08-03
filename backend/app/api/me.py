"""工程师个人贡献只读端点（批C 轨2）。

私有=安全线：归因主键一律取 request.state.user["username"]（服务端派生），
绝不接受 username 查询参数——登录者只能看到自己的贡献，杜绝越权查他人。
只精确归因：只有「我发起的任务」按 created_by_username 精确；反馈按 created_by
(display_name) 近似（可撞名，前端显式标注）。签发/样本个人归因本批不做（唯一
身份仅在审计轨留痕），前端诚实缺口条明说。零 schema 变更。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from . import classification_gate as cgate  # 与 tasks.py 同款遮蔽 chokepoint（tasks.py:15 同）
from . import object_authorization as oauth
from ._since import parse_since_utc

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me/contributions")
def me_contributions(request: Request, since: str | None = None) -> dict[str, Any]:
    username = request.state.user["username"]
    display_name = request.state.user["display_name"]
    since_utc = parse_since_utc(since)
    conn = request.app.state.conn_factory()
    try:
        since_created = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND created_at >= ?",
            (username, since_utc),
        ).fetchone()[0]
        since_completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND status = 'completed'"
            " AND finished_at IS NOT NULL AND finished_at >= ?",
            (username, since_utc),
        ).fetchone()[0]
        waiting_review = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ?"
            " AND origin = 'user' AND status = 'waiting_review'",
            (username,),
        ).fetchone()[0]
        total_created = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE created_by_username = ? AND origin = 'user'",
            (username,),
        ).fetchone()[0]
        # 反馈近似：feedback 表只有 created_by(display_name)，无 username 列——可撞名
        feedback_count_approx = conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE created_by = ?",
            (display_name,),
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "username": username,
        "since": since_utc,
        "since_created": since_created,
        "since_completed": since_completed,
        "waiting_review": waiting_review,
        "total_created": total_created,
        "feedback_count_approx": feedback_count_approx,
    }


@router.get("/me/tasks")
def me_tasks(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    conn = request.app.state.conn_factory()
    try:
        rows = oauth.list_readable_tasks(
            conn,
            username=oauth.authenticated_username(request),
            agent_id=None,
            status=None,
            conversation_id=None,
            origin="user",
            limit=limit,
            offset=0,
        )
        # ADR-0025 单 chokepoint：sensitive 任务承载字段遮蔽，与 /api/tasks 同款。
        return [cgate.redact_task_row_if_sensitive(conn, t) for t in rows]
    finally:
        conn.close()
