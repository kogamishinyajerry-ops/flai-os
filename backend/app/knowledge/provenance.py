"""知识引用回源读取器（评审 N7 / ADR-0029）：带密级门的只读原文通道。

KnowledgeService 的信任边界（service.py docstring）规定：服务层零授权判定，
除 Runtime 装配外不得直接持有服务实例。本模块是**经 ADR-0029 评审新增的第二
个合法持有者**——自带密级门的只读回源读取器，供 `GET /api/knowledge/chunk`
（签发人核对 knowledge_qa 草案引用出处）使用。除本读取器与 Runtime 装配外，
直接持有 KnowledgeService 的旧禁令不变。

密级门（fail-closed，全部显式比较，兜底拒绝）：
- scope 未注册 → KnowledgeScopeNotRegisteredError（对外 404，default-deny）；
- confidentiality == "restricted" → ProvenanceAccessDeniedError（对外 403）
  ——V0.1 无角色轴，登录态区分不了 admin，宁拒不泄；角色轴落地后另议放行；
- 枚举外/缺失密级 → 同样拒（无法验证 = 拒绝，同 scopes._confidentiality_denial
  的兜底哲学）；
- public_internal / department → 放行给登录用户（M11 全站登录已强制）。
  诚实边界：department 粒度的「本部门人员」判定在 V0.1 无部门轴，放行口径=
  「任何登录用户」——与现状一致（knowledge_qa 草案产物本就对登录用户可见，
  草案里已含语料摘录），记录于 ADR-0029，不静默。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import KnowledgeScopeNotRegisteredError
from .scopes import ScopeRegistry
from .service import KnowledgeService


class ProvenanceAccessDeniedError(Exception):
    """密级门拒绝回源（restricted / 未知密级）。"""


class ProvenanceAmbiguousError(Exception):
    """同 chunk_id 命中多个源文件且未带 source 消歧——拒绝猜，如实报歧义。"""

    def __init__(self, sources: list[str]) -> None:
        self.sources = sources
        super().__init__(f"chunk_id 命中 {len(sources)} 个源文件：{sources}")


@dataclass(frozen=True)
class ChunkProvenance:
    scope_id: str
    chunk_id: str
    doc_id: str
    source: str
    fingerprint: str
    text: str
    confidentiality: str


class ChunkProvenanceReader:
    """组合 ScopeRegistry（密级真值）与 KnowledgeService（语料读取）。"""

    def __init__(self, scope_registry: ScopeRegistry, knowledge_service: KnowledgeService) -> None:
        self._scope_registry = scope_registry
        self._knowledge_service = knowledge_service

    def read(self, scope_id: str, chunk_id: str, source: str | None = None) -> ChunkProvenance | None:
        scope = self._scope_registry.get(scope_id)
        if scope is None:
            raise KnowledgeScopeNotRegisteredError(
                f"knowledge scope {scope_id!r} 未在 Scope Registry 注册"
                "（default-deny：未注册即不存在）"
            )
        conf = scope.get("confidentiality")
        allowed = conf == "public_internal" or conf == "department"
        if allowed is not True:
            raise ProvenanceAccessDeniedError(
                f"scope {scope_id!r} 密级 {conf!r}：原文回源在角色轴落地前一律拒绝"
                "（fail-closed——restricted 与未知密级同拒）"
            )
        matches = self._knowledge_service.get_chunks_by_id(scope_id, chunk_id)
        if source is not None:
            matches = [c for c in matches if c.source == source]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise ProvenanceAmbiguousError(sorted({c.source for c in matches}))
        c = matches[0]
        return ChunkProvenance(
            scope_id=scope_id,
            chunk_id=c.chunk_id,
            doc_id=c.doc_id,
            source=c.source,
            fingerprint=c.fingerprint,
            text=c.text,
            confidentiality=conf,
        )
