"""case_table_50.xlsx 再生脚本（防二进制文件腐化，可随时重建核对）。

完全确定性（无随机）：50 个数据行 = 45 个合法 case + 3 个 mock 包线失败注入行
（altitude_m > 15000，行 10/25/40）+ 2 个解析行级错误行（行 15 mach 缺值、
行 33 power_kw 非数值）。期望口径见 case_001.json。

用法（仓根）：
    python3 agents/performance_disk_agent/eval_cases/generate_case_table.py
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent / "case_table_50.xlsx"

# 失败注入行（1-based 数据行序号 → altitude_m 覆盖值，均 > 15000 触发 mock 包线）
ENVELOPE_FAIL_ROWS = {10: 16000, 25: 17500, 40: 18200}
# 解析行级错误行：15 = mach 缺值；33 = power_kw 非数值
MISSING_MACH_ROW = 15
BAD_POWER_ROW = 33


def build_rows() -> list[list]:
    rows: list[list] = []
    for i in range(1, 51):
        case_id = f"case_{i:03d}"
        altitude = 2000 + (i * 137) % 9000          # 2000..10999，全部 < 15000
        mach = round(0.1 + (i % 7) * 0.08, 2)        # 0.10..0.58
        power = 500 + (i * 53) % 1500                # 500..1999

        if i in ENVELOPE_FAIL_ROWS:
            altitude = ENVELOPE_FAIL_ROWS[i]
        row: list = [case_id, altitude, mach, power]
        if i == MISSING_MACH_ROW:
            row[2] = None
        if i == BAD_POWER_ROW:
            row[3] = "not_a_number"
        rows.append(row)
    return rows


def main() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "cases"
    ws.append(["case_id", "altitude_m", "mach", "power_kw"])
    for row in build_rows():
        ws.append(row)
    wb.save(OUT)
    print(f"已生成：{OUT}（50 数据行 = 45 合法 + 3 包线失败注入 + 2 解析错误行）")


if __name__ == "__main__":
    main()
