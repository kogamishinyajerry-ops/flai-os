"""cfd_result_read（mock=false，只读，无 shell）：读 agent-cfd-live
case/run/<run_id>/ 时间戳子目录里的 CFD 求解产物（log.pimpleFoam + forceCoeffs），
返回原始 Cl/Cd/残差序列。不下判据（判据在 cfd_evaluate_agent workflow）。

run_id 先过正则白名单 ^\\d{8}-\\d{6}$ 才拼路径（防目录穿越），再与子目录内
.hub_run_id sidecar 对账（防读错 run）。FLAI_CFD_CASE_DIR 未配即 fail-closed。
解析器用 FLAi-OS 侧 SSOT（backend.app.cfd.cfd_log_parser），无跨仓依赖（ADR-0026）。
"""
from __future__ import annotations
import glob
import os
import re
from pathlib import Path
from typing import Any

from backend.app.cfd.cfd_log_parser import parse_residuals, parse_force_coeffs

_CASE_ENV = "FLAI_CFD_CASE_DIR"  # = agent-cfd-live case/run 根（run 子目录的父）
_LOG = "log.pimpleFoam"
_FORCE_GLOB = "postProcessing/forceCoeffs1/0/*.dat"
_RUN_ID_RE = re.compile(r"[0-9]{8}-[0-9]{6}")  # 用 fullmatch：re.match+$ 放行尾换行、\d 收非 ASCII 数字（Codex R0-P2-2 同款）


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": msg}


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    run_id = str(payload["run_id"])
    if not _RUN_ID_RE.fullmatch(run_id):
        return _fail(f"run_id 非法（须 YYYYMMDD-HHMMSS）：{run_id!r}——拒绝拼路径，fail-closed")
    # 评测上下文优先（#8 / R2-1）：eval 任务经**任务级 context** 注入材化快照的 fixture 根
    # （<materialized>/eval_cases/fixtures），令评测读**冻结**产物而非全局 $FLAI_CFD_CASE_DIR
    # 的活态——「评的就是晋升的那版」对「工具读外部活态」的 agent 也成立。context 缺该键
    # （普通任务）时回退活 env（真实 CFD 运行），语义不变。任务级传递、非进程全局 env，
    # 并发安全（worker 多线程并跑评测不互踩）。
    case_raw = (context or {}).get("eval_fixtures_dir") or os.environ.get(_CASE_ENV)
    if not case_raw:
        return _fail(f"{_CASE_ENV} 未配置——fail-closed，绝不猜路径")
    case = Path(case_raw).expanduser() / run_id  # 时间戳子目录（落法 2026-07-13）
    sidecar = case / ".hub_run_id"
    if not sidecar.is_file():
        return _fail(f"run {run_id} 不存在或 .hub_run_id 缺失——无可读结果")
    actual = sidecar.read_text(errors="replace").strip()
    if actual != run_id:
        return _fail(f"run_id 不符（请求 {run_id!r} ≠ sidecar {actual!r}）——防读错 run，fail-closed")
    log_path = case / _LOG
    if not log_path.is_file():
        return _fail("log.pimpleFoam 缺失——求解未产数据")

    text = log_path.read_text(errors="replace")
    steps = parse_residuals(text)
    fc = {"t": [], "cd": [], "cl": []}
    matches = sorted(glob.glob(str(case / _FORCE_GLOB)))
    if matches:
        fc = parse_force_coeffs(Path(matches[0]).read_text(errors="replace"))
    return {
        "status": "success",
        "run_id": str(run_id),
        "cl_series": fc["cl"],
        "cd_series": fc["cd"],
        "t_series": fc["t"],
        "resid_p_tail": [s["resid"].get("p") for s in steps[-20:]],
        "n_steps": len(steps),
        # Codex R2-P1（86gs 全分支审）：ended 是收敛门之一，须末**非空行全等**
        # "End"（OpenFOAM 正常收尾唯一形态，与 cfd_solve_launch 同判据）——
        # 子串判定会被重启/损坏 log 中段的 End 冒充。
        "ended": next((ln.strip() for ln in reversed(text[-400:].splitlines()) if ln.strip()), "") == "End",
    }
