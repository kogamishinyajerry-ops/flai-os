"""performance_disk_agent workflow：批量 case 计算的标准作业流（M3，Mock 阶段）。

流程：解析首个输入文件 → 逐 case 调用 performance_disk_mock（单 case 失败/异常
折叠为该 case failed，继续下一个，docs/05 §5）→ 三产物落 output_dir
（samples.jsonl / result_summary.xlsx / task_report.md，由 Runtime 自动注册为
输出文件）→ 返回 output_schema.json 合规摘要。

批量作业语义（ADR-0010）：只要解析成功且汇总写出，任务即 success——
**即使全部 case 计算失败**（失败如实计入 failed_count 与报告）；解析失败/
零有效 case/汇总写出失败才 failed。

诚实标注：本 Agent 走 performance_disk_mock（mock=true），samples.jsonl 每行、
task_report.md 头部均携带 mock 声明（docs/03 §3 四落点）。

事件：本文件 event_logger 发出的自定义类型（parse_started/parse_finished/
cases_generated/case_started/case_finished/case_failed/summary_generated）
由 Runtime 统一折叠为 agent_log，原始类型保留在 payload.workflow_event_type
（ADR-0008 既定机制，事件枚举不因业务 Agent 膨胀）。

V0.1 无 LLM：model.profile=none，task_report.md 为模板化字符串拼接；
LLM 生成摘要/异常归纳是 V0.2 债（ADR-0010）。
"""

from __future__ import annotations

import json
import os
from typing import Any

