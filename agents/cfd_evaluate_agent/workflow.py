"""cfd_evaluate_agent：读一次 CFD 求解结果 → 确定性算 St/Cd 对照 Williamson →
LLM(reasoning) 仅叙事这些确定性数字（强制水印草案）→ requires_human_review=true，
Runtime 转 waiting_review 等人签。

铁律边界（宪法铁律六 + §11.2「LLM 不判最终工程结论」）：
- St/Cd 与判据**全部来自确定性 oracle**（backend.app.cfd.st_oracle，纯 Python），
  LLM 只对已给定数字做工程叙事，绝不自算/新增/覆盖任何数字。
- 未收敛/数据不足 → 如实 verdict「未达评估条件」，st=None，绝不编造逼近 0.164
  （Goodhart 防御）。
- cfd_result_read 读取失败 → 诚实 failed，绝不伪造评估。
- 草案头强制水印「AI 辅助 · 未经工程师确认 · 判定权在人」。
- LLM 叙事失败/无 key 不阻断（确定性判据已落 evaluation.json），降级为显式
  「叙事不可用」占位，数字仍以确定性结果为准。
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

from backend.app.cfd.st_oracle import strouhal_from_cl, cd_mean_tail

_ST_REF = 0.164  # Williamson (1996) Re=100 圆柱绕流 Strouhal 参考
_RESID_TOL = 0.05  # 残差门（瞬态语义）：golden 收敛 run resid_p 尾部实测 ≤1.17e-2（4× 余量）
_EVAL_JSON = "evaluation.json"
_DRAFT_MD = "cfd_eval_draft.md"

_WATERMARK = (
    "> ⚠ **本文为 AI 辅助生成的 CFD 评估草案：结论数字（St、Cd_mean、与 Williamson "
    "参考的误差、收敛判据）全部来自确定性计算（非 LLM 臆测），叙事由模型辅助。"
    "未经工程师确认，不得作为设计/适航依据——判定权在人（宪法铁律六）。**"
)


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _load_system_prompt() -> str:
    return Path(__file__).with_name("prompt.md").read_text(encoding="utf-8").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    tool_registry = context["tool_registry"]
    output_dir = context["output_dir"]
    run_id = inputs.get("run_id")
    if not run_id:
        return _fail("缺 run_id，无法评估")

    res = tool_registry.call("cfd_result_read", {"run_id": run_id})
    if res.get("status") != "success":
        return _fail(f"读求解结果失败：{res.get('error_message', '未知')}——诚实失败，不伪造评估")

    # ── 确定性判据（唯一数字来源，非 LLM）──
    # 收敛=三门 AND（spec §4.4「残差 < tol 且 ≥N 个稳定周期」+ Codex R2-P1：
    # sidecar 在场时 solver 可能还在跑或已崩，只看周期数会给 unhealthy run 发
    # Williamson-consistent verdict）：
    #   ① oracle 周期门（≥3 稳定周期且振幅足够）
    #   ② 残差门 resid_p_tail 全 < 0.05——瞬态涡街的每步 Initial residual 不会
    #      降到稳态量级，golden 收敛 run 尾部实测 8.2e-3~1.17e-2（4× 余量）；
    #      发散/崩溃 run 的残差 >0.1 或 nan（nan 比较恒 False → 门自然拒）
    #   ③ ended 门（log 以 End 正常收尾——solver 还在跑/中途崩一律未达条件）
    st = strouhal_from_cl(res.get("t_series") or [], res.get("cl_series") or [], D=1.0, U=1.0)
    cd_mean = cd_mean_tail(res.get("cd_series") or [])
    resid_tail = [v for v in (res.get("resid_p_tail") or []) if v is not None]
    resid_ok = bool(resid_tail) and all(v < _RESID_TOL for v in resid_tail)
    ended_ok = res.get("ended") is True
    converged = st["converged"] and resid_ok and ended_ok
    st_value = st["st"] if converged else None  # 未达三门不给 St（诚实地板）
    st_error_pct = (abs(st_value - _ST_REF) / _ST_REF * 100.0) if st_value is not None else None
    if not converged:
        blockers = []
        if not st["converged"]:
            blockers.append(st["reason"])
        if not resid_ok:
            blockers.append(f"残差门未过（resid_p 尾部须全 <{_RESID_TOL:g}）")
        if not ended_ok:
            blockers.append("求解未正常收尾（无 End——可能仍在跑或中途崩）")
        verdict = "未达评估条件（" + "；".join(blockers) + "）"
    elif st_error_pct is not None and st_error_pct < 10:
        verdict = "收敛，St 与 Williamson 参考一致"
    else:
        verdict = "收敛但 St 偏离参考"

    evaluation = {
        "run_id": run_id, "converged": converged, "st": st_value,
        "st_ref": _ST_REF, "st_error_pct": st_error_pct, "n_cycles": st["n_cycles"],
        "cd_mean": cd_mean, "ended": res.get("ended"),
        "resid_gate": {"tol": _RESID_TOL, "passed": resid_ok}, "verdict": verdict,
        "oracle_reason": st["reason"], "source": "cfd_result_read → st_oracle(确定性)",
    }
    with open(os.path.join(output_dir, _EVAL_JSON), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=1)

    # ── LLM 只叙事这些确定性数字（失败/无 key 时降级为显式占位，不阻断）──
    narrative = ""
    gw = context.get("model_gateway")
    if gw is not None:
        try:
            profile = context["agent_config"]["model"]["profile"]
            facts = json.dumps(evaluation, ensure_ascii=False)
            msgs = [
                {"role": "system", "content": _load_system_prompt()},
                {"role": "user",
                 "content": f"对以下确定性评估结果做简短工程解读（不得改动或新增任何数字）：{facts}"},
            ]
            r = gw.chat(profile, msgs)
            narrative = (r.get("content") or "").strip()
        except Exception as exc:  # noqa: BLE001 - 叙事失败不阻断，确定性判据已落
            narrative = f"（LLM 叙事不可用：{exc.__class__.__name__}；以上确定性数字为准）"

    # ── 水印草案 ──
    st_disp = evaluation["st"] if evaluation["st"] is not None else "—（未收敛，不给数）"
    err_disp = f"{st_error_pct:.2f}%" if st_error_pct is not None else "—"
    cd_disp = f"{cd_mean:.4f}" if cd_mean is not None else "—"
    lines = [
        "# CFD 评估草案（圆柱绕流 Re=100）", "", _WATERMARK, "",
        "## 确定性判据（数字来源：st_oracle，非 LLM）", "",
        f"- 收敛（三门 AND）：{'是' if converged else '否'}",
        f"  - 周期门：{'过' if st['converged'] else '未过'}（{evaluation['oracle_reason']}）",
        f"  - 残差门（resid_p 尾部全 <{_RESID_TOL:g}）：{'过' if resid_ok else '未过'}",
        f"  - 收尾门（log 以 End 正常结束）：{'过' if ended_ok else '未过'}",
        f"- Strouhal St：{st_disp}",
        f"- 参考 St_ref（Williamson）：{_ST_REF}",
        f"- 相对误差：{err_disp}",
        f"- 平均阻力系数 Cd_mean：{cd_disp}",
        f"- 判定：{verdict}", "",
        "## 工程解读（AI 叙事，数字以上为准）", "", narrative or "（无）", "",
    ]
    with open(os.path.join(output_dir, _DRAFT_MD), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "run_id": run_id, "converged": converged, "st": evaluation["st"],
        "st_ref": _ST_REF, "st_error_pct": st_error_pct, "cd_mean": cd_mean,
        "verdict": verdict, "human_review_required": True,
        "artifacts": [_EVAL_JSON, _DRAFT_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}
