"""excel_summary_writer 单测：写出回读对账/计数口径/失败折叠。"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from tools_impl.excel_summary_writer.adapter import run

_CASES = [
    {
        "case_id": "case_001",
        "status": "success",
        "params": {"altitude_m": 1000.0, "mach": 0.3, "power_kw": 800.0},
        "outputs": {"shaft_power_kw": 700.0, "fuel_flow_kgps": 0.06, "egt_c": 450.0},
        "error_message": None,
    },
    {
        "case_id": "case_002",
        "status": "failed",
        "params": {"altitude_m": 16000.0, "mach": 0.5, "power_kw": 900.0},
        "outputs": None,
        "error_message": "超出 mock 包线",
    },
]


def test_write_then_read_back_rows_and_counts(tmp_path: Path) -> None:
    out = tmp_path / "result_summary.xlsx"
    result = run({"cases": _CASES, "output_path": str(out)})

    assert result["status"] == "success"
    assert result["file_path"] == str(out)
    assert result["ok_count"] == 1
    assert result["failed_count"] == 1
    assert out.is_file()

    ws = openpyxl.load_workbook(out)["result_summary"]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == (
        "case_id", "altitude_m", "mach", "power_kw",
        "shaft_power_kw", "fuel_flow_kgps", "egt_c", "status", "error_message",
    )
    assert len(rows) == 1 + len(_CASES)
    assert rows[1][0] == "case_001" and rows[1][7] == "success"
    assert rows[2][0] == "case_002" and rows[2][7] == "failed"
    assert rows[2][8] == "超出 mock 包线"
    # 失败 case 的输出列如实为空，绝不填伪造数值
    assert rows[2][4] is None and rows[2][5] is None and rows[2][6] is None


def test_empty_cases_writes_header_only(tmp_path: Path) -> None:
    out = tmp_path / "empty.xlsx"
    result = run({"cases": [], "output_path": str(out)})
    assert result["status"] == "success"
    assert result["ok_count"] == 0 and result["failed_count"] == 0
    ws = openpyxl.load_workbook(out).active
    assert len(list(ws.iter_rows(values_only=True))) == 1


def test_unwritable_output_path_folds_to_failed(tmp_path: Path) -> None:
    out = tmp_path / "no_such_dir" / "x.xlsx"  # 目录不存在
    result = run({"cases": _CASES, "output_path": str(out)})
    assert result["status"] == "failed"
    assert result["error_message"]
    assert not out.exists()
