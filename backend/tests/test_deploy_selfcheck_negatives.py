"""部署自检门「负例咬合」证据（M12-3）。

部署门（scripts/deploy_selfcheck.py）是内网上线前唯一的运行时形态闸——它每一项
都是 fail-closed 判定。但**「PASS 会亮绿」不证明「FAIL 会亮红」**：一个恒返 True 的
坏检查也能让 12/12 全绿。本文件为每一项检查补**失败路径咬合**：构造该项应当拒绝的
部署形态，断言 `check.ok is False`（且原因文案指向真实症结）——否则某项检查静默腐烂成
恒真时无人察觉，正是宪法「全绿无咬合实证=假信心」。

既有 test_deploy_selfcheck.py 只覆盖 check_model_gateway_config；本文件补齐其余检查。
纯 stdlib + 临时库/monkeypatch，不起服务。安全 gate 判定一律 `is False`，不认 truthiness。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.storage.db import get_conn, init_db
from scripts import deploy_selfcheck


# ---------- 夹具 ----------

def _valid_db(tmp_path: Path) -> Path:
    """一个 init_db 建好的合规库（全表 + classification 列 + worker_heartbeats 表）。"""
    db = tmp_path / "flai_os.db"
    init_db(db)
    return db


def _insert_beat(db: Path, *, generation: str, last_beat_at: str) -> None:
    conn = get_conn(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO worker_heartbeats"
            " (worker_id, generation, detail, started_at, last_beat_at)"
            " VALUES ('default', ?, NULL, ?, ?)",
            (generation, last_beat_at, last_beat_at),
        )
        conn.commit()
    finally:
        conn.close()


def _fake_http(monkeypatch, *, status: int = 200, payload: dict | None = None,
               body: bytes | None = None, raises: Exception | None = None) -> None:
    def fake_get(url: str):
        if raises is not None:
            raise raises
        if body is not None:
            return status, body
        return status, json.dumps(payload or {}).encode("utf-8")

    monkeypatch.setattr(deploy_selfcheck, "_http_get", fake_get)


# ---------- 1. check_db_file ----------

def test_db_file_missing_fails(tmp_path: Path) -> None:
    c = deploy_selfcheck.check_db_file(tmp_path / "nope.db")
    assert c.ok is False
    assert "未找到" in c.detail


def test_db_file_present_passes(tmp_path: Path) -> None:
    p = tmp_path / "x.db"
    p.write_bytes(b"")
    assert deploy_selfcheck.check_db_file(p).ok is True


# ---------- 2. check_tables ----------

def test_tables_missing_one_fails(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        conn.execute("DROP TABLE feedback")
        conn.commit()
        c = deploy_selfcheck.check_tables(conn)
    finally:
        conn.close()
    assert c.ok is False
    assert "feedback" in c.detail


def test_tables_empty_db_fails(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    try:
        c = deploy_selfcheck.check_tables(conn)
    finally:
        conn.close()
    assert c.ok is False


def test_tables_all_present_passes(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        assert deploy_selfcheck.check_tables(conn).ok is True
    finally:
        conn.close()


# ---------- 3. check_active_user ----------

def test_active_user_none_fails(tmp_path: Path) -> None:
    """init_db 不建账户——users 空是 fail-closed 的有意判定（ADR-0019 D9）。"""
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        c = deploy_selfcheck.check_active_user(conn)
    finally:
        conn.close()
    assert c.ok is False
    assert "user_admin.py create" in c.detail


def test_active_user_only_inactive_fails(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, created_at)"
            " VALUES ('ghost', 'Ghost', 'x', 'admin', 0, ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        c = deploy_selfcheck.check_active_user(conn)
    finally:
        conn.close()
    assert c.ok is False, "停用账户不计数——只有 is_active=1 才算"


def test_active_user_present_passes(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, created_at)"
            " VALUES ('jerry', 'Jerry', 'x', 'admin', 1, ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        assert deploy_selfcheck.check_active_user(conn).ok is True
    finally:
        conn.close()


# ---------- 4. check_classification_axis ----------

def test_classification_axis_missing_column_fails(tmp_path: Path) -> None:
    """旧代际库的 files/samples 无 classification 列——分级轴根本不存在。"""
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE files (id TEXT)")
        conn.execute("CREATE TABLE samples (id TEXT)")
        conn.commit()
        c = deploy_selfcheck.check_classification_axis(conn)
    finally:
        conn.close()
    assert c.ok is False
    assert "files" in c.detail and "samples" in c.detail


def test_classification_axis_present_passes(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    conn = get_conn(db)
    try:
        assert deploy_selfcheck.check_classification_axis(conn).ok is True
    finally:
        conn.close()


# ---------- 5. check_worker_generation（代际见证——五种失败模式全咬） ----------

def _run_worker_gen(db: Path):
    conn = get_conn(db)
    try:
        return deploy_selfcheck.check_worker_generation(conn)
    finally:
        conn.close()


def test_worker_gen_no_row_fails(tmp_path: Path) -> None:
    """worker 未启动（无心跳行）——部署顺序错或旧代码不写心跳，必 FAIL。"""
    assert _run_worker_gen(_valid_db(tmp_path)).ok is False


def test_worker_gen_wrong_generation_fails(tmp_path: Path) -> None:
    """心跳新鲜但代际是旧串——worker 没重启到新代码，洗白派生分级的正是这个洞。"""
    db = _valid_db(tmp_path)
    _insert_beat(db, generation="m0-ancient-generation",
                 last_beat_at=datetime.now(timezone.utc).isoformat())
    c = _run_worker_gen(db)
    assert c.ok is False
    assert deploy_selfcheck.WORKER_GENERATION in c.detail


def test_worker_gen_stale_beat_fails(tmp_path: Path) -> None:
    """代际对但心跳 120s 前——worker 已死/挂起，超 60s 窗口必 FAIL。"""
    db = _valid_db(tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    _insert_beat(db, generation=deploy_selfcheck.WORKER_GENERATION, last_beat_at=stale)
    assert _run_worker_gen(db).ok is False


def test_worker_gen_naive_timestamp_fails(tmp_path: Path) -> None:
    """无时区（naive）时间戳——无法安全比较年龄，fail-closed 拒。"""
    db = _valid_db(tmp_path)
    naive = datetime.now().replace(microsecond=0).isoformat()  # 无 tzinfo
    _insert_beat(db, generation=deploy_selfcheck.WORKER_GENERATION, last_beat_at=naive)
    c = _run_worker_gen(db)
    assert c.ok is False
    assert "naive" in c.detail or "时区" in c.detail


def test_worker_gen_malformed_timestamp_fails(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    _insert_beat(db, generation=deploy_selfcheck.WORKER_GENERATION, last_beat_at="不是时间戳")
    assert _run_worker_gen(db).ok is False


def test_worker_gen_fresh_and_current_passes(tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    _insert_beat(db, generation=deploy_selfcheck.WORKER_GENERATION,
                 last_beat_at=datetime.now(timezone.utc).isoformat())
    assert _run_worker_gen(db).ok is True


# ---------- 6. check_db_identity（库身份一致——服务侧=探针侧） ----------

def _local_fp(db: Path) -> str:
    return deploy_selfcheck._db_path_fingerprint(db)


def test_db_identity_mismatch_fails(monkeypatch, tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    _fake_http(monkeypatch, payload={"db_identity": "deadbeefdeadbeef"})
    c = deploy_selfcheck.check_db_identity("http://x", db)
    assert c.ok is False
    assert _local_fp(db) in c.detail  # 探针侧指纹如实报出


def test_db_identity_missing_field_fails(monkeypatch, tmp_path: Path) -> None:
    """旧服务 health 无 db_identity 字段——无法证明库一致，fail-closed。"""
    db = _valid_db(tmp_path)
    _fake_http(monkeypatch, payload={"status": "ok"})
    assert deploy_selfcheck.check_db_identity("http://x", db).ok is False


def test_db_identity_unreachable_fails(monkeypatch, tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    _fake_http(monkeypatch, raises=OSError("connection refused"))
    assert deploy_selfcheck.check_db_identity("http://x", db).ok is False


def test_db_identity_match_passes(monkeypatch, tmp_path: Path) -> None:
    db = _valid_db(tmp_path)
    _fake_http(monkeypatch, payload={"db_identity": _local_fp(db)})
    assert deploy_selfcheck.check_db_identity("http://x", db).ok is True


# ---------- 7. check_health ----------

def test_health_non_200_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, status=503, payload={"status": "ok"})
    assert deploy_selfcheck.check_health("http://x").ok is False


def test_health_non_json_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, status=200, body=b"<html>not json</html>")
    assert deploy_selfcheck.check_health("http://x").ok is False


def test_health_status_not_ok_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, status=200, payload={"status": "degraded"})
    assert deploy_selfcheck.check_health("http://x").ok is False


def test_health_unreachable_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, raises=OSError("refused"))
    assert deploy_selfcheck.check_health("http://x").ok is False


def test_health_ok_passes(monkeypatch) -> None:
    _fake_http(monkeypatch, status=200, payload={"status": "ok", "agents": 6, "tools": 5})
    assert deploy_selfcheck.check_health("http://x").ok is True


# ---------- 8. check_live_classification_generation（is True 纪律） ----------

def test_live_classification_false_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"classification_axis": False})
    assert deploy_selfcheck.check_live_classification_generation("http://x").ok is False


def test_live_classification_missing_fails(monkeypatch) -> None:
    """旧进程 health 无此标记——库可能已迁移但服务没重启到新代码。"""
    _fake_http(monkeypatch, payload={"status": "ok"})
    assert deploy_selfcheck.check_live_classification_generation("http://x").ok is False


def test_live_classification_truthy_not_true_fails(monkeypatch) -> None:
    """is True 纪律：字符串 'true'/整数 1 等 truthy 值不算——只认布尔真。"""
    for truthy in ("true", 1, "1"):
        _fake_http(monkeypatch, payload={"classification_axis": truthy})
        c = deploy_selfcheck.check_live_classification_generation("http://x")
        assert c.ok is False, f"classification_axis={truthy!r} 是 truthy 非 True，必 FAIL"


def test_live_classification_true_passes(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"classification_axis": True})
    assert deploy_selfcheck.check_live_classification_generation("http://x").ok is True


# ---------- 9. check_live_created_by_username_generation（迁移 #9 代际, is True） ----------

def test_live_username_axis_false_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"created_by_username_axis": False})
    assert deploy_selfcheck.check_live_created_by_username_generation("http://x").ok is False


def test_live_username_axis_missing_fails(monkeypatch) -> None:
    """旧 API health 无此标记——库可能已补列（迁移 #9）但 API 未重启到新代码，
    该窗口内旧 API 会造无归因 user 任务，必 FAIL 逼 operator 重启 API。"""
    _fake_http(monkeypatch, payload={"status": "ok", "classification_axis": True})
    assert deploy_selfcheck.check_live_created_by_username_generation("http://x").ok is False


def test_live_username_axis_truthy_not_true_fails(monkeypatch) -> None:
    """is True 纪律：truthy 非布尔真一律 FAIL（安全 gate 铁律）。"""
    for truthy in ("true", 1, "1"):
        _fake_http(monkeypatch, payload={"created_by_username_axis": truthy})
        c = deploy_selfcheck.check_live_created_by_username_generation("http://x")
        assert c.ok is False, f"created_by_username_axis={truthy!r} 是 truthy 非 True，必 FAIL"


def test_live_username_axis_true_passes(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"created_by_username_axis": True})
    assert deploy_selfcheck.check_live_created_by_username_generation("http://x").ok is True


# ---- 8c. check_live_eval_snapshot_generation（T2/#5 快照代际, is True, Codex R0-P1）----

def test_live_eval_snapshot_axis_false_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"eval_snapshot_axis": False})
    assert deploy_selfcheck.check_live_eval_snapshot_generation("http://x").ok is False


def test_live_eval_snapshot_axis_missing_fails(monkeypatch) -> None:
    """旧 API health 无此标记——库可能已迁出 eval_snapshots+worker 已更新，但 API 仍是
    T1 旧码不冻结快照；该窗口内旧 API 入队无 handle 的 run、worker 回退活磁盘执行，
    不可变保证静默失效，必 FAIL 逼 operator 重启 API。"""
    _fake_http(monkeypatch, payload={"status": "ok", "classification_axis": True})
    assert deploy_selfcheck.check_live_eval_snapshot_generation("http://x").ok is False


def test_live_eval_snapshot_axis_truthy_not_true_fails(monkeypatch) -> None:
    """is True 纪律：truthy 非布尔真一律 FAIL（安全 gate 铁律）。"""
    for truthy in ("true", 1, "1"):
        _fake_http(monkeypatch, payload={"eval_snapshot_axis": truthy})
        c = deploy_selfcheck.check_live_eval_snapshot_generation("http://x")
        assert c.ok is False, f"eval_snapshot_axis={truthy!r} 是 truthy 非 True，必 FAIL"


def test_live_eval_snapshot_axis_true_passes(monkeypatch) -> None:
    _fake_http(monkeypatch, payload={"eval_snapshot_axis": True})
    assert deploy_selfcheck.check_live_eval_snapshot_generation("http://x").ok is True


# ---------- 9. check_auth_generation（default-deny 见证） ----------

def test_auth_generation_200_fails(monkeypatch) -> None:
    """未认证拿到 200 = 鉴权中间件缺位，API 裸奔——最坏结果必 FAIL。"""
    _fake_http(monkeypatch, status=200, body=b"[]")
    c = deploy_selfcheck.check_auth_generation("http://x")
    assert c.ok is False
    assert "裸奔" in c.detail


def test_auth_generation_404_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, status=404, body=b"")
    assert deploy_selfcheck.check_auth_generation("http://x").ok is False


def test_auth_generation_unreachable_fails(monkeypatch) -> None:
    _fake_http(monkeypatch, raises=OSError("refused"))
    assert deploy_selfcheck.check_auth_generation("http://x").ok is False


def test_auth_generation_401_passes(monkeypatch) -> None:
    _fake_http(monkeypatch, status=401, body=b"")
    assert deploy_selfcheck.check_auth_generation("http://x").ok is True


# ---------- 10. check_frontend_dist ----------

def test_frontend_dist_missing_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deploy_selfcheck.config, "FRONTEND_DIST_DIR", tmp_path / "dist")
    assert deploy_selfcheck.check_frontend_dist().ok is False


def test_frontend_dist_present_passes(monkeypatch, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(deploy_selfcheck.config, "FRONTEND_DIST_DIR", dist)
    assert deploy_selfcheck.check_frontend_dist().ok is True


# ---------- 11. check_writable_dirs ----------

def test_writable_dirs_unwritable_fails(monkeypatch, tmp_path: Path) -> None:
    """目录祖先是文件 → mkdir(parents) 抛 NotADirectoryError（OSError）→ FAIL。
    比 chmod 更跨平台可靠（Windows 无 POSIX 权限位）。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr(deploy_selfcheck.config, "UPLOADS_DIR", blocker / "sub")
    monkeypatch.setattr(deploy_selfcheck.config, "TASK_RUNS_DIR", tmp_path / "ok_runs")
    c = deploy_selfcheck.check_writable_dirs()
    assert c.ok is False


def test_writable_dirs_writable_passes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deploy_selfcheck.config, "UPLOADS_DIR", tmp_path / "up")
    monkeypatch.setattr(deploy_selfcheck.config, "TASK_RUNS_DIR", tmp_path / "runs")
    assert deploy_selfcheck.check_writable_dirs().ok is True
