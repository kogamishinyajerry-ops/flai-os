"""step_response_evaluate_agent workflow：二阶阶跃响应超调仿真的确定性收敛评估（闭式解析解判据）。

零 LLM（model.profile=none，Runtime 已物理封死 gateway）零工具（tools=[]）：oracle
全部内联在本文件——不 import backend/app/* 任何模块（刻意规避 cfd_evaluate_agent
把 st_oracle 放进 backend/app/cfd/ 的先例；判据①=零内核 diff）。也不 import numpy。

判据（确定性，唯一数字来源，非 LLM）：
- 从上游 step_solution.json 的 params 现算闭式解析超调量
  Mp_ref = 100·e^(−ζπ/√(1−ζ²))（标准二阶欠阻尼系统单位阶跃超调，教科书精确闭式；
  数学上只依赖 ζ，与 ωn 无关）。
- 相对误差 err = |overshoot_fem − Mp_ref| / Mp_ref × 100%；err ≤ tolerance_pct 判「一致/收敛」。
- 上游 solver.converged≠true / 产物缺字段 / ζ 非欠阻尼(0<ζ<1) / 解析失败 → 诚实
  「未达评估条件」，绝不逢正必过、绝不编造通过（Goodhart 防御，镜像 st_oracle
  对 st=None 的处理哲学）。
- params 只从仿真产物单一来源读，不重新接受输入——杜绝两次录入互相漂移。
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

_EVAL_JSON = "evaluation.json"
_EVAL_MD = "evaluation.md"
_DEFAULT_TOLERANCE_PCT = 2.0

_WATERMARK = (
    "> ⚠ **本文为确定性阶跃响应评估草案：收敛判定（仿真超调、闭式解析超调 Mp_ref、相对误差、"
    "是否在容差内）全部来自确定性计算（纯 Python，零 LLM），非模型臆测。未经工程师"
    "确认，不得作为设计依据——判定权在人（宪法铁律六）。**"
)


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _analytic_overshoot_pct(zeta: float) -> float:
    """标准二阶欠阻尼系统单位阶跃超调量的闭式精确解（%）。仅对 0<ζ<1 有定义。"""
    if not (0.0 < zeta < 1.0):
        raise ValueError(f"ζ={zeta!r} 非欠阻尼（须 0<ζ<1），超调闭式无定义")
    return 100.0 * math.exp(-zeta * math.pi / math.sqrt(1.0 - zeta * zeta))


def _pick_solution_file(files: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """从注入文件里挑唯一的 .json 仿真产物。多附件绝不盲取 files[0]。"""
    json_files = [f for f in files if str(f.get("filename", "")).lower().endswith(".json")]
    if not files:
        return None, "无输入文件——需上游 step_solution.json（经 depends_on 管道或上传注入）"
    if not json_files:
        names = ", ".join(str(f.get("filename")) for f in files)
        return None, f"未见 .json 仿真产物（收到：{names}）"
    if len(json_files) > 1:
        names = ", ".join(str(f.get("filename")) for f in json_files)
        return None, f"检测到 {len(json_files)} 个 .json（{names}），无法判定用哪份仿真产物"
    return json_files[0], ""


def _load_solution(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("仿真产物顶层不是 JSON 对象")
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
        return _fail(f"仿真产物解析失败（{rec.get('filename')}）：{exc}——不伪造评估")

    # ── 上游产物字段校验（缺任一即未达评估条件，fail-closed）──
    params = solution.get("params")
    result = solution.get("response_result")
    solver = solution.get("solver") or {}
    if not isinstance(params, dict) or not isinstance(result, dict):
        return _fail("仿真产物缺 params/response_result 字段——非 step_response_solve_agent 完整产物，不评估")
    required_params = ("zeta", "omega_n")
    missing = [k for k in required_params if k not in params]
    if missing:
        return _fail(f"仿真产物 params 缺字段 {missing}——不评估")
    if "overshoot_pct" not in result:
        return _fail("仿真产物 response_result 缺 overshoot_pct——不评估")

    converged_upstream = solver.get("converged") is True

    # ── 确定性判据（唯一数字来源，非 LLM）──
    try:
        overshoot_fem = float(result["overshoot_pct"])
        zeta = float(params["zeta"])
        overshoot_ref = _analytic_overshoot_pct(zeta)  # ζ 越界在此 raise → fail-closed
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        return _fail(f"闭式解析参考值计算失败：{exc}——未达评估条件，不评估")

    # 上游未收敛 → 未达评估条件（不给通过/不给误差比较），fail-closed
    if not converged_upstream:
        error_pct: float | None = None
        passed = False
        verdict = "未达评估条件（上游 solver.converged≠true，仿真无效）"
    else:
        error_pct = abs(overshoot_fem - overshoot_ref) / overshoot_ref * 100.0
        passed = error_pct <= tolerance_pct
        verdict = ("仿真超调与闭式解析解一致（收敛）" if passed
                   else "仿真超调偏离闭式解析解（超出容差，建议加密时间步长或复核参数）")

    evaluation = {
        "zeta": zeta,
        "omega_n": float(params["omega_n"]),
        "overshoot_fem": overshoot_fem,
        "overshoot_ref": overshoot_ref,
        "error_pct": error_pct,
        "tolerance_pct": tolerance_pct,
        "upstream_converged": converged_upstream,
        "passed": passed,
        "verdict": verdict,
        "source": "step_solution.json(上游产物) → 包内闭式解析 oracle(确定性)",
        "human_review_required": True,
    }
    with open(os.path.join(output_dir, _EVAL_JSON), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=1)

    err_disp = f"{error_pct:.6g}%" if error_pct is not None else "—（未达评估条件，不给数）"
    lines = [
        "# 二阶系统阶跃响应超调评估草案", "", _WATERMARK, "",
        "## 确定性判据（数字来源：包内闭式解析 oracle，非 LLM）", "",
        f"- 阻尼比 ζ：{zeta:.6g}",
        f"- 仿真超调 overshoot_fem：{overshoot_fem:.6g}%",
        f"- 闭式解析参考 Mp_ref：{overshoot_ref:.6g}%",
        f"- 相对误差：{err_disp}",
        f"- 容差 tolerance_pct：{tolerance_pct:g}%",
        f"- 上游仿真收敛（solver.converged）：{'是' if converged_upstream else '否'}",
        f"- 判定：{'通过' if passed else '未通过'} —— {verdict}", "",
        "> 本判定停「等待人工审核」，签发权在具名工程师，不构成设计依据。", "",
    ]
    with open(os.path.join(output_dir, _EVAL_MD), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "zeta": zeta,
        "overshoot_fem": overshoot_fem,
        "overshoot_ref": overshoot_ref,
        "error_pct": error_pct,
        "tolerance_pct": tolerance_pct,
        "passed": passed,
        "verdict": verdict,
        "human_review_required": True,
        "artifacts": [_EVAL_JSON, _EVAL_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}
