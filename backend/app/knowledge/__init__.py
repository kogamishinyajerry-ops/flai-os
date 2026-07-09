"""Knowledge 内核检索服务（ADR-0015，收编自 COMAC_FDE core/{ingest,retrieve}.py）。

分层：chunking（文档→Chunk）→ bm25（分词+检索）→ scopes（注册表+装配对账）→
service（按 scope 检索+索引缓存）。授权不在本包——agent 白名单与密级门在
runtime._KnowledgeContext（运行时）与 scopes.reconcile_agent_scopes（装配期）。
"""

from .bm25 import BM25Index, tokenize
from .chunking import Chunk
from .scopes import ScopeRegistry, reconcile_agent_scopes, resolve_source_dir
from .service import KnowledgeHit, KnowledgeService

__all__ = [
    "BM25Index",
    "Chunk",
    "KnowledgeHit",
    "KnowledgeService",
    "ScopeRegistry",
    "reconcile_agent_scopes",
    "resolve_source_dir",
    "tokenize",
]
