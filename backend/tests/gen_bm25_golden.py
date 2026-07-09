"""BM25 golden 差分 oracle 再生成工具（非测试，pytest 不收集——无 test_ 前缀）。

用真 rank_bm25 v0.2.2 BM25Okapi 生成 G1/G2/G3 三组语料的参考分数，冻结进
backend/tests/test_knowledge_bm25.py 的常量块。oracle 维护（loop-auditor d9）：
本脚本随仓存档，golden 与测试常量的一致性靠"语料/查询字面量与测试文件逐字
相同"维系——改任一侧必须同步另一侧并重跑本脚本对账。

初次生成环境：jieba 0.42.1（jieba 大版本变更分词结果时 golden 需重生成）。

运行（仓根）：
uv run --no-project --with "rank-bm25==0.2.2" --with jieba python backend/tests/gen_bm25_golden.py
"""
import math
import re

import jieba
import rank_bm25
from rank_bm25 import BM25Okapi

_DROP = re.compile(r"^[\s\W_]+$")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in jieba.lcut(text) if not _DROP.match(t)]


# ── 常量块（与测试文件逐字相同）─────────────────────────────────────

G1_DOCS = [
    "APU 滑油压力低告警多见于滑油滤堵塞或者滑油量不足。",
    "短舱排液孔堵塞会导致滑油积聚，检查排液孔是否有异物。",
    "APU 起动失败常见原因包括起动机故障与燃油供应不足。",
    "燃油滤压差告警提示燃油滤堵塞，需要更换滤芯。",
    "排液孔定期检查是短舱维护的重要项目，防止液体积聚。",
    "起动机更换后需要进行 APU 起动测试验证。",
]
G1_QUERIES = ["滑油滤堵塞", "APU 起动失败"]

G2_DOCS = [
    "排液孔堵塞需要立即清理。",
    "排液孔堵塞已经排除。",
]
G2_QUERY = "排液孔堵塞"

G3_DOCS = [
    "EGT 超温 egt overtemp 限制值 650 摄氏度。",
    "N1 转速波动 rpm fluctuation 需要持续监控。",
    "点火系统 igniter 检查 3 次均正常。",
]
G3_QUERY = "EGT 超温 650"

# ── 生成 ───────────────────────────────────────────────────────────

print(f"rank_bm25 version: {getattr(rank_bm25, '__version__', 'unknown')}")


def raw_idf(corpus_tok: list[list[str]], term: str) -> float:
    n = sum(1 for doc in corpus_tok if term in doc)
    big_n = len(corpus_tok)
    return math.log(big_n - n + 0.5) - math.log(n + 0.5)


def report(name: str, docs: list[str], queries: list[str]) -> None:
    corpus_tok = [tokenize(d) for d in docs]
    bm = BM25Okapi(corpus_tok)
    print(f"\n=== {name} ===")
    for i, toks in enumerate(corpus_tok):
        print(f"  doc[{i}] tokens = {toks}")
    print(f"  average_idf = {bm.average_idf:.6f}, eps = {0.25 * bm.average_idf:.6f}")
    for q in queries:
        q_tok = tokenize(q)
        print(f"  query {q!r} tokens = {q_tok}")
        for t in q_tok:
            raw = raw_idf(corpus_tok, t)
            stored = bm.idf.get(t)
            flag = " <-- NEGATIVE raw idf (floor path)" if raw < 0 else ""
            print(f"    idf[{t!r}]: raw={raw:.6f} stored={stored:.6f}{flag}")
        scores = bm.get_scores(q_tok)
        formatted = ", ".join(f"{s:.6f}" for s in scores)
        print(f"    GOLDEN {name} {q!r}: [{formatted}]")


report("G1", G1_DOCS, G1_QUERIES)
report("G2", G2_DOCS, [G2_QUERY])
report("G3", G3_DOCS, [G3_QUERY])
