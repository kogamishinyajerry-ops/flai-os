const STORAGE_PREFIX = "flai-os:guide-batch:v1:";
const MAX_SERIALIZED_LENGTH = 512_000;
const OPERATION_ID_RE = /^guide_batch_[A-Za-z0-9_-]{8,100}$/;
const DIGEST_RE = /^[0-9a-f]{64}$/;

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isBoundedString(value, max = 256) {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function exactKeyCoverage(record, expectedKeys, valueIsValid) {
  if (!isRecord(record)) return false;
  const actualKeys = Object.keys(record).sort();
  const expected = [...new Set(expectedKeys)].sort();
  return actualKeys.length === expected.length
    && actualKeys.every((key, index) => key === expected[index])
    && actualKeys.every((key) => valueIsValid(record[key]));
}

function validItem(item, index) {
  if (!isRecord(item) || !isBoundedString(item.agentId, 128)) return false;
  if (item.name !== null && typeof item.name !== "string") return false;
  if (!isRecord(item.inputs)) return false;
  if (
    !Array.isArray(item.inputFileIds)
    || item.inputFileIds.some((fileId) => !isBoundedString(fileId, 128))
  ) return false;
  if (item.retryOf !== null && !isBoundedString(item.retryOf, 128)) return false;
  if (!Array.isArray(item.after)) return false;
  return item.after.every(
    (dependencyIndex) => Number.isInteger(dependencyIndex)
      && dependencyIndex >= 0
      && dependencyIndex < index,
  );
}

export function validBatchCreationAttempt(attempt) {
  if (!isRecord(attempt) || attempt.schemaVersion !== 1) return false;
  if (!isBoundedString(attempt.conversationId, 128)) return false;
  if (attempt.retryOf !== null && !isBoundedString(attempt.retryOf, 128)) return false;
  if (
    !isBoundedString(attempt.operationId, 128)
    || OPERATION_ID_RE.test(attempt.operationId) !== true
  ) return false;
  if (
    !Array.isArray(attempt.items)
    || attempt.items.length < 1
    || attempt.items.length > 5
    || attempt.items.some((item, index) => validItem(item, index) !== true)
  ) return false;

  const agentIds = attempt.items.map((item) => item.agentId);
  if (new Set(agentIds).size !== agentIds.length) return false;
  if (
    exactKeyCoverage(
      attempt.pinnedVersions,
      agentIds,
      (value) => isBoundedString(value, 64),
    ) !== true
  ) return false;
  if (
    exactKeyCoverage(
      attempt.pinnedPackageDigests,
      agentIds,
      (value) => typeof value === "string" && DIGEST_RE.test(value) === true,
    ) !== true
  ) return false;

  const snapshot = attempt.submittedPlanSnapshot;
  return isRecord(snapshot)
    && snapshot.conversationId === attempt.conversationId
    && snapshot.retryOf === attempt.retryOf;
}

function storageFor(storage) {
  let resolved = storage;
  if (resolved === undefined) {
    try {
      // origin-local 持久日志跨刷新、同源新标签页与浏览器恢复保留；只有拿到
      // 权威成功或零写入结论才删除。内容只保存本次 batch 已要发送的精确快照。
      resolved = globalThis.localStorage;
    } catch {
      throw new Error("创建操作日志不可用");
    }
  }
  if (
    !resolved
    || typeof resolved.getItem !== "function"
    || typeof resolved.setItem !== "function"
    || typeof resolved.removeItem !== "function"
  ) {
    throw new Error("创建操作日志不可用");
  }
  return resolved;
}

function storageKey(conversationId) {
  if (!isBoundedString(conversationId, 128)) {
    throw new Error("会话标识无法写入创建操作日志");
  }
  return `${STORAGE_PREFIX}${encodeURIComponent(conversationId)}`;
}

export function persistBatchCreationAttempt(attempt, storage) {
  const durable = {
    schemaVersion: 1,
    conversationId: attempt?.conversationId,
    retryOf: attempt?.retryOf ?? null,
    items: attempt?.items,
    pinnedVersions: attempt?.pinnedVersions,
    pinnedPackageDigests: attempt?.pinnedPackageDigests,
    operationId: attempt?.operationId,
    submittedPlanSnapshot: attempt?.submittedPlanSnapshot,
  };
  let serialized;
  try {
    serialized = JSON.stringify(durable);
  } catch {
    throw new Error("创建请求无法序列化");
  }
  if (
    typeof serialized !== "string"
    || serialized.length === 0
    || serialized.length > MAX_SERIALIZED_LENGTH
  ) {
    throw new Error("创建请求超出本地操作日志上限");
  }

  const canonical = JSON.parse(serialized);
  if (validBatchCreationAttempt(canonical) !== true) {
    throw new Error("创建请求缺少可恢复的版本、摘要或任务快照");
  }
  const targetStorage = storageFor(storage);
  const key = storageKey(canonical.conversationId);
  const existing = targetStorage.getItem(key);
  if (existing !== null) {
    const restored = restoreBatchCreationAttempt(canonical.conversationId, targetStorage);
    if (
      restored.state === "ready"
      && restored.attempt.operationId === canonical.operationId
      && existing === serialized
    ) return restored.attempt;
    if (restored.state === "ready") {
      throw new Error("该会话已有待核的开工请求，禁止换操作标识覆盖");
    }
    throw new Error("该会话已有无法读取的开工记录，禁止覆盖");
  }
  targetStorage.setItem(key, serialized);
  if (targetStorage.getItem(key) !== serialized) {
    throw new Error("创建操作日志写后核对失败");
  }
  return canonical;
}

export function restoreBatchCreationAttempt(
  conversationId,
  storage,
) {
  let raw;
  try {
    raw = storageFor(storage).getItem(storageKey(conversationId));
  } catch {
    // 当前版本在日志不可用时会在 POST 前阻断，因此这里没有可恢复记录的证据；
    // 不锁死所有历史会话，但后续开工仍会在 persist 阶段 fail-closed。
    return { state: "unavailable", attempt: null };
  }
  if (raw === null) return { state: "empty", attempt: null };
  if (typeof raw !== "string" || raw.length === 0 || raw.length > MAX_SERIALIZED_LENGTH) {
    return { state: "corrupt", attempt: null };
  }
  try {
    const parsed = JSON.parse(raw);
    if (
      validBatchCreationAttempt(parsed) !== true
      || parsed.conversationId !== conversationId
    ) {
      return { state: "corrupt", attempt: null };
    }
    return { state: "ready", attempt: parsed };
  } catch {
    return { state: "corrupt", attempt: null };
  }
}

export function clearBatchCreationAttempt(
  conversationId,
  operationId,
  storage,
) {
  const restored = restoreBatchCreationAttempt(conversationId, storage);
  if (
    restored.state !== "ready"
    || restored.attempt.operationId !== operationId
  ) return false;
  try {
    storageFor(storage).removeItem(storageKey(conversationId));
    return true;
  } catch {
    return false;
  }
}
