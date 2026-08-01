"""step_response_solve_agent + step_response_evaluate_agent（判据①第二发零内核 diff 验证弹）。

与第一发（FEA 梁固有频率）是**不同的模块类**：本发是初值问题 ODE 的时间积分
（梯形/双线性 Tustin），第一发是特征值问题的空间离散——判据①要求「连续 2 个
不同模块类接入内核零 diff」，二者刻意选不同数值范式。

三层验证：
1. 单元（直调 workflow.run）：纯 stdlib 梯形积分对闭式解析超调、评估 oracle 的
   正/负判定与 fail-closed。诚实负例（n_steps=12 粗步长 41.5% 误差）是非注入的
   真源回归——oracle 若逢正必过就会误判它通过。tamper 用改坏上游产物证明比对非空洞。
2. 集成（真实 runtime + resolver + 人签）：solve→evaluate 经 depends_on/input_binding
   声明式串联，**未签发的 solve 上游 resolver 绝不放行下游**（K1 签发见证闸），
   人签后才管道产物入队 evaluate——同时验证本发消费的协作运行时。
3. eval_cases 实跑（run_agent_evals）：两 Agent 的 eval_cases 经真实治理 runner 全绿。

零内核 diff（backend/app 零改动）是本发一次性属性，经 `git diff backend/app` 为空
验证并记于设计文档——不放进永久 pytest 套件（第一发 Codex/loop-auditor 定论：
HEAD-vs-main 的 git-diff 断言既会在未来合法改内核的分支上误红，又对纯 untracked 文件盲）。
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from backend.app.governance.eval_runner import run_agent_evals
from backend.app.jobs.runner import JobRunner, resolve_dependencies_once
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "agents" / "step_response_evaluate_agent" / "eval_cases" / "fixtures"


def _closed_form_overshoot_pct(zeta: float) -> float:
    return 100.0 * math.exp(-zeta * math.pi / math.sqrt(1.0 - zeta * zeta))


# 欠阻尼算例：ζ=0.5 → Mp=16.3034%；ζ=0.3 → Mp=37.2326%（闭式解析参考）
_ZETA05 = {"zeta": 0.5, "omega_n": 1.0, "n_steps": 2000}
_ZETA05_MP = _closed_form_overshoot_pct(0.5)


def _load_workflow(agent_id: str):
    """按 Runtime 同款方式加载 workflow.py（spec_from_file_location，无父包）。"""
    path = REPO_ROOT / "agents" / agent_id / "workflow.py"
    spec = importlib.util.spec_from_file_location(f"flai_agent_{agent_id}_workflow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SOLVE = _load_workflow("step_response_solve_agent")
_EVAL = _load_workflow("step_response_evaluate_agent")


class _Logger:
    def log(self, *a, **k):
        pass


# ─────────────────────── 单元：solve ───────────────────────
def test_solve_matches_closed_form_zeta05(tmp_path):
    out = _SOLVE.run({"inputs": _ZETA05, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "success"
    sol = json.loads((tmp_path / "step_solution.json").read_text())
    assert sol["solver"]["converged"] is True
    ov = sol["response_result"]["overshoot_pct"]
    # 梯形 n=2000 相对闭式解析超调误差应极小（~0.0016%）
    assert abs(ov - _ZETA05_MP) / _ZETA05_MP < 1e-4
    assert sol["params"]["zeta"] == 0.5  # params 原样回存供 evaluate
    md = (tmp_path / "step_solution.md").read_text()
    assert "判定权在人" in md  # 强制水印


def test_solve_matches_closed_form_zeta03_omega2(tmp_path):
    """ζ=0.3 ωn=2：同时验 ωn≠1（不同时间尺度）——超调只依赖 ζ，时间尺度不改超调。"""
    inputs = {"zeta": 0.3, "omega_n": 2.0, "n_steps": 2000}
    out = _SOLVE.run({"inputs": inputs, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "success"
    sol = json.loads((tmp_path / "step_solution.json").read_text())
    ref = _closed_form_overshoot_pct(0.3)
    assert abs(sol["response_result"]["overshoot_pct"] - ref) / ref < 1e-3


def test_solve_convergence_improves_with_more_steps(tmp_path):
    """梯形从 O(h²) 收敛：n=2000 比 n=12 更接近闭式。真源回归（诚实负例的来源）。"""
    def overshoot(n):
        d = tmp_path / f"n{n}"
        d.mkdir()
        base = {"zeta": 0.5, "omega_n": 1.0, "n_steps": n}
        _SOLVE.run({"inputs": base, "output_dir": str(d), "event_logger": _Logger()})
        return json.loads((d / "step_solution.json").read_text())["response_result"]["overshoot_pct"]
    err_coarse = abs(overshoot(12) - _ZETA05_MP) / _ZETA05_MP
    err_fine = abs(overshoot(2000) - _ZETA05_MP) / _ZETA05_MP
    assert err_coarse > 0.10          # n=12 粗步长 ~41% 误差（诚实负例的来源）
    assert err_fine < 1e-3            # n=2000 已收敛
    assert err_fine < err_coarse      # 单调收敛


def test_solve_a_stable_at_coarse_no_blowup(tmp_path):
    """本发核心设计断言：梯形 A-稳定——粗到落入显式 RK4 的发散区仍不发散、且钉住方法。
    n_steps=4 时 ωn·dt≈3.63（|z|≈3.63 > RK4 振荡稳定限 2.828，RK4 放大因子 |R(z)|≈3.70>1）：
    梯形须给出有限有界解（peak≈1.347，超调≈34.71%），而显式 RK4 在此发散（peak→39.7、
    max|y|→151.6）。故 `peak<2` 与超调紧带宽两条断言各自独立会被 RK4 替换破坏——真区分
    梯形 vs RK4。（Codex P2-2 + loop-auditor Gap2 交叉命中：原 n=6 的 ωn·dt=2.42<2.828，
    RK4 在该处 |R|=0.80 仍稳定=测试防不住方法替换；已独立数值复核 n=4 处 RK4 真发散。）
    也防未来『优化』成显式法作废诚实负例。"""
    inputs = {"zeta": 0.5, "omega_n": 1.0, "n_steps": 4}
    out = _SOLVE.run({"inputs": inputs, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "success"
    sol = json.loads((tmp_path / "step_solution.json").read_text())
    ov = sol["response_result"]["overshoot_pct"]
    peak = sol["response_result"]["peak_value"]
    assert math.isfinite(ov) and math.isfinite(peak)
    assert peak < 2.0                # 梯形 peak≈1.347 有界；RK4 此处发散(peak≈39.7)破此断言
    assert 33.5 < ov < 36.0          # 钉梯形 n=4 特定超调 34.71%；RK4 的 ~3867% 破此断言


def test_solve_fail_closed_branch_reachable(tmp_path, monkeypatch):
    """solve 的无效仿真 fail-closed 分支（正常输入面不可达：0<ζ<1 恒有界内超调）
    经 monkeypatch 强制 _simulate_overshoot 返回 ok=False → run() 须诚实 failed，绝不出解。"""
    monkeypatch.setattr(_SOLVE, "_simulate_overshoot",
                        lambda z, w, n: (0.0, 0.5, 10.0, 0.1, False))
    out = _SOLVE.run({"inputs": _ZETA05, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "failed"
    assert not (tmp_path / "step_solution.json").exists()  # 不落无效解


# ─────────────────────── 单元：evaluate ───────────────────────
def _eval_on_file(tmp_path, solution_path: Path, tolerance_pct=2.0):
    ctx = {"inputs": {"tolerance_pct": tolerance_pct},
           "files": [{"filename": solution_path.name, "id": "x", "path": str(solution_path)}],
           "output_dir": str(tmp_path), "event_logger": _Logger()}
    out = _EVAL.run(ctx)
    ev = json.loads((tmp_path / "evaluation.json").read_text()) if out["status"] == "success" else None
    return out, ev


def _eval_on_dict(tmp_path, solution: dict, tolerance_pct=2.0):
    p = tmp_path / "step_solution.json"
    p.write_text(json.dumps(solution, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return _eval_on_file(out_dir, p, tolerance_pct)


def test_evaluate_passes_on_converged_fixture(tmp_path):
    out, ev = _eval_on_file(tmp_path, FIXTURES / "underdamped_fine" / "step_solution.json")
    assert out["status"] == "success"
    assert ev["passed"] is True
    assert ev["error_pct"] < 0.5
    assert ev["upstream_converged"] is True
    md = (tmp_path / "evaluation.md").read_text()
    assert "判定权在人" in md and "一致" in md


def test_evaluate_honest_fail_on_coarse_fixture(tmp_path):
    """诚实负例（非注入）：ζ=0.5 但 n_steps=12 真实粗步长 41.5% 误差 > 2% 容差 → passed=False。
    oracle 若逢正必过就会误判它通过——这是 oracle 判别力的真源回归见证。"""
    out, ev = _eval_on_file(tmp_path, FIXTURES / "coarse_grid" / "step_solution.json")
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] > 10.0
    assert "超出容差" in (tmp_path / "evaluation.md").read_text()


def test_evaluate_fail_closed_on_unconverged_upstream(tmp_path):
    """tamper：上游 solver.converged=false → 不给通过、error_pct=None、不编造。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["solver"]["converged"] = False  # 拆上游收敛见证
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] is None          # 未达评估条件绝不给误差数
    assert "未达评估条件" in ev["verdict"]


