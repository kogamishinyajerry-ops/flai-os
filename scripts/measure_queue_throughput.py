"""Gate2-T1-M3（规模天花板量测）：job 队列吞吐 + 端到端时延 load benchmark。

对单串行 JobRunner 施 N 并发提交 × 单 worker 排干负载，量测吞吐（tasks/s）+ 端到端时延
p50/p99/max + 初始队列深度/最老龄期，落逐任务 JSONL（第三方可复算）。靶=hello_agent
（mock_echo，profile=none，确定性、无 LLM），跑完整最小任务生命周期。

**诚实边界（写死避免误读）**：
- 测量非优化。单 worker 串行是**刻意设计**（低 QPS、人在环签发），绝不当性能 bug。
- 「N 并发」= 并发**提交方**（多线程 create_task 入队），worker 仍单串行——量的是「队列
  机器 + 最小任务生命周期」的排干天花板，不是「加 worker 提吞吐」。tail 时延随队列深度线性
  增长正是该单串行设计的预期特征。
- 绝不碰 data/：用独立 tmp/自定义 db_dir（默认 tempfile 临时目录）。

反空洞（承接 measure_llm_latency gate-design BLOCK#1）：曲线来自**真排干**的原始逐任务
时延（JSONL 可复算）+ fail-closed（任一任务未达 completed → 非零退出、绝不出幸存者偏差
曲线）+ 两次重跑数量级 sanity。percentile/summarize/same_order_of_magnitude/bench_verdict
为纯函数（无 I/O），单测覆盖。

跑法（本机即可，无需内网 LLM）：`python scripts/measure_queue_throughput.py -n 200 -c 8`。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.app.jobs.runner import JobRunner  # noqa: E402
from backend.app.model_gateway.gateway import ModelGateway  # noqa: E402
from backend.app.runtime.registry import AgentRegistry  # noqa: E402
from backend.app.runtime.runtime import AgentRuntime  # noqa: E402
from backend.app.storage import repos  # noqa: E402
from backend.app.storage.db import get_conn, init_db  # noqa: E402
from backend.app.tools.registry import ToolRegistry  # noqa: E402


# ── 纯函数（无 I/O，单测 + tamper 覆盖）────────────────────────────────────

def percentile(sorted_vals: list[float], q: float) -> float:
    """最近秩（nearest-rank）百分位。sorted_vals 须已升序、非空；q∈[0,1]。"""
    if not sorted_vals:
        raise ValueError("percentile of empty sample")
    if q <= 0.0:
        return sorted_vals[0]
    if q >= 1.0:
        return sorted_vals[-1]
    rank = math.ceil(q * len(sorted_vals))  # 1-indexed
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def summarize(latencies_ms: list[float]) -> dict:
    """从时延列表算汇总。空样本显式返 n=0 + None（绝不伪造数字）。"""
    ok = sorted(latencies_ms)
    if not ok:
        return {"n": 0, "p50_ms": None, "p99_ms": None, "max_ms": None, "min_ms": None}
    return {
        "n": len(ok),
        "p50_ms": round(percentile(ok, 0.50), 1),
        "p99_ms": round(percentile(ok, 0.99), 1),
        "max_ms": round(ok[-1], 1),
        "min_ms": round(ok[0], 1),
    }


def same_order_of_magnitude(a: float, b: float, *, factor: float = 10.0) -> bool:
    """两次重跑吞吐 sanity：非零且比值在 factor 内视为同数量级（防一次性噪声/伪造曲线）。
    宽松（factor=10）——只排除数量级级别的失真，不做精度断言（负载机上吞吐本就抖）。"""
    if a <= 0.0 or b <= 0.0:
        return False
    hi, lo = (a, b) if a >= b else (b, a)
    return (hi / lo) <= factor


def bench_verdict(result: dict) -> tuple[bool, str]:
    """M3 fail-closed 判定（纯函数，可单测 + tamper）：唯全部任务真排干至 completed 且样本数
    相符才通过——任一任务未 completed → indeterminate（被排除的任务令幸存者曲线偏差，绝不
    宣称通过，镜像 measure_llm_latency.gate_verdict 幸存者防线）。"""
    n = result["n_tasks"]
    # A3（C1-P1-3）零任务拒：n<=0 时 `all([])` 真空真 + summary.n=0 会把空跑伪装成通过（无任何
    # 负载证据的假绿）。fail-closed 直接判 indeterminate，绝不放行空跑曲线。
    if n <= 0:
        return False, (f"indeterminate：n_tasks={n} <= 0（空跑）——all([]) 真空真 + summary.n=0 会"
                       "伪装通过，fail-closed 拒；须 n_tasks >= 1 才有可判定负载")
    completed = sum(1 for r in result["records"] if r["status"] == "completed")
    if result["all_completed"] is not True:
        return False, (f"indeterminate：{completed}/{n} 达 completed——未全排干，剩余任务令幸存者"
                       "曲线偏差；排查后重跑，勿宣称通过")
    if result["summary"]["n"] != n:
        return False, f"样本数不符：summary.n={result['summary']['n']} != n_tasks={n}（曲线不可信）"
    return True, (f"通过：{n} 任务全排干；吞吐 {result['throughput_tps']:.1f} tasks/s，"
                  f"端到端 p50={result['summary']['p50_ms']}ms p99={result['summary']['p99_ms']}ms")


# ── benchmark 主体 ────────────────────────────────────────────────────────

def _assemble_runner(db_dir: Path) -> tuple[JobRunner, "object"]:
    """在独立 tmp DB 装配真 registry + hello_agent 的 JobRunner（绝不碰 data/）。返回
    (runner, conn_factory)。与 test_job_runner 的 runtime_env 同款最小装配（无 bootstrap
    knowledge/scope 复杂度——hello_agent knowledge.enabled=false）。"""
    db_dir.mkdir(parents=True, exist_ok=True)  # 先建目录再开库（直接调用方如测试传入未建的 tmp）
    db_path = db_dir / "bench.db"
    init_db(db_path)

    agent_registry = AgentRegistry(REPO / "agents", REPO / "contracts" / "agent.schema.json")
    agent_registry.scan()
    tool_registry = ToolRegistry(REPO / "tools_impl", REPO / "contracts" / "tool.schema.json")
    tool_registry.scan()

    def conn_factory():
        return get_conn(db_path)

    c = conn_factory()
    try:
        agent_registry.sync_to_db(c)
    finally:
        c.close()

    model_gateway = ModelGateway(
        REPO / "backend" / "app" / "model_gateway" / "profiles.yaml", conn_factory=conn_factory
    )
    runtime = AgentRuntime(
        agent_registry, tool_registry, model_gateway, conn_factory, db_dir / "task_runs"
    )
    return JobRunner(runtime, conn_factory), conn_factory


def run_benchmark(*, db_dir: Path, n_tasks: int, n_submitters: int,
                  agent_id: str = "hello_agent") -> dict:
    """跑一轮 benchmark：N 并发提交 → 单串行 worker 排干 → 逐任务时延。返回结果 dict
    （含 records/summary/throughput/all_completed），不 sys.exit（判定交 bench_verdict/main）。"""
    # A3（C1-P1-3）零任务拒（fail-closed）：n<=0 空跑会令 all([]) 真空真 + summary.n=0 伪装通过；
    # n_submitters<=0 令 ThreadPoolExecutor 退化。入口即拒，绝不产出空洞曲线。
    if n_tasks <= 0:
        raise ValueError(f"n_tasks 必须 >= 1（空跑无可判定负载，fail-closed 拒）：得 {n_tasks}")
    if n_submitters <= 0:
        raise ValueError(f"n_submitters 必须 >= 1：得 {n_submitters}")
    runner, conn_factory = _assemble_runner(db_dir)

    # per-run 任务 id 命名空间（Codex R2-P2）：旧固定 bench_000000 在 --db-dir 复用（同库二跑）时
    # create_task 主键冲突直接炸——破「可复跑」。uuid 前缀令每轮 id 全局唯一；本轮记录只按本轮 tid
    # 集合收集，旧行不进曲线。诚实边界：上轮**中途放弃**残留的 queued 旧行会被本轮 drain 一并排掉
    # （计入 drain 墙钟但不入 records）——复用库跑精确对照请换空目录，本修只保证「不炸、曲线不混行」。
    run_tag = uuid.uuid4().hex[:8]

    # 1) N 并发提交入队（多线程 create_task + queued），记逐任务 enqueue 单调时刻 + 墙钟时刻
    #    （A5-P2-4：墙钟 ISO 时刻落盘供第三方复算 enqueue→complete 跨度）。
    enqueue_mono: dict[str, float] = {}
    enqueue_wall: dict[str, str] = {}

    def _submit(i: int) -> None:
        tid = f"bench_{run_tag}_{i:06d}"
        c = conn_factory()
        try:
            repos.create_task(
                c, task_id=tid, agent_id=agent_id, agent_version="0.1.0",
                name=f"bench {i}", created_by="bench", inputs={"name": f"n{i}"},
                input_file_ids=[], metadata={},
            )
            repos.set_task_status(c, tid, "queued")
        finally:
            c.close()
        enqueue_mono[tid] = time.monotonic()  # dict 单键赋值线程安全（GIL），键互不相同
        enqueue_wall[tid] = datetime.now(timezone.utc).isoformat()

    with ThreadPoolExecutor(max_workers=n_submitters) as ex:
        list(ex.map(_submit, range(n_tasks)))

    # 2) 采初始积压（把 M3 与 M2 get_queue_depth 互证：深队列 + 最老龄期）。
    c = conn_factory()
    try:
        initial_depth = repos.get_queue_depth(c)
    finally:
        c.close()

    # 3) 单串行排干；每 run_once 后只采队列龄期（O(1) 聚合），**不再逐轮扫全部 completed 行**。
    #    A5-P2-3：drain **每轮**采最老 queued 龄期留 max——串行 drain 的龄期峰值出现在排干后段
    #    （最后一条 queued 等得最久），只采「提交后-worker 启动前」的 initial 会漏掉峰值。
    #    ★Codex R2-P2：旧实现每 run_once 后 SELECT 全部 completed 行再 Python 去重=O(N²) 总观测
    #    开销（N 大时曲线量的是 instrumentation 天花板而非 JobRunner）。完成时刻改由 DB 权威
    #    finished_at 落库、drain 结束后**末次一扫**（O(N) 总量）——逐任务时延 = finished_at −
    #    enqueued_at（两者本就逐行落 JSONL，第三方复算与曲线自此同一口径）。
    max_queued_age_s = initial_depth.get("oldest_queued_age_s") or 0.0
    drain_start = time.monotonic()
    while True:
        c = conn_factory()
        try:
            depth = repos.get_queue_depth(c)
        finally:
            c.close()
        age = depth.get("oldest_queued_age_s")
        if age is not None and age > max_queued_age_s:
            max_queued_age_s = age

        did = runner.run_once()
        if did is not True:
            break
    drain_wall_s = time.monotonic() - drain_start

    # 4) 末次一扫收集逐任务记录 + fail-closed 终态核对（finished_at 由 DB 权威落 completed 时刻）。
    c = conn_factory()
    try:
        final_rows = {tid: repos.get_task(c, tid) for tid in enqueue_mono}
    finally:
        c.close()
    final_status = {tid: row["status"] for tid, row in final_rows.items()}

    records: list[dict] = []
    latencies_ms: list[float] = []
    for tid in sorted(enqueue_mono):
        status = final_status[tid]
        finished_at = final_rows[tid].get("finished_at")
        enqueued_at = enqueue_wall.get(tid)
        # 时延 = DB 权威 finished_at − 提交观测 enqueued_at（均 ISO 墙钟、均逐行落盘——曲线与第三方
        # 复算同一口径）。任一缺失/畸形 → None（诚实缺测，不猜值；completed 但无时延会被 summarize
        # 排除、bench_verdict 的 all_completed 核对不受影响）。
        latency_ms: float | None = None
        if finished_at is not None and enqueued_at is not None:
            try:
                latency_ms = (
                    datetime.fromisoformat(finished_at) - datetime.fromisoformat(enqueued_at)
                ).total_seconds() * 1000.0
            except ValueError:
                latency_ms = None
        records.append({
            "task_id": tid, "status": status, "latency_ms": latency_ms,
            # A5-P2-4：真实 enqueue（提交观测）+ complete（DB 权威 finished_at）墙钟时刻，
            # 配合 run-level drain_wall_s 令第三方可独立复算跨度/吞吐。
            "enqueued_at": enqueued_at,
            "finished_at": finished_at,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if status == "completed" and latency_ms is not None:
            latencies_ms.append(latency_ms)

    all_completed = (len(final_status) == n_tasks
                     and all(s == "completed" for s in final_status.values()))
    throughput_tps = (len(latencies_ms) / drain_wall_s) if drain_wall_s > 0 else 0.0
    return {
        "n_tasks": n_tasks,
        "n_submitters": n_submitters,
        "all_completed": all_completed,
        "drain_wall_s": round(drain_wall_s, 4),
        "max_queued_age_s": round(max_queued_age_s, 4),
        "throughput_tps": throughput_tps,
        "initial_queue_depth": initial_depth,
        "summary": summarize(latencies_ms),
        "records": records,
    }


def write_records_jsonl(records: list[dict], path: str | Path) -> None:
    """逐任务原始记录落 JSONL（第三方可复算吞吐/时延）。行数 == n_tasks。"""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_run_summary(result: dict, path: str | Path) -> None:
    """run-level 汇总落 JSON（A5-P2-4）：drain_wall_s + 吞吐 + max_queued_age_s + 初始积压 +
    时延汇总。此前 JSONL 只有 post-drain 的 per-task latency+ts，而吞吐用的 drain_wall_s 从不
    落盘→第三方拿不到 drain 墙钟基准、无法独立复算吞吐（n/drain_wall_s）。本文件补齐该基准。"""
    summary = {
        "n_tasks": result["n_tasks"],
        "n_submitters": result["n_submitters"],
        "all_completed": result["all_completed"],
        "drain_wall_s": result["drain_wall_s"],
        "max_queued_age_s": result.get("max_queued_age_s"),
        "throughput_tps": result["throughput_tps"],
        "initial_queue_depth": result["initial_queue_depth"],
        "latency_summary_ms": result["summary"],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def _suffixed(path: str, suffix: str) -> str:
    """在文件名 stem 与后缀间插入 .suffix（run1/run2/comparison 分别落盘，互不覆盖）。"""
    p = Path(path)
    return str(p.with_name(f"{p.stem}.{suffix}{p.suffix}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="job 队列吞吐 load benchmark（Gate2-T1-M3）")
    parser.add_argument("-n", "--tasks", type=int, default=200, help="入队任务总数（默认 200）")
    parser.add_argument("-c", "--submitters", type=int, default=8,
                        help="并发提交线程数（默认 8）——worker 仍单串行")
    parser.add_argument("-o", "--out", default="queue_throughput_samples.jsonl",
                        help="逐任务原始记录落盘路径（可第三方复算）")
    parser.add_argument("--summary-out", default="queue_throughput_summary.json",
                        help="run-level 汇总落盘路径（drain_wall_s 基准，A5-P2-4 可复算）")
    parser.add_argument("--db-dir", default=None,
                        help="benchmark 专用 DB 目录（默认临时目录，绝不碰 data/）")
    args = parser.parse_args()

    # A3（C1-P1-3）零任务拒（fail-closed）：--tasks/--submitters <= 0 清晰非零退出，绝不空跑报绿。
    if args.tasks <= 0 or args.submitters <= 0:
        print(f"错误：--tasks({args.tasks})/--submitters({args.submitters}) 必须 >= 1"
              "（空跑无可判定负载，fail-closed 拒）", file=sys.stderr)
        return 2

    base_dir = Path(args.db_dir) if args.db_dir else Path(tempfile.mkdtemp(prefix="flai_bench_"))
    base_dir.mkdir(parents=True, exist_ok=True)

    # A5-P2-b（Codex R1）：M3 要求**同配置重跑对照**——单跑一次的吞吐排不掉一次性噪声/伪造曲线。
    # 跑两遍（各自独立 db 子目录，互不污染），各自 records/summary 分别落盘；**两遍 bench_verdict 都
    # 通过 AND 两遍吞吐同数量级（same_order_of_magnitude）才判 M3 通过**。对照结论落盘可第三方复算。
    results = []
    for run_idx in (1, 2):
        db_dir = base_dir / f"run{run_idx}"
        db_dir.mkdir(parents=True, exist_ok=True)
        print(f"benchmark run {run_idx}/2：n_tasks={args.tasks} submitters={args.submitters} db_dir={db_dir}")
        result = run_benchmark(db_dir=db_dir, n_tasks=args.tasks, n_submitters=args.submitters)
        out_path = _suffixed(args.out, f"run{run_idx}")
        summary_path = _suffixed(args.summary_out, f"run{run_idx}")
        write_records_jsonl(result["records"], out_path)
        write_run_summary(result, summary_path)
        print(f"  run {run_idx} → 吞吐={round(result['throughput_tps'], 1)} tps · "
              f"all_completed={result['all_completed']} · drain_wall_s={round(result['drain_wall_s'], 2)} · "
              f"记录={out_path} · 汇总={summary_path}")
        results.append(result)

    r1, r2 = results
    tps1, tps2 = r1["throughput_tps"], r2["throughput_tps"]
    comparable = same_order_of_magnitude(tps1, tps2)
    passed1, verdict1 = bench_verdict(r1)
    passed2, verdict2 = bench_verdict(r2)
    # M3 通过 = 两遍各自都排干通过 AND 两遍吞吐同数量级（三者缺一不可，fail-closed）。
    passed = passed1 and passed2 and comparable

    comparison = {
        "n_tasks": args.tasks,
        "n_submitters": args.submitters,
        "run1": {"throughput_tps": round(tps1, 2), "drain_wall_s": r1["drain_wall_s"],
                 "all_completed": r1["all_completed"], "passed": passed1, "verdict": verdict1},
        "run2": {"throughput_tps": round(tps2, 2), "drain_wall_s": r2["drain_wall_s"],
                 "all_completed": r2["all_completed"], "passed": passed2, "verdict": verdict2},
        "same_order_of_magnitude": comparable,
        "throughput_ratio": (round(max(tps1, tps2) / min(tps1, tps2), 2)
                             if min(tps1, tps2) > 0.0 else None),
        "passed": passed,
    }
    cmp_path = _suffixed(args.summary_out, "comparison")
    with open(cmp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    print("\n=== 两遍同配置对照（A5-P2-b）===")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    print(f"对照结论已落盘：{cmp_path}（可第三方复算）")
    if comparable is False:
        print(f"⚠ 两遍吞吐非同数量级（{round(tps1, 1)} vs {round(tps2, 1)} tps）——疑一次性噪声/环境漂移")

    print(f"\nM3 判定 → {'✅ ' if passed else '❌ '}"
          f"run1[{'PASS' if passed1 else 'FAIL'}] · run2[{'PASS' if passed2 else 'FAIL'}] · "
          f"同数量级[{'是' if comparable else '否'}]")
    # fail-closed：唯两遍都排干且同数量级才 exit 0；否则非零，部署自动化不会误标绿。
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
