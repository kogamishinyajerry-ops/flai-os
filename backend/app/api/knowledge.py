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

from ..core.errors import (
    InvalidScopePackageError,
    KnowledgeIngestError,
    KnowledgeScopeNotRegisteredError,
    KnowledgeSourceUnavailableError,
)
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
    # chunk_id 上限对齐真实生产者（Codex 治理审 R0 P3）：doc_id=文件 stem，长文件名
    # 可产生 >200 字符的合法 chunk_id；上限设 512 覆盖现实 stem，短于 Service 侧无硬限
    # 但 URL 长度足够。仍设上限=DoS-echo 自保。
    chunk_id: str = Query(min_length=1, max_length=512),
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
        # 泛化对外文案（Codex 治理审 R0 P2）：不回显 scope_id repr。注意这**降低**
        # 泄漏面但**未消除存在性枚举**——404(未注册)/403(受限)/404(缺 chunk) 状态码
        # 仍可区分 scope 状态；这是刻意接受的边界（内网已登录员工受众 + 合法引用
        # 持有者应看到真实原因），如实记于 ADR-0029 §D5′，不 over-claim「杜绝枚举」。
        raise HTTPException(status_code=404, detail="知识范围不存在或未注册") from exc
    except ProvenanceAccessDeniedError as exc:
        # 泛化：只告知「受限不放行」，不回显具体密级值（P2）。
        raise HTTPException(
            status_code=403,
            detail="该知识范围为受限密级，原文回源在角色轴落地前一律不放行",
        ) from exc
    except ProvenanceAmbiguousError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"chunk_id {chunk_id!r} 命中多个源文件，请带 source 参数消歧："
                f"{exc.sources}"
            ),
        ) from exc
    except KnowledgeSourceUnavailableError as exc:
        # 语料源未接入/目录缺失（Codex 治理审 R0 P2 异常映射补全）：稳定 503，
        # 不外发内部路径细节（str(exc) 可能含目录），只给泛化可读文案。
        raise HTTPException(
            status_code=503, detail="该知识范围的语料源当前不可用"
        ) from exc
    except InvalidScopePackageError as exc:
        # scope 配置非法（含 `../` 逃逸等安全违规）：稳定 409，绝不回显路径。
        raise HTTPException(
            status_code=409, detail="该知识范围配置无效，暂不可回源"
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