def test_evaluate_catches_wrong_overshoot_tamper(tmp_path):
    """tamper：把上游 overshoot 改成偏离闭式 50% 的错值 → oracle 必判 passed=False。
    证明仿真 vs 闭式的比对非空洞（不是无论输入都过）。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["response_result"]["overshoot_pct"] = _ZETA05_MP * 1.50  # 篡改成 +50%
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] > 40.0


def test_evaluate_fail_closed_on_bad_zeta(tmp_path):
    """tamper：params.zeta 篡改成越域值 → 闭式超调无定义 → 诚实 failed，不臆测、不编造。
    守 oracle 的 ζ 定义域护栏（_analytic_overshoot_pct 的 0<ζ<1 断言）。
    **关键含 ζ=-0.5（负阻尼）**：loop-auditor Gap1 变异测试证——ζ=1.5 时 sqrt(1-1.5²)
    自身抛 math domain error，护栏对它冗余（删护栏该值仍 failed=空洞见证）；护栏真正
    独占保护的是 ζ≤0（sqrt 不抛，无护栏则静默给 overshoot_ref≈613% 假判为 success）。
    故必须含 ζ=-0.5/0.0 才真咬住护栏——删护栏时这两个子例才会由绿转红。"""
    for i, bad_zeta in enumerate((-0.5, 0.0, 1.5)):
        good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
        good["params"]["zeta"] = bad_zeta
        d = tmp_path / f"z{i}"
        d.mkdir()
        out, ev = _eval_on_dict(d, good)
        assert out["status"] == "failed", f"ζ={bad_zeta} 应 fail-closed 但得 {out['status']}"


def test_evaluate_fail_closed_on_bad_omega_n(tmp_path):
    """Codex 异源审 P1：evaluate 走 file_upload 路径，solve input_schema 不作用于 params。
    tamper：params.omega_n 篡改成 -1 / 0（非正=非稳定标准二阶系统），即便 ζ/overshoot
    匹配、converged=true，也须 fail-closed，绝不假绿。中和 omega_n 护栏则此测试转红。"""
    for i, bad_wn in enumerate((-1.0, 0.0)):
        good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
        good["params"]["omega_n"] = bad_wn
        d = tmp_path / f"wn{i}"
        d.mkdir()
        out, ev = _eval_on_dict(d, good)
        assert out["status"] == "failed", f"ωn={bad_wn} 应 fail-closed 但得 {out['status']}"


def test_evaluate_fail_closed_on_underflow_ref(tmp_path):
    """Codex 异源审 P2：ζ=0.999992（schema 合法但过接近临界阻尼）令闭式 Mp_ref 下溢到 0——
    未加护栏时相对误差除零崩。护栏须 fail-closed（未达评估条件），绝不崩、绝不假绿。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["params"]["zeta"] = 0.999992
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "failed"


