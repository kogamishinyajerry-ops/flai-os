"""fea_solve_agent workflow：等截面 Euler-Bernoulli 梁一阶固有频率的纯 Python 有限元求解。

零 LLM（model.profile=none）零工具（tools=[]）：全部逻辑内联在本文件——
不 import backend.app.* 任何模块（CFD 那发把 oracle 放进 backend/app/cfd/ 是本
发刻意规避的先例；判据①=零内核 diff）。也不 import numpy（未接入本仓
pyproject/verify_all.sh 的 uv --with 列表）。若需拆分同包私有模块，须用
importlib.util.spec_from_file_location 手动加载，绝不用 `from . import x`——
Runtime 以 spec_from_file_location 按独立合成模块名加载 workflow.py，无父包
上下文，相对/包内 import 会在执行期炸。

数值方法（教科书标准，非本文件发明）：
- 单元：2 节点三次 Hermite 梁单元，每节点 DOF=(挠度 v, 转角 θ)。
  刚度阵 Ke = EI/l³·[[12,6l,-12,6l],[6l,4l²,-6l,2l²],[-12,-6l,12,-6l],[6l,2l²,-6l,4l²]]；
  一致质量阵 Me = ρA·l/420·[[156,22l,54,-13l],[22l,4l²,13l,-3l²],[54,13l,156,-22l],[-13l,-3l²,-22l,4l²]]。
- 广义特征值 K φ = λ M φ，最小 λ₁=ω₁²。K（约束后）与一致 M 均对称正定，
  故 K-λM 正定 ⟺ λ<λ₁（Sylvester/正定性）。用纯 stdlib Cholesky 正定性
  探测做二分：Cholesky 成功=正定=λ<λ₁；找成→败翻转点即 λ₁。对正定矩阵
  Cholesky 无需选主元数值稳定，非正定时主元≤0 干净检出——比无主元 LDLᵀ
  对不定阵可能 breakdown 更稳。
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

_SOLUTION_JSON = "fea_solution.json"
_SOLUTION_MD = "fea_solution.md"

_WATERMARK = (
    "> ⚠ **本文为确定性有限元计算结果（纯 Python 直接刚度法，零 LLM）：ω₁ 由标准梁单元"
    "离散 + 广义特征值求解得出，非模型臆测。是否满足设计要求由 fea_evaluate_agent 对照"
    "闭式解析解判据给出；未经工程师确认，不得作为设计/适航依据——判定权在人（宪法铁律六）。**"
)

_DEFAULT_N_ELEMENTS = 8


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


# ── 单元矩阵（长度 l、EI、rhoA=ρA）────────────────────────────────────────
def _elem_stiffness(l: float, EI: float) -> list[list[float]]:
    l2, l3 = l * l, l * l * l
    base = [
        [12.0, 6.0 * l, -12.0, 6.0 * l],
        [6.0 * l, 4.0 * l2, -6.0 * l, 2.0 * l2],
        [-12.0, -6.0 * l, 12.0, -6.0 * l],
        [6.0 * l, 2.0 * l2, -6.0 * l, 4.0 * l2],
    ]
    c = EI / l3
    return [[c * x for x in row] for row in base]


def _elem_mass(l: float, rhoA: float) -> list[list[float]]:
    l2 = l * l
    base = [
        [156.0, 22.0 * l, 54.0, -13.0 * l],
        [22.0 * l, 4.0 * l2, 13.0 * l, -3.0 * l2],
        [54.0, 13.0 * l, 156.0, -22.0 * l],
        [-13.0 * l, -3.0 * l2, -22.0 * l, 4.0 * l2],
    ]
    c = rhoA * l / 420.0
    return [[c * x for x in row] for row in base]


def _assemble(n: int, E: float, I: float, L: float, rho: float, A: float) -> tuple[list[list[float]], list[list[float]]]:
    """组装全局 K、M（size = 2*(n+1)）。节点 i 的 DOF = (2i, 2i+1)。"""
    ndof = 2 * (n + 1)
    K = [[0.0] * ndof for _ in range(ndof)]
    M = [[0.0] * ndof for _ in range(ndof)]
    le = L / n
    Ke = _elem_stiffness(le, E * I)
    Me = _elem_mass(le, rho * A)
    for e in range(n):
        g = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]  # 本单元 4 个全局 DOF
        for a in range(4):
            for b in range(4):
                K[g[a]][g[b]] += Ke[a][b]
                M[g[a]][g[b]] += Me[a][b]
    return K, M


def _keep_dofs(bc: str, n: int) -> list[int]:
    """返回约束后保留的 DOF 索引（升序）。
    cantilever：node0 固支 → 去 v0(0)、θ0(1)。
    simply_supported：两端铰支 → 去 v0(0)、v_n(2n)（转角自由）。"""
    ndof = 2 * (n + 1)
    if bc == "cantilever":
        removed = {0, 1}
    elif bc == "simply_supported":
        removed = {0, 2 * n}
    else:  # pragma: no cover - jsonschema enum 已在 Runtime 层拦截
        raise ValueError(f"未知边界条件：{bc!r}")
    return [d for d in range(ndof) if d not in removed]


def _submatrix(A: list[list[float]], keep: list[int]) -> list[list[float]]:
    return [[A[i][j] for j in keep] for i in keep]


def _is_positive_definite(A: list[list[float]]) -> bool:
    """纯 stdlib Cholesky 尝试：True 当且仅当 A 对称正定。主元（对角）≤0 即非正定。"""
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = A[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0.0:
                    return False
                L[i][j] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    return True


def _smallest_eigenvalue(K: list[list[float]], M: list[list[float]], scale: float) -> tuple[float, bool]:
    """广义特征值 Kφ=λMφ 的最小 λ₁：λ₁ = sup{λ : K-λM 正定}。
    返回 (λ₁, converged)。converged=False 表示二分未能定界（不出解，交诚实 failed）。"""
    ndof = len(K)

    def pd_at(lam: float) -> bool:
        shifted = [[K[i][j] - lam * M[i][j] for j in range(ndof)] for i in range(ndof)]
        return _is_positive_definite(shifted)

    if not pd_at(0.0):
        # λ=0 时 K 本身应正定（约束充分）；不正定=结构约束不足/机构，无正频率
        return 0.0, False
    lo, hi = 0.0, max(scale, 1.0)
    expand = 0
    while pd_at(hi):
        hi *= 2.0
        expand += 1
        if expand > 200:  # 病态：无法在合理范围内跨过 λ₁
            return 0.0, False
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if pd_at(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-13 * max(1.0, hi):
            break
    return 0.5 * (lo + hi), True


def _solve_omega1(bc: str, E: float, I: float, L: float, rho: float, A: float, n: int) -> tuple[float, bool]:
    K, M = _assemble(n, E, I, L, rho, A)
    keep = _keep_dofs(bc, n)
    Kr = _submatrix(K, keep)
    Mr = _submatrix(M, keep)
    # 二分种子：ω²≈(EI)/(ρA L⁴) 量级的若干倍即安全上界（while 循环会自扩张）
    scale = (E * I) / (rho * A * L ** 4)
    lam1, converged = _smallest_eigenvalue(Kr, Mr, scale)
    if not converged or lam1 <= 0.0:
        return 0.0, False
    return math.sqrt(lam1), True


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    output_dir = context["output_dir"]

    # jsonschema（input_schema.json）已在 Runtime _validate_inputs 层保证形状/物性正号/
    # 边界枚举合法；本函数只做数值求解与机制诚实（约束不足/不收敛→failed）。
    bc = inputs["boundary_condition"]
    E = float(inputs["E"])
    I = float(inputs["I"])
    L = float(inputs["L"])
    rho = float(inputs["rho"])
    A = float(inputs["A"])
    n = int(inputs.get("n_elements", _DEFAULT_N_ELEMENTS))

    omega1, converged = _solve_omega1(bc, E, I, L, rho, A, n)
    if not converged:
        return _fail(
            f"有限元特征值求解未收敛（边界={bc}，n_elements={n}）——刚度阵可能非正定"
            "（结构约束不足成机构）或数值病态；诚实失败，绝不返回发散数当解。"
        )

    f1_hz = omega1 / (2.0 * math.pi)
    solution = {
        "params": {
            "boundary_condition": bc, "E": E, "I": I, "L": L, "rho": rho, "A": A,
            "n_elements": n,
        },
        "fem_result": {
            "omega1_rad_s": omega1,
            "f1_hz": f1_hz,
            "dof_count": 2 * (n + 1),
            "element_type": "euler_bernoulli_cubic_hermite_2node",
            "mass_formulation": "consistent",
        },
        "solver": {
            "method": "cholesky_pd_bisection_generalized_eig",
            "rel_tol": 1e-13,
            "converged": True,
        },
        "human_review_required": True,
    }
    with open(os.path.join(output_dir, _SOLUTION_JSON), "w", encoding="utf-8") as f:
        json.dump(solution, f, ensure_ascii=False, indent=1)

    bc_disp = {"cantilever": "悬臂（fixed-free）", "simply_supported": "简支（pinned-pinned）"}[bc]
    lines = [
        "# FEA 梁一阶固有频率求解结果", "", _WATERMARK, "",
        "## 求解参数", "",
        f"- 边界条件：{bc_disp}",
        f"- 杨氏模量 E：{E:.6g} Pa",
        f"- 截面惯性矩 I：{I:.6g} m⁴",
        f"- 跨长 L：{L:.6g} m",
        f"- 密度 ρ：{rho:.6g} kg/m³",
        f"- 截面积 A：{A:.6g} m²",
        f"- 离散单元数 n_elements：{n}（自由度 {2 * (n + 1)}）", "",
        "## 有限元结果（确定性，数字来源：直接刚度法，非 LLM）", "",
        f"- 一阶圆频率 ω₁：{omega1:.6f} rad/s",
        f"- 一阶固有频率 f₁：{f1_hz:.6f} Hz",
        "- 单元类型：2 节点三次 Hermite 梁单元 · 一致质量阵",
        "- 求解方法：广义特征值 Cholesky 正定性二分", "",
        "> 收敛性/是否满足设计要求由 fea_evaluate_agent 对照闭式解析解判据给出，"
        "本结果停「等待人工审核」，签发权在具名工程师。", "",
    ]
    with open(os.path.join(output_dir, _SOLUTION_MD), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "boundary_condition": bc,
        "omega1_rad_s": omega1,
        "f1_hz": f1_hz,
        "n_elements": n,
        "converged": True,
        "human_review_required": True,
        "artifacts": [_SOLUTION_JSON, _SOLUTION_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}
