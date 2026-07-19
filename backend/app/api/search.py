"""P2.4 authenticated, read-only addressing search endpoint."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..storage import search as search_store


router = APIRouter(prefix="/api", tags=["search"])

_ALLOWED_PARAMS = frozenset(
    {"q", "scope", "limit", "cursor", "status", "agent_id", "task_scope"}
)
_TASK_FILTERS = frozenset({"status", "agent_id", "task_scope"})


def _json_response(payload: dict[str, Any], *, status_code: int) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _invalid(detail: str) -> JSONResponse:
    return _json_response({"detail": detail}, status_code=422)


@router.get("/search")
def search_addresses(
    request: Request,
    q: str | None = Query(default=None, description="2-128 字符的字面量查询"),
    scope: str | None = Query(
        default=None, description="conversation/message/task/artifact 之一"
    ),
    limit: str = Query(default="8", description="每个 scope 返回 1-20 条"),
    cursor: str | None = Query(default=None, description="不透明 keyset cursor"),
    status: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    task_scope: str = Query(default="all", description="task/artifact: all 或 mine"),
) -> JSONResponse:
    pairs = list(request.query_params.multi_items())
    keys = [key for key, _ in pairs]
    unknown = sorted(set(keys) - _ALLOWED_PARAMS)
    if unknown:
        return _invalid(f"不接受查询参数：{', '.join(unknown)}")
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        return _invalid(f"查询参数不得重复：{', '.join(duplicated)}")

    if q is None:
        return _invalid("缺少 q")
    if scope is None:
        return _invalid("缺少 scope")

    raw_limit = limit
    try:
        limit = int(raw_limit, 10)
    except (TypeError, ValueError):
        return _invalid("limit 必须是 1-20 的整数")
    # Query strings are text; reject alternate spellings rather than silently
    # accepting floats, signs, or bool-like values as pagination contracts.
    if str(limit) != raw_limit:
        return _invalid("limit 必须是 1-20 的十进制整数")
    if scope not in {"task", "artifact"} and any(
        key in keys for key in _TASK_FILTERS
    ):
        return _invalid("该 scope 不接受任务过滤参数")

    try:
        prepared = search_store.prepare_search_request(
            principal_username=request.state.user["username"],
            query=q,
            scope=scope,
            limit=limit,
            cursor=cursor,
            status=status,
            agent_id=agent_id,
            task_scope=task_scope,
            cursor_signing_key=request.app.state.search_cursor_signing_key,
        )
    except search_store.SearchInputError as exc:
        return _invalid(str(exc))

    conn = None
    try:
        conn = request.app.state.conn_factory()
        page = search_store.execute_prepared_search(conn, prepared)
    except search_store.SearchCapacityExceededError:
        result = _json_response(
            {"detail": "search_capacity_exceeded"}, status_code=503
        )
    except (search_store.SearchUnavailableError, sqlite3.Error):
        result = _json_response(
            {"detail": "search_source_unavailable"}, status_code=503
        )
    else:
        result = _json_response(page, status_code=200)
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                result = _json_response(
                    {"detail": "search_source_unavailable"}, status_code=503
                )

    return result