_SUMMARY_XLSX = "result_summary.xlsx"
_SAMPLES_JSONL = "samples.jsonl"
_REPORT_MD = "task_report.md"


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def run(context: dict[str, Any]) -> dict[str, Any]:
    event_logger = context["event_logger"]
    tool_registry = context["tool_registry"]
    inputs = context.get("inputs") or {}
    files = context.get("files") or []
    output_dir = context["output_dir"]

    # ── 1) 输入文件（平台经 input_file_ids 注入 context.files，元素含落盘 path）──
    if not files:
        return _fail("无输入文件：请上传 case 表（.xlsx）后重试")
    case_file = files[0]

    # ── 2) 解析 ──────────────────────────────────────────────────────────
    event_logger.log("parse_started", {"filename": case_file.get("filename"), "file_id": case_file.get("id")})
    parser_payload: dict[str, Any] = {"file_path": case_file["path"]}
    if inputs.get("sheet_name"):
        parser_payload["sheet_name"] = inputs["sheet_name"]
    try:
        parse_result = tool_registry.call("excel_case_parser", parser_payload)
    except Exception as exc:  # noqa: BLE001 - 解析器调用本身炸了：任务级失败，如实上报
        return _fail(f"case 表解析调用失败：{exc.__class__.__name__}: {exc}")

    if parse_result.get("status") != "success":
        return _fail(f"case 表解析失败：{parse_result.get('error_message', '未知原因')}")

    cases = parse_result["cases"]
    row_errors = parse_result.get("errors", [])
    event_logger.log("parse_finished", {"case_count": len(cases), "row_error_count": len(row_errors)})
    event_logger.log("cases_generated", {"case_ids": [c["case_id"] for c in cases]})

    # ── 3) 逐 case 计算：单 case 失败/异常绝不摧毁任务 ───────────────────
    results: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["case_id"]
        params = case["params"]
        event_logger.log("case_started", {"case_id": case_id, "mock": True})
        record: dict[str, Any] = {
            "case_id": case_id, "params": params,
            "outputs": None, "status": "failed", "error_message": None,
        }
        try:
            calc = tool_registry.call(
                "performance_disk_mock", {"case_id": case_id, "params": params}
            )
            if calc.get("status") == "success":
                record["status"] = "success"
                record["outputs"] = calc["outputs"]
                event_logger.log("case_finished", {"case_id": case_id, "mock": True})
            else:
                record["error_message"] = calc.get("error_message", "工具返回失败态")
                event_logger.log(
                    "case_failed",
                    {"case_id": case_id, "error": record["error_message"], "mock": True},
                )
        except Exception as exc:  # noqa: BLE001 - 单 case 异常折叠，继续下一个（docs/05 §5）
            record["error_message"] = f"{exc.__class__.__name__}: {exc}"
            event_logger.log(
                "case_failed",
                {"case_id": case_id, "error": record["error_message"], "mock": True},
            )
        results.append(record)

    ok_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - ok_count

    # ── 4) 产物一：samples.jsonl（每行一个 case，mock 如实标注）───────────
    samples_path = os.path.join(output_dir, _SAMPLES_JSONL)
    with open(samples_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "case_id": r["case_id"],
                "inputs": r["params"],
                "outputs": r["outputs"],
                "status": r["status"],
                "error_message": r["error_message"],
                "mock": True,
            }, ensure_ascii=False) + "\n")

    # ── 5) 产物二：result_summary.xlsx（经 excel_summary_writer）──────────
    summary_path = os.path.join(output_dir, _SUMMARY_XLSX)
    try:
        write_result = tool_registry.call(
            "excel_summary_writer", {"cases": results, "output_path": summary_path}
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(f"汇总表写出调用失败：{exc.__class__.__name__}: {exc}")
    if write_result.get("status") != "success":
        return _fail(f"汇总表写出失败：{write_result.get('error_message', '未知原因')}")
    event_logger.log("summary_generated", {
        "file": _SUMMARY_XLSX, "ok_count": ok_count, "failed_count": failed_count,
    })

    # ── 6) 产物三：task_report.md（模板化字符串，V0.1 无 LLM）─────────────
    report_path = os.path.join(output_dir, _REPORT_MD)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(_render_report(results, row_errors, ok_count, failed_count))

    summary = {
        "total_cases": len(results),
        "ok_count": ok_count,
        "failed_count": failed_count,
        "row_errors": len(row_errors),
        "mock": True,
        "artifacts": [_SUMMARY_XLSX, _SAMPLES_JSONL, _REPORT_MD],
    }
    return {"status": "success", "outputs": [summary]}


def _render_report(
    results: list[dict[str, Any]],
    row_errors: list[dict[str, Any]],
    ok_count: int,
    failed_count: int,
) -> str:
    """纯 Python 字符串模板报告（无 LLM）。"""
    lines: list[str] = []
    lines.append("# 批量计算任务报告")
    lines.append("")
    lines.append("> **MOCK 声明**：本报告全部计算结果由 `performance_disk_mock`"
                 "（mock=true）纯虚构公式产生，与任何真实性能盘无关，**无任何工程"
                 "意义**，不得用于设计/校核/决策（宪法第五条诚实标注）。")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 有效 case 总数：{len(results)}")
    lines.append(f"- 计算成功：{ok_count}")
    lines.append(f"- 计算失败：{failed_count}")
    lines.append(f"- 解析阶段行级错误（已跳过）：{len(row_errors)}")
    lines.append("")

    executed = [r for r in results]
    if executed:
        lines.append("## 参数范围（有效 case）")
        lines.append("")
        for name in ("altitude_m", "mach", "power_kw"):
            values = [r["params"][name] for r in executed if name in r["params"]]
            if values:
                lines.append(f"- {name}：{min(values):g} ～ {max(values):g}")
        lines.append("")

    failed_cases = [r for r in results if r["status"] == "failed"]
    if failed_cases:
        lines.append("## 失败 case 清单")
        lines.append("")
        lines.append("| case_id | 失败原因 |")
        lines.append("|---|---|")
        for r in failed_cases:
            lines.append(f"| {r['case_id']} | {r['error_message']} |")
        lines.append("")

    if row_errors:
        lines.append("## 解析行级错误清单（未进入计算）")
        lines.append("")
        lines.append("| Excel 行号 | case_id | 错误 |")
        lines.append("|---|---|---|")
        for e in row_errors:
            lines.append(f"| {e.get('row')} | {e.get('case_id') or '—'} | {e.get('error')} |")
        lines.append("")

    lines.append("## 产物")
    lines.append("")
    lines.append(f"- `{_SUMMARY_XLSX}`：逐 case 结果汇总表")
    lines.append(f"- `{_SAMPLES_JSONL}`：样本沉淀（每行一个 case，含 mock 标注）")
    lines.append("")
    lines.append("*报告为模板化生成（V0.1 无 LLM 参与）。*")
    return "\n".join(lines) + "\n"
