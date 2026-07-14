"""#8 / R2-1 端到端验收：cfd_evaluate_agent 的**评测**经不可变快照路径读**冻结** fixture
（任务级 context 注入 eval_fixtures_dir），而非全局 $FLAI_CFD_CASE_DIR 活态或活磁盘。

R2-1 边界（T2/#5 遗留、已建 issue #8）：cfd_result_read 这类「读外部活态」的工具，其 agent 的
评测在 T2 快照下仍从 `$FLAI_CFD_CASE_DIR` 读**活**目录——「评的就是晋升的那版」对它不成立。
#8/approach-B 把材化快照的 fixture 根经**任务级 context**（非进程全局 env，并发安全）路由进工具，
令评测读冻结产物。链路：runtime `_build_context`（origin='eval' → 注入 eval_fixtures_dir=
<materialized>/eval_cases/fixtures）→ ToolRegistry.call（转发 tool_context）→ adapter（context
优先于 env）。

本测试是该闭环的端到端咬合证，用**真** ToolRegistry / AgentRuntime / AgentRegistry（非替身），
走 registry.py 真实 tool_context 管道：
  GREEN — enqueue→冻结快照→**删光活磁盘 fixtures + 清空全局 env**→经快照路径执行评测→仍跑出
          真实评估（case_001 收敛、case_002 诚实地板），证数据来自**冻结** fixture 而非活态。
  RED（tamper）— 把 adapter.run 换回「只认全局 env、无视 context」的 pre-#8 版 → 活 fixtures 已删
          + env 已清 → 工具 fail-closed → case 全 failed，证路由承重、GREEN 非空转。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from backend.app.config import AGENTS_DIR, CONTRACTS_DIR, TOOLS_DIR
from backend.app.governance import eval_runner
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry

_AGENT = "cfd_evaluate_agent"


class _StubGateway:
    """cfd_evaluate 用 LLM 仅做**非阻断**叙事（失败/含事实集外数字即弃用换占位）。返回无数字
    文本即被 workflow 原样采用，不影响确定性判据——converged/St 只来自 fixture 数据，非 LLM。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {"content": "工程解读占位（无数字）"}

    def embed(self, *a: Any, **k: Any) -> dict[str, Any]:
        raise AssertionError("cfd_evaluate 不应调用 embed")

    def vision(self, *a: Any, **k: Any) -> dict[str, Any]:
        raise AssertionError("cfd_evaluate 不应调用 vision")


