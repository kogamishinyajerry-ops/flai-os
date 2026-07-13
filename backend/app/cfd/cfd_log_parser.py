"""CFD 日志解析：log.pimpleFoam 残差 + forceCoeffs Cl/Cd。

数值行为复刻 agent-cfd-live/server/parsers.py，与 sim-live-hub
adapters/cfd_openfoam/cfd_log_parser.py **逐字同源**（同一 good-run-01 golden 对账）。
FLAi-OS 侧独立持有一份，避免生产部署跨仓 sys.path 依赖（ADR-0026）。
"""
from __future__ import annotations
import math
import re

_RESID_RE = re.compile(r"Solving for (\w+), Initial residual = ([0-9.eE+-]+)")
_TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)")
_CLOCK_RE = re.compile(r"^ExecutionTime = [0-9.eE+-]+ s\s+ClockTime = ([0-9.eE+-]+) s")


def parse_residuals(text: str) -> list[dict]:
    steps: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = _TIME_RE.match(line)
        if m:
            if cur is not None:
                steps.append(cur)
            cur = {"t": float(m.group(1)), "resid": {}, "clock_s": None}
            continue
        if cur is None:
            continue
        m = _RESID_RE.search(line)
        if m:
            # 每步每变量取「首次」（Initial residual），同名后续（PIMPLE 内循环）不覆盖首值
            cur["resid"].setdefault(m.group(1), float(m.group(2)))
            continue
        m = _CLOCK_RE.match(line)
        if m:
            cur["clock_s"] = float(m.group(1))
    if cur is not None:
        steps.append(cur)
    return steps


def parse_force_coeffs(text: str) -> dict:
    t: list[float] = []
    cd: list[float] = []
    cl: list[float] = []
    cols: dict | None = None
    for line in text.splitlines():
        low = line.lower()
        if line.startswith("#"):
            if "cd" in low and "cl" in low:
                # header 行：建列名→索引映射（去掉开头 '#'）
                names = low.lstrip("#").split()
                cols = {n: i for i, n in enumerate(names)}
            continue
        vals = line.split()
        if len(vals) < 3:
            continue
        i_cd = cols.get("cd", 2) if cols else 2
        i_cl = cols.get("cl", 3) if cols else 3
        if i_cd >= len(vals) or i_cl >= len(vals):
            continue
        # 整行先转换再一起 append（Codex R2-P2：流式读到半写行时，逐列 append
        # 会在 ValueError 前已推入部分列 → t/cd/cl 长度撕裂，oracle 拒整个 run）；
        # 非有限值（发散 run 的 nan/inf）整行拒——它们会穿进 cd_mean/evaluation.json
        # 的 NaN token 并炸 FastAPI 严格 JSON（Codex R2-P2）。
        try:
            row = (float(vals[0]), float(vals[i_cd]), float(vals[i_cl]))
        except ValueError:
            continue
        if not all(math.isfinite(v) for v in row):
            continue
        t.append(row[0])
        cd.append(row[1])
        cl.append(row[2])
    return {"t": t, "cd": cd, "cl": cl}
