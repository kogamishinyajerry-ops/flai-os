"""backlog_cli 一致性回归(ADR-0028「队列一致性」,Codex R0 四 finding 的钥匙)。

import 方式沿 test_m11_auth 的 `import scripts.backup_restore` 先例。
每个 witness 对应一条 R0 finding:回放源态校验 / 坏行 fail-closed /
空 --by 拒绝 / reconcile 孤儿清理。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import scripts.backlog_cli as cli


@pytest.fixture(autouse=True)
def backlog_dir(monkeypatch, tmp_path):
    d = tmp_path / "req_backlog"
    d.mkdir(parents=True)
    monkeypatch.setenv("FLAI_REQ_BACKLOG_DIR", str(d))
    yield d


def _write_rows(backlog_dir: Path, rows: list) -> None:
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows]
    (backlog_dir / "backlog.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _assessed(rid: str) -> dict:
    return {
        "kind": "assessed", "rid": rid, "at": "2026-07-15T08:00:00+00:00",
        "req_name": "样例需求", "submitter": "测试", "department": "测试科",
        "safety_effective": "B级", "weekly_saved": 1.0, "asset_hits": [],
        "status": "assessed", "card_file": "assessment_card.md",
    }


def _change(rid: str, frm: str, to: str) -> dict:
    return {"kind": "status_change", "rid": rid, "at": "2026-07-15T09:00:00+00:00",
            "from": frm, "to": to, "by": "测试", "note": ""}


# ── witness 1:回放源态校验(R0-P2 并发双写)────────────────────────────────


def test_replay_rejects_stale_from_state(backlog_dir) -> None:
    """两条都声称 from=queued 的并发事件:第一条生效,第二条源态已过期 → 坏行;
    折叠结果绝不出现 parked→in_progress 这类非法序列。"""
    _write_rows(backlog_dir, [
        _assessed("r1"),
        _change("r1", "assessed", "queued"),
        _change("r1", "queued", "parked"),        # 并发写 A:生效
        _change("r1", "queued", "in_progress"),   # 并发写 B:from 已过期,必须拒
    ])
    items, bad = cli._fold()
    assert items["r1"]["status"] == "parked", "先到的合法转移生效"
    assert bad == 1, "源态过期的并发事件必须按坏行计"


def test_replay_rejects_illegal_transition_even_with_matching_from(backlog_dir) -> None:
    """from 匹配但转移本身非法(delivered 是终态):回放层同样拒。"""
    _write_rows(backlog_dir, [
        _assessed("r1"),
        _change("r1", "assessed", "queued"),
        _change("r1", "queued", "in_progress"),
        _change("r1", "in_progress", "delivered"),
        _change("r1", "delivered", "queued"),  # 终态复活,非法
    ])
    items, bad = cli._fold()
    assert items["r1"]["status"] == "delivered"
    assert bad == 1


# ── witness 2:坏行 fail-closed(R0-P2)───────────────────────────────────


def test_set_status_refuses_when_ledger_has_bad_rows(backlog_dir, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1"), "{not-json"])
    rc = cli.main(["set-status", "r1", "queued", "--by", "严冬杰"])
    assert rc == 1
    assert "坏行" in capsys.readouterr().err
    rows = (backlog_dir / "backlog.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2, "拒绝写入:文件不得追加新行"


# ── witness 3:空 --by 拒绝(R0-P2 匿名穿透)──────────────────────────────


def test_set_status_rejects_blank_actor(backlog_dir, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1")])
    rc = cli.main(["set-status", "r1", "queued", "--by", "   "])
    assert rc == 1
    assert "不能为空" in capsys.readouterr().err


def test_reconcile_rejects_blank_actor(backlog_dir, tmp_path, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1")])
    rc = cli.main(["reconcile", "--by", "", "--db", str(tmp_path / "x.db")])
    assert rc == 1
    assert "不能为空" in capsys.readouterr().err


# ── witness 4:reconcile 孤儿清理(R0-P1 残余窗口)────────────────────────


def _make_task_db(path: Path, rows: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, status TEXT NOT NULL)")
    conn.executemany("INSERT INTO tasks (id, status) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_reconcile_cleans_orphans_only(backlog_dir, tmp_path, capsys) -> None:
    """failed 任务的活跃档案 → rejected;waiting_review 任务不动;
    不在库中的 rid 跳过并提示;终态档案不动。"""
    _write_rows(backlog_dir, [
        _assessed("t_failed"),
        _assessed("t_ok"),
        _assessed("t_alien"),
        _assessed("t_done"),
        _change("t_done", "assessed", "queued"),
        _change("t_done", "queued", "in_progress"),
        _change("t_done", "in_progress", "delivered"),
    ])
    db = tmp_path / "flai_os.db"
    _make_task_db(db, [
        ("t_failed", "failed"),
        ("t_ok", "waiting_review"),
        ("t_done", "failed"),  # 已 delivered 的档案即使任务 failed 也不动(终态)
    ])
    rc = cli.main(["reconcile", "--by", "严冬杰", "--db", str(db)])
    assert rc == 0
    out = capsys.readouterr()
    assert "清理 1 条" in out.out
    assert "t_alien" in out.err, "库中不存在的 rid 必须提示人工核查,绝不猜"

    items, bad = cli._fold()
    assert bad == 0, "对账写入的转移必须回放合法"
    assert items["t_failed"]["status"] == "rejected"
    assert "reconcile" in items["t_failed"]["last_change"]["note"]
    assert items["t_ok"]["status"] == "assessed"
    assert items["t_done"]["status"] == "delivered"


def test_reconcile_missing_db_fails(backlog_dir, tmp_path, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1")])
    rc = cli.main(["reconcile", "--by", "严冬杰", "--db", str(tmp_path / "nope.db")])
    assert rc == 1
    assert "任务库不存在" in capsys.readouterr().err


# ── witness 5(R1-P1):reconcile 缺省尊重 FLAI_DB_PATH ────────────────────


def test_reconcile_honors_flai_db_path(backlog_dir, tmp_path, monkeypatch, capsys) -> None:
    """部署机 export FLAI_DB_PATH 时,不带 --db 的 reconcile 必须打到该库,
    绝不能默认仓内陈旧库(错库对账会把活档案错杀成不可逆 rejected)。"""
    _write_rows(backlog_dir, [_assessed("t_failed")])
    db = tmp_path / "deployed.db"
    _make_task_db(db, [("t_failed", "failed")])
    monkeypatch.setenv("FLAI_DB_PATH", str(db))
    rc = cli.main(["reconcile", "--by", "严冬杰"])
    assert rc == 0
    assert "清理 1 条" in capsys.readouterr().out
    items, _bad = cli._fold()
    assert items["t_failed"]["status"] == "rejected"


# ── witness 6(R1-P2):跨进程写锁互斥 ─────────────────────────────────────


def test_write_lock_mutual_exclusion(backlog_dir, capsys) -> None:
    """锁文件被占(模拟并发的另一方):set-status 必须 fail-closed 退出,
    账本零写入;错误信息给出锁路径供人工核清崩溃遗留。"""
    _write_rows(backlog_dir, [_assessed("r1")])
    lock = backlog_dir / "backlog.jsonl.lock"
    lock.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["set-status", "r1", "queued", "--by", "严冬杰"])
    assert "写锁被占用" in str(exc_info.value)
    rows = (backlog_dir / "backlog.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1, "拿不到锁绝不写入"
    lock.unlink()
    assert cli.main(["set-status", "r1", "queued", "--by", "严冬杰"]) == 0, "锁释放后正常流转"
    assert not lock.exists(), "正常路径锁文件必须清理"


# ── witness 7(R1-P2):show 与 list 同一坏行警告契约 ──────────────────────


def test_show_reports_bad_rows(backlog_dir, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1"), "{not-json"])
    rc = cli.main(["show", "r1"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "1 条" in err and "队列行" in err, "show 的读者必须被告知账本有坏行"


# ── witness 8(R1-P2):坏库 fail-closed 且零写入 ──────────────────────────


def test_reconcile_corrupt_db_fails_zero_write(backlog_dir, tmp_path, capsys) -> None:
    _write_rows(backlog_dir, [_assessed("r1")])
    fake_db = tmp_path / "corrupt.db"
    fake_db.write_text("这不是 SQLite 文件", encoding="utf-8")
    rc = cli.main(["reconcile", "--by", "严冬杰", "--db", str(fake_db)])
    assert rc == 1
    assert "读取失败" in capsys.readouterr().err
    rows = (backlog_dir / "backlog.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1, "坏库诊断必须发生在任何账本写入之前(零写入)"


# ── witness 9(R2-P2 verbatim):懒查询下坏库仍必须被探针咬住 ──────────────


def test_reconcile_probes_db_even_with_terminal_only_ledger(backlog_dir, tmp_path, capsys) -> None:
    """队列全终态(循环零查询)+ 坏库:无条件探针仍须诊断退出,
    绝不返回 0 冒充『对账成功』。"""
    _write_rows(backlog_dir, [
        _assessed("t_done"),
        _change("t_done", "assessed", "rejected"),
    ])
    fake_db = tmp_path / "corrupt.db"
    fake_db.write_text("这不是 SQLite 文件", encoding="utf-8")
    rc = cli.main(["reconcile", "--by", "严冬杰", "--db", str(fake_db)])
    assert rc == 1
    assert "读取失败" in capsys.readouterr().err


def test_reconcile_probes_missing_tasks_table(backlog_dir, tmp_path, capsys) -> None:
    """合法 SQLite 但缺 tasks 表(旧库/错库):探针必须咬住。"""
    _write_rows(backlog_dir, [_assessed("t_done"), _change("t_done", "assessed", "rejected")])
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE misc (x TEXT)")
    conn.commit(); conn.close()
    rc = cli.main(["reconcile", "--by", "严冬杰", "--db", str(db)])
    assert rc == 1
    assert "读取失败" in capsys.readouterr().err


# ── witness 10(R2-P2 verbatim):show 在 rid 缺席时仍须报坏行 ─────────────


def test_show_warns_bad_rows_even_when_rid_missing(backlog_dir, capsys) -> None:
    """rid 的 assessed 行本身坏掉 → fold 后 rid 缺席:show 只报『不存在』会把
    账本损伤伪装成普通缺数据,坏行警告必须先于早退发出。"""
    broken_assessed = json.dumps(_assessed("r_broken"), ensure_ascii=False)[:-10]  # 截断成坏行
    _write_rows(backlog_dir, [broken_assessed])
    rc = cli.main(["show", "r_broken"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "rid 不存在" in err
    assert "队列行" in err, "坏行警告必须在缺席早退前发出"