def test_evaluate_fail_closed_on_nonfinite_overshoot(tmp_path):
    """Codex 异源审 P2：上游 overshoot_pct=1e309（json 解析为 inf）——未加护栏时
    json.dump 把 overshoot_fem 字段写成非标准 Infinity 却报 success。**用 converged=false 路径**：
    结果级护栏 G5（error_pct 有限性）只在 converged 分支，不在此路径，故本测试唯一见证
    overshoot_fem 有限性护栏 G2（tamper 自证发现：converged=true 时 inf 会流到 error_pct 被
    G5 兜住掩盖 G2 见证——空洞；converged=false 时只有 G2 能拦 overshoot_fem=inf 进 json）。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["response_result"]["overshoot_pct"] = 1e309  # → inf
    good["solver"]["converged"] = False   # 走 not-converged 分支，G5 不触及，唯一见证 G2
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "failed"
    assert not (tmp_path / "out" / "evaluation.json").exists()  # 不落 Infinity 产物


def test_evaluate_fail_closed_on_error_pct_overflow(tmp_path):
    """Codex R1 P2（更深边界）：ζ=0.999991 令 overshoot_ref=2.6e-320（次正规、>0 且有限，
    过前置输入护栏），配 overshoot_fem=1.0 则相对误差除法溢出成 inf。结果级护栏须 fail-closed，
    绝不让 json 写出非标准 Infinity 却报 success。中和结果级护栏则此测试转红。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["params"]["zeta"] = 0.999991
    good["response_result"]["overshoot_pct"] = 1.0
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "failed"
    assert not (tmp_path / "out" / "evaluation.json").exists()  # 不落 Infinity 产物


