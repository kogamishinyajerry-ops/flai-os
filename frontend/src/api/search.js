import { request } from "./client.js";
import {
  SEARCH_SCOPES,
  isSearchableQuery,
  normalizeSearchQuery,
  validateSearchPage,
} from "../utils/searchCore.js";

const TASK_STATUSES = new Set([
  "created", "queued", "validating", "running", "waiting_review", "parsing",
  "analyzing", "completed", "failed", "cancelled",
]);
const CURSOR_PATTERN = /^[A-Za-z0-9_-]{1,4096}$/u;
const AGENT_ID_PATTERN = /^[a-z][a-z0-9_]{2,63}$/u;

// P2.4 read-only addressing endpoint.  Identity is derived from the login
// session; callers cannot send owner/username hints.
export async function searchAddresses({
  q,
  scope,
  limit = 6,
  cursor,
  status,
  agentId,
  taskScope,
} = {}) {
  const query = normalizeSearchQuery(q);
  if (!SEARCH_SCOPES.includes(scope)) throw new TypeError("未知搜索范围");
  if (!isSearchableQuery(query)) throw new TypeError("搜索词必须为 2-128 个非控制字符");
  if (!Number.isInteger(limit) || limit < 1 || limit > 20) {
    throw new TypeError("搜索条数必须为 1-20 的整数");
  }
  if (cursor !== undefined && cursor !== null && !CURSOR_PATTERN.test(cursor)) {
    throw new TypeError("搜索游标形状无效");
  }
  const isTaskScope = scope === "task" || scope === "artifact";
  if (!isTaskScope && (status !== undefined || agentId !== undefined || taskScope !== undefined)) {
    throw new TypeError("该搜索范围不接受任务过滤参数");
  }
  if (status !== undefined && !TASK_STATUSES.has(status)) {
    throw new TypeError("任务状态过滤值无效");
  }
  if (agentId !== undefined && !AGENT_ID_PATTERN.test(agentId)) {
    throw new TypeError("Agent 过滤值形状无效");
  }
  if (taskScope !== undefined && !["all", "mine"].includes(taskScope)) {
    throw new TypeError("任务范围过滤值无效");
  }
  const params = new URLSearchParams({ q: query, scope, limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  if (status) params.set("status", status);
  if (agentId) params.set("agent_id", agentId);
  if (taskScope) params.set("task_scope", taskScope);
  const payload = await request(`/api/search?${params.toString()}`, { cache: "no-store" });
  return validateSearchPage(payload, { scope, query });
}
