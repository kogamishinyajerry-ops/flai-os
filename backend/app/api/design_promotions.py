"""Authenticated P2.8 comparison, release, publication, and rollback API.

Every actor is derived from the authenticated request principal.  Client
payloads contain no signer field, and publication is available only through an
explicit synchronous request carrying strict confirmation and exact hashes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path as ApiPath, Request, Response

from ..design_promotion.contracts import (
    Actor,
    ComparisonCreate,
    PublishRequest,
    ReleaseDecisionRequest,
    ReleaseRequestCreate,
    RollbackRequest,
    SelectionRequest,
)
from ..design_promotion.service import (
    DesignPromotionError,
    DesignPromotionService,
    PngFrame,
    SensitiveCandidateRequiresRoleAxis,
)


router = APIRouter(prefix="/api", tags=["design-promotions"])

ComparisonId = Annotated[
    str, ApiPath(pattern=r"^comparison_[a-f0-9]{32}$", max_length=43)
]
ReleaseRequestId = Annotated[
    str, ApiPath(pattern=r"^release_[a-f0-9]{32}$", max_length=40)
]
FrameId = Annotated[str, ApiPath(pattern=r"^frame_[a-f0-9]{32}$", max_length=38)]


def _service(request: Request) -> DesignPromotionService:
    service = getattr(request.app.state, "design_promotion_service", None)
    if not isinstance(service, DesignPromotionService):
        raise RuntimeError("design promotion service is not assembled")
    return service


def _actor(request: Request) -> Actor:
    principal = request.state.user
    return Actor(
        username=principal["username"], display_name=principal["display_name"]
    )


def _raise_http(exc: DesignPromotionError) -> None:
    if isinstance(exc, SensitiveCandidateRequiresRoleAxis):
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/design-comparisons", status_code=201)
def create_design_comparison(
    body: ComparisonCreate, request: Request, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).create_comparison(body, actor=_actor(request))
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.get("/design-comparisons/{comparison_id}")
def get_design_comparison(
    comparison_id: ComparisonId, request: Request, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).get_comparison(comparison_id)
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.get(
    "/design-comparisons/{comparison_id}/frames/{frame_id}/{side}.png",
    response_class=Response,
)
def get_design_comparison_frame(
    comparison_id: ComparisonId,
    frame_id: FrameId,
    side: Literal["current", "candidate"],
    request: Request,
) -> Response:
    try:
        frame: PngFrame = _service(request).get_comparison_frame(
            comparison_id, frame_id, side
        )
    except DesignPromotionError as exc:
        _raise_http(exc)
    return Response(
        content=frame.content,
        media_type=frame.media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/design-comparisons/{comparison_id}/selection")
def decide_design_candidate(
    comparison_id: ComparisonId,
    body: SelectionRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).decide_candidate(
            comparison_id, body, actor=_actor(request)
        )
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.post("/design-release-requests", status_code=201)
def create_design_release_request(
    body: ReleaseRequestCreate, request: Request, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).create_release_request(body, actor=_actor(request))
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.post("/design-release-requests/{release_request_id}/decision")
def decide_design_release(
    release_request_id: ReleaseRequestId,
    body: ReleaseDecisionRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).decide_release(
            release_request_id, body, actor=_actor(request)
        )
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.post("/design-release-requests/{release_request_id}/publish")
def publish_design_release(
    release_request_id: ReleaseRequestId,
    body: PublishRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).publish_release(
            release_request_id, body, actor=_actor(request)
        )
    except DesignPromotionError as exc:
        _raise_http(exc)


@router.post("/design-release-requests/{release_request_id}/rollback")
def rollback_design_release(
    release_request_id: ReleaseRequestId,
    body: RollbackRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _service(request).rollback_release(
            release_request_id, body, actor=_actor(request)
        )
    except DesignPromotionError as exc:
        _raise_http(exc)
