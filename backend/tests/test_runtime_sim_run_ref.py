"""Runtime sim_run_ref 回填（P3.2 接缝，spec §4.3 挂账项落地）：
workflow 成功输出 outputs[0].sim_run_ref（module@run_id）→ Runtime 在成功
路径回填 task.metadata.sim_run_ref（经 repos.set_task_sim_run_ref，metadata
标注非状态迁移）。全链用真实 runtime.execute + 真实 cfd_solve_agent +
真实 cfd_solve_launch adapter（mock subprocess，无容器）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db

from backend.tests.test_runtime import _FakeModelGateway, _RealishToolRegistry

_AGENT_SCHEMA = CONTRACTS_DIR / "agent.schema.json"

RID = "20260713-101010"


def _make_runtime(tmp_path: Path) -> tuple[AgentRuntime, Path]:
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    registry = AgentRegistry(AGENTS_DIR, _AGENT_SCHEMA)
    registry.scan()
    assert registry.errors == [], f"意外的无效包：{registry.errors}"
    runtime = AgentRuntime(
        agent_registry=registry,
        tool_registry=_RealishToolRegistry(TOOLS_DIR),
        model_gateway=_FakeModelGateway(),
        conn_factory=lambda: get_conn(db_path),
        task_runs_dir=tmp_path / "task_runs",
        uploads_dir=tmp_path / "uploads",
    )
    return runtime, db_path


def _queue_task(db_path: Path, inputs: dict[str, Any]) -> str:
    conn = get_conn(db_path)
    try:
        task = repos.create_task(
            conn, task_id="task_cfd_1", agent_id="cfd_solve_agent", agent_version="0.1.0",
            name="CFD 求解", created_by="tester", inputs=inputs, input_file_ids=[], metadata={},
        )
        repos.set_task_status(conn, task["id"], "queued")
        repos.set_task_status(conn, task["id"], "validating")
        return task["id"]
    finally:
        conn.close()


def _cfd_env(monkeypatch, tmp_path: Path) -> None:
    case_root = tmp_path / "case_run"
    case_root.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    (template / "cyl2d.msh").write_text("$MeshFormat\n")
    for d in ("0", "constant", "system"):
        (template / d).mkdir()
    monkeypatch.setenv("FLAI_CFD_CONTAINER", "cfd-openfoam-live")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(case_root))
    monkeypatch.setenv("FLAI_CFD_TEMPLATE_DIR", str(template))


def _mock_docker(monkeypatch) -> None:
    """行为忠实替身（对齐 cfd_solve_launch R2 修复后的探测语义）：
    checkMesh → stdout 含 Mesh OK.；busy 扫（pgrep+grep -q '^run根/'）→ rc=1
    无活跃求解；launch（nohup … & echo $!）→ stdout 给 PID；alive PID 探测
    （readlink /proc/<pid>/cwd）→ rc=0 命中。"""
    import tools_impl.cfd_solve_launch.adapter as mod

    def fake_run(argv, **kw):
        joined = " ".join(str(a) for a in argv)

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        if "checkMesh" in joined:
            R.stdout = "... Mesh OK.\nEnd\n"
        elif "pgrep" in joined:
            R.returncode = 1  # busy 扫（唯一 pgrep 调用点）：无活跃求解
            R.stdout = ""
        elif "nohup" in joined:
            R.stdout = "4242\n"  # launch 回执 PID
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def test_sim_run_ref_backfilled_on_success(monkeypatch, tmp_path: Path) -> None:
    _cfd_env(monkeypatch, tmp_path)
    _mock_docker(monkeypatch)
    runtime, db_path = _make_runtime(tmp_path)
    task_id = _queue_task(db_path, {"case": "cylinder_re100", "run_id": RID})

    result = runtime.execute(task_id)

    assert result["status"] == "completed"
    conn = get_conn(db_path)
    try:
        task = repos.get_task(conn, task_id)
        ref = (task.get("metadata") or {}).get("sim_run_ref")
        assert ref is not None, "成功路径必须回填 metadata.sim_run_ref"
        assert ref["module"] == "cfd_openfoam"
        assert ref["run_id"] == RID
    finally:
        conn.close()


def test_no_backfill_on_launch_failure(monkeypatch, tmp_path: Path) -> None:
    # 发起失败（config 缺失 fail-closed）→ 任务 failed，metadata 不得出现 sim_run_ref
    monkeypatch.delenv("FLAI_CFD_CONTAINER", raising=False)
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    monkeypatch.delenv("FLAI_CFD_TEMPLATE_DIR", raising=False)
    runtime, db_path = _make_runtime(tmp_path)
    task_id = _queue_task(db_path, {"case": "cylinder_re100", "run_id": RID})

    result = runtime.execute(task_id)

    assert result["status"] == "failed"
    conn = get_conn(db_path)
    try:
        task = repos.get_task(conn, task_id)
        assert (task.get("metadata") or {}).get("sim_run_ref") is None
    finally:
        conn.close()


def test_malformed_sim_run_ref_not_backfilled(monkeypatch, tmp_path: Path) -> None:
    # 回填是 metadata 标注非承重：畸形 sim_run_ref → 不回填、记 warning 事件、
    # 不抛（错误方向=少标注，绝不因标注失败摧毁已成功的任务）。
    # 直接单元测 _backfill_sim_run_ref（runtime 经 importlib 独立加载 workflow，
    # monkeypatch agents.* 模块对 execute 全链不可达）。
    runtime, db_path = _make_runtime(tmp_path)
    task_id = _queue_task(db_path, {"case": "cylinder_re100", "run_id": RID})
    conn = get_conn(db_path)
    try:
        for bad in ("no-at-separator", "cfd_openfoam@../../etc",
                    f"cfd_openfoam@{RID}\n", "UPPER@20260713-101010", "@", ""):
            runtime._backfill_sim_run_ref(
                conn, task_id, "cfd_solve_agent",
                {"outputs": [{"sim_run_ref": bad}]},
            )
            task = repos.get_task(conn, task_id)
            assert (task.get("metadata") or {}).get("sim_run_ref") is None, f"畸形被回填：{bad!r}"
        # 合法值经同一入口正常回填（对照）
        runtime._backfill_sim_run_ref(
            conn, task_id, "cfd_solve_agent",
            {"outputs": [{"sim_run_ref": f"cfd_openfoam@{RID}"}]},
        )
        task = repos.get_task(conn, task_id)
        assert (task.get("metadata") or {}).get("sim_run_ref", {}).get("run_id") == RID
    finally:
        conn.close()
