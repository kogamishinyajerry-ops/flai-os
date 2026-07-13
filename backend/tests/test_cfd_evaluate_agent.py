"""cfd_evaluate_agent 全链（golden 夹具，stub model_gateway/tool_registry，无容器）：
确定性 St/Cd 落库 + 水印草案 + 未收敛路径不编造 St。自足：本仓 parser + golden。
"""
import json
from pathlib import Path

from agents.cfd_evaluate_agent.workflow import run as eval_run
from backend.app.cfd.cfd_log_parser import parse_force_coeffs

GOLDEN = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cfd_good_run"
          / "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat")


class _StubGateway:
    def chat(self, profile, messages):
        return {"content": "涡街稳定，St 与 Williamson 一致，建议采信。", "finish_reason": "stop"}


class _StubToolRegistry:
    """返回 good-run golden 的 Cl/Cd（本仓解析器）。"""

    def __init__(self, converged=True):
        self._converged = converged

    def call(self, tool_id, payload):
        assert tool_id == "cfd_result_read"
        fc = parse_force_coeffs(GOLDEN.read_text(errors="replace"))
        if self._converged:
            return {"status": "success", "run_id": payload["run_id"],
                    "cl_series": fc["cl"], "cd_series": fc["cd"], "t_series": fc["t"],
                    "resid_p_tail": [1e-6] * 20, "n_steps": 7500, "ended": True}
        # 未收敛路径：常值 Cl（未起振）→ oracle 应拒出 St
        n = len(fc["t"])
        return {"status": "success", "run_id": payload["run_id"],
                "cl_series": [0.5] * n, "cd_series": fc["cd"], "t_series": fc["t"],
                "resid_p_tail": [1e-1] * 20, "n_steps": 200, "ended": True}


class _Logger:
    def log(self, *a, **k):
        pass


def _ctx(tmp_path, converged=True):
    return {"inputs": {"run_id": "20260713-101010"}, "files": [], "output_dir": str(tmp_path),
            "event_logger": _Logger(), "tool_registry": _StubToolRegistry(converged),
            "model_gateway": _StubGateway(), "agent_config": {"model": {"profile": "reasoning"}}}


def test_evaluate_produces_deterministic_st_and_watermarked_draft(tmp_path):
    out = eval_run(_ctx(tmp_path))
    assert out["status"] == "success"
    ev = json.loads((tmp_path / "evaluation.json").read_text())
    assert ev["converged"] is True
    assert 0.15 < ev["st"] < 0.185
    assert ev["st_ref"] == 0.164
    draft = (tmp_path / "cfd_eval_draft.md").read_text()
    assert "AI 辅助" in draft and "判定权在人" in draft  # 强制水印


def test_unconverged_does_not_fabricate_st(tmp_path):
    out = eval_run(_ctx(tmp_path, converged=False))
    assert out["status"] == "success"  # 诚实草案仍产出，交人审
    ev = json.loads((tmp_path / "evaluation.json").read_text())
    assert ev["converged"] is False
    assert ev["st"] is None  # 未起振绝不编造
    assert ev["st_error_pct"] is None
    assert "未达评估条件" in ev["verdict"]


def _healthy_read(payload):
    fc = parse_force_coeffs(GOLDEN.read_text(errors="replace"))
    return {"status": "success", "run_id": payload["run_id"],
            "cl_series": fc["cl"], "cd_series": fc["cd"], "t_series": fc["t"],
            "resid_p_tail": [1e-2] * 20, "n_steps": 7500, "ended": True}


def test_high_residual_blocks_convergence_despite_cycles(tmp_path):
    # Codex R2-P1：sidecar 在场时 solver 可能已崩——周期够但残差爆，三门 AND 必须拒
    class _Reg:
        def call(self, tool_id, payload):
            out = _healthy_read(payload)
            out["resid_p_tail"] = [0.3] * 20  # >> tol 0.05（发散量级）
            return out

    ctx = _ctx(tmp_path)
    ctx["tool_registry"] = _Reg()
    out = eval_run(ctx)
    assert out["status"] == "success"  # 诚实草案仍产出交人审
    ev = json.loads((tmp_path / "evaluation.json").read_text())
    assert ev["converged"] is False
    assert ev["st"] is None  # 残差门未过绝不给 Williamson-consistent 数
    assert "残差门" in ev["verdict"]


def test_not_ended_blocks_convergence(tmp_path):
    # solver 仍在跑（ended=False）：周期/残差都好也未达评估条件
    class _Reg:
        def call(self, tool_id, payload):
            out = _healthy_read(payload)
            out["ended"] = False
            return out

    ctx = _ctx(tmp_path)
    ctx["tool_registry"] = _Reg()
    out = eval_run(ctx)
    ev = json.loads((tmp_path / "evaluation.json").read_text())
    assert ev["converged"] is False
    assert ev["st"] is None
    assert "收尾" in ev["verdict"]


def test_tool_failure_fails_honestly(tmp_path):
    class _FailReg:
        def call(self, tool_id, payload):
            return {"status": "failed", "error_message": "run 不存在"}
    ctx = _ctx(tmp_path)
    ctx["tool_registry"] = _FailReg()
    out = eval_run(ctx)
    assert out["status"] == "failed"  # 上游读取失败不伪造评估
