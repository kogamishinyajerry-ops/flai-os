"""ax_web_extract 的固定 argv 构造。

调用方只能提交语义字段；二进制路径、输出路径和 ax flags 均由平台控制。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_fetch_args(
    *,
    url: str,
    raw_path: Path,
    max_bytes: int,
    timeout_seconds: float,
) -> list[str]:
    return [
        url,
        "--output",
        str(raw_path),
        "--max-bytes",
        str(max_bytes),
        "--max-time",
        str(timeout_seconds),
    ]


def build_derive_args(
    *,
    operation: str,
    payload: dict[str, Any],
    raw_path: Path,
    limit: int,
    budget_tokens: int,
) -> tuple[list[str], bool]:
    if operation == "extract":
        args = [str(raw_path), str(payload["selector"])]
        if isinstance(payload.get("row"), str):
            args.extend(["--row", str(payload["row"])])
        args.append("--json")
        output_is_json = True
    elif isinstance(payload.get("needle"), str):
        args = [str(raw_path), "--locate", str(payload["needle"])]
        output_is_json = True
    else:
        args = [str(raw_path), "--outline"]
        output_is_json = False
    args.extend(["--limit", str(limit), "--budget", str(budget_tokens)])
    return args, output_is_json
