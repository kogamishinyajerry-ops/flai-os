"""hello_agent workflow.py 的 M0 执行测试：eval_cases 不是摆设。

用 stub tool_registry / event_logger 直接驱动 run(context)，断言来源 =
agents/hello_agent/eval_cases/case_001.json（反审 P2-5：夹具必须被消费）。
M1 平台 Runtime 就绪后，本测试保留为 workflow 层回归，Runtime 层另测。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "agents/hello_agent"


def _load_workflow():
    spec = importlib.util.spec_from_file_location("hello_workflow", PKG / "workflow.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StubRegistry:
    """转发到真实 mock_echo adapter（先注册再调用的最小体现）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool_id: str, payload: dict) -> dict:
        from tools_impl.mock_tools.adapter import run as echo
        assert tool_id == "mock_echo", f"hello_agent 只白名单了 mock_echo，实调 {tool_id}"
        self.calls.append((tool_id, payload))
        return echo(payload)


class StubLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def log(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


def test_run_satisfies_eval_case_001(tmp_path) -> None:
    case = json.loads((PKG / "eval_cases/case_001.json").read_text(encoding="utf-8"))
    registry, logger = StubRegistry(), StubLogger()
    result = _load_workflow().run({
        "inputs": case["inputs"],
        "tool_registry": registry,
        "event_logger": logger,
        "output_dir": str(tmp_path),
    })
    assert result["status"] == "success"
    greeting = result["outputs"][0]["greeting"]
    assert case["expected"]["greeting_contains"] in greeting
    assert registry.calls, "必须经 Tool Registry 调工具（宪法铁律二）"
    assert logger.events, "必须产生事件（宪法铁律三：无事件=没发生）"
    assert (tmp_path / "hello_output.json").is_file(), "产物必须落盘 output_dir"


def test_run_without_registry_fails_honestly(tmp_path) -> None:
    """无 tool_registry 时必须诚实 failed，绝不伪造工具结果（宪法第五条）。"""
    result = _load_workflow().run({
        "inputs": {"name": "x"}, "tool_registry": None,
        "event_logger": None, "output_dir": str(tmp_path),
    })
    assert result["status"] == "failed"
    assert not (tmp_path / "hello_output.json").exists()
