"""确定性 Strouhal / Cd 计算——评估 Agent 的 oracle，纯 Python 无 LLM。

St = f·D/U，f 由 Cl(t) 末段稳定振荡的过零点数估计（上升沿 + 线性插值，
复刻 agent-cfd-live/server/parsers.py 的 estimate_strouhal 数值行为，
good-run-01 golden 对账 St=0.16734）。未起振/数据不足 → converged=False 且
st=None，绝不编造逼近参考值 0.164（Goodhart 防御）。
"""
from __future__ import annotations


def cd_mean_tail(cd: list[float], frac: float = 0.5) -> float | None:
    if not cd:
        return None
    tail = cd[max(0, int(len(cd) * (1 - frac))):]
    return sum(tail) / len(tail) if tail else None


def strouhal_from_cl(t: list[float], cl: list[float], D: float = 1.0, U: float = 1.0) -> dict:
    n = len(cl)
    if n < 20 or len(t) != n:
        return {"st": None, "n_cycles": 0, "converged": False,
                "reason": "样本不足（<20 点）或 t/cl 长度不符"}
    # 取末 60% 作稳定段；减去段均值找过零点（正向穿越）
    lo = int(n * 0.4)
    seg_t, seg = t[lo:], cl[lo:]
    mean = sum(seg) / len(seg)
    dev = [v - mean for v in seg]
    amp = (max(dev) - min(dev)) / 2.0
    if amp < 1e-3:
        return {"st": None, "n_cycles": 0, "converged": False,
                "reason": f"Cl 振幅过小（{amp:.2e}）——未起振，不出 St"}
    # 正向过零时刻（线性插值）
    crossings: list[float] = []
    for i in range(1, len(dev)):
        if dev[i - 1] <= 0 < dev[i]:
            frac = -dev[i - 1] / (dev[i] - dev[i - 1])
            crossings.append(seg_t[i - 1] + frac * (seg_t[i] - seg_t[i - 1]))
    n_cycles = len(crossings) - 1
    if n_cycles < 3:
        return {"st": None, "n_cycles": max(0, n_cycles), "converged": False,
                "reason": f"稳定周期不足（{max(0, n_cycles)}<3）"}
    period = (crossings[-1] - crossings[0]) / n_cycles
    if period <= 0:
        return {"st": None, "n_cycles": n_cycles, "converged": False,
                "reason": "周期非正，数据异常"}
    f = 1.0 / period
    return {"st": f * D / U, "n_cycles": n_cycles, "converged": True,
            "reason": f"{n_cycles} 个稳定周期，f={f:.4f}"}
