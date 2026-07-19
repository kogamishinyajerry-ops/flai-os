"""P2.4 read-only exact addressing search.

The first production version deliberately uses a bounded deterministic SQLite
scan instead of FTS.  That keeps the public contract independent of optional
SQLite tokenizer support on the Windows deployment target while preserving a
hard fail-closed capacity boundary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


SEARCH_SCOPES = frozenset({"conversation", "message", "task", "artifact"})
TASK_STATUSES = frozenset(
    {
        "created",
        "queued",
        "validating",
        "running",
        "waiting_review",
        "parsing",
        "analyzing",
        "completed",
        "failed",
        "cancelled",
    }
)
MAX_SOURCE_ROWS = 50_000
MAX_SOURCE_TEXT_CHARS = 16_000_000
MAX_SNIPPET_CHARS = 240

_CURSOR_VERSION = 1
_CURSOR_RE = re.compile(r"^[A-Za-z0-9_-]{1,4096}$")
_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_CONVERSATION_ID_RE = re.compile(r"^conv_[a-f0-9]{32}$")
_MESSAGE_ID_RE = re.compile(r"^msg_[a-f0-9]{32}$")
_CURSOR_DOMAIN = b"flai-os/search-cursor/v1\x00"


class SearchInputError(ValueError):
    """The caller supplied an invalid query, filter, or cursor."""


class SearchUnavailableError(RuntimeError):
    """The search source failed and must not be represented as an empty page."""


class SearchCapacityExceededError(SearchUnavailableError):
    """A deterministic scan would exceed its frozen safety capacity."""


@dataclass(frozen=True)
class PreparedSearch:
    principal_username: str
    query: str
    scope: str
    limit: int
    status: str | None
    agent_id: str | None
    task_scope: str
    binding: str
    snapshot_at: str
    last: dict[str, Any] | None
    cursor_signing_key: bytes = field(repr=False)


def normalize_query(value: Any) -> str:
    if not isinstance(value, str):
        raise SearchInputError("q 必须是字符串")
    query = value.strip()
    if not 2 <= len(query) <= 128:
        raise SearchInputError("q 去除首尾空白后长度必须为 2-128")
    if any(unicodedata.category(char) == "Cc" for char in query):
        raise SearchInputError("q 不得包含控制字符")
    return query


def validate_search_options(
    *,
    scope: Any,
    limit: Any,
    status: Any = None,
    agent_id: Any = None,
    task_scope: Any = "all",
) -> tuple[str, int, str | None, str | None, str]:
    if not isinstance(scope, str) or scope not in SEARCH_SCOPES:
        raise SearchInputError("scope 只认 conversation/message/task/artifact")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise SearchInputError("limit 必须是 1-20 的整数")
    if status is not None and (
        not isinstance(status, str) or status not in TASK_STATUSES
    ):
        raise SearchInputError("status 不是受支持的任务状态")
    if agent_id is not None and (
        not isinstance(agent_id, str) or _AGENT_ID_RE.fullmatch(agent_id) is None
    ):
        raise SearchInputError("agent_id 形状非法")
    if not isinstance(task_scope, str) or task_scope not in {"all", "mine"}:
        raise SearchInputError("task_scope 只认 all/mine")
    if scope not in {"task", "artifact"} and (
        status is not None or agent_id is not None or task_scope != "all"
    ):
        raise SearchInputError("该 scope 不接受任务过滤参数")
    return scope, limit, status, agent_id, task_scope


def search_addresses(
    conn: sqlite3.Connection,
    *,
    principal_username: str,
    query: str,
    scope: str,
    limit: int = 8,
    cursor: str | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    task_scope: str = "all",
    cursor_signing_key: bytes,
) -> dict[str, Any]:
    """Return one honest, snapshot-bounded page for a single source.

    A singular scope is intentional: the QuickSwitcher can request all four
    sources in parallel and tell the user precisely which source failed instead
    of turning a partial backend failure into a misleading global empty state.
    """

    prepared = prepare_search_request(
        principal_username=principal_username,
        query=query,
        scope=scope,
        limit=limit,
        cursor=cursor,
        status=status,
        agent_id=agent_id,
        task_scope=task_scope,
        cursor_signing_key=cursor_signing_key,
    )
    return execute_prepared_search(conn, prepared)


def prepare_search_request(
    *,
    principal_username: str,
    query: str,
    scope: str,
    limit: int = 8,
    cursor: str | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    task_scope: str = "all",
    cursor_signing_key: bytes,
) -> PreparedSearch:
    """Validate and bind every caller-controlled value without opening SQLite."""

    if not isinstance(principal_username, str) or not principal_username:
        raise SearchInputError("principal username 缺失")
    if not isinstance(cursor_signing_key, bytes) or len(cursor_signing_key) < 32:
        raise SearchInputError("cursor signing key 缺失")
    normalized = normalize_query(query)
    scope, limit, status, agent_id, task_scope = validate_search_options(
        scope=scope,
        limit=limit,
        status=status,
        agent_id=agent_id,
        task_scope=task_scope,
    )
    binding = _binding_digest(
        principal_username=principal_username,
        query=normalized,
        scope=scope,
        limit=limit,
        status=status,
        agent_id=agent_id,
        task_scope=task_scope,
    )

    if cursor is None:
        snapshot_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        last: dict[str, Any] | None = None
    else:
        decoded = _decode_cursor(
            cursor,
            expected_binding=binding,
            signing_key=cursor_signing_key,
        )
        snapshot_at = decoded["snapshot_at"]
        last = decoded["last"]
    return PreparedSearch(
        principal_username=principal_username,
        query=normalized,
        scope=scope,
        limit=limit,
        status=status,
        agent_id=agent_id,
        task_scope=task_scope,
        binding=binding,
        snapshot_at=snapshot_at,
        last=last,
        cursor_signing_key=cursor_signing_key,
    )


def execute_prepared_search(
    conn: sqlite3.Connection, prepared: PreparedSearch
) -> dict[str, Any]:
    """Execute a previously validated search request on one read snapshot."""

    owns_read_transaction = conn.in_transaction is False
    try:
        if owns_read_transaction is True:
            # get_conn() is autocommit.  Pin COUNT/size/SELECT to one read
            # snapshot so a concurrent insert cannot cross the capacity gate.
            conn.execute("BEGIN")
        hits = _search_scope(
            conn,
            principal_username=prepared.principal_username,
            query=prepared.query,
            scope=prepared.scope,
            snapshot_at=prepared.snapshot_at,
            status=prepared.status,
            agent_id=prepared.agent_id,
            task_scope=prepared.task_scope,
        )
    except SearchUnavailableError:
        raise
    except (sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SearchUnavailableError("search_source_unavailable") from exc
    finally:
        if owns_read_transaction is True and conn.in_transaction is True:
            conn.execute("ROLLBACK")

    if prepared.last is not None:
        hits = [hit for hit in hits if _comes_after(hit, prepared.last)]
    has_more = len(hits) > prepared.limit
    page_hits = hits[: prepared.limit]
    items = [{key: value for key, value in hit.items() if not key.startswith("_")} for hit in page_hits]
    next_cursor = None
    if has_more is True:
        tail = page_hits[-1]
        next_cursor = _encode_cursor(
            binding=prepared.binding,
            snapshot_at=prepared.snapshot_at,
            signing_key=prepared.cursor_signing_key,
            last={
                "rank": tail["_rank"],
                "created_at": tail["created_at"],
                "id": tail["id"],
            },
        )
    return {
        "schema_version": "search-page/v1",
        "scope": prepared.scope,
        "query": prepared.query,
        "snapshot_at": prepared.snapshot_at,
        "items": items,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _search_scope(
    conn: sqlite3.Connection,
    *,
    principal_username: str,
    query: str,
    scope: str,
    snapshot_at: str,
    status: str | None,
    agent_id: str | None,
    task_scope: str,
) -> list[dict[str, Any]]:
    if scope == "conversation":
        rows = _bounded_fetch(
            conn,
            "SELECT COUNT(*) FROM conversations "
            "WHERE created_by_username = ? AND created_at <= ?",
            "SELECT id, agent_id, status, created_at FROM conversations "
            "WHERE created_by_username = ? AND created_at <= ?",
            (principal_username, snapshot_at),
        )
        hits = []
        for row in rows:
            rank = _match_rank(row["id"], (row["agent_id"],), query)
            if rank is None:
                continue
            hits.append(
                {
                    "kind": "conversation",
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "match_kind": _match_kind(rank),
                    "_rank": rank,
                }
            )
        return _sort_hits(hits)

    if scope == "message":
        args = (principal_username, snapshot_at)
        rows = _bounded_fetch(
            conn,
            "SELECT COUNT(*) FROM conversation_messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.created_by_username = ? AND m.created_at <= ?",
            "SELECT m.message_id AS id, m.conversation_id, c.agent_id AS conversation_agent_id, "
            "m.role, m.content, m.created_at FROM conversation_messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.created_by_username = ? AND m.created_at <= ?",
            args,
            size_sql="SELECT COALESCE(SUM(length(m.content)), 0) "
            "FROM conversation_messages m "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.created_by_username = ? AND m.created_at <= ?",
        )
        hits = []
        for row in rows:
            rank = _match_rank(row["id"], (row["content"],), query)
            if rank is None:
                continue
            snippet, truncated = _snippet(row["content"], query)
            hits.append(
                {
                    "kind": "message",
                    "id": row["id"],
                    "conversation_id": row["conversation_id"],
                    "conversation_agent_id": row["conversation_agent_id"],
                    "role": row["role"],
                    "snippet": snippet,
                    "snippet_truncated": truncated,
                    "created_at": row["created_at"],
                    "match_kind": _match_kind(rank),
                    "_rank": rank,
                }
            )
        return _sort_hits(hits)

    task_where, task_args = _task_where(
        principal_username=principal_username,
        snapshot_at=snapshot_at,
        status=status,
        agent_id=agent_id,
        task_scope=task_scope,
        alias="t" if scope == "artifact" else "",
    )
    if scope == "task":
        rows = _bounded_fetch(
            conn,
            f"SELECT COUNT(*) FROM tasks{task_where}",
            "SELECT id, name, agent_id, status, data_classification, created_at "
            f"FROM tasks{task_where}",
            task_args,
        )
        hits = []
        for row in rows:
            rank = _match_rank(row["id"], (row["name"], row["agent_id"]), query)
            if rank is None:
                continue
            classification, withheld = _classification_projection(row["data_classification"])
            hits.append(
                {
                    "kind": "task",
                    "id": row["id"],
                    "name": row["name"],
                    "agent_id": row["agent_id"],
                    "status": row["status"],
                    "data_classification": classification,
                    "content_withheld": withheld,
                    "created_at": row["created_at"],
                    "match_kind": _match_kind(rank),
                    "_rank": rank,
                }
            )
        return _sort_hits(hits)

    if scope == "artifact":
        joined_where = task_where + " AND f.kind = 'output' AND f.task_id = t.id AND f.created_at <= ?"
        artifact_args = (*task_args, snapshot_at)
        rows = _bounded_fetch(
            conn,
            "SELECT COUNT(*) FROM files f JOIN tasks t ON t.id = f.task_id" + joined_where,
            "SELECT f.id, f.filename, f.size_bytes, f.classification, f.created_at, "
            "t.id AS task_id, t.name AS task_name, t.output_file_ids "
            "FROM files f JOIN tasks t ON t.id = f.task_id" + joined_where,
            artifact_args,
            size_sql="SELECT COALESCE(SUM(length(t.output_file_ids) + length(f.filename)), 0) "
            "FROM files f JOIN tasks t ON t.id = f.task_id" + joined_where,
        )
        hits = []
        for row in rows:
            membership = json.loads(row["output_file_ids"])
            if not isinstance(membership, list) or any(
                not isinstance(item, str) for item in membership
            ) or len(membership) != len(set(membership)):
                raise SearchUnavailableError("search_authoritative_membership_invalid")
            if row["id"] not in membership:
                continue
            rank = _match_rank(row["id"], (row["filename"],), query)
            if rank is None:
                continue
            classification, withheld = _classification_projection(row["classification"])
            hits.append(
                {
                    "kind": "artifact",
                    "id": row["id"],
                    "filename": row["filename"],
                    "task_id": row["task_id"],
                    "task_name": row["task_name"],
                    "size_bytes": row["size_bytes"],
                    "data_classification": classification,
                    "content_withheld": withheld,
                    "created_at": row["created_at"],
                    "match_kind": _match_kind(rank),
                    "_rank": rank,
                }
            )
        return _sort_hits(hits)

    raise SearchInputError("scope 不受支持")


def _task_where(
    *,
    principal_username: str,
    snapshot_at: str,
    status: str | None,
    agent_id: str | None,
    task_scope: str,
    alias: str,
) -> tuple[str, tuple[Any, ...]]:
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}origin = 'user'", f"{prefix}created_at <= ?"]
    args: list[Any] = [snapshot_at]
    if status is not None:
        clauses.append(f"{prefix}status = ?")
        args.append(status)
    if agent_id is not None:
        clauses.append(f"{prefix}agent_id = ?")
        args.append(agent_id)
    if task_scope == "mine":
        clauses.append(f"{prefix}created_by_username = ?")
        args.append(principal_username)
    return " WHERE " + " AND ".join(clauses), tuple(args)


def _bounded_fetch(
    conn: sqlite3.Connection,
    count_sql: str,
    select_sql: str,
    params: tuple[Any, ...],
    *,
    size_sql: str | None = None,
) -> list[sqlite3.Row]:
    count_row = conn.execute(count_sql, params).fetchone()
    if count_row is None or type(count_row[0]) is not int:
        raise SearchUnavailableError("search_source_count_invalid")
    if count_row[0] > MAX_SOURCE_ROWS:
        raise SearchCapacityExceededError("search_capacity_exceeded")
    if size_sql is not None:
        size_row = conn.execute(size_sql, params).fetchone()
        if size_row is None or type(size_row[0]) is not int:
            raise SearchUnavailableError("search_source_size_invalid")
        if size_row[0] > MAX_SOURCE_TEXT_CHARS:
            raise SearchCapacityExceededError("search_capacity_exceeded")
    return conn.execute(select_sql, params).fetchall()


def _ascii_fold(value: str) -> str:
    if not isinstance(value, str):
        raise SearchUnavailableError("search_source_text_invalid")
    return value.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _match_rank(identifier: str, texts: Iterable[Any], query: str) -> int | None:
    identifier_folded = _ascii_fold(identifier)
    query_folded = _ascii_fold(query)
    if identifier_folded == query_folded:
        return 0
    if identifier_folded.startswith(query_folded):
        return 1
    folded_texts = [_ascii_fold(text) for text in texts if text is not None]
    if any(text.startswith(query_folded) for text in folded_texts):
        return 2
    if query_folded in identifier_folded or any(
        query_folded in text for text in folded_texts
    ):
        return 3
    return None


def _match_kind(rank: int) -> str:
    return ("exact_id", "id_prefix", "text_prefix", "text_contains")[rank]


def _sort_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for hit in hits:
        _validate_hit(hit)
        hit["_created_order"] = _timestamp_order_value(hit["created_at"])
    hits.sort(
        key=lambda hit: (hit["_rank"], -hit["_created_order"], hit["id"])
    )
    return hits


def _validate_hit(hit: dict[str, Any]) -> None:
    kind = hit.get("kind")
    identifier = hit.get("id")
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200:
        raise SearchUnavailableError("search_source_id_invalid")
    if type(hit.get("_rank")) is not int or not 0 <= hit["_rank"] <= 3:
        raise SearchUnavailableError("search_source_rank_invalid")
    _timestamp_order_value(hit.get("created_at"))
    if kind == "conversation":
        if _CONVERSATION_ID_RE.fullmatch(identifier) is None:
            raise SearchUnavailableError("search_conversation_id_invalid")
        if _AGENT_ID_RE.fullmatch(str(hit.get("agent_id", ""))) is None:
            raise SearchUnavailableError("search_agent_id_invalid")
        if hit.get("status") not in {"active", "concluded"}:
            raise SearchUnavailableError("search_conversation_status_invalid")
        return
    if kind == "message":
        if _MESSAGE_ID_RE.fullmatch(identifier) is None:
            raise SearchUnavailableError("search_message_id_invalid")
        if _CONVERSATION_ID_RE.fullmatch(str(hit.get("conversation_id", ""))) is None:
            raise SearchUnavailableError("search_conversation_id_invalid")
        if _AGENT_ID_RE.fullmatch(str(hit.get("conversation_agent_id", ""))) is None:
            raise SearchUnavailableError("search_agent_id_invalid")
        if hit.get("role") not in {"user", "assistant"}:
            raise SearchUnavailableError("search_message_role_invalid")
        if not isinstance(hit.get("snippet"), str) or len(hit["snippet"]) > MAX_SNIPPET_CHARS:
            raise SearchUnavailableError("search_message_snippet_invalid")
        if type(hit.get("snippet_truncated")) is not bool:
            raise SearchUnavailableError("search_message_snippet_invalid")
        return
    if kind == "task":
        name = hit.get("name")
        if name is not None and (
            not isinstance(name, str) or not 1 <= len(name) <= 200
        ):
            raise SearchUnavailableError("search_task_name_invalid")
        if _AGENT_ID_RE.fullmatch(str(hit.get("agent_id", ""))) is None:
            raise SearchUnavailableError("search_agent_id_invalid")
        if hit.get("status") not in TASK_STATUSES:
            raise SearchUnavailableError("search_task_status_invalid")
        _validate_classification_projection(hit)
        return
    if kind == "artifact":
        filename = hit.get("filename")
        task_name = hit.get("task_name")
        if not isinstance(filename, str) or not filename:
            raise SearchUnavailableError("search_artifact_filename_invalid")
        if not isinstance(hit.get("task_id"), str) or not 1 <= len(hit["task_id"]) <= 200:
            raise SearchUnavailableError("search_task_id_invalid")
        if task_name is not None and (
            not isinstance(task_name, str) or not 1 <= len(task_name) <= 200
        ):
            raise SearchUnavailableError("search_task_name_invalid")
        if type(hit.get("size_bytes")) is not int or hit["size_bytes"] < 0:
            raise SearchUnavailableError("search_artifact_size_invalid")
        _validate_classification_projection(hit)
        return
    raise SearchUnavailableError("search_source_kind_invalid")


def _validate_classification_projection(hit: dict[str, Any]) -> None:
    classification = hit.get("data_classification")
    withheld = hit.get("content_withheld")
    if classification not in {"internal", "sensitive", None}:
        raise SearchUnavailableError("search_classification_invalid")
    expected = classification != "internal"
    if type(withheld) is not bool or withheld is not expected:
        raise SearchUnavailableError("search_classification_gate_invalid")


def _timestamp_order_value(value: Any) -> int:
    if not isinstance(value, str) or not value:
        raise SearchUnavailableError("search_source_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("naive timestamp")
        utc = parsed.astimezone(timezone.utc)
        epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
        delta = utc - epoch
    except (ValueError, OverflowError, OSError) as exc:
        raise SearchUnavailableError("search_source_timestamp_invalid") from exc
    return (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )


def _snippet(content: Any, query: str) -> tuple[str, bool]:
    if not isinstance(content, str):
        raise SearchUnavailableError("search_message_content_invalid")
    if len(content) <= MAX_SNIPPET_CHARS:
        return content.replace("\r", " ").replace("\n", " "), False
    position = _ascii_fold(content).find(_ascii_fold(query))
    if position < 0:
        position = 0
    prefix = position > 60
    suffix = True
    decoration = int(prefix) + int(suffix)
    budget = MAX_SNIPPET_CHARS - decoration
    start = max(0, min(position - 60, len(content) - budget))
    end = min(len(content), start + budget)
    prefix = start > 0
    suffix = end < len(content)
    decoration = int(prefix) + int(suffix)
    if end - start + decoration > MAX_SNIPPET_CHARS:
        end -= end - start + decoration - MAX_SNIPPET_CHARS
    snippet = ("…" if prefix else "") + content[start:end] + ("…" if suffix else "")
    return snippet.replace("\r", " ").replace("\n", " "), True


def _classification_projection(value: Any) -> tuple[str | None, bool]:
    if value == "internal":
        return "internal", False
    if value == "sensitive":
        return "sensitive", True
    # Unknown/NULL is never silently relabelled internal.  Keep the unknown fact
    # visible while withholding all content-bearing projections.
    return None, True


def _binding_digest(
    *,
    principal_username: str,
    query: str,
    scope: str,
    limit: int,
    status: str | None,
    agent_id: str | None,
    task_scope: str,
) -> str:
    canonical = json.dumps(
        {
            "principal_username": principal_username,
            "query": query,
            "scope": scope,
            "limit": limit,
            "status": status,
            "agent_id": agent_id,
            "task_scope": task_scope,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(_CURSOR_DOMAIN + canonical).hexdigest()


def _encode_cursor(
    *, binding: str, snapshot_at: str, last: dict[str, Any], signing_key: bytes
) -> str:
    core = {
        "v": _CURSOR_VERSION,
        "binding": binding,
        "snapshot_at": snapshot_at,
        "last": last,
    }
    canonical = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload = dict(core)
    payload["mac"] = hmac.new(
        signing_key, _CURSOR_DOMAIN + canonical, hashlib.sha256
    ).hexdigest()
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: Any, *, expected_binding: str, signing_key: bytes
) -> dict[str, Any]:
    if not isinstance(cursor, str) or _CURSOR_RE.fullmatch(cursor) is None:
        raise SearchInputError("cursor 形状非法")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SearchInputError("cursor 形状非法") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "v",
        "binding",
        "snapshot_at",
        "last",
        "mac",
    }:
        raise SearchInputError("cursor 形状非法")
    if type(payload["v"]) is not int or payload["v"] != _CURSOR_VERSION:
        raise SearchInputError("cursor 版本非法")
    if payload["binding"] != expected_binding:
        raise SearchInputError("cursor 与当前 principal/query/filter 不匹配")
    last = payload["last"]
    if not isinstance(last, dict) or set(last) != {"rank", "created_at", "id"}:
        raise SearchInputError("cursor 排序键非法")
    if type(last["rank"]) is not int or not 0 <= last["rank"] <= 3:
        raise SearchInputError("cursor 排序键非法")
    if not isinstance(last["id"], str) or not 1 <= len(last["id"]) <= 200:
        raise SearchInputError("cursor 排序键非法")
    core = {key: payload[key] for key in ("v", "binding", "snapshot_at", "last")}
    canonical = json.dumps(
        core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    expected_mac = hmac.new(
        signing_key, _CURSOR_DOMAIN + canonical, hashlib.sha256
    ).hexdigest()
    if not isinstance(payload["mac"], str) or not hmac.compare_digest(
        payload["mac"], expected_mac
    ):
        raise SearchInputError("cursor 校验失败")
    try:
        snapshot_order = _timestamp_order_value(payload["snapshot_at"])
        last_order = _timestamp_order_value(last["created_at"])
    except SearchUnavailableError as exc:
        raise SearchInputError("cursor 时间戳非法") from exc
    if last_order > snapshot_order:
        raise SearchInputError("cursor 时间戳非法")
    snapshot_datetime = datetime.fromisoformat(payload["snapshot_at"]).astimezone(
        timezone.utc
    )
    canonical_snapshot = snapshot_datetime.isoformat(timespec="microseconds")
    if payload["snapshot_at"] != canonical_snapshot:
        raise SearchInputError("cursor snapshot 时间戳不规范")
    if snapshot_datetime > datetime.now(timezone.utc) + timedelta(seconds=5):
        raise SearchInputError("cursor snapshot 不得来自未来")
    return payload


def _comes_after(hit: dict[str, Any], last: dict[str, Any]) -> bool:
    if hit["_rank"] != last["rank"]:
        return hit["_rank"] > last["rank"]
    hit_created = hit.get("_created_order")
    last_created = _timestamp_order_value(last["created_at"])
    if hit_created != last_created:
        return hit_created < last_created
    return hit["id"] > last["id"]
