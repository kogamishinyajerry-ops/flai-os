"""Authenticated owner-scoped read-only feature and asset map endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..ontology import FeatureAssetMapUnavailableError


router = APIRouter(prefix="/api", tags=["feature-asset-map"])


@router.get("/feature-asset-map")
def get_feature_asset_map(request: Request) -> dict[str, Any]:
    try:
        conn = request.app.state.conn_factory()
    except Exception as exc:  # noqa: BLE001 - API boundary collapses infra detail.
        raise HTTPException(
            status_code=503,
            detail="功能/资产地图暂不可用",
        ) from exc
    try:
        return request.app.state.feature_asset_map_catalog.snapshot(
            conn,
            username=request.state.auth_session.username,
        )
    except FeatureAssetMapUnavailableError as exc:
        raise HTTPException(status_code=503, detail="功能/资产地图暂不可用") from exc
    finally:
        try:
            conn.close()
        except Exception as exc:  # noqa: BLE001 - close failure is unavailable.
            raise HTTPException(
                status_code=503,
                detail="功能/资产地图暂不可用",
            ) from exc
