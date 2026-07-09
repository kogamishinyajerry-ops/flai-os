"""mock_echo 工具适配器（mock=true，见 tool.yaml）。

契约：入参 payload 必含 message(object)；返回必含 status(success|failed)。
工具适配器**绝不抛裸异常**——一切失败折叠为 {"status": "failed", "error_message": ...}，
由 Job Runner 据此记 tool_failed 事件（单 case 失败不崩整个任务的地基）。
"""

from __future__ import annotations

from typing import Any


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context  # V0.1 未用；保留形参以符合 Tool Registry 调用约定
    if not isinstance(payload, dict) or "message" not in payload:
        return {
            "status": "failed",
            "echoed": {},
            "error_message": "入参缺少必填字段 message（见 tool.yaml input_schema）",
        }
    message = payload["message"]
    if not isinstance(message, dict):
        return {
            "status": "failed",
            "echoed": {},
            "error_message": f"message 必须是 object，实得 {type(message).__name__}",
        }
    return {"status": "success", "echoed": message}
