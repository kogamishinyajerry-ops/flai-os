"""知识引用回源端点（评审 N7 / ADR-0029）：签发人核对 [source · chunk] 引用的原文。

存在理由：knowledge_qa 草案带出处引用，但签发人点不开原文就只能橡皮图章——
引用体系的信任价值折半。本端点给「一步回源」：按检索事件里的
（scope_id, chunk_id）取当前语料原文与出处三钥（source/fingerprint/doc_id）。

安全边界（Codex 命中即审对象）：
- 登录强制：走全站 auth 中间件（M11），未登录 401；
- 密级门在 ChunkProvenanceReader（restricted/未知密级 → 403 fail-closed，
  角色轴落地前宁拒不泄）——本端点不自带第二套判定，单一门单一真源；
- chunk_id 含 `#`（f"{doc_id}#{i}"），一律走 query 参数不进路径；
- 同 id 多源文件命中且未带 source 消歧 → 409 如实报歧义（绝不猜首个）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from ..core.errors import KnowledgeIngestError, KnowledgeScopeNotRegisteredError
from ..knowledge.provenance import (
    ChunkProvenanceReader,
    ProvenanceAccessDeniedError,
    ProvenanceAmbiguousError,
)

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/knowledge/chunk")
def read_chunk(
    request: Request,
    scope_id: str = Query(min_length=1, max_length=100),
    chunk_id: str = Query(min_length=1, max_length=200),
    source: str | None = Query(default=None, min_length=1, max_length=500),
) -> dict[str, Any]:
    # 读取器按请求组装（零状态，成员是 app.state 单例）：API 只持有带密级门的
    # reader，不直接持有 KnowledgeService（service.py 信任边界，ADR-0029 修订版）。
    reader = ChunkProvenanceReader(
        request.app.state.scope_registry, request.app.state.knowledge_service
    )
    try:
        chunk = reader.read(scope_id, chunk_id, source=source)
    except KnowledgeScopeNotRegisteredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProvenanceAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProvenanceAmbiguousError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"chunk_id {chunk_id!r} 命中多个源文件，请带 source 参数消歧："
                f"{exc.sources}"
            ),
        ) from exc
    except KnowledgeIngestError as exc:
        # 语料为空/摄取失败：scope 在册但当前读不出内容——如实 409，不冒充 404
        # 「引用不存在」（引用可能在检索当时真实存在，是语料后来变了）。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"scope {scope_id!r} 当前语料中不存在 chunk {chunk_id!r}"
                "——语料可能在检索后被更新/删除（回源读的是当前语料，非检索时点快照）"
            ),
        )
    return {
        "scope_id": chunk.scope_id,
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "source": chunk.source,
        "fingerprint": chunk.fingerprint,
        "text": chunk.text,
        "confidentiality": chunk.confidentiality,
    }