def _setup(tmp_path: Path):
    """临时 agents 目录（cfd_evaluate 副本，好删活 fixtures 验冻结读）+ 真 registry /
    真 tool_registry（走 registry.py 真实 tool_context 管道）/ 真 runtime。"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    pkg = agents_dir / _AGENT
    shutil.copytree(AGENTS_DIR / _AGENT, pkg)

    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    def conn_factory():
        return get_conn(db_path)

    registry = AgentRegistry(agents_dir, CONTRACTS_DIR / "agent.schema.json")
    registry.scan()
    assert registry.get(_AGENT) is not None, registry.errors

    tool_registry = ToolRegistry(TOOLS_DIR, CONTRACTS_DIR / "tool.schema.json")
    tool_registry.scan()

    runtime = AgentRuntime(
        agent_registry=registry,
        tool_registry=tool_registry,
        model_gateway=_StubGateway(),
        conn_factory=conn_factory,
        task_runs_dir=tmp_path / "task_runs",
        uploads_dir=tmp_path / "uploads",
    )
    return pkg, conn_factory, registry, runtime


def _enqueue_and_claim(conn_factory, registry):
    conn = conn_factory()
    try:
        run = eval_runner.enqueue_eval_run(
            conn, agent_registry=registry, agent_id=_AGENT, triggered_by="acceptance"
        )
        claimed = repos.claim_next_queued_eval_run(conn, quota=4)
    finally:
        conn.close()
    return run, claimed


def _execute(run_id, conn_factory, registry, runtime, tmp_path):
    return eval_runner.execute_eval_run(
        run_id=run_id, conn_factory=conn_factory, agent_registry=registry,
        runtime=runtime, uploads_dir=tmp_path / "uploads", task_runs_dir=tmp_path / "task_runs",
    )


def _verdict(result: dict[str, Any], case_frag: str) -> dict[str, Any] | None:
    for cr in result.get("case_results", []):
        if case_frag in (cr.get("case_file") or ""):
            return cr
    return None


def test_cfd_evaluate_eval_reads_frozen_fixtures_via_snapshot(tmp_path, monkeypatch):
    # 全局活 env 清空——证评测绝不靠它（若工具读它必 fail-closed）。
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    pkg, conn_factory, registry, runtime = _setup(tmp_path)

    run, claimed = _enqueue_and_claim(conn_factory, registry)
    assert run["snapshot_handle"].startswith("snap_"), "入队须冻结不可变快照"
    assert claimed is not None and claimed["id"] == run["id"], "认领须把该 run 翻 running"

    # 删光活磁盘 fixtures——若执行读活包（而非材化快照），工具必失败。
    shutil.rmtree(pkg / "eval_cases" / "fixtures")
    assert not (pkg / "eval_cases" / "fixtures").exists()

    result = _execute(run["id"], conn_factory, registry, runtime, tmp_path)

    # 收敛路径（case_001）+ 诚实地板路径（case_002）都从**冻结** fixture 跑出真实评估。
    assert result["status"] == "completed", result
    c1 = _verdict(result, "case_001")
    c2 = _verdict(result, "case_002")
    assert c1 is not None and c1["verdict"] == "passed", ("case_001 未过", c1)
    assert c2 is not None and c2["verdict"] == "passed", ("case_002 未过", c2)
    assert result["passed"] == 2 and result["failed"] == 0, result

    # 绝无「env 未配置 / .hub_run_id 缺失 / run 不存在」——证没读到删掉的活目录或空 env。
    for cr in result["case_results"]:
        detail = (cr.get("detail") or "")
        assert "未配置" not in detail, ("疑似回退空 env", cr)
        assert "缺失" not in detail and "不存在" not in detail, ("疑似读到删掉的活目录", cr)


def test_tamper_env_only_adapter_breaks_frozen_read_red(tmp_path, monkeypatch):
    """tamper（RED）：把 cfd_result_read.run 换回「只认全局 env、无视 context」的 pre-#8 版 →
    活 fixtures 已删 + env 已清 → 工具 fail-closed → 评测全 failed。证 context 路由承重、
    上面的 GREEN 非空转（真 ToolRegistry 每次 call 都 importlib+getattr，故 setattr 生效）。"""
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    pkg, conn_factory, registry, runtime = _setup(tmp_path)

    run, claimed = _enqueue_and_claim(conn_factory, registry)
    assert claimed is not None

    shutil.rmtree(pkg / "eval_cases" / "fixtures")

    def _env_only_run(payload, context=None):
        # pre-#8：只认 $FLAI_CFD_CASE_DIR，无视 context（env 已清 → 恒 fail-closed）。
        if not os.environ.get("FLAI_CFD_CASE_DIR"):
            return {"status": "failed", "error_message": "FLAI_CFD_CASE_DIR 未配置——fail-closed"}
        return {"status": "failed", "error_message": "FLAI_CFD_CASE_DIR 未配置——fail-closed"}

    monkeypatch.setattr("tools_impl.cfd_result_read.adapter.run", _env_only_run)

    result = _execute(run["id"], conn_factory, registry, runtime, tmp_path)

    # 工具读不到冻结 fixture → workflow 诚实 failed（读求解结果失败）→ case failed。
    assert result["passed"] == 0, ("tamper 下不该有 case 过", result)
    assert result["failed"] >= 1, ("tamper 须至少咬出一个 failed", result)
