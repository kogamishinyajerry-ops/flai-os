"""step_response_solve_agent workflow：标准二阶欠阻尼系统单位阶跃响应的纯 Python 仿真。

零 LLM（model.profile=none）零工具（tools=[]）：全部逻辑内联在本文件——
不 import backend.app.* 任何模块（CFD 那发把 oracle 放进 backend/app/cfd/ 是判据①
刻意规避的先例；判据①=零内核 diff）。也不 import numpy（未接入本仓
pyproject/verify_all.sh 的 uv --with 列表）。若需拆分同包私有模块，须用
importlib.util.spec_from_file_location 手动加载，绝不用 `from . import x`——
Runtime 以 spec_from_file_location 按独立合成模块名加载 workflow.py，无父包
上下文，相对/包内 import 会在执行期炸。

数值方法（教科书标准，非本文件发明）：
- 系统：G(s)=ωn²/(s²+2ζωn·s+ωn²)，单位阶跃 u(t)=1。状态 x=[y, ẏ]，
  ẋ=A·x+B·u，A=[[0,1],[−ωn²,−2ζωn]]，B=[0,ωn²]，x(0)=[0,0]。
- 积分：梯形（双线性变换/Tustin）定步长隐式法——控制学科 canonical 离散，
  **A-稳定**（对任意步长不发散，无 RK4 那样的显式稳定上限），全局误差 O(h²)。
  每步解 2×2 线性系统 (I−h/2·A)·x_{k+1}=(I+h/2·A)·x_k+h·B（u_k=u_{k+1}=1），
  纯 stdlib Cramer 法。梯形对稳态一致：DC 增益恒 =1，故稳态 y_ss=1 精确。
- 仿真窗 horizon=2 个阻尼周期=4π/ωd（ωd=ωn√(1−ζ²)）；欠阻尼首峰在 tp=π/ωd
  =horizon/4，恒在窗内且为全局最大（后续峰因阻尼更小）。超调 Mp 由轨迹 argmax
  取（峰值−稳态）。粗 n_steps 下梯形 O(h²) 幅值误差使超调偏离闭式——真实离散
  误差，交 evaluate 侧对照闭式解析解裁定收敛。
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

_SOLUTION_JSON = "step_solution.json"
_SOLUTION_MD = "step_solution.md"

_WATERMARK = (
    "> ⚠ **本文为确定性阶跃响应仿真结果（纯 Python 梯形积分，零 LLM）：超调量由标准"
    "二阶系统状态空间离散积分得出，非模型臆测。是否满足设计要求由 step_response_evaluate_agent"
    "对照闭式解析解判据给出；未经工程师确认，不得作为设计依据——判定权在人（宪法铁律六）。**"
)

_DEFAULT_N_STEPS = 2000


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _simulate_overshoot(
    zeta: float, omega_n: float, n_steps: int
) -> tuple[float, float, float, float, bool]:
    """梯形（双线性）定步长积分单位阶跃响应，返回
    (overshoot_pct, peak_value, horizon, dt, ok)。

    ok=False 表示仿真无效（非有限/无超调/峰值落窗边界）→ 交诚实 failed。
    A-稳定：对任意 n_steps 不发散（不同于显式 RK4 的 ωn·h<2.8 稳定上限），
    故粗 n_steps 只是精度差、绝不 blowup——诚实负例（欠离散超容差）无发散悬崖。"""
    wd = omega_n * math.sqrt(1.0 - zeta * zeta)
    horizon = 4.0 * math.pi / wd  # 2 个阻尼周期；欠阻尼首峰 tp=π/ωd=horizon/4 恒在窗内
    h = horizon / n_steps
    wn2 = omega_n * omega_n
    a10, a11 = -wn2, -2.0 * zeta * omega_n  # A 第二行（第一行 [0,1]）
    hh = h / 2.0
    # M = I − (h/2)A ; P = I + (h/2)A（A[0]=[0,1], A[1]=[a10,a11]）
    m00, m01 = 1.0, -hh
    m10, m11 = -hh * a10, 1.0 - hh * a11
    p00, p01 = 1.0, hh
    p10, p11 = hh * a10, 1.0 + hh * a11
    detM = m00 * m11 - m01 * m10
    if not math.isfinite(detM) or detM == 0.0:
        return 0.0, 0.0, horizon, h, False
    force = h * wn2  # h·B 的第二分量（第一分量 0）
    y, v = 0.0, 0.0  # x=[y, ẏ]，零初值
    peak, peak_idx = 0.0, 0
    for k in range(1, n_steps + 1):
        r0 = p00 * y + p01 * v
        r1 = p10 * y + p11 * v + force
        yn = (r0 * m11 - m01 * r1) / detM
        vn = (m00 * r1 - r0 * m10) / detM
        y, v = yn, vn
        if not (math.isfinite(y) and math.isfinite(v)):
            return 0.0, 0.0, horizon, h, False  # 非有限（理论上 A-稳定不该发生）→ 诚实失败
        if y > peak:
            peak, peak_idx = y, k
    overshoot_pct = (peak - 1.0) * 100.0
    # 有效性：峰值有限、确有超调（峰>稳态1）、峰不落窗边界（horizon 覆盖首峰）
    ok = math.isfinite(peak) and peak > 1.0 and 0 < peak_idx < n_steps
    return overshoot_pct, peak, horizon, h, ok


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    output_dir = context["output_dir"]

    # jsonschema（input_schema.json）已在 Runtime _validate_inputs 层保证 0<ζ<1、
    # ωn 正且量级合理、n_steps 范围；本函数只做仿真与机制诚实（无效仿真→failed）。
    zeta = float(inputs["zeta"])
    omega_n = float(inputs["omega_n"])
    n_steps = int(inputs.get("n_steps", _DEFAULT_N_STEPS))

    overshoot_pct, peak, horizon, dt, ok = _simulate_overshoot(zeta, omega_n, n_steps)
    if not ok:
        return _fail(
            f"阶跃响应仿真无效（ζ={zeta}, ωn={omega_n}, n_steps={n_steps}）——轨迹非有限"
            "或未在仿真窗内解析到超调峰值；诚实失败，绝不返回无效数当解。"
        )

    solution = {
        "params": {"zeta": zeta, "omega_n": omega_n, "n_steps": n_steps},
        "response_result": {
            "overshoot_pct": overshoot_pct,
            "peak_value": peak,
            "steady_state": 1.0,
            "n_steps": n_steps,
            "horizon_s": horizon,
            "dt_s": dt,
            "integrator": "trapezoidal_bilinear_fixed_step",
        },
        "solver": {
            "method": "trapezoidal_bilinear_fixed_step",
            "converged": True,
        },
        "human_review_required": True,
    }
    with open(os.path.join(output_dir, _SOLUTION_JSON), "w", encoding="utf-8") as f:
        json.dump(solution, f, ensure_ascii=False, indent=1)

    lines = [
        "# 二阶系统阶跃响应仿真结果", "", _WATERMARK, "",
        "## 求解参数", "",
        f"- 阻尼比 ζ：{zeta:.6g}",
        f"- 自然频率 ωn：{omega_n:.6g} rad/s",
        f"- 仿真步数 n_steps：{n_steps}（步长 dt={dt:.6g}s，仿真窗={horizon:.6g}s=2 个阻尼周期）", "",
        "## 仿真结果（确定性，数字来源：梯形定步长积分，非 LLM）", "",
        f"- 超调量 overshoot：{overshoot_pct:.6g}%",
        f"- 峰值 y_peak：{peak:.6g}（稳态 y_ss=1）",
        "- 积分器：梯形（双线性/Tustin）定步长隐式，A-稳定", "",
        "> 收敛性/是否满足设计要求由 step_response_evaluate_agent 对照闭式解析解判据"
        "（Mp=e^(−ζπ/√(1−ζ²))）给出，本结果停「等待人工审核」，签发权在具名工程师。", "",
    ]
    with open(os.path.join(output_dir, _SOLUTION_MD), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "zeta": zeta,
        "omega_n": omega_n,
        "overshoot_pct": overshoot_pct,
        "n_steps": n_steps,
        "converged": True,
        "human_review_required": True,
        "artifacts": [_SOLUTION_JSON, _SOLUTION_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}
