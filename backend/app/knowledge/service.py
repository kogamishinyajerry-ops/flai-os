"""Knowledge 检索服务：scope_id + query → 出处完备的 KnowledgeHit 列表（ADR-0015）。

分层与既有 runtime 模式刻意同构：本模块之于 runtime/runtime.py 的
_KnowledgeContext，如同 tools/registry.py 的 ToolRegistry 之于
_ToolRegistryContext——服务层只管「解析 scope → 摄取语料 → 建索引 → 检索」，
授权判定整层不存在于此（信任边界见 KnowledgeService docstring）。

索引缓存以 manifest（相对路径 + 内容指纹）为失效判据：增/删/改任一源文件都
改变 manifest，下次检索自动重建索引——绝不基于 mtime 猜新鲜度（内网 Windows
拷贝会保留 mtime，指纹才是内容的真值）。manifest 的遍历/跳过规则必须与
chunking.ingest_dir 完全一致（rglob + 跳过点前缀分量），否则会出现
「索引里有但 manifest 看不见」的失效盲区。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import KnowledgeIngestError, KnowledgeScopeNotRegisteredError
from .bm25 import BM25Index
from .chunking import Chunk, ingest_dir
from .scopes import ScopeRegistry, resolve_source_dir

# top_k 硬上限：防单次检索把整库塞进上下文（payload 爆炸），超限静默截到 50
# 而非报错——调用方要"尽量多"是合法意图，上限是内核自保不是调用方违规。
MAX_TOP_K = 50

# manifest 条目：（相对源目录的 POSIX 路径, sha256(文件字节)[:12]）。
_Manifest = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class KnowledgeHit:
    """单条检索命中。出处四钥（scope_id/chunk_id/source/fingerprint）构造期强制非空。

    与 chunking.Chunk.__post_init__ 同款约束（loop-auditor Finding 3）：frozen
    只防已构造实例被改，非空校验把 docs/06 §4「无出处禁止进入上下文」落到
    类型层——防的是漏填/空串，不是恶意伪造。
    """

    scope_id: str
    chunk_id: str
    doc_id: str
    text: str
    source: str  # 出处：相对 scope 源目录的 POSIX 相对路径
    fingerprint: str  # 出处：sha256(源文件字节)[:12]
    score: float

    def __post_init__(self) -> None:
        for field_name in ("scope_id", "chunk_id", "source", "fingerprint"):
            value = getattr(self, field_name)
            if not (isinstance(value, str) and value.strip()):
                raise ValueError(f"KnowledgeHit.{field_name} 出处字段不得为空（docs/06 §4）")


class KnowledgeService:
    """按 scope 提供 BM25 检索 + 每 scope 索引缓存。

    **信任边界（loop-auditor Finding 2②，收口 tamper T5 的被证对象）**：
    本服务是内核内部 API，**不做任何授权判定**——agent 白名单与密级门全部在
    runtime._KnowledgeContext 层（与 _ToolRegistryContext/ToolRegistry 的分层
    完全同构）。绕过 context 直调本服务没有白名单保护：任何已注册 scope
    （无论密级）都能直接查到。因此除 Runtime 装配外，任何代码不得直接持有
    KnowledgeService 实例。**ADR-0029 修订**：新增第二个合法持有者
    provenance.ChunkProvenanceReader（自带密级门的只读回源通道，restricted/
    未知密级一律拒）——除此二者外禁令不变。
    """

    def __init__(self, scope_registry: ScopeRegistry) -> None:
        self._scope_registry = scope_registry
        # 缓存键 = scope_id，值 = (manifest, index, chunks)；manifest 不一致即整体重建。
        self._cache: dict[str, tuple[_Manifest, BM25Index, list[Chunk]]] = {}

    def search(self, scope_id: str, query: str, top_k: int = 5) -> list[KnowledgeHit]:
        """在单个已注册 scope 内检索，返回按分数降序的 KnowledgeHit（仅 score > 0）。

        - query 为空/全空白 → ValueError（空查询没有可检索的语义）；
        - top_k 上限 50（MAX_TOP_K）：>50 按 50 截断，不报错；
        - scope 未注册 → KnowledgeScopeNotRegisteredError（default-deny：未注册即不存在）；
        - 源目录不可用/逃逸 → resolve_source_dir 的异常原样向上透传；
        - 语料为空 → KnowledgeIngestError（fail-closed：空语料的零命中会被
          误读为"查过了没有"，必须与健康语料的零命中 [] 相区分）。
        """
        if query.strip() == "":
            raise ValueError("query 不得为空或全空白")
        if top_k < 1:
            # 负值会走 Python 负切片静默丢弃高分命中（反方审观察 c），显式拒绝。
            raise ValueError(f"top_k 必须 ≥1（收到 {top_k}）")
        if top_k > MAX_TOP_K:
            top_k = MAX_TOP_K
        scope = self._scope_registry.get(scope_id)
        if scope is None:
            raise KnowledgeScopeNotRegisteredError(
                f"knowledge scope {scope_id!r} 未在 Scope Registry 注册"
                "（default-deny：未注册即不存在）"
            )
        source_dir = resolve_source_dir(scope, self._scope_registry.scope_dir(scope_id))
        index = self._get_index(scope_id, source_dir)
        return [
            KnowledgeHit(
                scope_id=scope_id,
                chunk_id=hit.chunk.chunk_id,
                doc_id=hit.chunk.doc_id,
                text=hit.chunk.text,
                source=hit.chunk.source,
                fingerprint=hit.chunk.fingerprint,
                score=hit.score,
            )
            for hit in index.search(query, top_k=top_k)
        ]

    def get_chunks_by_id(self, scope_id: str, chunk_id: str) -> list[Chunk]:
        """按 chunk_id 取语料原文（评审 N7 引用回源），返回**全部**同 id 命中。

        chunk_id = f"{doc_id}#{i}" 而 doc_id 取文件 stem——同 stem 不同路径的
        文件会产生同 id chunk（模块 docstring 已声明的已知限制）。这里如实返回
        全部匹配，让上层带 source 消歧或显式报歧义，绝不首个命中就当唯一真相。

        - scope 未注册 → KnowledgeScopeNotRegisteredError（default-deny）；
        - 语料为空 → KnowledgeIngestError（与 search 同口径 fail-closed）；
        - 返回的是**当前语料**的 chunk：检索发生后语料若已更新，内容可能与
          检索当时不同（fingerprint 供上层比对，本层不伪装时间机器）。
        """
        scope = self._scope_registry.get(scope_id)
        if scope is None:
            raise KnowledgeScopeNotRegisteredError(
                f"knowledge scope {scope_id!r} 未在 Scope Registry 注册"
                "（default-deny：未注册即不存在）"
            )
        source_dir = resolve_source_dir(scope, self._scope_registry.scope_dir(scope_id))
        self._get_index(scope_id, source_dir)  # 命中即建/刷新缓存（manifest 失效判据同 search）
        chunks = self._cache[scope_id][2]
        return [c for c in chunks if c.chunk_id == chunk_id]

    def _get_index(self, scope_id: str, source_dir: Path) -> BM25Index:
        """取 scope 的 BM25 索引：manifest 与缓存一致则复用，否则重摄取重建。"""
        manifest = _build_manifest(source_dir)
        cached = self._cache.get(scope_id)
        if cached is not None and cached[0] == manifest:
            return cached[1]
        chunks = ingest_dir(source_dir)
        if not chunks:
            raise KnowledgeIngestError(
                f"scope {scope_id!r} 语料为空，拒绝提供检索"
                "（fail-closed：空语料的零命中会被误读为'查过了没有'）"
            )
        index = BM25Index.build(chunks)
        self._cache[scope_id] = (manifest, index, chunks)
        return index


def _build_manifest(source_dir: Path) -> _Manifest:
    """源目录 → 排序 manifest。遍历/跳过规则与 chunking.ingest_dir 严格一致。"""
    entries: list[tuple[str, str]] = []
    for p in source_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(source_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        entries.append((rel.as_posix(), digest))
    return tuple(sorted(entries))
