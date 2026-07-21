"""ax v0.1.18 stdout 的确定性解析。外部文本始终是数据，不是指令。"""

from __future__ import annotations

import json
from typing import Any


def parse_fetch_report(stdout: str) -> dict[str, Any]:
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ax fetch stdout 不是合法 JSON：{exc}") from exc
    if not isinstance(report, dict):
        raise ValueError("ax fetch stdout 顶层不是对象")
    return report


def parse_derived_output(
    *,
    operation: str,
    output_is_json: bool,
    stdout: str,
    stderr: str,
) -> tuple[Any, bool]:
    if output_is_json:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ax 派生 stdout 不是合法 JSON：{exc}") from exc
        data: Any = {"mode": "locate", "hits": parsed} if operation == "discover" else parsed
    else:
        data = {
            "mode": "outline",
            "lines": [line.strip() for line in stdout.splitlines() if line.strip()],
        }
    return data, "more result(s) hidden" in stderr
