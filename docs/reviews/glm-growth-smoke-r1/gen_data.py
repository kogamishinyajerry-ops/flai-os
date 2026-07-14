#!/usr/bin/env python3
"""GLM 生长烟测 R1 合成数据生成器（种子固定可复现；全部虚构，零真实工程数据）。

生成后自动重读文件计算真值（各通道超限次数），打印为判分 oracle。
"""
import csv
import math
import pathlib
import random
import sys

SEED = 20260713
CHANNELS = ["CH1", "CH2", "CH3", "CH4"]
BASE = {"CH1": 120.0, "CH2": 650.0, "CH3": 3.2, "CH4": 45.0}
AMP = {"CH1": 6.0, "CH2": 35.0, "CH3": 0.15, "CH4": 2.5}
# 限值与基线留 >4σ 裕度，越限只来自显式注入（真值可控）
LIMITS = {"CH1": (90.0, 150.0), "CH2": (500.0, 760.0), "CH3": (2.0, 4.0), "CH4": (35.0, 60.0)}
INJECT_HIGH_CH2 = [23, 24, 57, 101, 102, 150, 177]  # 7 次上越限
INJECT_LOW_CH4 = [40, 88, 89, 166]  # 4 次下越限


def main(outdir: str) -> None:
    rng = random.Random(SEED)
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(200):
        row = {"t_s": round(i * 0.5, 1)}
        for ch in CHANNELS:
            v = BASE[ch] + AMP[ch] * math.sin(i / 17.0) + rng.gauss(0, AMP[ch] * 0.35)
            row[ch] = round(v, 3)
        rows.append(row)
    for i in INJECT_HIGH_CH2:
        rows[i]["CH2"] = round(LIMITS["CH2"][1] + rng.uniform(5, 40), 3)
    for i in INJECT_LOW_CH4:
        rows[i]["CH4"] = round(LIMITS["CH4"][0] - rng.uniform(1, 4), 3)

    points = out / "bench_points.csv"
    with points.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t_s"] + CHANNELS)
        w.writeheader()
        w.writerows(rows)
    limits_csv = out / "bench_limits.csv"
    with limits_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["channel", "lower", "upper"])
        for ch in CHANNELS:
            w.writerow([ch, LIMITS[ch][0], LIMITS[ch][1]])

    # oracle：重读文件按限值数真值（不信注入清单，信落盘字节）
    with points.open() as f:
        data = list(csv.DictReader(f))
    print(f"OK {points.name} {len(data)} rows + {limits_csv.name} {len(CHANNELS)} channels -> {out}")
    for ch in CHANNELS:
        lo, hi = LIMITS[ch]
        vals = [float(r[ch]) for r in data]
        n_over = sum(1 for v in vals if v > hi)
        n_under = sum(1 for v in vals if v < lo)
        print(
            f"ORACLE {ch}: mean={sum(vals)/len(vals):.3f} max={max(vals):.3f} "
            f"min={min(vals):.3f} over={n_over} under={n_under}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