def test_evaluate_fail_closed_on_huge_overshoot_overflow(tmp_path):
    """Codex R2 P2：error_pct 非有限的另一可达来源——上游 overshoot_pct=1e308（有限但极大，
    过 overshoot_fem 有限护栏）配普通 ζ=0.5（overshoot_ref≈16.3）时，相对误差 1e308/16.3×100
    仍溢出成 inf。结果级护栏须一并 fail-closed（证其覆盖两条溢出来源，非只次正规参考那条）。"""
    good = json.loads((FIXTURES / "underdamped_fine" / "step_solution.json").read_text())
    good["response_result"]["overshoot_pct"] = 1e308  # 有限但极大 → error_pct 溢出 inf
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "failed"
    assert not (tmp_path / "out" / "evaluation.json").exists()  # 不落 Infinity 产物


def test_evaluate_fail_closed_on_missing_params(tmp_path):
    """tamper：产物缺 params → 诚实 failed，不臆测参数、不编造评估。"""
    out, ev = _eval_on_dict(tmp_path, {"response_result": {"overshoot_pct": 16.3}, "solver": {"converged": True}})
    assert out["status"] == "failed"


def test_evaluate_fail_closed_on_no_json_input(tmp_path):
    """无 .json 输入文件 → 诚实 failed。"""
    ctx = {"inputs": {"tolerance_pct": 2.0}, "files": [], "output_dir": str(tmp_path), "event_logger": _Logger()}
    out = _EVAL.run(ctx)
    assert out["status"] == "failed"


