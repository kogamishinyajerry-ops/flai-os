"""SQLite 备份/恢复演练（M11-B3：备份不演练=没有备份）。

用法（仓根）：
    python3 scripts/backup_restore.py backup   # 在线备份 → data/backups/，保留最近 14 份
    python3 scripts/backup_restore.py drill    # 备份 → tmp 恢复 → 完整性演练门（PASS 才算备份成立）
    python3 scripts/backup_restore.py restore <备份文件> <目标路径>   # 恢复（目标已存在则拒绝覆盖）

设计口径：
- 在线备份用 sqlite3 backup API（WAL 模式安全，不锁写者；绝不 cp 正在写的 db 文件——
  WAL 未 checkpoint 的页会丢）。
- 演练门 = 恢复到 tmp 后 ①PRAGMA integrity_check==ok ②表清单与源库一致
  ③governance 证据链三表（samples/eval_runs/promotions）行数与源库一致。
  任一不满足=FAIL（退出码 1），备份不算成立。
- 范围诚实声明：本脚本只备 DB。uploads/task_runs 文件目录一期走文件级同步
  （rsync/robocopy，见 README 运维段），不冒充已覆盖。
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_PATH = REPO / "data" / "flai_os.db"
BACKUP_DIR = REPO / "data" / "backups"
KEEP = 14
_EVIDENCE_TABLES = ("samples", "eval_runs", "promotions")


def _online_backup(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src))
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def _table_names(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _counts(db: Path, tables: tuple[str, ...]) -> dict[str, int]:
    conn = sqlite3.connect(str(db))
    try:
        out = {}
        for t in tables:
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                out[t] = -1  # 表不存在（老库）——如实记录，对账时以源库为准
        return out
    finally:
        conn.close()


def cmd_backup() -> int:
    if not DB_PATH.is_file():
        print(f"诚实失败：源库不存在 {DB_PATH}")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"flai_os-{stamp}.db"
    _online_backup(DB_PATH, dest)
    size = dest.stat().st_size
    print(f"备份完成：{dest}（{size} 字节）")
    olds = sorted(BACKUP_DIR.glob("flai_os-*.db"))
    for old in olds[:-KEEP]:
        old.unlink()
        print(f"轮转删除：{old.name}")
    print(f"当前保留 {min(len(olds), KEEP)} 份（上限 {KEEP}）")
    return 0


def cmd_drill() -> int:
    if not DB_PATH.is_file():
        print(f"诚实失败：源库不存在 {DB_PATH}")
        return 1
    with tempfile.TemporaryDirectory(prefix="flai_drill_") as td:
        restored = Path(td) / "restored.db"
        _online_backup(DB_PATH, restored)

        conn = sqlite3.connect(str(restored))
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        ok_integrity = integrity == "ok"

        src_tables = _table_names(DB_PATH)
        dst_tables = _table_names(restored)
        ok_tables = src_tables == dst_tables

        src_counts = _counts(DB_PATH, _EVIDENCE_TABLES)
        dst_counts = _counts(restored, _EVIDENCE_TABLES)
        ok_evidence = src_counts == dst_counts

        print(f"integrity_check: {integrity}")
        print(f"表清单一致: {ok_tables}（源 {len(src_tables)} 表）")
        print(f"证据链三表行数一致: {ok_evidence} {dst_counts}")
        passed = ok_integrity is True and ok_tables is True and ok_evidence is True
        print("DRILL " + ("PASS：备份-恢复环成立" if passed else "FAIL：备份不算成立，先修再信"))
        return 0 if passed else 1


def cmd_restore(backup_file: str, target: str) -> int:
    src = Path(backup_file)
    dest = Path(target)
    if not src.is_file():
        print(f"诚实失败：备份文件不存在 {src}")
        return 1
    if dest.exists():
        print(f"拒绝覆盖已存在目标：{dest}（恢复是高危动作，请先移走现库再恢复）")
        return 1
    try:
        _online_backup(src, dest)
        conn = sqlite3.connect(str(dest))
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            # 鉴权状态 fail-closed 对账（ADR-0019 / Codex R1 审 P1）：备份逐表原样
            # 恢复会连同旧 auth_sessions 一起复活——登出/停用/改密前的备份会让
            # 被盗但未过期的 token 或已撤销的凭据重新生效。恢复即清空全部会话，
            # 强制所有人重新登录（时间旅行回旧账户状态是恢复的固有语义，但绝不
            # 让旧活会话跟着复活）。表不存在（M11 前老备份）则 no-op。
            purged = 0
            try:
                purged = conn.execute("DELETE FROM auth_sessions").rowcount
                conn.commit()
            except sqlite3.OperationalError as exc:
                # 只放行「表不存在」（M11 前老备份，无会话可复活=安全，Codex R2 审
                # P1）；DELETE/commit 因磁盘满/锁失败绝不吞——否则谎报恢复成功而旧
                # 会话 token 仍活。真失败原样抛给外层 abort（坏产物 unlink）。
                if "no such table" not in str(exc).lower():
                    raise
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        dest.unlink(missing_ok=True)  # 坏恢复产物不留盘，防被误当可用库
        print(f"诚实失败：备份文件损坏，恢复中止（{exc}）")
        return 1
    print(f"恢复完成：{dest}，integrity_check={integrity}；已清空 {purged} 条恢复出的会话（强制重登）")
    return 0 if integrity == "ok" else 1


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "backup":
        return cmd_backup()
    if cmd == "drill":
        return cmd_drill()
    if cmd == "restore" and len(sys.argv) == 4:
        return cmd_restore(sys.argv[2], sys.argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
