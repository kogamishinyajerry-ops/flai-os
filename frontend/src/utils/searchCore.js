// P2.4 server-side addressing contract.  This module stays framework-free so
// the response boundary and deep-link construction can be exercised by Node.

export const SEARCH_SCOPES = Object.freeze([
  "conversation",
  "message",
  "task",
  "artifact",
]);

export const SEARCH_MIN_QUERY_LENGTH = 2;
export const SEARCH_MAX_QUERY_LENGTH = 128;
const MATCH_KINDS = new Set(["exact_id", "id_prefix", "text_prefix", "text_contains"]);
const TASK_STATUSES = new Set([
  "created", "queued", "validating", "running", "waiting_review", "parsing",
  "analyzing", "completed", "failed", "cancelled",
]);
const TIMESTAMP_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/u;

export class SearchContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "SearchContractError";
  }
}

export function normalizeSearchQuery(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function isSearchableQuery(value) {
  const query = normalizeSearchQuery(value);
  const length = [...query].length;
  return length >= SEARCH_MIN_QUERY_LENGTH
    && length <= SEARCH_MAX_QUERY_LENGTH
    && !/[\u0000-\u001f\u007f-\u009f]/u.test(query);
}

function assertString(value, label, { allowEmpty = false, nullable = false } = {}) {
  if (nullable && value === null) return;
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) {
    throw new SearchContractError(`搜索响应字段 ${label} 不是有效字符串`);
  }
}

function assertPattern(value, pattern, label) {
  assertString(value, label);
  if (!pattern.test(value)) throw new SearchContractError(`搜索响应字段 ${label} 格式无效`);
}

function assertAgentId(value, label) {
  assertPattern(value, /^[a-z][a-z0-9_]{2,63}$/u, label);
}

function assertTimestamp(value, label) {
  assertPattern(value, TIMESTAMP_PATTERN, label);
}

function assertNullableStringField(item, key, label) {
  if (!Object.hasOwn(item, key)) throw new SearchContractError(`搜索响应缺少字段 ${label}`);
  assertString(item[key], label, { nullable: true });
}

function assertExactKeys(value, allowed, label) {
  const extra = Object.keys(value).filter((key) => !allowed.includes(key));
  if (extra.length) throw new SearchContractError(`搜索响应 ${label} 含未声明字段 ${extra.join(",")}`);
}

function assertClassification(item, label) {
  if (!Object.hasOwn(item, "data_classification")) {
    throw new SearchContractError(`搜索响应缺少字段 ${label}`);
  }
  if (!["internal", "sensitive", null].includes(item.data_classification)) {
    throw new SearchContractError(`搜索响应字段 ${label} 超出允许范围`);
  }
}

function assertWithheld(item, label) {
  if (typeof item.content_withheld !== "boolean") {
    throw new SearchContractError(`搜索响应 ${label} 不是布尔值`);
  }
  const shouldWithhold = item.data_classification !== "internal";
  if (item.content_withheld !== shouldWithhold) {
    throw new SearchContractError(`搜索响应 ${label} 未遵守密级 fail-closed 关系`);
  }
}

function assertBaseItem(item, scope, index) {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    throw new SearchContractError(`搜索响应 ${scope}[${index}] 不是对象`);
  }
  if (item.kind !== scope) {
    throw new SearchContractError(`搜索响应 ${scope}[${index}] 类型错位`);
  }
  assertString(item.id, `${scope}[${index}].id`);
  assertTimestamp(item.created_at, `${scope}[${index}].created_at`);
  assertString(item.match_kind, `${scope}[${index}].match_kind`);
  if (!MATCH_KINDS.has(item.match_kind)) {
    throw new SearchContractError(`搜索响应 ${scope}[${index}].match_kind 超出允许范围`);
  }
}

function assertTypedItem(item, scope, index) {
  assertBaseItem(item, scope, index);
  if (scope === "conversation") {
    assertExactKeys(item, ["kind", "id", "agent_id", "status", "created_at", "match_kind"], `conversation[${index}]`);
    assertPattern(item.id, /^conv_[a-f0-9]{32}$/u, `conversation[${index}].id`);
    assertAgentId(item.agent_id, `conversation[${index}].agent_id`);
    assertString(item.status, `conversation[${index}].status`);
    if (!["active", "concluded"].includes(item.status)) {
      throw new SearchContractError(`搜索响应 conversation[${index}].status 超出允许范围`);
    }
    return;
  }
  if (scope === "message") {
    assertExactKeys(item, [
      "kind", "id", "conversation_id", "conversation_agent_id", "role", "snippet",
      "snippet_truncated", "created_at", "match_kind",
    ], `message[${index}]`);
    assertPattern(item.id, /^msg_[a-f0-9]{32}$/u, `message[${index}].id`);
    assertPattern(item.conversation_id, /^conv_[a-f0-9]{32}$/u, `message[${index}].conversation_id`);
    assertAgentId(item.conversation_agent_id, `message[${index}].conversation_agent_id`);
    assertString(item.role, `message[${index}].role`);
    if (!["user", "assistant"].includes(item.role)) {
      throw new SearchContractError(`搜索响应 message[${index}].role 超出允许范围`);
    }
    assertString(item.snippet, `message[${index}].snippet`, { allowEmpty: true });
    if ([...item.snippet].length > 240) {
      throw new SearchContractError(`搜索响应 message[${index}].snippet 超出长度上限`);
    }
    if (typeof item.snippet_truncated !== "boolean") {
      throw new SearchContractError(`搜索响应 message[${index}].snippet_truncated 不是布尔值`);
    }
    return;
  }
  if (scope === "task") {
    assertExactKeys(item, [
      "kind", "id", "name", "agent_id", "status", "data_classification",
      "content_withheld", "created_at", "match_kind",
    ], `task[${index}]`);
    assertNullableStringField(item, "name", `task[${index}].name`);
    if (item.id.length > 200) throw new SearchContractError(`搜索响应字段 task[${index}].id 过长`);
    if (typeof item.name === "string" && item.name.length > 200) {
      throw new SearchContractError(`搜索响应字段 task[${index}].name 过长`);
    }
    assertAgentId(item.agent_id, `task[${index}].agent_id`);
    assertString(item.status, `task[${index}].status`);
    if (!TASK_STATUSES.has(item.status)) {
      throw new SearchContractError(`搜索响应 task[${index}].status 超出允许范围`);
    }
    assertClassification(item, `task[${index}].data_classification`);
    assertWithheld(item, `task[${index}].content_withheld`);
    return;
  }
  assertExactKeys(item, [
    "kind", "id", "filename", "task_id", "task_name", "size_bytes",
    "data_classification", "content_withheld", "created_at", "match_kind",
  ], `artifact[${index}]`);
  assertString(item.filename, `artifact[${index}].filename`);
  assertString(item.task_id, `artifact[${index}].task_id`);
  if (item.id.length > 200 || item.task_id.length > 200) {
    throw new SearchContractError(`搜索响应 artifact[${index}] 地址字段过长`);
  }
  assertNullableStringField(item, "task_name", `artifact[${index}].task_name`);
  if (typeof item.task_name === "string" && item.task_name.length > 200) {
    throw new SearchContractError(`搜索响应字段 artifact[${index}].task_name 过长`);
  }
  if (!Number.isInteger(item.size_bytes) || item.size_bytes < 0) {
    throw new SearchContractError(`搜索响应 artifact[${index}].size_bytes 不是非负整数`);
  }
  assertClassification(item, `artifact[${index}].data_classification`);
  assertWithheld(item, `artifact[${index}].content_withheld`);
}

