"""Authenticated owner-scoped read-only feature and asset map endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..ontology import FeatureAssetMapUnavailableError


router = APIRouter(prefix="/api", tags=["feature-asset-map"])


@router.get("/feature-asset-map")
def get_feature_asset_map(request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        return request.app.state.feature_asset_map_catalog.snapshot(
            conn,
            username=request.state.auth_session.username,
        )
    except FeatureAssetMapUnavailableError as exc:
        raise HTTPException(status_code=503, detail="功能/资产地图暂不可用") from exc
    finally:
        conn.close()
