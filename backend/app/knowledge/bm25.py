"""离线 BM25 检索（jieba 分词），零外部服务依赖。

上游出处：COMAC_FDE core/retrieve.py（收编=复制适配）。上游依赖 rank_bm25 库，
本模块用纯 Python 复刻 rank_bm25 v0.2.2 BM25Okapi 的数值行为（k1=1.5、b=0.75、
epsilon=0.25），由 golden 差分测试逐值对齐（abs=1e-6）——收编不引入新三方依赖。

与 chunking.Chunk 的耦合仅存在于类型注解（TYPE_CHECKING guard，运行时不 import）：
运行时只 duck-type 访问 chunk.text，便于并行开发解耦；集成后注解自然指向真 Chunk。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import jieba

if TYPE_CHECKING:
    from .chunking import Chunk

# 整个 token 全由空白/非词字符/下划线组成者丢弃（纯标点、纯空格）——正则与 FDE 相同。
_DROP = re.compile(r"^[\s\W_]+$")

# BM25Okapi 参数：与 rank_bm25 v0.2.2 默认值一致，不开放调参（数值等价是契约）。
_K1 = 1.5
_B = 0.75
_EPSILON = 0.25


def tokenize(text: str) -> list[str]:
    """jieba 精确模式分词 → 小写 → 丢弃全标点/空白 token。"""
    return [t.lower() for t in jieba.lcut(text) if not _DROP.match(t)]


class BM25Okapi:
    """rank_bm25 v0.2.2 BM25Okapi 的纯 Python 数值等价复刻。

    必须复刻而非"修复"的参考实现行为：
    - idf(term) = ln((N − n + 0.5) / (n + 0.5))，n 为含该词文档数；
    - 负 idf 一律地板到 epsilon × average_idf（average_idf 为全词表 idf 均值，
      求均值时**含负值本身**；小语料下 average_idf 可为负，地板值随之为负——
      这是小语料 IDF 退化的参考实现行为，golden G2 专门钉死该路径）；
    - 查询词不在词表 → 贡献 0；查询词重复出现 → 重复累加。
    """

    def __init__(self, corpus: list[list[str]]) -> None:
        # 上游 rank_bm25 对空 corpus 会在 avgdl 计算处除零，这里显式 fail-closed。
        if not corpus:
            raise ValueError("空 corpus 不可建 BM25")
        # 全部文档分词后均为空（如纯标点语料）→ 参考实现在 average_idf 处除零，
        # 这里升级为诚实错误：零词汇语料建了索引也永远零命中，属坏语料。
        if not any(corpus):
            raise ValueError("语料分词后无有效词汇，不可建 BM25（纯标点/空白语料）")
        self.corpus_size = len(corpus)
        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_len) / self.corpus_size
        # 每篇文档词频表 + 每词出现文档数（nd）。
        self.doc_freqs: list[dict[str, int]] = []
        nd: dict[str, int] = {}
        for doc in corpus:
            freq: dict[str, int] = {}
            for tok in doc:
                freq[tok] = freq.get(tok, 0) + 1
            self.doc_freqs.append(freq)
            for tok in freq:
                nd[tok] = nd.get(tok, 0) + 1
        self._calc_idf(nd)

    def _calc_idf(self, nd: dict[str, int]) -> None:
        """镜像 rank_bm25 的 _calc_idf：先算全词表 idf 与均值，再地板负值。"""
        self.idf: dict[str, float] = {}
        idf_sum = 0.0
        negative_idfs: list[str] = []
        for word, freq in nd.items():
            idf = math.log(self.corpus_size - freq + 0.5) - math.log(freq + 0.5)
            self.idf[word] = idf
            idf_sum += idf
            if idf < 0:
                negative_idfs.append(word)
        self.average_idf = idf_sum / len(self.idf)
        eps = _EPSILON * self.average_idf
        for word in negative_idfs:
            self.idf[word] = eps

    def get_scores(self, query: list[str]) -> list[float]:
        """score(q, d) = Σ_t idf(t) · f(t,d)·(k1+1) / (f(t,d) + k1·(1 − b + b·|d|/avgdl))。"""
        scores = [0.0] * self.corpus_size
        for q in query:
            idf = self.idf.get(q) or 0.0  # 词表外查询词贡献 0（与参考实现同写法）
            for i in range(self.corpus_size):
                f = self.doc_freqs[i].get(q, 0)
                denom = f + _K1 * (1 - _B + _B * self.doc_len[i] / self.avgdl)
                scores[i] += idf * (f * (_K1 + 1) / denom)
        return scores


@dataclass
class Hit:
    chunk: Chunk
    score: float


class BM25Index:
    def __init__(self, chunks: list[Chunk], bm25: BM25Okapi) -> None:
        self.chunks = chunks
        self._bm25 = bm25

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "BM25Index":
        if not chunks:
            raise ValueError("空语料不可建索引")
        return cls(chunks, BM25Okapi([tokenize(c.text) for c in chunks]))

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        """仅返回 score > 0 的命中，按分数降序截 top_k。

        并列分数按语料原始顺序稳定排列（sorted 稳定性，与 FDE 行为一致）；
        零命中（查询词全在语料外或分数非正）诚实返回 []，不凑数。
        """
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [Hit(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]
