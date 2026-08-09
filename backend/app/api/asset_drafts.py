"""Authenticated, side-effect-free Asset Draft preview endpoint."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.errors import ConversationNotFoundError
from ..governance.signer_provenance import SignerContext
from ..ontology import (
    AssetCandidateConflictError,
    AssetCandidateNotFoundError,
    AssetCandidateUnavailableError,
    AssetDraftInputError,
    AssetDraftProjectionError,
    AssetDraftSourceError,
    SkillPackageConflictError,
    SkillPackageNotFoundError,
    SkillPackageUnavailableError,
)
from ..runtime.generalization_draft_record import (
    GeneralizationDraftRecordIntegrityError,
    GeneralizationDraftRecordNotFoundError,
    load_verified_generalization_draft_record,
)
from ..storage import asset_candidates as candidate_store
from . import object_authorization as oauth

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


class GeneralizationDraftRecordPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["generalization_draft_record_preview_request.v1"]
    expected_content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AssetCandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["asset_candidate_decision_request.v1"]
    action: Literal["accept", "reject"]
    expected_candidate_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    expected_bundle_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class SkillPackageDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["skill_package_decision_request.v1"]
    action: Literal["approve", "reject"]
    expected_package_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


@router.post("/conversations/{conversation_id}/asset-draft-preview")
def preview_asset_draft(
    conversation_id: str,
    body: AssetDraftPreviewRequest,
    request: Request,
) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        oauth.require_owned_conversation_inputs(
            conn,
            conversation_id,
            oauth.authenticated_username(request),
        )
    finally:
        conn.close()
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


@router.post(
    "/conversations/{conversation_id}/generalization-draft-records/"
    "{record_id}/asset-draft-preview"
)
def preview_generalization_draft_record(
    conversation_id: str,
    record_id: str,
    body: GeneralizationDraftRecordPreviewRequest,
    request: Request,
) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        owner_username = oauth.authenticated_username(request)
        oauth.require_owned_conversation(
            conn,
            conversation_id,
            owner_username,
        )
        verified = load_verified_generalization_draft_record(
            conn,
            conversation_id=conversation_id,
            record_id=record_id,
            owner_username=owner_username,
        )
    except GeneralizationDraftRecordNotFoundError:
        oauth.raise_resource_not_found()
    except GeneralizationDraftRecordIntegrityError as exc:
        raise HTTPException(
            status_code=503,
            detail="泛化草稿记录来源或证据不可用",
        ) from exc
    finally:
        conn.close()

    public_record = verified["public_record"]
    if body.expected_content_digest != public_record["content_digest"]:
        raise HTTPException(status_code=409, detail="泛化草稿记录内容摘要已变化")

    try:
        asset_draft = request.app.state.asset_draft_builder.preview(
            conversation=verified["source_context"]["conversation"],
            generalization=verified["payload"],
        )
    except (
        AssetDraftSourceError,
        AssetDraftInputError,
        AssetDraftProjectionError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail="泛化草稿记录来源或证据不可用",
        ) from exc

    return {
        "schema_version": "generalization_draft_record_preview_response.v1",
        "source_record": {
            "id": public_record["id"],
            "content_digest": public_record["content_digest"],
            "record_digest": public_record["record_digest"],
            "source_context_digest": public_record["source_context_digest"],
        },
        "asset_draft": asset_draft,
    }


def _candidate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AssetCandidateNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, AssetCandidateConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=503, detail="资产候选来源或账本不可用")


def _skill_package_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SkillPackageNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SkillPackageConflictError):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        )
    return HTTPException(status_code=503, detail="Skill Package 来源或证据不可用")


def _authorize_task_candidate_request(
    conn: Any,
    *,
    task_id: str,
    request: Request,
) -> str:
    """Authorize task lineage and any existing Candidate before ledger decode."""

    username = oauth.authenticated_username(request)
    candidate_id = candidate_store.get_latest_id_for_task(conn, task_id)
    if candidate_id is None:
        oauth.require_owned_task_conversation_inputs(conn, task_id, username)
        return username
    context = oauth.require_owned_asset_candidate_inputs(
        conn, candidate_id, username
    )
    if context.get("source_task_id") != task_id:
        oauth.raise_resource_not_found()
    return username


@router.post("/tasks/{task_id}/asset-candidate")
def create_asset_candidate(task_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        _authorize_task_candidate_request(conn, task_id=task_id, request=request)
        session = request.state.auth_session
        return request.app.state.asset_candidate_ledger.create_for_completed_task(
            conn,
            task_id=task_id,
            initiated_by_user_id=session.user_id,
            initiated_by_username=session.username,
        )
    except (
        AssetCandidateNotFoundError,
        AssetCandidateConflictError,
        AssetCandidateUnavailableError,
    ) as exc:
        raise _candidate_error(exc) from exc
    finally:
        conn.close()


@router.get("/tasks/{task_id}/asset-candidate")
def get_asset_candidate(task_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        _authorize_task_candidate_request(conn, task_id=task_id, request=request)
        return request.app.state.asset_candidate_ledger.get_for_task(
            conn,
            task_id=task_id,
            username=request.state.auth_session.username,
        )
    except (
        AssetCandidateNotFoundError,
        AssetCandidateConflictError,
        AssetCandidateUnavailableError,
    ) as exc:
        raise _candidate_error(exc) from exc
    finally:
        conn.close()


@router.post("/asset-candidates/{candidate_id}/decision")
def decide_asset_candidate(
    candidate_id: str,
    body: AssetCandidateDecisionRequest,
    request: Request,
) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        oauth.require_owned_asset_candidate_inputs(
            conn,
            candidate_id,
            oauth.authenticated_username(request),
        )
        return request.app.state.asset_candidate_ledger.decide(
            conn,
            candidate_id=candidate_id,
            action=body.action,
            expected_candidate_digest=body.expected_candidate_digest,
            expected_bundle_digest=body.expected_bundle_digest,
            signer_context=SignerContext.from_authenticated_session(
                request.state.auth_session
            ),
        )
    except (
        AssetCandidateNotFoundError,
        AssetCandidateConflictError,
        AssetCandidateUnavailableError,
    ) as exc:
        raise _candidate_error(exc) from exc
    finally:
        conn.close()


@router.get("/skill-packages/{package_id}")
def get_skill_package(package_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        conn.execute("BEGIN")
        try:
            username = oauth.authenticated_username(request)
            oauth.require_owned_skill_package_inputs(
                conn,
                package_id,
                username,
            )
            result = request.app.state.candidate_materializer.get(
                conn,
                package_id=package_id,
                username=username,
            )
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise
    except (
        SkillPackageNotFoundError,
        SkillPackageConflictError,
        SkillPackageUnavailableError,
    ) as exc:
        raise _skill_package_error(exc) from exc
    finally:
        conn.close()


@router.get("/skill-packages/{package_id}/review-content")
def get_skill_package_review_content(
    package_id: str,
    request: Request,
) -> dict[str, Any]:
    """Disclose the exact, cold-verified package bytes only to its owner."""

    conn = request.app.state.conn_factory()
    try:
        conn.execute("BEGIN")
        try:
            username = oauth.authenticated_username(request)
            oauth.require_owned_skill_package_inputs(
                conn,
                package_id,
                username,
            )
            result = request.app.state.candidate_materializer.get_review_content(
                conn,
                package_id=package_id,
                username=username,
            )
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise
    except (
        SkillPackageNotFoundError,
        SkillPackageConflictError,
        SkillPackageUnavailableError,
    ) as exc:
        raise _skill_package_error(exc) from exc
    finally:
        conn.close()


@router.post("/skill-packages/{package_id}/decision")
def decide_skill_package(
    package_id: str,
    body: SkillPackageDecisionRequest,
    request: Request,
) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            oauth.require_owned_skill_package_inputs(
                conn,
                package_id,
                oauth.authenticated_username(request),
            )
            result = request.app.state.candidate_materializer.decide(
                conn,
                package_id=package_id,
                expected_package_digest=body.expected_package_digest,
                action=body.action,
                signer_context=SignerContext.from_authenticated_session(
                    request.state.auth_session
                ),
            )
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise
    except (
        SkillPackageNotFoundError,
        SkillPackageConflictError,
        SkillPackageUnavailableError,
    ) as exc:
        raise _skill_package_error(exc) from exc
    finally:
        conn.close()
