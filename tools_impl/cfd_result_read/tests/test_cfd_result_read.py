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