export function validateSearchPage(payload, { scope, query } = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new SearchContractError("搜索响应不是对象");
  }
  assertExactKeys(
    payload,
    ["schema_version", "scope", "query", "snapshot_at", "items", "has_more", "next_cursor"],
    "page",
  );
  if (payload.schema_version !== "search-page/v1") {
    throw new SearchContractError("搜索响应版本不受支持");
  }
  if (!SEARCH_SCOPES.includes(payload.scope) || (scope && payload.scope !== scope)) {
    throw new SearchContractError("搜索响应 scope 与请求不一致");
  }
  const expectedQuery = normalizeSearchQuery(query ?? payload.query);
  if (payload.query !== expectedQuery || !isSearchableQuery(payload.query)) {
    throw new SearchContractError("搜索响应 query 与请求不一致");
  }
  assertTimestamp(payload.snapshot_at, "snapshot_at");
  if (!Array.isArray(payload.items)) {
    throw new SearchContractError("搜索响应 items 不是数组");
  }
  if (payload.items.length > 20) {
    throw new SearchContractError("搜索响应 items 超出单页上限");
  }
  payload.items.forEach((item, index) => assertTypedItem(item, payload.scope, index));
  if (new Set(payload.items.map((item) => item.id)).size !== payload.items.length) {
    throw new SearchContractError("搜索响应 items 含重复地址");
  }
  if (typeof payload.has_more !== "boolean") {
    throw new SearchContractError("搜索响应 has_more 不是布尔值");
  }
  if (payload.next_cursor !== null && typeof payload.next_cursor !== "string") {
    throw new SearchContractError("搜索响应 next_cursor 不是字符串或 null");
  }
  if (
    typeof payload.next_cursor === "string"
    && !/^[A-Za-z0-9_-]{1,4096}$/u.test(payload.next_cursor)
  ) {
    throw new SearchContractError("搜索响应 next_cursor 不是有效的不透明游标");
  }
  if (payload.has_more !== (typeof payload.next_cursor === "string" && payload.next_cursor.length > 0)) {
    throw new SearchContractError("搜索响应 has_more 与 next_cursor 不一致");
  }
  return payload;
}

export function searchSelectionKey(type, item) {
  return item?.id ? `${type}:${item.id}` : "";
}

export function reconcileSearchSelection(keys, selectedKey = "") {
  if (!Array.isArray(keys) || keys.length === 0) return { index: 0, key: "" };
  const stableIndex = selectedKey ? keys.indexOf(selectedKey) : -1;
  const index = stableIndex >= 0 ? stableIndex : 0;
  return { index, key: keys[index] };
}

export function mergeSearchItems(primary, supplemental, limit = 6) {
  const merged = [];
  const seen = new Set();
  for (const item of [...(primary || []), ...(supplemental || [])]) {
    if (!item || typeof item.id !== "string" || item.id.length === 0 || seen.has(item.id)) continue;
    seen.add(item.id);
    merged.push(item);
    if (merged.length >= limit) break;
  }
  return merged;
}

export function buildSearchResultRoute(kind, item) {
  if (!item || item.kind !== kind) throw new SearchContractError("无法为错位的搜索结果生成地址");
  if (kind === "conversation") {
    return `/?${new URLSearchParams({ c: item.id }).toString()}`;
  }
  if (kind === "message") {
    return `/?${new URLSearchParams({ c: item.conversation_id, m: item.id }).toString()}`;
  }
  if (kind === "task") return `/tasks/${encodeURIComponent(item.id)}`;
  if (kind === "artifact") {
    return `/tasks/${encodeURIComponent(item.task_id)}?${new URLSearchParams({ file: item.id }).toString()}`;
  }
  if (kind === "agent") return "/portal";
  throw new SearchContractError("未知搜索结果类型");
}
