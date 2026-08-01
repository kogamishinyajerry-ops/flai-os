"""Authenticated, side-effect-free Asset Draft preview endpoint."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.errors import ConversationNotFoundError
from ..ontology import (
    AssetDraftInputError,
    AssetDraftProjectionError,
    AssetDraftSourceError,
)

router = APIRouter(prefix="/api", tags=["asset-drafts"])


class AssetGeneralizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=160)
    trigger: str = Field(max_length=2000)
    desired_outcome: str = Field(max_length=2000)
    inputs: list[str] = Field(max_length=20)
    outputs: list[str] = Field(max_length=20)
    steps: list[str] = Field(max_length=20)
    evidence_requirements: list[str] = Field(max_length=20)
    human_decision_points: list[str] = Field(max_length=20)
    limitations: list[str] = Field(max_length=20)

    @field_validator(
        "inputs",
        "outputs",
        "steps",
        "evidence_requirements",
        "human_decision_points",
        "limitations",
    )
    @classmethod
    def list_items_must_be_bounded_and_non_blank(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item.strip():
                raise ValueError("数组项不得为空白")
            if len(item) > 1000:
                raise ValueError("数组项不得超过 1000 字符")
        return value


class AssetDraftPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["asset_draft_preview_request.v1"]
    generalization: AssetGeneralizationRequest


@router.post("/conversations/{conversation_id}/asset-draft-preview")
def preview_asset_draft(
    conversation_id: str,
    body: AssetDraftPreviewRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        conversation = request.app.state.conversation_service.get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        # 持久化 JSON 或旧记录形状损坏属于来源不可用；不把内部解码细节
        # 泄露给调用者，也不让它绕过 v0 的通用 503 失败语义。
        raise HTTPException(status_code=503, detail="资产草稿来源不可用") from exc

    try:
        return request.app.state.asset_draft_builder.preview(
            conversation=conversation,
            generalization=body.generalization.model_dump(),
        )
    except AssetDraftSourceError as exc:
        raise HTTPException(status_code=409, detail=f"无法形成 Work Case：{exc}") from exc
    except AssetDraftInputError as exc:
        # HTTP/Pydantic 已覆盖正常调用；保留深模块防御的诚实映射，避免未来
        # 非 HTTP adapter 把结构错误变成 500。
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssetDraftProjectionError as exc:
        raise HTTPException(status_code=503, detail="资产草稿投影不可用") from exc
