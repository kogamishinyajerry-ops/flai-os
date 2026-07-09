"""hello_agent 标准 workflow 骨架示例。

本文件演示 FLAi-OS Agent Package 的统一入口约定：
    def run(context: dict) -> dict

M0 阶段仅作字段/骨架示例，不接入真实 Runtime；M1 起由平台 Runtime
按 agent.yaml.workflow.entrypoint 动态加载并调用本函数。

`context` 为运行时注入的字典（鸭子类型，无需依赖尚未实现的平台模块），
约定至少包含以下键（详见 docs/02_Agent_Package_Standard.md）：
    - "inputs": dict          # 已通过 input_schema.json 校验的输入
    - "tool_registry": object # 提供 .call(tool_id: str, payload: dict) -> dict
    - "event_logger": object  # 提供 .log(event_type: str, payload: dict) -> None
    - "output_dir": str       # 本次运行专属的输出目录（工作区隔离）

返回值约定：
    {"status": "success" | "failed", "outputs": [ {...符合 output_schema.json} ]}
"""

from __future__ import annotations

import json
import os
from typing import Any


def run(context: dict[str, Any]) -> dict[str, Any]:
    """标准入口：读输入 -> 调工具 -> 记事件 -> 落盘 -> 返回结果。

    Args:
        context: 运行时上下文字典，字段见模块 docstring。

    Returns:
        包含 status 与 outputs 的结果字典。工具调用失败时 status="failed"，
        绝不向上抛出裸异常——由平台侧决定如何处理失败态。
    """
    event_logger = context.get("event_logger")
    inputs = context.get("inputs", {})
    tool_registry = context.get("tool_registry")
    output_dir = context.get("output_dir", ".")

    name = inputs.get("name", "")

    if event_logger is not None:
        event_logger.log("agent_started", {"agent_id": "hello_agent", "inputs": inputs})

    if tool_registry is None:
        # 骨架自证模式：无 tool_registry 时不调用工具，直接返回失败态，
        # 绝不伪造工具结果冒充真实调用。
        return {"status": "failed", "outputs": [], "error_message": "tool_registry 未注入"}

    tool_result = tool_registry.call("mock_echo", {"message": {"name": name}})

    if tool_result.get("status") != "success":
        if event_logger is not None:
            event_logger.log("agent_failed", {"agent_id": "hello_agent", "reason": tool_result})
        return {"status": "failed", "outputs": [], "error_message": "mock_echo 调用失败"}

    echoed = tool_result.get("echoed", {})
    greeting = f"你好，{name}！这是 hello_agent 的示例问候。"

    output = {"greeting": greeting, "echoed": echoed}

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "hello_output.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if event_logger is not None:
        event_logger.log("agent_completed", {"agent_id": "hello_agent", "output_path": output_path})

    return {"status": "success", "outputs": [output]}
