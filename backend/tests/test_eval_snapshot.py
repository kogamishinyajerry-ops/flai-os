"""T2 不可变评测快照（#5）存储原语。

eval_snapshots：handle=内容 sha256 的 insert-once 存储。二次写同 handle 绝不覆盖
（不可变；末尾 tamper：改 OR REPLACE 允许覆盖→RED）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


@pytest.fixture()
def conn_factory(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    def factory():
        return get_conn(db_path)

    return factory


def test_insert_snapshot_then_get_roundtrip(conn_factory) -> None:
    conn = conn_factory()
    try:
        repos.insert_eval_snapshot(conn, handle="h1", agent_id="a", agent_version="0.1.0",
                                   eval_cases_digest="d1", content_json='{"x":1}')
        snap = repos.get_eval_snapshot(conn, "h1")
    finally:
        conn.close()
    assert snap is not None
    assert snap["handle"] == "h1" and snap["content_json"] == '{"x":1}'
    assert snap["agent_version"] == "0.1.0" and snap["eval_cases_digest"] == "d1"


def test_get_missing_snapshot_returns_none(conn_factory) -> None:
    conn = conn_factory()
    try:
        assert repos.get_eval_snapshot(conn, "nope") is None
    finally:
        conn.close()


def test_snapshot_is_immutable_insert_once(conn_factory) -> None:
    """同 handle 二次写入（内容不同）绝不覆盖——不可变（tamper 改 OR REPLACE→RED）。"""
    conn = conn_factory()
    try:
        repos.insert_eval_snapshot(conn, handle="h", agent_id="a", agent_version="0.1.0",
                                   eval_cases_digest="d", content_json='{"frozen":true}')
        # 二次写同 handle 换内容（模拟 enqueue 重放 / 篡改尝试）
        repos.insert_eval_snapshot(conn, handle="h", agent_id="a", agent_version="9.9.9",
                                   eval_cases_digest="TAMPERED", content_json='{"frozen":false}')
        snap = repos.get_eval_snapshot(conn, "h")
    finally:
        conn.close()
    assert snap["content_json"] == '{"frozen":true}', "insert-once：二次写绝不覆盖冻结内容"
    assert snap["agent_version"] == "0.1.0" and snap["eval_cases_digest"] == "d"


REPO = Path(__file__).resolve().parents[2]


def _fresh_registry(tmp_path: Path):
    import shutil

    from backend.app.runtime.registry import AgentRegistry

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "hello_agent")
    reg = AgentRegistry(agents_dir, REPO / "contracts" / "agent.schema.json")
    reg.scan()
    assert reg.get("hello_agent") is not None
    return reg, agents_dir / "hello_agent"


def test_enqueue_freezes_snapshot_and_binds_run(conn_factory, tmp_path) -> None:
    """enqueue 冻结不可变快照 + run 绑 handle；快照含材化所需文件（workflow.py + cases）。"""
    import json as _json

    from backend.app.governance import eval_runner

    reg, _pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        run = eval_runner.enqueue_eval_run(
            conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t"
        )
        snap = repos.get_eval_snapshot(conn, run["snapshot_handle"])
    finally:
        conn.close()
    assert run["status"] == "queued"
    handle = run["snapshot_handle"]
    assert handle and handle.startswith("snap_"), "run 绑定内容派生 handle"
    assert snap is not None
    content = _json.loads(snap["content_json"])
    assert content["agent_id"] == "hello_agent"
    assert "workflow.py" in content["files"], "workflow.py 必冻结（runtime 显式加载执行）"
    assert "agent.yaml" in content["files"]
    assert any(k.startswith("eval_cases/") for k in content["files"]), "eval_cases 必冻结"


def test_enqueue_snapshot_is_content_derived_and_deduped(conn_factory, tmp_path) -> None:
    """同一活包两次 enqueue → 同 handle（内容派生）→ 快照去重到一行（insert-once）。"""
    from backend.app.governance import eval_runner

    reg, _pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        r1 = eval_runner.enqueue_eval_run(conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t")
        r2 = eval_runner.enqueue_eval_run(conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t")
        n = conn.execute("SELECT COUNT(*) FROM eval_snapshots").fetchone()[0]
    finally:
        conn.close()
    assert r1["snapshot_handle"] == r2["snapshot_handle"], "同活包→同内容派生 handle"
    assert r1["id"] != r2["id"], "两个不同 run 引用同一快照"
    assert n == 1, "内容派生 + insert-once → 快照去重到一行"


def test_materialized_snapshot_is_frozen_against_live_edits(conn_factory, tmp_path) -> None:
    """#5 核心：enqueue 冻结后改活磁盘包（case/workflow），材化快照得到的仍是冻结原文——
    执行读快照非活磁盘，enqueue 后改活包对该 run 无影响（materialization 层确定性验证）。"""
    import json as _json
    import tempfile as _tempfile

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        handle = eval_runner.freeze_eval_snapshot(conn, agent_registry=reg, agent_id="hello_agent")
        frozen_case = (pkg / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
        # enqueue 之后篡改活磁盘包
        (pkg / "eval_cases" / "case_001.json").write_text('{"MUTATED_LIVE": true}', encoding="utf-8")
        (pkg / "workflow.py").write_text("# MUTATED LIVE WORKFLOW\n", encoding="utf-8")
        snap = repos.get_eval_snapshot(conn, handle)
    finally:
        conn.close()

    content = _json.loads(snap["content_json"])
    with _tempfile.TemporaryDirectory() as td:
        eval_runner._materialize_snapshot(content, Path(td))
        mat_case = (Path(td) / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
        mat_wf = (Path(td) / "workflow.py").read_text(encoding="utf-8")
    assert "MUTATED_LIVE" not in mat_case and mat_case == frozen_case, "材化 case 是冻结原文"
    assert "MUTATED LIVE" not in mat_wf, "材化 workflow 是冻结原文，非活磁盘改动"
