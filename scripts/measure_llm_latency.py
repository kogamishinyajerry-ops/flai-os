"""P0-B3（导入准入门）：内网模型延迟采样工具——测 p50/p99 + 落盘逐请求原始时延。

反空洞（gate-design 审 BLOCK#1）：B3 判据要求「内网延迟实测记录」是**工具产出、
可第三方复算的原始时延**，非手写汇总数字。本脚本对已配置的模型端点发 N 次真实请求，
逐请求记（时间戳/状态/时延 ms）落 JSONL，并按最近秩算 p50/p99；配置的
`FLAI_LLM_TIMEOUT_S` 须 > 实测 p99 才算 B3 通过。

现存 `scripts/probe_llm_gateway.py` 只做单次协议观测、不测延迟、不落盘（其 docstring
自认），故新增本脚本。**在目标机（内网）跑**：须配 FLAI_LLM_BASE_URL / FLAI_LLM_API_KEY
/ FLAI_LLM_MODEL_REASONING。percentile/summarize 为纯函数（无 I/O），单测覆盖。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone

import httpx

REQUIRED_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING")


def percentile(sorted_vals: list[float], q: float) -> float:
    """最近秩（nearest-rank）百分位。sorted_vals 须已升序、非空；q∈[0,1]。纯函数可单测。"""
    if not sorted_vals:
        raise ValueError("percentile of empty sample")
    if q <= 0.0:
        return sorted_vals[0]
    if q >= 1.0:
        return sorted_vals[-1]
    rank = math.ceil(q * len(sorted_vals))  # 1-indexed
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def summarize(latencies_ms: list[float]) -> dict:
    """从成功请求时延列表算汇总。空样本显式返 n=0 + None（不伪造数字）。"""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="内网模型延迟采样（P0-B3 导入准入门）")
    parser.add_argument("-n", "--samples", type=int, default=20, help="请求次数（默认 20）")
    parser.add_argument("-o", "--out", default="llm_latency_samples.jsonl",
                        help="逐请求原始时延落盘路径（可第三方复算）")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="采样期单请求超时上限秒（宽松，避免采样工具自身截断样本失真）")
    args = parser.parse_args()

    values = {name: os.environ.get(name) for name in REQUIRED_ENV_VARS}
    missing = [n for n, v in values.items() if not v]
    if missing:
        print("缺少环境变量：" + ", ".join(missing))
        return 2

    endpoint = f"{values['FLAI_LLM_BASE_URL'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {values['FLAI_LLM_API_KEY']}", "Content-Type": "application/json"}
    payload = {"model": values["FLAI_LLM_MODEL_REASONING"], "messages": [{"role": "user", "content": "ping"}]}

    latencies: list[float] = []
    with open(args.out, "w", encoding="utf-8") as f:
        for i in range(args.samples):
            t0 = time.monotonic()
            record: dict = {"i": i, "ts": datetime.now(timezone.utc).isoformat()}
            try:
                resp = httpx.post(endpoint, headers=headers, json=payload, timeout=args.timeout)
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                ok = 200 <= resp.status_code < 300
                record.update({"status": resp.status_code, "latency_ms": round(elapsed_ms, 1), "ok": ok})
                if ok:
                    latencies.append(elapsed_ms)
            except httpx.HTTPError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                record.update({"status": None, "latency_ms": round(elapsed_ms, 1),
                               "ok": False, "error": type(exc).__name__})
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"[{i + 1}/{args.samples}] status={record.get('status')} {record['latency_ms']}ms")

    summary = summarize(latencies)
    print("\n=== 延迟汇总（仅成功请求）===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"逐请求原始时延已落盘：{args.out}（可第三方复算）")
    configured = os.environ.get("FLAI_LLM_TIMEOUT_S")
    p99 = summary["p99_ms"]
    if p99 is not None:
        p99_s = p99 / 1000.0
        cfg_s = float(configured) if configured else 120.0
        verdict = "通过" if cfg_s > p99_s else "**不通过：配置超时 ≤ p99，须调大 FLAI_LLM_TIMEOUT_S**"
        print(f"\nP0-B3 判据：FLAI_LLM_TIMEOUT_S={cfg_s}s vs 实测 p99={p99_s:.2f}s → {verdict}")
    else:
        print("\nP0-B3 判据：零成功样本，无法判定——先排查端点连通性")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
