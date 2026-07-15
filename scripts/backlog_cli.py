# -*- coding: utf-8 -*-
"""需求待办队列管理 CLI(ADR-0028,requirement_intake_agent 配套)。

队列文件 data/requirement_backlog/backlog.jsonl 是 append-only 事件流:
- kind=assessed      —— requirement_intake_agent 评估后写入(建档)
- kind=status_change —— 本 CLI 写入(人工流转,必须 --by 具名:平台纪律
  「人是唯一签发者」在队列上的映射——匿名流转不可审计)

读取 = 按行序 fold:assessed 建档,status_change 依序覆盖 status。坏行跳过
但计数并在输出尾行提示(容错不静默)。本 CLI 绝不改写/删除已有行——历史
即台账。FLAI_REQ_BACKLOG_DIR 可重定向目录(与 workflow 同一约定)。

用法:
  python scripts/backlog_cli.py list [--status assessed]
  python scripts/backlog_cli.py show <rid>
  python scripts/backlog_cli.py set-status <rid> <to> --by 姓名 [--note 备注]
  python scripts/backlog_cli.py reconcile --by 姓名 [--db data/flai_os.db]

一致性纪律(Codex R0 审查落地):
- 回放校验源态:status_change 行的 from 必须等于该 rid 当前 folded 状态,
  不符即坏行(并发双写产生的"个体合法、序列非法"转移在回放层被拒)。
- 坏行 fail-closed:队列文件存在坏行时 set-status 拒绝写入(先修文件),
  只读命令(list/show)照常但醒目提示。
- reconcile 对账:workflow 在 run() 返回前登记,若之后 Runtime 侧失败
  (产物注册炸/进程死),任务 failed 而 assessed 行成孤儿——reconcile 只读
  任务库比对,把「任务已 failed 且队列仍活跃」的行补 status_change→rejected
  (残余窗口的机械清理路径,ADR-0028)。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKLOG_FILE = "backlog.jsonl"

# 状态机:assessed 起点;terminal = delivered / rejected。
_STATUSES = ("assessed", "queued", "in_progress", "parked", "delivered", "rejected")
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "assessed": frozenset({"queued", "parked", "rejected"}),
    "queued": frozenset({"in_progress", "parked", "rejected"}),
    "in_progress": frozenset({"delivered", "parked", "rejected"}),
    "parked": frozenset({"queued", "rejected"}),
    "delivered": frozenset(),
    "rejected": frozenset(),
}


def _backlog_path() -> Path:
    override = os.environ.get("FLAI_REQ_BACKLOG_DIR")
    base = Path(override) if override else _REPO_ROOT / "data" / "requirement_backlog"
    return base / _BACKLOG_FILE


def _default_db_path() -> str:
    """与 backend/app/config.py 的 DB_PATH 同一优先级:FLAI_DB_PATH 环境变量
    优先(Codex R1-P1:部署机 DB 不在仓内默认路径时,对账打到陈旧库会把活
    档案错杀成不可逆的 rejected),缺省仓内 data/flai_os.db。"""
    return os.environ.get("FLAI_DB_PATH") or str(_REPO_ROOT / "data" / "flai_os.db")


class _LedgerLock:
    """跨进程写锁(Codex R1-P2):set-status/reconcile 的 fold→append 必须
    互斥,否则两进程各自 fold 同一状态、双双 append 报成功,回放层把后到的
    判成坏行 → 账本进入 write-blocked。锁 = O_CREAT|O_EXCL 原子创建锁文件
    (POSIX/Windows 通吃,内网目标是 Windows);拿不到就 fail-closed 报重试,
    绝不带锁硬写。进程崩死遗留锁时错误信息给出锁路径供人工核清。"""

    def __init__(self, backlog_file: Path) -> None:
        self._path = backlog_file.with_suffix(backlog_file.suffix + ".lock")
        self._fd: int | None = None

    def __enter__(self) -> "_LedgerLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit(
                f"队列写锁被占用:{self._path}——另一个 set-status/reconcile 正在进行,"
                "稍后重试;若确认无并发操作(进程崩溃遗留),人工删除该锁文件后再试。"
            )
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._path.unlink(missing_ok=True)


def _fold() -> tuple[dict[str, dict], int]:
    """回放事件流 → {rid: 档案};返回 (档案表, 坏行数)。"""
    path = _backlog_path()
    items: dict[str, dict] = {}
    bad = 0
    if path.is_file() is False:
        return items, bad
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line == "":
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        kind = row.get("kind")
        rid = row.get("rid")
        if not isinstance(rid, str) or rid == "":
            bad += 1
            continue
        if kind == "assessed":
            if rid not in items:  # 幂等:重复 assessed 只认第一条
                items[rid] = dict(row)
        elif kind == "status_change":
            current = items.get(rid, {}).get("status")
            # 回放三重校验(Codex R0-P2):档案在 + 目标态合法 + **源态匹配当前
            # folded 状态**——并发双写各自"个体合法"的事件,序列上第二条的 from
            # 已过期,回放层拒绝,状态机不变量在读路径也成立。
            if (
                rid in items
                and row.get("to") in _STATUSES
                and row.get("from") == current
                and row.get("to") in _ALLOWED_TRANSITIONS.get(str(current), frozenset())
            ):
                items[rid]["status"] = row["to"]
                items[rid]["last_change"] = {
                    "at": row.get("at"), "by": row.get("by"), "note": row.get("note"),
                }
            else:
                bad += 1  # 无档案/非法目标/源态过期(并发写),一律坏行
        else:
            bad += 1
    return items, bad


def _age_days(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return "?"
    delta = datetime.now(timezone.utc) - then
    return str(max(delta.days, 0))


def cmd_list(args: argparse.Namespace) -> int:
    items, bad = _fold()
    rows = sorted(items.values(), key=lambda r: str(r.get("at", "")))
    if args.status:
        rows = [r for r in rows if r.get("status") == args.status]
    if len(rows) == 0:
        print("(队列为空)" if not args.status else f"(无 status={args.status} 的需求)")
    else:
        print(f"{'rid':<14} {'需求':<26} {'提出人':<8} {'安全':<6} {'省时h/周':<8} {'状态':<12} 龄期天")
        for r in rows:
            saved = r.get("weekly_saved")
            saved_s = f"{saved:.1f}" if isinstance(saved, (int, float)) else "-"
            print(
                f"{str(r.get('rid', ''))[:13]:<14} {str(r.get('req_name', ''))[:24]:<26} "
                f"{str(r.get('submitter', '')):<8} {str(r.get('safety_effective', '-')):<6} "
                f"{saved_s:<8} {str(r.get('status', '?')):<12} {_age_days(r.get('at'))}"
            )
    if bad > 0:
        print(f"⚠ 跳过 {bad} 条无法解析/非法的队列行(append-only 文件,人工核查勿手改)", file=sys.stderr)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    items, bad = _fold()
    item = items.get(args.rid)
    if item is None:
        print(f"rid 不存在:{args.rid}", file=sys.stderr)
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    if bad > 0:
        # 与 list 同一坏行警告契约(Codex R1-P2):show 的读者同样必须知道
        # 有转移被回放层拒掉、账本当前处于写保护。
        print(f"⚠ 跳过 {bad} 条无法解析/非法的队列行(账本写入已被保护,先人工核查)", file=sys.stderr)
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    by = args.by.strip()
    if by == "":
        # argparse required 只保证参数在场,拦不住 --by ""(Codex R0-P2:匿名穿透)。
        print("操作人不能为空:--by 必须是非空姓名(人是唯一签发者,匿名不可审计)", file=sys.stderr)
        return 1
    path = _backlog_path()
    # fold→append 全程持锁(Codex R1-P2):并发的另一方拿不到锁直接退出重试,
    # 不产生"个体成功、序列坏行"的账本损伤。
    with _LedgerLock(path):
        items, bad = _fold()
        if bad > 0:
            # 坏行=历史不完整,基于残缺历史写新转移只会加剧账本损伤(Codex R0-P2):
            # fail-closed,先人工核查文件再流转。
            print(f"队列文件存在 {bad} 条坏行,拒绝写入新流转——先人工核查 backlog.jsonl", file=sys.stderr)
            return 1
        item = items.get(args.rid)
        if item is None:
            print(f"rid 不存在:{args.rid}(先经 requirement_intake_agent 评估建档)", file=sys.stderr)
            return 1
        current = str(item.get("status", "assessed"))
        if args.to not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
            print(
                f"非法流转:{current} → {args.to}"
                f"(允许:{sorted(_ALLOWED_TRANSITIONS.get(current, frozenset())) or '无(终态)'})",
                file=sys.stderr,
            )
            return 1
        record = {
            "kind": "status_change",
            "rid": args.rid,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "from": current,
            "to": args.to,
            "by": by,
            "note": args.note or "",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{args.rid}: {current} → {args.to}(by {by})")
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    """对账清理(Codex R0-P1 残余窗口):workflow 在 run() 返回前登记待办,
    若之后 Runtime 侧失败(产物注册炸/进程死),任务 failed 而 assessed 行成
    孤儿。本命令**只读**任务库比对:队列中仍活跃(非终态)的 rid,任务库里
    已是 failed/cancelled → 补 status_change→rejected(note 注明对账来源)。
    任务库连不上/rid 不在库中一律跳过并提示,绝不猜。"""
    by = args.by.strip()
    if by == "":
        print("操作人不能为空:--by 必须是非空姓名", file=sys.stderr)
        return 1
    db_path = Path(args.db)
    if db_path.is_file() is False:
        print(f"任务库不存在:{db_path}(用 --db 指定 flai_os.db 路径,或 export FLAI_DB_PATH)", file=sys.stderr)
        return 1
    path = _backlog_path()
    # 两阶段(Codex R1-P2):阶段一全量只读收集,任何 sqlite 错误在写入任何
    # 账本行**之前**发生 → 干净 exit 1 零写入,绝不留半程对账;阶段二统一
    # append。全程持锁(与 set-status 互斥)。
    with _LedgerLock(path):
        items, bad = _fold()
        if bad > 0:
            print(f"队列文件存在 {bad} 条坏行,拒绝对账写入——先人工核查 backlog.jsonl", file=sys.stderr)
            return 1
        cleaned_plan: list[tuple[str, str, str]] = []  # (rid, from, 任务终态)
        skipped: list[str] = []
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # 只读,对账绝不写库
            try:
                for rid, item in sorted(items.items()):
                    if item.get("status") in ("delivered", "rejected"):
                        continue  # 终态不动
                    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (rid,)).fetchone()
                    if row is None:
                        skipped.append(rid)  # 库里没有(异地评估/库不同源):不猜,提示人工
                        continue
                    if row[0] in ("failed", "cancelled"):
                        cleaned_plan.append((rid, str(item.get("status")), str(row[0])))
            finally:
                conn.close()
        except sqlite3.Error as exc:
            # 坏库/非 SQLite 文件/缺 tasks 表:fail-closed 诊断而非 traceback
            # (Codex R1-P2),且发生在任何账本写入之前=零写入。
            print(f"任务库读取失败({db_path}):{exc}——对账取消,账本零写入", file=sys.stderr)
            return 1
        for rid, frm, task_state in cleaned_plan:
            record = {
                "kind": "status_change",
                "rid": rid,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "from": frm,
                "to": "rejected",
                "by": by,
                "note": f"reconcile:对应任务终态={task_state},孤儿档案清理(ADR-0028 残余窗口)",
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{rid}: {frm} → rejected(任务 {task_state},对账清理)")
    if skipped:
        print(f"⚠ {len(skipped)} 条 rid 不在任务库中,未动(人工核查):{'、'.join(skipped[:5])}", file=sys.stderr)
    print(f"对账完成:清理 {len(cleaned_plan)} 条孤儿档案")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="需求待办队列管理(ADR-0028)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出需求档案")
    p_list.add_argument("--status", choices=_STATUSES)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="查看单条档案(fold 后 JSON)")
    p_show.add_argument("rid")
    p_show.set_defaults(func=cmd_show)

    p_set = sub.add_parser("set-status", help="流转状态(须具名)")
    p_set.add_argument("rid")
    p_set.add_argument("to", choices=[s for s in _STATUSES if s != "assessed"])
    p_set.add_argument("--by", required=True, help="操作人姓名(人是唯一签发者,匿名不可审计)")
    p_set.add_argument("--note", default="")
    p_set.set_defaults(func=cmd_set_status)

    p_rec = sub.add_parser("reconcile", help="对账清理:任务已 failed 的孤儿档案 → rejected(只读任务库)")
    p_rec.add_argument("--by", required=True, help="执行对账的操作人姓名")
    p_rec.add_argument("--db", default=_default_db_path(),
                       help="任务库路径(只读打开;缺省尊重 FLAI_DB_PATH,与平台 config 同优先级)")
    p_rec.set_defaults(func=cmd_reconcile)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
