"""excel_summary_writer 适配器（mock=false，真实写文件）。

只忠实写出调用方给的 case 结果，不做任何计算/判断/过滤：
- 列序固定：case_id → 参数列（按 _PARAM_ORDER 中实际出现者）→ 输出列
  （按 _OUTPUT_ORDER 中实际出现者）→ status → error_message。
- ok_count/failed_count 用 `== "success"` / `== "failed"` 判定（安全 gate
  一律显式比较，不用 truthiness）。
- 适配器绝不抛裸异常（docs/03）：写盘失败折叠为 {"status":"failed", ...}。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PARAM_ORDER = ("altitude_m", "mach", "power_kw", "bleed_flow_kgps")
_OUTPUT_ORDER = ("shaft_power_kw", "fuel_flow_kgps", "egt_c")


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context  # V0.1 未用
    cases: list[dict[str, Any]] = payload["cases"]
    output_path = Path(payload["output_path"])

    param_cols = [
        p for p in _PARAM_ORDER
        if any(p in (c.get("params") or {}) for c in cases)
    ]
    output_cols = [
        o for o in _OUTPUT_ORDER
        if any(o in (c.get("outputs") or {}) for c in cases)
    ]

    try:
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "result_summary"
        ws.append(["case_id", *param_cols, *output_cols, "status", "error_message"])

        ok_count = 0
        failed_count = 0
        for case in cases:
            params = case.get("params") or {}
            outputs = case.get("outputs") or {}
            status = case.get("status")
            if status == "success":
                ok_count += 1
            else:
                failed_count += 1
            ws.append([
                case.get("case_id"),
                *[params.get(p) for p in param_cols],
                *[outputs.get(o) for o in output_cols],
                status,
                case.get("error_message"),
            ])

        wb.save(output_path)
    except Exception as exc:  # noqa: BLE001 - 契约要求绝不裸抛
        return {"status": "failed", "error_message": f"汇总表写出失败：{exc.__class__.__name__}: {exc}"}

    return {
        "status": "success",
        "file_path": str(output_path),
        "ok_count": ok_count,
        "failed_count": failed_count,
    }
