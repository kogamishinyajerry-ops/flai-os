"""fea_solve_agent + fea_evaluate_agent（判据①第一发零内核 diff 验证弹）。

两层验证：
1. 单元（直调 workflow.run）：纯 stdlib 有限元求解对闭式解析解、评估 oracle 的
   正/负判定与 fail-closed。诚实负例（欠网格化 10.99% 误差）是非注入的真源回归——
   oracle 若逢正必过就会误判它通过。tamper 用改坏上游产物证明比对非空洞。
2. 集成（真实 runtime + resolver + 人签）：solve→evaluate 经 depends_on/input_binding
   声明式串联，**未签发的 solve 上游 resolver 绝不放行下游**（K1 签发见证闸），
   人签后才管道产物入队 evaluate——同时验证本发消费的协作运行时。

零内核 diff 断言（test_zero_kernel_diff_footprint）：本发不改 backend/app。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from backend.app.jobs.runner import JobRunner, resolve_dependencies_once
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.runtime.registry import AgentRegistry
from backend.app.runtime.runtime import AgentRuntime
from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db
from backend.app.tools.registry import ToolRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "agents" / "fea_evaluate_agent" / "eval_cases" / "fixtures"

# 悬臂钢梁算例（50×10mm 矩形截面，L=1.0m）：闭式 ω₁=52.49706 rad/s
_CANTILEVER = {
    "boundary_condition": "cantilever", "E": 210e9, "I": 4.1666666666666667e-9,
    "L": 1.0, "rho": 7850.0, "A": 5e-4, "n_elements": 10,
}
_CANTILEVER_OMEGA1 = 52.497056  # 闭式解析参考


def _load_workflow(agent_id: str):
    """按 Runtime 同款方式加载 workflow.py（spec_from_file_location，无父包）。"""
    path = REPO_ROOT / "agents" / agent_id / "workflow.py"
    spec = importlib.util.spec_from_file_location(f"flai_agent_{agent_id}_workflow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SOLVE = _load_workflow("fea_solve_agent")
_EVAL = _load_workflow("fea_evaluate_agent")


class _Logger:
    def log(self, *a, **k):
        pass


# ─────────────────────── 单元：solve ───────────────────────
def test_solve_cantilever_matches_closed_form(tmp_path):
    out = _SOLVE.run({"inputs": _CANTILEVER, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "success"
    sol = json.loads((tmp_path / "fea_solution.json").read_text())
    assert sol["solver"]["converged"] is True
    omega1 = sol["fem_result"]["omega1_rad_s"]
    # FEM 相对闭式解析解误差应极小（n=10 三次 Hermite 单元 ~8.6e-5%）
    assert abs(omega1 - _CANTILEVER_OMEGA1) / _CANTILEVER_OMEGA1 < 1e-4
    assert sol["params"]["boundary_condition"] == "cantilever"  # params 原样回存供 evaluate
    md = (tmp_path / "fea_solution.md").read_text()
    assert "判定权在人" in md  # 强制水印


def test_solve_simply_supported_matches_closed_form(tmp_path):
    inputs = {"boundary_condition": "simply_supported", "E": 7.0e10, "I": 1.256637e-7,
              "L": 2.0, "rho": 2700.0, "A": 1.256637e-3, "n_elements": 8}
    out = _SOLVE.run({"inputs": inputs, "output_dir": str(tmp_path), "event_logger": _Logger()})
    assert out["status"] == "success"
    sol = json.loads((tmp_path / "fea_solution.json").read_text())
    ref = (3.141592653589793 ** 2) * (7.0e10 * 1.256637e-7 / (2700.0 * 1.256637e-3 * 2.0 ** 4)) ** 0.5
    assert abs(sol["fem_result"]["omega1_rad_s"] - ref) / ref < 1e-3


def test_solve_convergence_improves_with_more_elements(tmp_path):
    """三次 Hermite 单元从上方单调收敛：n=8 比 n=1 更接近闭式（简支）。真源回归。"""
    def omega(n):
        d = tmp_path / f"n{n}"
        d.mkdir()
        base = {"boundary_condition": "simply_supported", "E": 7.0e10, "I": 1.256637e-7,
                "L": 2.0, "rho": 2700.0, "A": 1.256637e-3, "n_elements": n}
        _SOLVE.run({"inputs": base, "output_dir": str(d), "event_logger": _Logger()})
        return json.loads((d / "fea_solution.json").read_text())["fem_result"]["omega1_rad_s"]
    ref = (3.141592653589793 ** 2) * (7.0e10 * 1.256637e-7 / (2700.0 * 1.256637e-3 * 2.0 ** 4)) ** 0.5
    err1 = abs(omega(1) - ref) / ref
    err8 = abs(omega(8) - ref) / ref
    assert err1 > 0.10          # n=1 欠网格化 ~11% 误差（诚实负例的来源）
    assert err8 < 1e-3          # n=8 已收敛
    assert err8 < err1          # 单调收敛


# ─────────────────────── 单元：evaluate ───────────────────────
def _eval_on_file(tmp_path, solution_path: Path, tolerance_pct=2.0):
    ctx = {"inputs": {"tolerance_pct": tolerance_pct},
           "files": [{"filename": solution_path.name, "id": "x", "path": str(solution_path)}],
           "output_dir": str(tmp_path), "event_logger": _Logger()}
    out = _EVAL.run(ctx)
    ev = json.loads((tmp_path / "evaluation.json").read_text()) if out["status"] == "success" else None
    return out, ev


def _eval_on_dict(tmp_path, solution: dict, tolerance_pct=2.0):
    p = tmp_path / "fea_solution.json"
    p.write_text(json.dumps(solution, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    return _eval_on_file(out_dir, p, tolerance_pct)


def test_evaluate_passes_on_converged_fixture(tmp_path):
    out, ev = _eval_on_file(tmp_path, FIXTURES / "cantilever_n10" / "fea_solution.json")
    assert out["status"] == "success"
    assert ev["passed"] is True
    assert ev["error_pct"] < 0.01
    assert ev["upstream_converged"] is True
    md = (tmp_path / "evaluation.md").read_text()
    assert "判定权在人" in md and "一致" in md


def test_evaluate_honest_fail_on_under_meshed_fixture(tmp_path):
    """诚实负例（非注入）：简支 n=1 真实欠网格化 10.99% 误差 > 2% 容差 → passed=False。
    oracle 若逢正必过就会误判它通过——这是 oracle 判别力的真源回归见证。"""
    out, ev = _eval_on_file(tmp_path, FIXTURES / "ss_n1" / "fea_solution.json")
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] > 10.0
    assert "超出容差" in (tmp_path / "evaluation.md").read_text()


def test_evaluate_fail_closed_on_unconverged_upstream(tmp_path):
    """tamper：上游 solver.converged=false → 不给通过、error_pct=None、不编造。"""
    good = json.loads((FIXTURES / "cantilever_n10" / "fea_solution.json").read_text())
    good["solver"]["converged"] = False  # 拆上游收敛见证
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] is None          # 未达评估条件绝不给误差数
    assert "未达评估条件" in ev["verdict"]


def test_evaluate_catches_wrong_omega_tamper(tmp_path):
    """tamper：把上游 ω₁_fem 改成偏离闭式 20% 的错值 → oracle 必判 passed=False。
    证明 FEM vs 闭式的比对非空洞（不是无论输入都过）。"""
    good = json.loads((FIXTURES / "cantilever_n10" / "fea_solution.json").read_text())
    good["fem_result"]["omega1_rad_s"] = _CANTILEVER_OMEGA1 * 1.20  # 篡改成 +20%
    out, ev = _eval_on_dict(tmp_path, good)
    assert out["status"] == "success"
    assert ev["passed"] is False
    assert ev["error_pct"] > 15.0


def test_evaluate_fail_closed_on_missing_params(tmp_path):
    """tamper：产物缺 params → 诚实 failed，不臆测参数、不编造评估。"""
    out, ev = _eval_on_dict(tmp_path, {"fem_result": {"omega1_rad_s": 52.5}, "solver": {"converged": True}})
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
    return {"cf": cf, "runtime": runtime}


def test_chain_solve_signoff_then_evaluate(env):
    """全链：solve→waiting_review→（未签则 resolver 不放行）→人签 completed→resolver
    管道产物→evaluate→waiting_review→人签 completed，评估 passed=True。

    这条链同时验证：①两 Agent 均 review-gated（人是唯一签发者）②协作运行时
    depends_on/input_binding 确定性串联 ③K1 签发见证闸拦未签上游。"""
    cf = env["cf"]
    runner = JobRunner(env["runtime"], cf)

    conn = cf()
    try:
        repos.create_task(conn, task_id="solve1", agent_id="fea_solve_agent", agent_version="0.1.0",
                          name="梁求解", created_by="工程师张三", inputs=_CANTILEVER, origin="user")
        repos.set_task_status(conn, "solve1", "queued")
        repos.create_task(conn, task_id="eval1", agent_id="fea_evaluate_agent", agent_version="0.1.0",
                          name="梁评估", created_by="工程师张三", inputs={"tolerance_pct": 2.0},
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
    assert resolve_dependencies_once(cf) == 0
    conn = cf()
    try:
        assert repos.get_task(conn, "eval1")["status"] == "created"  # 未签则下游滞留
    finally:
        conn.close()

    # 3) 人工签发 solve → completed + review_approved 事件（K1 签发见证达成）
    conn = cf()
    try:
        repos.apply_human_review(conn, "solve1", action="approve", reviewer="工程师张三", comment=None)
        assert repos.get_task(conn, "solve1")["status"] == "completed"
    finally:
        conn.close()

    # 4) resolver 现在管道 solve 产物入 evaluate 并入队
    assert resolve_dependencies_once(cf) == 1
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

    # 6) 人工签发 evaluate → completed；评估 passed=True（悬臂 n=10 误差 8.6e-5%）
    conn = cf()
    try:
        repos.apply_human_review(conn, "eval1", action="approve", reviewer="工程师张三", comment=None)
        eval_task = repos.get_task(conn, "eval1")
        assert eval_task["status"] == "completed"
        out_files = repos.list_files_by_ids(conn, eval_task.get("output_file_ids") or [])
    finally:
        conn.close()
    ev_json = next(f for f in out_files if f["filename"] == "evaluation.json")
    data = json.loads(Path(ev_json["path"]).read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["error_pct"] < 0.01


# ─────────────────────── 判据①：零内核 diff 断言 ───────────────────────
def test_zero_kernel_diff_footprint():
    """判据①的可度量断言：本发相对 main 分叉点不改 backend/app/*（内核）。
    只加 agents/fea_*_agent/ 包 + 本测试文件。若某后续改动碰了内核，此测试红。"""
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", "main"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    changed = subprocess.run(
        ["git", "diff", "--name-only", merge_base, "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    # 已提交的内核改动为零；工作树未提交改动也一并检查（本发实现期）
    changed += subprocess.run(
        ["git", "diff", "--name-only", merge_base], cwd=REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.split()
    kernel_touched = sorted({p for p in changed if p.startswith("backend/app/")})
    assert kernel_touched == [], f"判据①违背：本发碰了内核 backend/app：{kernel_touched}"
