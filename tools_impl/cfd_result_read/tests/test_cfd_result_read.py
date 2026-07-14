"""cfd_result_read：golden 全链 + run_id 对账/目录穿越/缺 env 三重 fail-closed。
自足：用本仓 golden 夹具，零跨仓依赖。"""
import shutil
from pathlib import Path

from tools_impl.cfd_result_read.adapter import run

FIX = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "cfd_good_run"


def _seed(case_dir: Path, rid: str):
    (case_dir / ".hub_run_id").write_text(rid)


def test_reads_good_run(monkeypatch, tmp_path):
    rid = "20260713-101010"
    sub = tmp_path / rid
    shutil.copytree(FIX, sub)
    _seed(sub, rid)
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))  # = case/run 根
    out = run({"run_id": rid})
    assert out["status"] == "success"
    assert len(out["cl_series"]) > 20
    assert len(out["cd_series"]) == len(out["cl_series"])
    assert out["ended"] is True


def test_run_id_mismatch_fail_closed(monkeypatch, tmp_path):
    rid = "20260713-101010"
    sub = tmp_path / rid
    shutil.copytree(FIX, sub)
    _seed(sub, "20990101-000000")  # sidecar 与目录名/请求不符
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    out = run({"run_id": rid})
    assert out["status"] == "failed"  # 防读错 run


def test_run_id_traversal_rejected(monkeypatch, tmp_path):
    # 目录穿越：非 ^\d{8}-\d{6}$ 一律拒（先于任何路径拼接）
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    out = run({"run_id": "../../../etc"})
    assert out["status"] == "failed"


def test_missing_env_fail_closed(monkeypatch):
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    out = run({"run_id": "20260713-101010"})
    assert out["status"] == "failed"


def test_context_eval_fixtures_dir_preferred_over_env(monkeypatch, tmp_path):
    """#8/R2-1：eval 任务经任务级 context 注入材化 fixture 根，工具读**它**而非全局 env
    ——「评的就是晋升的那版」对工具读外部态的 agent 也成立。此处 env 指向空目录、context
    指向有夹具的目录，读到成功即证 context 优先。tamper：adapter 去掉 context 优先读 →
    读空 env 目录 → failed → RED。"""
    rid = "20260713-101010"
    frozen = tmp_path / "frozen"
    (frozen / rid).mkdir(parents=True)
    shutil.copytree(FIX, frozen / rid, dirs_exist_ok=True)
    _seed(frozen / rid, rid)
    empty_env = tmp_path / "empty"
    empty_env.mkdir()
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(empty_env))  # 活 env 指向空目录
    out = run({"run_id": rid}, {"eval_fixtures_dir": str(frozen)})
    assert out["status"] == "success", "context 提供的 fixture 根优先于全局 env"
    assert len(out["cl_series"]) > 20


def test_context_without_fixtures_dir_falls_back_to_env(monkeypatch, tmp_path):
    """普通任务（context 无 eval_fixtures_dir）回退全局 env——真实 CFD 运行语义不变。"""
    rid = "20260713-101010"
    sub = tmp_path / rid
    shutil.copytree(FIX, sub)
    _seed(sub, rid)
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    out = run({"run_id": rid}, {"task_id": "t1"})  # context 有 task_id 但无 eval_fixtures_dir
    assert out["status"] == "success", "无 eval_fixtures_dir 时回退活 env"


def test_ended_requires_final_nonempty_line_end(monkeypatch, tmp_path):
    # Codex R2-P1：ended 是收敛门——log 中段的 End（重启/损坏 log）不算收尾，
    # 只有末非空行全等 "End" 才算。
    rid = "20260713-101010"
    sub = tmp_path / rid
    shutil.copytree(FIX, sub)
    _seed(sub, rid)
    log = sub / "log.pimpleFoam"
    log.write_text(log.read_text(errors="replace")
                   + "\nTime = 151\nsmoothSolver:  Solving for Ux, Initial residual = 0.1\n")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    out = run({"run_id": rid})
    assert out["status"] == "success"
    assert out["ended"] is False  # End 在中段=重启过，不是正常收尾
