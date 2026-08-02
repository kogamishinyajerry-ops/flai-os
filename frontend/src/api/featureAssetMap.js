import { ApiError, request } from "./client.js";
import { buildFeatureAssetMapView } from "../utils/featureAssetMap.js";


export async function getFeatureAssetMap() {
  const snapshot = await request("/api/feature-asset-map");
  const view = buildFeatureAssetMapView(snapshot);
  if (!view.available) {
    throw new ApiError(
      502,
      "功能/资产地图响应不完整，已停止披露，未展示残缺数据",
    );
  }
  return view;
}