# ─────────────────────── 集成：真实 runtime + resolver + 人签 ───────────────────────
@pytest.fixture()
def env(tmp_path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)
    agent_registry = AgentRegistry(REPO_ROOT / "agents", REPO_ROOT / "contracts" / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(REPO_ROOT / "tools_impl", REPO_ROOT / "contracts" / "tool.schema.json")
    tool_registry.scan()

    def cf():
        return get_conn(db_path)

    conn = cf()
    try:
        agent_registry.sync_to_db(conn)
    finally:
        conn.close()
    model_gateway = ModelGateway(
        REPO_ROOT / "backend" / "app" / "model_gateway" / "profiles.yaml", conn_factory=cf
    )
    runtime = AgentRuntime(agent_registry, tool_registry, model_gateway, cf, tmp_path / "task_runs")
    return {"cf": cf, "runtime": runtime, "registry": agent_registry}


def test_chain_solve_signoff_then_evaluate(env):
    """全链：solve→waiting_review→（未签则 resolver 不放行）→人签 completed→resolver
    管道产物→evaluate→waiting_review→人签 completed，评估 passed=True。

    同时验证：①两 Agent 均 review-gated（人是唯一签发者）②协作运行时
    depends_on/input_binding 确定性串联 ③K1 签发见证闸拦未签上游。"""
    cf = env["cf"]
    runner = JobRunner(env["runtime"], cf)

    conn = cf()
    try:
        repos.create_task(conn, task_id="solve1", agent_id="step_response_solve_agent", agent_version="0.1.0",
                          name="阶跃仿真", created_by="工程师李四", inputs=_ZETA05, origin="user")
        repos.set_task_status(conn, "solve1", "queued")
        repos.create_task(conn, task_id="eval1", agent_id="step_response_evaluate_agent", agent_version="0.1.0",
                          name="超调评估", created_by="工程师李四", inputs={"tolerance_pct": 2.0},
                          depends_on=["solve1"], input_binding={"from_tasks": ["solve1"]}, origin="user")
    finally:
        conn.close()

    # 1) solve 执行 → waiting_review（rhr=true，非 completed）
    assert runner.run_once() is True
    conn = cf()
    try:
        assert repos.get_task(conn, "solve1")["status"] == "waiting_review"
        assert repos.get_task(conn, "eval1")["status"] == "created"
    finally:
        conn.close()

    # 2) K1 签发见证闸：solve 未签发（仍 waiting_review）→ resolver 绝不放行下游
    assert resolve_dependencies_once(cf, env["registry"]) == 0
    conn = cf()
    try:
        assert repos.get_task(conn, "eval1")["status"] == "created"  # 未签则下游滞留
    finally:
        conn.close()

    # 3) 人工签发 solve → completed + review_approved 事件（K1 签发见证达成）
    conn = cf()
    try:
        repos.apply_human_review(conn, "solve1", action="approve", reviewer="工程师李四", comment=None)
        assert repos.get_task(conn, "solve1")["status"] == "completed"
    finally:
        conn.close()

    # 4) resolver 现在管道 solve 产物入 evaluate 并入队
    assert resolve_dependencies_once(cf, env["registry"]) == 1
    conn = cf()
    try:
        assert repos.get_task(conn, "eval1")["status"] == "queued"
    finally:
        conn.close()

    # 5) evaluate 执行 → waiting_review
    assert runner.run_once() is True
    conn = cf()
    try:
        assert repos.get_task(conn, "eval1")["status"] == "waiting_review"
    finally:
        conn.close()

    # 6) 人工签发 evaluate → completed；评估 passed=True（ζ=0.5 n=2000 误差 0.0016%）
    conn = cf()
    try:
        repos.apply_human_review(conn, "eval1", action="approve", reviewer="工程师李四", comment=None)
        eval_task = repos.get_task(conn, "eval1")
        assert eval_task["status"] == "completed"
        out_files = repos.list_files_by_ids(conn, eval_task.get("output_file_ids") or [])
    finally:
        conn.close()
    ev_json = next(f for f in out_files if f["filename"] == "evaluation.json")
    data = json.loads(Path(ev_json["path"]).read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["error_pct"] < 0.5


def test_eval_cases_all_green_through_runner(env):
    """两 Agent 的 eval_cases 经真实治理 runner（run_agent_evals，全链 runtime.execute
    + checks 机判）全绿——非休眠资产。同时坐实晋升门 min_eval_coverage：
    ≥3 approved case + 至少 1 个 status_is:failed。"""
    runtime = env["runtime"]
    for agent_id in ("step_response_solve_agent", "step_response_evaluate_agent"):
        result = run_agent_evals(
            conn_factory=env["cf"], agent_registry=env["registry"], runtime=runtime,
            uploads_dir=runtime.uploads_dir, task_runs_dir=runtime.task_runs_dir,
            agent_id=agent_id, triggered_by="pytest",
        )
        assert result["total"] >= 3, f"{agent_id} eval 覆盖不足：{result}"
        assert result["failed"] == 0, f"{agent_id} eval 有失败：{result.get('case_results')}"
        assert result["skipped"] == 0, f"{agent_id} eval 有跳过（无 checks?）：{result}"


def test_promotion_coverage_has_failure_path():
    """两 Agent 的 eval_cases 各含 ≥3 approved + 至少 1 个 status_is:failed，
    满足 min_eval_coverage 晋升门。直查磁盘 eval_cases（run_agent_evals 的 case_results
    不回传原始 checks）。"""
    for agent_id in ("step_response_solve_agent", "step_response_evaluate_agent"):
        cases_dir = REPO_ROOT / "agents" / agent_id / "eval_cases"
        approved = []
        for p in sorted(cases_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("curation", "approved") in (None, "approved"):
                approved.append(data)
        assert len(approved) >= 3, f"{agent_id} approved case < 3"
        has_failed = any(
            isinstance(c, dict) and c.get("kind") == "status_is" and c.get("value") == "failed"
            for case in approved for c in (case.get("checks") or [])
        )
        assert has_failed, f"{agent_id} 缺 status_is:failed 失败路径案（min_eval_coverage 会拒晋升）"
