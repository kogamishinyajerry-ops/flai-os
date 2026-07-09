"""knowledge/bm25.py witness 测试（SPEC §3，一钥一门）。

golden 差分 oracle：G1/G2/G3 参考分数由真 rank_bm25 v0.2.2 生成后冻结，
再生成工具随仓存档 = backend/tests/gen_bm25_golden.py（非测试不被收集），命令：

    uv run --no-project --with "rank-bm25==0.2.2" --with jieba python backend/tests/gen_bm25_golden.py

本文件中的语料/查询字面量与生成脚本逐字相同（改任一侧必同步另一侧并重跑对账）。
生成时已验证 G2 查询词 raw idf = -1.609438 < 0（负 idf 地板路径真触发，
地板值 eps = 0.25 × average_idf = -0.150885，分数非零负值）。

BM25Index 结构性测试用 SimpleNamespace 鸭子型样本代替真 Chunk（并行解耦，
BM25Index 运行时只访问 .text）——与 SPEC 签名 list[Chunk] 的偏离已报告主控。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.knowledge.bm25 import BM25Index, BM25Okapi, tokenize

# ── 常量块（与生成脚本逐字相同）─────────────────────────────────────

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

# ── golden 冻结分数（rank_bm25 v0.2.2 真实输出，6 位小数）───────────

GOLDEN_G1 = {
    "滑油滤堵塞": [1.282790, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000],
    "APU 起动失败": [0.000000, 0.000000, 1.863115, 0.000000, 0.000000, 0.655176],
}
# G2 = 小语料退化：2 篇文档、查询词在两篇都出现 → 负 idf 地板的专属钥匙。
# 若实现漏掉 epsilon 地板（用 raw idf 或 clamp 到 0），仅本组红。
GOLDEN_G2 = [-0.434865, -0.471962]
GOLDEN_G3 = [1.721739, 0.000000, 0.000000]


def _scores(docs: list[str], query: str) -> list[float]:
    return BM25Okapi([tokenize(d) for d in docs]).get_scores(tokenize(query))


# ── witness 1：G1/G2/G3 差分逐值对齐 ────────────────────────────────


@pytest.mark.parametrize("query", G1_QUERIES)
def test_golden_g1_normal_corpus(query: str) -> None:
    assert _scores(G1_DOCS, query) == pytest.approx(GOLDEN_G1[query], abs=1e-6)


def test_golden_g2_negative_idf_floor() -> None:
    """负 idf 地板专属钥匙：分数为非零负值，raw idf / clamp-0 实现均无法对齐。"""
    assert _scores(G2_DOCS, G2_QUERY) == pytest.approx(GOLDEN_G2, abs=1e-6)


def test_golden_g3_mixed_language() -> None:
    assert _scores(G3_DOCS, G3_QUERY) == pytest.approx(GOLDEN_G3, abs=1e-6)


# ── witness 2：tokenize ─────────────────────────────────────────────


def test_tokenize_drops_pure_punctuation_and_whitespace() -> None:
    assert tokenize("！！！ ，。、 --- ___ \t\n") == []


def test_tokenize_lowercases_english() -> None:
    assert tokenize("Hello WORLD") == ["hello", "world"]


def test_tokenize_segments_chinese() -> None:
    toks = tokenize("短舱排液孔堵塞")
    assert len(toks) >= 2
    assert all(tok for tok in toks)


# ── witness 3：空语料 fail-closed ───────────────────────────────────


def test_build_empty_chunks_raises_value_error() -> None:
    with pytest.raises(ValueError):
        BM25Index.build([])


def test_bm25okapi_empty_corpus_raises_value_error() -> None:
    with pytest.raises(ValueError):
        BM25Okapi([])


# ── witness 4-6：BM25Index.search（SimpleNamespace 鸭子型样本）──────


def _chunk(i: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        doc_id=f"doc{i}",
        chunk_id=f"doc{i}#0",
        text=text,
        source=f"doc{i}.txt",
        fingerprint="0" * 12,
    )


def test_search_zero_hit_returns_empty() -> None:
    """score > 0 过滤的专属钥匙：语料外词零命中 → []，不凑数。"""
    index = BM25Index.build([_chunk(i, t) for i, t in enumerate(G1_DOCS)])
    assert index.search("区块链") == []


def test_search_top_k_truncates_and_sorts_descending() -> None:
    chunks = [
        _chunk(0, "滑油 液位 巡查"),
        _chunk(1, "压力 传感器"),
        _chunk(2, "泄漏 检测 程序 启动"),
        _chunk(3, "正常 巡检 记录"),
    ]
    index = BM25Index.build(chunks)
    all_hits = index.search("滑油 压力 泄漏", top_k=5)
    assert len(all_hits) == 3  # 三篇各命中一个查询词
    truncated = index.search("滑油 压力 泄漏", top_k=2)
    assert len(truncated) == 2
    assert truncated[0].score > truncated[1].score
    assert [h.chunk.chunk_id for h in truncated] == [h.chunk.chunk_id for h in all_hits[:2]]


def test_search_tie_order_is_stable() -> None:
    """边界 witness：并列分数按语料原始顺序稳定排列（sorted 稳定性）。"""
    chunks = [
        _chunk(0, "电源 电压 正常"),
        _chunk(1, "滑油 压力 告警"),
        _chunk(2, "滑油 压力 告警"),
        _chunk(3, "起动 电机 测试"),
        _chunk(4, "点火 装置 检查"),
    ]
    index = BM25Index.build(chunks)
    hits = index.search("滑油")
    assert len(hits) == 2
    assert hits[0].score == pytest.approx(hits[1].score)
    assert hits[0].chunk is chunks[1]
    assert hits[1].chunk is chunks[2]


def test_zero_vocabulary_corpus_rejected():
    """witness 7：全语料分词后零词汇 → 诚实 ValueError（参考实现此处除零，
    本实现升级为可读错误；BM25Okapi 与 BM25Index.build 两入口各一钥）。"""
    with pytest.raises(ValueError, match="无有效词汇"):
        BM25Okapi([[], []])
    with pytest.raises(ValueError, match="无有效词汇"):
        BM25Index.build([_chunk(0, "！！！…（）"), _chunk(1, "。。。")])
