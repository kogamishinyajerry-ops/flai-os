"""cfd_solve_agent（category=tool_automation，零 LLM，fire-and-register）：
经 cfd_solve_launch 发起真实 CFD 求解（圆柱绕流 Re=100）并登记 run_id →
输出 sim_run_ref（Runtime 成功路径回填 task.metadata.sim_run_ref，工作台
监控浮窗/深链据此看活的）→ 任务即 completed（求解在容器后台真跑 ~200s，
不阻塞）。人看到收敛后再建 cfd_evaluate_agent 任务（run_id 承接）。

requires_human_review=false：发起动作本身=人建任务的动作，审在评估阶段
（cfd_evaluate_agent waiting_review 人签）——不破「人是唯一签发者」。

run_id：inputs.run_id 可选注入（测试/eval_cases 确定性重放），缺省生成
UTC 时间戳 YYYYMMDD-HHMMSS（须过 cfd_solve_launch 的正则白名单，且为
hub run_discovery newest_by_name 的排序键）。发起失败（容器未 up/网格失败/
config 缺失）诚实 failed，绝不谎报已发起。
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

_MODULE = "cfd_openfoam"


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": msg}


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    reg = context["tool_registry"]
    logger = context.get("event_logger")
    case = inputs.get("case", "cylinder_re100")
    # run_id：注入优先（确定性重放）；缺省 UTC 时间戳（Tool 侧仍会正则校验）
    run_id = inputs.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if logger:
        logger.log("cfd_launch_started", {"case": case, "run_id": run_id})

    payload: dict[str, Any] = {"case": case, "run_id": run_id}
    et = inputs.get("end_time")
    if et is not None:
        payload["end_time"] = et
    res = reg.call("cfd_solve_launch", payload)
    if res.get("status") != "success":
        return _fail(f"发起求解失败：{res.get('error_message', '未知')}")

    sim_run_ref = f"{_MODULE}@{run_id}"
    if logger:
        logger.log("cfd_launched", {"run_id": run_id, "sim_run_ref": sim_run_ref})
    return {"status": "success", "outputs": [{
        "run_id": run_id,
        "sim_run_ref": sim_run_ref,
        "container": res.get("container"),
        "checkmesh_ok": res.get("checkmesh_ok"),
        "human_review_required": False,
        "note": "已发起真实 CFD 求解（约 200s）——实时监控见工作台监控浮窗/本任务「查看仿真监控 ↗」深链；"
                "看到收敛后请创建『CFD 评估』任务（run_id 承接）交工程师签发。",
        "artifacts": [],
    }]}
