"""cfd_solve_agent workflow 单测（stub tool_registry，无容器）：
fire-and-register 输出 sim_run_ref / run_id 生成与注入 / 发起失败诚实传播。
"""
import re

from agents.cfd_solve_agent.workflow import run as solve_run

RID = "20260713-101010"


class _StubReg:
    def __init__(self):
        self.calls = []

    def call(self, tool_id, payload):
        self.calls.append((tool_id, payload))
        assert tool_id == "cfd_solve_launch"
        assert payload["case"] == "cylinder_re100"
        assert re.match(r"^\d{8}-\d{6}$", payload["run_id"])
        return {"status": "success", "run_id": payload["run_id"], "run_dir": "/x",
                "container": "cfd-openfoam-live", "checkmesh_ok": True,
                "launched_at": payload["run_id"]}


class _Logger:
    def log(self, *a, **k):
        pass


def _ctx(tmp_path, inputs):
    return {"inputs": inputs, "files": [], "output_dir": str(tmp_path),
            "event_logger": _Logger(), "tool_registry": _StubReg(),
            "agent_config": {"model": {"profile": "none"}}}


def test_solve_fire_and_register_with_injected_run_id(tmp_path):
    ctx = _ctx(tmp_path, {"case": "cylinder_re100", "run_id": RID})
    out = solve_run(ctx)
    assert out["status"] == "success"
    o = out["outputs"][0]
    assert o["run_id"] == RID
    assert o["sim_run_ref"] == f"cfd_openfoam@{RID}"
    assert "监控" in o.get("note", "")
    assert o["human_review_required"] is False


def test_solve_generates_timestamp_run_id_when_absent(tmp_path):
    ctx = _ctx(tmp_path, {"case": "cylinder_re100"})
    out = solve_run(ctx)
    assert out["status"] == "success"
    rid = out["outputs"][0]["run_id"]
    assert re.match(r"^\d{8}-\d{6}$", rid), f"生成的 run_id 须过 Tool 正则白名单：{rid!r}"
    assert out["outputs"][0]["sim_run_ref"] == f"cfd_openfoam@{rid}"


def test_launch_failure_propagates(tmp_path):
    class _BadReg:
        def call(self, t, p):
            return {"status": "failed", "error_message": "容器未就绪"}

    ctx = _ctx(tmp_path, {"case": "cylinder_re100", "run_id": RID})
    ctx["tool_registry"] = _BadReg()
    out = solve_run(ctx)
    assert out["status"] == "failed"
    assert "容器未就绪" in out["error_message"]


def test_end_time_passthrough(tmp_path):
    ctx = _ctx(tmp_path, {"case": "cylinder_re100", "run_id": RID, "end_time": 60})
    out = solve_run(ctx)
    assert out["status"] == "success"
    reg = ctx["tool_registry"]
    _, payload = reg.calls[0]
    assert payload["end_time"] == 60
