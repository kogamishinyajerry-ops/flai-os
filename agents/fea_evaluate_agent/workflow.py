"""fea_evaluate_agent workflow：梁一阶固有频率 FEM 解的确定性收敛评估（闭式解析解判据）。

零 LLM（model.profile=none，Runtime 已物理封死 gateway）零工具（tools=[]）：oracle
全部内联在本文件——不 import backend/app/* 任何模块（刻意规避 cfd_evaluate_agent
把 st_oracle 放进 backend/app/cfd/ 的先例；判据①=零内核 diff）。也不 import numpy。

判据（确定性，唯一数字来源，非 LLM）：
- 从上游 fea_solution.json 的 params 现算闭式解析一阶圆频率
  ω₁_ref = (β₁L)²·√(EI/(ρA·L⁴))，悬臂 β₁L=1.8751040687（cos·cosh=-1 首根，
  已二分独立复根到 1e-13），简支 β₁L=π（sin(βL)=0 的精确闭式）。
- 相对误差 err = |ω₁_fem − ω₁_ref| / ω₁_ref × 100%；err ≤ tolerance_pct 判「一致/收敛」。
- 上游 solver.converged≠true / 产物缺字段 / 边界条件未知 / 解析失败 → 诚实
  「未达评估条件」，绝不逢正必过、绝不编造通过（Goodhart 防御，镜像 st_oracle
  对 st=None 的处理哲学）。
- params 只从求解产物单一来源读，不重新接受输入——杜绝两次录入互相漂移。
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

_EVAL_JSON = "evaluation.json"
_EVAL_MD = "evaluation.md"
_DEFAULT_TOLERANCE_PCT = 2.0

# 闭式特征值 β₁L：悬臂=cos(x)cosh(x)+1=0 首根（Timoshenko/Blevins 标准表列
# 1.87510407…，已用二分对 cos(x)cosh(x)+1 独立复根验证到 1e-13）；简支=π。
_CANTILEVER_BETA1L = 1.8751040687119611
_SIMPLY_SUPPORTED_BETA1L = math.pi

_WATERMARK = (
    "> ⚠ **本文为确定性有限元评估草案：收敛判定（FEM ω₁、闭式解析 ω₁_ref、相对误差、"
    "是否在容差内）全部来自确定性计算（纯 Python，零 LLM），非模型臆测。未经工程师"
    "确认，不得作为设计/适航依据——判定权在人（宪法铁律六）。**"
)


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _analytic_omega1(bc: str, E: float, I: float, L: float, rho: float, A: float) -> float:
    if bc == "cantilever":
        beta1_l = _CANTILEVER_BETA1L
    elif bc == "simply_supported":
        beta1_l = _SIMPLY_SUPPORTED_BETA1L
    else:
        raise ValueError(f"未知边界条件：{bc!r}")
    return (beta1_l ** 2) * math.sqrt(E * I / (rho * A * L ** 4))


def _pick_solution_file(files: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """从注入文件里挑唯一的 .json 求解产物。多附件绝不盲取 files[0]。"""
    json_files = [f for f in files if str(f.get("filename", "")).lower().endswith(".json")]
    if not files:
        return None, "无输入文件——需上游 fea_solution.json（经 depends_on 管道或上传注入）"
    if not json_files:
        names = ", ".join(str(f.get("filename")) for f in files)
        return None, f"未见 .json 求解产物（收到：{names}）"
    if len(json_files) > 1:
        names = ", ".join(str(f.get("filename")) for f in json_files)
        return None, f"检测到 {len(json_files)} 个 .json（{names}），无法判定用哪份求解产物"
    return json_files[0], ""


def _load_solution(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("求解产物顶层不是 JSON 对象")
    return data


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    files = context.get("files") or []
    output_dir = context["output_dir"]

    tolerance_pct = float(inputs.get("tolerance_pct", _DEFAULT_TOLERANCE_PCT))

    rec, err = _pick_solution_file(files)
    if rec is None:
        return _fail(err + "——诚实失败，不伪造评估")
    try:
        solution = _load_solution(rec["path"])
    except Exception as exc:  # noqa: BLE001 - 上游产物解析失败=诚实 failed，不编造
        return _fail(f"求解产物解析失败（{rec.get('filename')}）：{exc}——不伪造评估")

    # ── 上游产物字段校验（缺任一即未达评估条件，fail-closed）──
    params = solution.get("params")
    fem = solution.get("fem_result")
    solver = solution.get("solver") or {}
    if not isinstance(params, dict) or not isinstance(fem, dict):
        return _fail("求解产物缺 params/fem_result 字段——非 fea_solve_agent 完整产物，不评估")
    required_params = ("boundary_condition", "E", "I", "L", "rho", "A")
    missing = [k for k in required_params if k not in params]
    if missing:
        return _fail(f"求解产物 params 缺字段 {missing}——不评估")
    if "omega1_rad_s" not in fem:
        return _fail("求解产物 fem_result 缺 omega1_rad_s——不评估")

    bc = params["boundary_condition"]
    converged_upstream = solver.get("converged") is True

    # ── 确定性判据（唯一数字来源，非 LLM）──
    try:
        omega1_fem = float(fem["omega1_rad_s"])
        omega1_ref = _analytic_omega1(
            bc, float(params["E"]), float(params["I"]), float(params["L"]),
            float(params["rho"]), float(params["A"]),
        )
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        return _fail(f"闭式解析参考值计算失败：{exc}——不评估")

    # 上游未收敛 → 未达评估条件（不给通过/不给误差比较），fail-closed
    if not converged_upstream:
        error_pct: float | None = None
        passed = False
        verdict = "未达评估条件（上游 solver.converged≠true，求解未收敛）"
    else:
        error_pct = abs(omega1_fem - omega1_ref) / omega1_ref * 100.0
        passed = error_pct <= tolerance_pct
        verdict = ("FEM 与闭式解析解一致（收敛）" if passed
                   else "FEM 偏离闭式解析解（超出容差，建议加密网格或复核参数）")

    evaluation = {
        "boundary_condition": bc,
        "omega1_fem": omega1_fem,
        "omega1_ref": omega1_ref,
        "error_pct": error_pct,
        "tolerance_pct": tolerance_pct,
        "upstream_converged": converged_upstream,
        "passed": passed,
        "verdict": verdict,
        "source": "fea_solution.json(上游产物) → 包内闭式解析 oracle(确定性)",
        "human_review_required": True,
    }
    with open(os.path.join(output_dir, _EVAL_JSON), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=1)

    err_disp = f"{error_pct:.6f}%" if error_pct is not None else "—（未达评估条件，不给数）"
    bc_disp = {"cantilever": "悬臂（fixed-free）",
               "simply_supported": "简支（pinned-pinned）"}.get(bc, bc)
    lines = [
        "# FEA 梁一阶固有频率评估草案", "", _WATERMARK, "",
        "## 确定性判据（数字来源：包内闭式解析 oracle，非 LLM）", "",
        f"- 边界条件：{bc_disp}",
        f"- FEM 一阶圆频率 ω₁_fem：{omega1_fem:.6f} rad/s",
        f"- 闭式解析参考 ω₁_ref：{omega1_ref:.6f} rad/s",
        f"- 相对误差：{err_disp}",
        f"- 容差 tolerance_pct：{tolerance_pct:g}%",
        f"- 上游求解收敛（solver.converged）：{'是' if converged_upstream else '否'}",
        f"- 判定：{'通过' if passed else '未通过'} —— {verdict}", "",
        "> 本判定停「等待人工审核」，签发权在具名工程师，不构成设计/适航依据。", "",
    ]
    with open(os.path.join(output_dir, _EVAL_MD), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "boundary_condition": bc,
        "omega1_fem": omega1_fem,
        "omega1_ref": omega1_ref,
        "error_pct": error_pct,
        "tolerance_pct": tolerance_pct,
        "passed": passed,
        "verdict": verdict,
        "human_review_required": True,
        "artifacts": [_EVAL_JSON, _EVAL_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}
