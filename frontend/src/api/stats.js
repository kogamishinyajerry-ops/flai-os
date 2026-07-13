import { request } from "./client";

// 批B /today 只读聚合端点（backend/app/api/stats.py + governance.py §list_promotions_all）。
// since 必须 offset-aware ISO8601（服务端 fail-closed，naive/纯日期 422）——
// `new Date(...).toISOString()` 产生的 'Z' 后缀服务端已归一化，可直接传。
export const getStatsOverview = (sinceIso) =>
  request(`/api/stats/overview?since=${encodeURIComponent(sinceIso)}`);

// 全局最近晋升（最近优先，limit 服务端夹取 1-100）。
export const listGlobalPromotions = (limit = 20) =>
  request(`/api/promotions?limit=${limit}`);
