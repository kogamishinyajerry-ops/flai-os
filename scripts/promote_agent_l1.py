"""真实环境晋升实证：跑评测 → L0→L1 晋升门（M11-A2，ADR-0018 治理闭环首次真实使用）。

用法（仓根，服务须先从当前代码重启——见下方前置检查）：
    uv run --no-project --with jsonschema --with pyyaml --with fastapi --with httpx \
      --with python-multipart --with "pydantic>2" --with jieba --with openpyxl \
      python scripts/promote_agent_l1.py performance_disk_agent 张工

前置（fail-closed 自检，不满足即拒跑）：
- 常驻 API（:8620）打治理路由（GET /api/agents/{id}/eval-runs）：
  404「接口不存在」= 老代码（无治理路由）→ 拒跑；401 = ≥M11 代码
  （鉴权中间件在场，ADR-0019）→ 新代见证放行；200 = 已登录新代同样放行。
  老代码 worker 的 claim 没有 origin 过滤，会抢走 eval 任务并把评测输入
  污染进真实样本库，绝不带病跑。
- 本脚本在进程内直连真实 data/（与常驻服务同一 DB/包目录），评测任务
  origin='eval'，新代码 worker 不会抢。

产出：真实 eval_runs 证据 + agents/<id>/agent.yaml maturity L0→L1 +
changelog 条目 + promotions 审计记录。常驻 API 的内存投影在其下次重扫/
重启后对齐（DB 投影本脚本已同步）。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：python scripts/promote_agent_l1.py <agent_id> <confirmed_by>")
        return 2
    agent_id, confirmed_by = sys.argv[1], sys.argv[2]

    import httpx

    try:
        probe = httpx.get(
            f"http://127.0.0.1:8620/api/agents/{agent_id}/eval-runs", timeout=3
        )
        if probe.status_code == 404 and "接口不存在" in probe.text:
            print(
                "诚实拒跑：常驻服务是旧代码（无治理路由）。老 worker 会抢 eval 任务\n"
                "并污染真实样本库。请先从当前代码重启两个服务：\n"
                "  scripts/dev_start_backend.sh 与 scripts/dev_start_worker.sh"
            )
            return 1
        # 401 = 鉴权中间件在场（≥M11/ADR-0019）——正是「新代」见证，放行继续；
        # 本脚本走进程内直连不经 HTTP，无需登录态。
    except httpx.HTTPError:
        print("提示：常驻 API 未响应（:8620）。若 worker 也未在跑则无抢单风险，继续。")

    from backend.app import config
    from backend.app.bootstrap import assemble
    from backend.app.governance import eval_runner, promotion, signer_provenance
    from backend.app.runtime.runtime import AgentRuntime
    from backend.app.storage.db import get_conn, init_db

    init_db(config.DB_PATH)

    def conn_factory():
        return get_conn(config.DB_PATH)

    asm = assemble(
        agents_dir=config.AGENTS_DIR, tools_dir=config.TOOLS_DIR,
        contracts_dir=config.CONTRACTS_DIR, knowledge_dir=config.KNOWLEDGE_DIR,
        conn_factory=conn_factory,
    )
    runtime = AgentRuntime(
        asm.agent_registry, asm.tool_registry, asm.model_gateway, conn_factory,
        config.TASK_RUNS_DIR, knowledge_service=asm.knowledge_service,
        uploads_dir=config.UPLOADS_DIR,
        scope_registry=asm.scope_registry,  # ADR-0021 知识轴（Codex R1 审 P1）
    )

    print(f"[1/2] 跑评测：{agent_id} …")
    run = eval_runner.run_agent_evals(
        conn_factory=conn_factory, agent_registry=asm.agent_registry,
        runtime=runtime, uploads_dir=config.UPLOADS_DIR,
        task_runs_dir=config.TASK_RUNS_DIR,
        agent_id=agent_id, triggered_by=confirmed_by,
    )
    print(
        f"    run={run['id']} status={run['status']} "
        f"passed={run['passed']}/{run['total']} skipped={run['skipped']}"
    )
    for cr in run["case_results"]:
        print(f"    - {cr['case_file']}: {cr['verdict']}")
    is_green = run["total"] > 0 and run["failed"] == 0 and run["skipped"] == 0
    if is_green is not True or run["status"] != "completed":
        print("评测未全绿，晋升不发起（fail-closed）。")
        return 1

    print(f"[2/2] 晋升门：{agent_id} L0→L1 …")
    try:
        record = promotion.promote_agent(
            conn_factory=conn_factory, agent_registry=asm.agent_registry,
            scope_registry=asm.scope_registry, agent_id=agent_id,
            to_maturity="L1", eval_run_id=run["id"],
            confirmations={"exception_paths_handled": True},
            signer=signer_provenance.SignerContext.from_server_cli(confirmed_by),
            attestation_records=asm.promotion_attestation_records,
        )
    except promotion.PromotionRejected as exc:
        print("晋升被拒，逐条判定：")
        for name, check in exc.checks.items():
            print(f"    {'✓' if check['ok'] is True else '✗'} {name}: {check['detail']}")
        return 1
    print(
        f"    晋升成功：{record['from_maturity']}→{record['to_maturity']}"
        f"（promotions #{record['id']}，eval_run={record['eval_run_id']}）"
    )
    print("完成。常驻 API 内存投影将在其重扫/重启后对齐（DB 投影已同步）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
