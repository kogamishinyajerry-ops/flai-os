"""performance_disk_mock 单测：确定性/包线失败注入/mock 诚实标注。"""

from __future__ import annotations

from tools_impl.performance_disk_mock.adapter import run

_PARAMS = {"altitude_m": 5000.0, "mach": 0.5, "power_kw": 1000.0}


def test_success_output_shape_and_mock_flag() -> None:
    result = run({"case_id": "case_001", "params": dict(_PARAMS)})
    assert result["status"] == "success"
    assert result["mock"] is True, "mock 工具输出必须如实自标 mock=true（宪法第五条）"
    assert set(result["outputs"].keys()) == {"shaft_power_kw", "fuel_flow_kgps", "egt_c"}
    for v in result["outputs"].values():
        assert isinstance(v, float)


def test_deterministic_same_input_same_output() -> None:
    """确定性：同输入必同输出（纯代数，无随机/无时间依赖）。"""
    a = run({"params": dict(_PARAMS)})
    b = run({"params": dict(_PARAMS)})
    assert a == b


def test_envelope_failure_injection_above_15000() -> None:
    result = run({"params": {"altitude_m": 15001.0, "mach": 0.5, "power_kw": 1000.0}})
    assert result["status"] == "failed"
    assert result["mock"] is True
    assert "超出 mock 包线" in result["error_message"]
    assert "outputs" not in result, "失败时绝不附带任何伪造输出"


def test_envelope_boundary_15000_is_inside() -> None:
    """边界语义：> 15000 失败，= 15000 成功（README 声明口径）。"""
    result = run({"params": {"altitude_m": 15000.0, "mach": 0.5, "power_kw": 1000.0}})
    assert result["status"] == "success"


def test_bleed_flow_affects_outputs_deterministically() -> None:
    without = run({"params": dict(_PARAMS)})
    with_bleed = run({"params": {**_PARAMS, "bleed_flow_kgps": 2.0}})
    assert with_bleed["status"] == "success"
    assert with_bleed["outputs"] != without["outputs"]
