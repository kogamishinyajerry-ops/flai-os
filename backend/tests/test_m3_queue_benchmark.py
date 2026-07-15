"""Gate2-T1-M3（规模天花板量测）：benchmark 纯函数单测 + 小 N 真排干 smoke + fail-closed。

- percentile/summarize/same_order_of_magnitude/bench_verdict 纯函数（反空洞：可复算、空样本
  不伪造、fail-closed 幸存者防线）。
- 小 N 真 hello_agent 排干 smoke：证 benchmark 真跑（非硬编码曲线）+ 全达 completed +
  样本数/JSONL 行数相符 + 两次重跑吞吐同数量级。
- fail-closed tamper：任一任务未 completed → bench_verdict 拒绝通过（承接
  measure_llm_latency 幸存者 tamper）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_bench():
    path = REPO_ROOT / "scripts" / "measure_queue_throughput.py"
    spec = importlib.util.spec_from_file_location("measure_queue_throughput", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 纯函数 ────────────────────────────────────────────────────────────────

def test_percentile_nearest_rank() -> None:
    m = _load_bench()
    vals = [10.0, 20.0, 30.0, 40.0, 100.0]  # 已升序
    assert m.percentile(vals, 0.50) == 30.0
    assert m.percentile(vals, 0.99) == 100.0
    assert m.percentile(vals, 0.0) == 10.0


def test_summarize_empty_no_fabrication() -> None:
    """空样本不伪造数字。tamper：让 summarize 对空样本回非 None p99 → 本断言红。"""
    m = _load_bench()
    s = m.summarize([])
    assert s["n"] == 0 and s["p99_ms"] is None and s["p50_ms"] is None


def test_same_order_of_magnitude() -> None:
    m = _load_bench()
    assert m.same_order_of_magnitude(100.0, 300.0) is True   # 3x 内
    assert m.same_order_of_magnitude(100.0, 2000.0) is False  # 20x 超 factor
    assert m.same_order_of_magnitude(0.0, 100.0) is False     # 零/负 = 不可信


def test_bench_verdict_fail_closed_on_incomplete() -> None:
    """★fail-closed tamper 锚：任一任务未 completed → indeterminate（不通过）。删 bench_verdict
    的 `all_completed is not True` 分支 → 本断言红（未排干仍报通过=幸存者假绿）。"""
    m = _load_bench()
    bad = {
        "n_tasks": 3, "all_completed": False, "throughput_tps": 1.0,
        "records": [{"status": "completed"}, {"status": "completed"}, {"status": "failed"}],
        "summary": {"n": 2, "p50_ms": 1.0, "p99_ms": 5.0},
    }
    ok, msg = m.bench_verdict(bad)
    assert ok is False and "indeterminate" in msg


def test_bench_verdict_fail_closed_on_sample_count_mismatch() -> None:
    """样本数与任务数不符 → 不通过（曲线不可信）。"""
    m = _load_bench()
    mismatch = {
        "n_tasks": 3, "all_completed": True, "throughput_tps": 1.0,
        "records": [{"status": "completed"}] * 3,
        "summary": {"n": 2, "p50_ms": 1.0, "p99_ms": 5.0},
    }
    assert m.bench_verdict(mismatch)[0] is False


def test_bench_verdict_pass_on_full_drain() -> None:
    m = _load_bench()
    good = {
        "n_tasks": 2, "all_completed": True, "throughput_tps": 5.0,
        "records": [{"status": "completed"}, {"status": "completed"}],
        "summary": {"n": 2, "p50_ms": 1.0, "p99_ms": 2.0},
    }
    assert m.bench_verdict(good)[0] is True


def test_bench_verdict_rejects_zero_tasks() -> None:
    """★A3 tamper 锚：n_tasks=0 空跑 → indeterminate（不通过）。空 records 令 all([]) 真空真 +
    summary.n==0 会伪装通过（无任何负载证据的假绿）。删 bench_verdict 的 `n <= 0` 分支 → 空跑
    报通过 → 本断言红。"""
    m = _load_bench()
    empty = {
        "n_tasks": 0, "all_completed": True, "throughput_tps": 0.0,
        "records": [], "summary": {"n": 0, "p50_ms": None, "p99_ms": None},
    }
    ok, msg = m.bench_verdict(empty)
    assert ok is False and "indeterminate" in msg


def test_run_benchmark_rejects_zero_tasks(tmp_path) -> None:
    """A3：run_benchmark 入口 fail-closed 拒 n_tasks<=0 / n_submitters<=0（绝不空跑产曲线）。"""
    m = _load_bench()
    with pytest.raises(ValueError):
        m.run_benchmark(db_dir=tmp_path / "z0", n_tasks=0, n_submitters=3)
    with pytest.raises(ValueError):
        m.run_benchmark(db_dir=tmp_path / "z1", n_tasks=3, n_submitters=0)


# ── 小 N 真排干 smoke + 两次重跑数量级 sanity ──────────────────────────────

def test_benchmark_truly_drains_and_reruns_same_magnitude(tmp_path) -> None:
    """★smoke tamper 锚：把 benchmark 改成不真跑、直返硬编码曲线 → 'all_completed/summary.n==N/
    JSONL 行数==N' 断言红。小 N=6 真 hello_agent 排干（含 mock_echo + 文件 I/O）证真跑，
    两次重跑吞吐同数量级证非一次性噪声/伪造。"""
    m = _load_bench()
    n = 6

    res_a = m.run_benchmark(db_dir=tmp_path / "run_a", n_tasks=n, n_submitters=3)
    assert res_a["all_completed"] is True             # 全排干至 completed
    assert res_a["summary"]["n"] == n                 # 真样本算，非伪造
    assert res_a["summary"]["p99_ms"] is not None
    assert len(res_a["records"]) == n
    assert res_a["throughput_tps"] > 0.0
    # 初始积压 = 全 N 入队（M3↔M2 get_queue_depth 互证深队列）。
    assert res_a["initial_queue_depth"]["queued"] == n

    # JSONL 行数 == n（逐任务原始可复算）。
    out = tmp_path / "samples.jsonl"
    m.write_records_jsonl(res_a["records"], out)
    assert sum(1 for _ in out.open(encoding="utf-8")) == n

    res_b = m.run_benchmark(db_dir=tmp_path / "run_b", n_tasks=n, n_submitters=3)
    assert res_b["all_completed"] is True
    assert m.same_order_of_magnitude(
        res_a["throughput_tps"], res_b["throughput_tps"]
    ) is True  # 两次重跑同数量级，非一次性噪声/伪造


def test_run_summary_and_records_are_reproducible(tmp_path) -> None:
    """★A5-P2-4 tamper 锚：run-level 汇总落 drain_wall_s 基准 + 逐任务落真实 enqueue/finish 墙钟
    时刻，令第三方可独立复算吞吐（n/drain_wall_s）。此前 JSONL 只有 post-drain latency+ts、
    drain_wall_s 从不落盘。删 write_run_summary 的 drain_wall_s 字段 → 本断言红。
    并证 A5-P2-3：drain 期采到的 max_queued_age_s 已落 run 汇总。"""
    m = _load_bench()
    n = 5
    res = m.run_benchmark(db_dir=tmp_path / "rep", n_tasks=n, n_submitters=3)

    summary_path = tmp_path / "summary.json"
    m.write_run_summary(res, summary_path)
    loaded = json.loads(summary_path.read_text(encoding="utf-8"))
    # drain 墙钟基准落盘（可复算吞吐）。
    assert loaded["drain_wall_s"] == res["drain_wall_s"]
    assert loaded["drain_wall_s"] > 0.0
    assert "max_queued_age_s" in loaded  # A5-P2-3 drain 期峰值龄期
    # 逐任务真实 enqueue/finish 墙钟时刻可复算（completed 任务两者皆非空）。
    for rec in res["records"]:
        assert rec["enqueued_at"] is not None
        if rec["status"] == "completed":
            assert rec["finished_at"] is not None
