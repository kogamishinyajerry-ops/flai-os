"""GC 债只读诊断：统计孤儿文件与疑似弃置会话，不做任何数据修改。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "flai_os.db"


class DiagnosticError(Exception):
    """数据库结构或内容不足以得出可靠诊断。"""


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return parsed


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _require_columns(conn: sqlite3.Connection, table: str, required: set[str]) -> None:
    columns = _table_columns(conn, table)
    if not columns:
        raise DiagnosticError(f"缺少表 {table}")
    missing = sorted(required - columns)
    if missing:
        raise DiagnosticError(f"表 {table} 缺少列：{', '.join(missing)}")


def _parse_file_ids(owner: str, field: str, raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"{owner} 的 {field} 不是有效 JSON 数组") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DiagnosticError(f"{owner} 的 {field} 必须是字符串数组")
    return value


def _conversation_attachment_ids(conn: sqlite3.Connection) -> set[str]:
    """导引会话附件的存续引用（conversation_messages.file_ids，ADR-0014/M7）。

    表或列不存在 = M6/M7 之前的旧 schema，彼时不存在会话附件，任务两列并集即完备；
    如实打印说明后返回空集，不把「无法观测」伪装成「已观测为零」之外的结论。
    """
    columns = _table_columns(conn, "conversation_messages")
    if not columns:
        print("会话附件引用：conversation_messages 表不存在（旧 schema，无会话附件可引用）")
        return set()
    if "file_ids" not in columns:
        print("会话附件引用：conversation_messages 缺 file_ids 列（M7 前 schema，无会话附件可引用）")
        return set()
    ids: set[str] = set()
    for row in conn.execute("SELECT id, file_ids FROM conversation_messages"):
        ids.update(_parse_file_ids(f"会话消息 {row['id']}", "file_ids", row["file_ids"]))
    return ids


def _report_orphan_files(conn: sqlite3.Connection) -> None:
    _require_columns(conn, "tasks", {"id", "input_file_ids", "output_file_ids"})
    _require_columns(conn, "files", {"id", "size_bytes"})

    referenced_ids: set[str] = set()
    for task in conn.execute("SELECT id, input_file_ids, output_file_ids FROM tasks"):
        owner = f"任务 {task['id']}"
        referenced_ids.update(_parse_file_ids(owner, "input_file_ids", task["input_file_ids"]))
        referenced_ids.update(_parse_file_ids(owner, "output_file_ids", task["output_file_ids"]))
    referenced_ids.update(_conversation_attachment_ids(conn))

    # 禁令：绝不使用 files.task_id 判定孤儿；输入附件的该列恒为 NULL。孤儿口径 =
    # files.id 不出现在【tasks.input_file_ids ∪ tasks.output_file_ids ∪
    # conversation_messages.file_ids】三个存续引用源的并集（漏掉会话附件会把
    # 在用附件误判为孤儿，Codex 互审 P1）。
    orphan_rows = [
        row
        for row in conn.execute("SELECT id, size_bytes FROM files ORDER BY id")
        if row["id"] not in referenced_ids
    ]
    total_bytes = sum(int(row["size_bytes"]) for row in orphan_rows)
    sample_ids = [row["id"] for row in orphan_rows[:10]]

    print(f"孤儿文件数量：{len(orphan_rows)}")
    print(f"孤儿文件合计字节：{total_bytes}")
    print(f"孤儿文件样例 id（最多 10 个）：{', '.join(sample_ids) if sample_ids else '（无）'}")


def _parse_utc_timestamp(conversation_id: str, raw: str) -> datetime:
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError) as exc:
        raise DiagnosticError(f"会话 {conversation_id} 的 updated_at 不是有效 ISO 时间：{raw!r}") from exc
    if parsed.tzinfo is None:
        raise DiagnosticError(f"会话 {conversation_id} 的 updated_at 缺少时区：{raw!r}")
    return parsed.astimezone(timezone.utc)


def _report_stale_conversations(conn: sqlite3.Connection, stale_days: int) -> None:
    _require_columns(conn, "conversations", {"id", "status", "updated_at"})
    _require_columns(conn, "tasks", {"conversation_id"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    candidates: list[tuple[datetime, str, str]] = []
    rows = conn.execute(
        """
        SELECT c.id, c.updated_at
        FROM conversations AS c
        WHERE c.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM tasks AS t WHERE t.conversation_id = c.id
          )
        """
    )
    for row in rows:
        updated_at = _parse_utc_timestamp(row["id"], row["updated_at"])
        if updated_at < cutoff:
            candidates.append((updated_at, row["id"], row["updated_at"]))
    candidates.sort(key=lambda item: (item[0], item[1]))

    print(f"陈旧阈值（UTC）：{cutoff.isoformat()}")
    print(f"疑似弃置会话数量：{len(candidates)}")
    if candidates:
        sample = ", ".join(f"{item[1]} (updated_at={item[2]})" for item in candidates[:10])
    else:
        sample = "（无）"
    print(f"疑似弃置会话样例（最多 10 个）：{sample}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="SQLite 文件路径；默认 data/flai_os.db")
    parser.add_argument("--stale-days", type=_non_negative_int, default=7, help="陈旧天数阈值（默认 7）")
    args = parser.parse_args(argv)

    db_path = Path(args.db).expanduser() if args.db else DEFAULT_DB_PATH
    if not db_path.is_file():
        print(f"数据库不存在：{db_path}")
        return 2

    print(f"数据库：{db_path.resolve()}")
    try:
        conn = _open_readonly(db_path)
    except sqlite3.Error as exc:
        print(f"只读打开数据库失败：{exc}")
        return 1

    exit_code = 0
    try:
        conn.execute("BEGIN")
        try:
            _report_orphan_files(conn)
        except (DiagnosticError, sqlite3.Error) as exc:
            print(f"孤儿文件：无法统计（{exc}）")
            exit_code = 1
        try:
            _report_stale_conversations(conn, args.stale_days)
        except (DiagnosticError, sqlite3.Error) as exc:
            print(f"疑似弃置会话：无法统计（{exc}）")
            exit_code = 1
    finally:
        conn.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
