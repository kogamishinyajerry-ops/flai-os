// Per-tab durable intent for Guide safe_auto turns.
//
// This record is only a crash/reload recovery aid. It never grants authority: every create,
// read, and message POST is authenticated and authorized again by the backend. Keeping the
// principal in the record lets the client fail closed before replay if the shared cookie has
// switched users or roles in another tab.

// The physical key intentionally stays at its original v1 name. Reusing it lets the v2 reader
// see an in-flight v1 record and fail closed as unsupported; moving to a new key would silently
// ignore that older pending intent and could permit a second safe-auto turn.
export const GUIDE_SAFE_AUTO_OUTBOX_KEY = "flai.guide.safe_auto.outbox.v1";
export const GUIDE_SAFE_AUTO_OUTBOX_VERSION = 2;

const PHASES = new Set([
  "preparing_uploads",
  "prepared",
  "creating_conversation",
  "posting_message",
  "awaiting_confirmation",
  "blocked",
]);
const AUTH_ROLES = new Set(["admin", "agent_developer", "business_user"]);
const REQUEST_ID_PATTERN = /^[A-Za-z0-9_.:-]{8,64}$/;


export class GuideSafeAutoOutboxError extends Error {
  constructor(code, message, cause = null) {
    super(`${code}: ${message}`);
    this.name = "GuideSafeAutoOutboxError";
    this.code = code;
    if (cause) this.cause = cause;
  }
}


function fail(code, message, cause = null) {
  throw new GuideSafeAutoOutboxError(code, message, cause);
}


function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}


function hasExactKeys(value, keys) {
  if (!isPlainObject(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}


function normalizePrincipal(principal) {
  if (
    !hasExactKeys(principal, ["username", "role"]) ||
    typeof principal.username !== "string" ||
    principal.username.length < 1 ||
    principal.username.length > 100 ||
    !AUTH_ROLES.has(principal.role)
  ) {
    fail("OUTBOX_PRINCIPAL_INVALID", "认证主体缺少服务端 username/role");
  }
  return { username: principal.username, role: principal.role };
}


function samePrincipal(left, right) {
  return left.username === right.username && left.role === right.role;
}


function validId(value, { nullable = false } = {}) {
  if (nullable && value === null) return true;
  return typeof value === "string" && value.length > 0 && value.length <= 128;
}


function validIsoTimestamp(value, { nullable = false } = {}) {
  if (nullable && value === null) return true;
  return typeof value === "string" && value.length > 0 && Number.isFinite(Date.parse(value));
}


function validNullableNonNegativeInteger(value) {
  return value === null || (Number.isSafeInteger(value) && value >= 0);
}


function validAttachmentIntent(entry) {
  return (
    hasExactKeys(entry, ["token", "name", "size_bytes", "mime_type", "last_modified"]) &&
    validId(entry.token) &&
    typeof entry.name === "string" &&
    entry.name.length > 0 &&
    entry.name.length <= 512 &&
    validNullableNonNegativeInteger(entry.size_bytes) &&
    typeof entry.mime_type === "string" &&
    entry.mime_type.length <= 255 &&
    validNullableNonNegativeInteger(entry.last_modified)
  );
}


function validateRecord(record) {
  if (!isPlainObject(record) || record.version !== GUIDE_SAFE_AUTO_OUTBOX_VERSION) {
    fail("OUTBOX_VERSION_UNSUPPORTED", "未知或缺失的 outbox 版本");
  }
  if (
    !hasExactKeys(record, [
      "version",
      "principal",
      "request_id",
      "agent_id",
      "conversation_id",
      "payload",
      "files",
      "attachment_intent",
      "phase",
      "created_at",
      "last_attempt_at",
    ])
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "outbox 字段不完整或包含未知字段");
  }
  normalizePrincipal(record.principal);
  if (
    typeof record.request_id !== "string" ||
    !REQUEST_ID_PATTERN.test(record.request_id) ||
    record.agent_id !== "guide_agent"
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "request_id/agent_id 非法");
  }
  if (!validId(record.conversation_id, { nullable: true })) {
    fail("OUTBOX_RECORD_MALFORMED", "conversation_id 非法");
  }
  if (
    !hasExactKeys(record.payload, ["content", "file_ids"]) ||
    typeof record.payload.content !== "string" ||
    !record.payload.content.trim() ||
    record.payload.content.length > 16000 ||
    !Array.isArray(record.payload.file_ids) ||
    record.payload.file_ids.length > 5 ||
    !record.payload.file_ids.every((id) => validId(id)) ||
    new Set(record.payload.file_ids).size !== record.payload.file_ids.length
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "payload 非法");
  }
  if (
    !Array.isArray(record.files) ||
    record.files.length !== record.payload.file_ids.length ||
    record.files.some(
      (file) =>
        !hasExactKeys(file, ["id", "name"]) ||
        !validId(file.id) ||
        typeof file.name !== "string" ||
        !file.name ||
        file.name.length > 512,
    ) ||
    record.files.some((file, index) => file.id !== record.payload.file_ids[index])
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "附件恢复记录必须与 file_ids 一一对应且不得含 raw File");
  }
  if (
    !Array.isArray(record.attachment_intent) ||
    record.attachment_intent.length > 5 ||
    record.attachment_intent.some((entry) => !validAttachmentIntent(entry)) ||
    new Set(record.attachment_intent.map((entry) => entry.token)).size !==
      record.attachment_intent.length
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "附件意图描述非法或包含重复 token");
  }
  if (record.phase === "preparing_uploads") {
    if (
      record.attachment_intent.length === 0 ||
      record.payload.file_ids.length !== 0 ||
      record.files.length !== 0
    ) {
      fail("OUTBOX_RECORD_MALFORMED", "上传准备阶段不得伪造服务端 file_id");
    }
  } else if (
    record.attachment_intent.length !== record.files.length ||
    record.attachment_intent.some((entry, index) => entry.name !== record.files[index].name)
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "附件意图必须与已绑定文件一一对应");
  }
  if (
    !PHASES.has(record.phase) ||
    !validIsoTimestamp(record.created_at) ||
    !validIsoTimestamp(record.last_attempt_at, { nullable: true })
  ) {
    fail("OUTBOX_RECORD_MALFORMED", "phase/时间戳非法");
  }
  return record;
}


function immutableIntentMatches(record, intent, principal) {
  return (
    samePrincipal(record.principal, principal) &&
    record.request_id === intent.requestId &&
    record.agent_id === intent.agentId &&
    record.conversation_id === intent.conversationId &&
    record.payload.content === intent.content &&
    JSON.stringify(record.payload.file_ids) === JSON.stringify(intent.fileIds) &&
    JSON.stringify(record.files) === JSON.stringify(intent.files) &&
    JSON.stringify(record.attachment_intent) === JSON.stringify(intent.attachmentIntent)
  );
}


function normalizeAttachmentIntent(entries, fallbackFiles = []) {
  const source = entries === undefined
    ? fallbackFiles.map((file) => ({
        token: file?.id,
        name: file?.name,
        sizeBytes: null,
        mimeType: "",
        lastModified: null,
      }))
    : entries;
  if (!Array.isArray(source)) fail("OUTBOX_INTENT_INVALID", "附件意图缺失");
  const normalized = source.map((entry) => ({
    token: entry?.token,
    name: entry?.name,
    size_bytes: entry?.sizeBytes ?? null,
    mime_type: entry?.mimeType ?? "",
    last_modified: entry?.lastModified ?? null,
  }));
  if (
    normalized.length > 5 ||
    normalized.some((entry) => !validAttachmentIntent(entry)) ||
    new Set(normalized.map((entry) => entry.token)).size !== normalized.length
  ) {
    fail("OUTBOX_INTENT_INVALID", "附件意图描述非法或包含重复 token");
  }
  return normalized;
}


function uploadIntentMatches(record, intent, principal) {
  return (
    samePrincipal(record.principal, principal) &&
    record.request_id === intent.requestId &&
    record.agent_id === intent.agentId &&
    record.conversation_id === intent.conversationId &&
    record.payload.content === intent.content &&
    JSON.stringify(record.attachment_intent) === JSON.stringify(intent.attachmentIntent)
  );
}


function normalizeIntent(intent) {
  if (!isPlainObject(intent)) fail("OUTBOX_INTENT_INVALID", "发送意图缺失");
  const normalized = {
    requestId: intent.requestId,
    agentId: intent.agentId,
    conversationId: intent.conversationId ?? null,
    content: typeof intent.content === "string" ? intent.content.trim() : intent.content,
    fileIds: Array.isArray(intent.fileIds) ? [...intent.fileIds] : intent.fileIds,
    files: Array.isArray(intent.files)
      ? intent.files.map((file) => ({ id: file?.id, name: file?.name }))
      : intent.files,
  };
  normalized.attachmentIntent = normalizeAttachmentIntent(
    intent.attachmentIntent,
    normalized.files,
  );
  const probe = {
    version: GUIDE_SAFE_AUTO_OUTBOX_VERSION,
    principal: { username: "probe", role: "admin" },
    request_id: normalized.requestId,
    agent_id: normalized.agentId,
    conversation_id: normalized.conversationId,
    payload: { content: normalized.content, file_ids: normalized.fileIds },
    files: normalized.files,
    attachment_intent: normalized.attachmentIntent,
    phase: "prepared",
    created_at: new Date(0).toISOString(),
    last_attempt_at: null,
  };
  try {
    validateRecord(probe);
  } catch (error) {
    fail("OUTBOX_INTENT_INVALID", error.message, error);
  }
  return normalized;
}


function normalizeUploadIntent(intent) {
  if (!isPlainObject(intent)) fail("OUTBOX_INTENT_INVALID", "上传前发送意图缺失");
  const normalized = {
    requestId: intent.requestId,
    agentId: intent.agentId,
    conversationId: intent.conversationId ?? null,
    content: typeof intent.content === "string" ? intent.content.trim() : intent.content,
    attachmentIntent: normalizeAttachmentIntent(intent.attachmentIntent),
  };
  const probe = {
    version: GUIDE_SAFE_AUTO_OUTBOX_VERSION,
    principal: { username: "probe", role: "admin" },
    request_id: normalized.requestId,
    agent_id: normalized.agentId,
    conversation_id: normalized.conversationId,
    payload: { content: normalized.content, file_ids: [] },
    files: [],
    attachment_intent: normalized.attachmentIntent,
    phase: normalized.attachmentIntent.length > 0 ? "preparing_uploads" : "prepared",
    created_at: new Date(0).toISOString(),
    last_attempt_at: null,
  };
  try {
    validateRecord(probe);
  } catch (error) {
    fail("OUTBOX_INTENT_INVALID", error.message, error);
  }
  return normalized;
}


export function createGuideSafeAutoOutbox({
  storage = undefined,
  key = GUIDE_SAFE_AUTO_OUTBOX_KEY,
  now = () => new Date().toISOString(),
} = {}) {
  let resolvedStorage = storage;
  let storageAccessError = null;
  if (resolvedStorage === undefined) {
    try {
      resolvedStorage = globalThis.sessionStorage;
    } catch (error) {
      storageAccessError = error;
    }
  }

  // Some privacy/sandbox policies throw while merely accessing window.sessionStorage. Do not
  // let that crash Vue setup and white-screen the page: expose an adapter whose first operation
  // is translated into a typed fail-closed error. GuidePage then locks the composer, and both
  // create/message POST counts remain zero.
  if (!resolvedStorage) {
    const unavailable = () => {
      throw storageAccessError || new Error("sessionStorage unavailable");
    };
    resolvedStorage = { getItem: unavailable, setItem: unavailable, removeItem: unavailable };
  }

  function readRaw() {
    try {
      return resolvedStorage.getItem(key);
    } catch (error) {
      fail("OUTBOX_STORAGE_READ_FAILED", "读取 sessionStorage 失败", error);
    }
  }

  function read() {
    const raw = readRaw();
    if (raw === null) return null;
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (error) {
      fail("OUTBOX_RECORD_MALFORMED", "outbox 不是合法 JSON", error);
    }
    return validateRecord(parsed);
  }

  function write(record) {
    validateRecord(record);
    const serialized = JSON.stringify(record);
    try {
      resolvedStorage.setItem(key, serialized);
    } catch (error) {
      fail("OUTBOX_STORAGE_WRITE_FAILED", "写入 sessionStorage 失败", error);
    }
    let roundTrip;
    try {
      roundTrip = resolvedStorage.getItem(key);
    } catch (error) {
      fail("OUTBOX_STORAGE_READBACK_FAILED", "sessionStorage 写后回读失败", error);
    }
    if (roundTrip !== serialized) {
      fail("OUTBOX_STORAGE_READBACK_FAILED", "sessionStorage 写后回读不一致");
    }
    return record;
  }

  function requireOwnedRecord(principal, requestId = null) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const record = read();
    if (!record) fail("OUTBOX_RECORD_MISSING", "待恢复意图不存在");
    if (!samePrincipal(record.principal, normalizedPrincipal)) {
      fail("OUTBOX_PRINCIPAL_MISMATCH", "当前认证主体与待恢复意图不一致");
    }
    if (requestId !== null && record.request_id !== requestId) {
      fail("OUTBOX_REQUEST_MISMATCH", "request_id 与待恢复意图不一致");
    }
    return record;
  }

  function prepare(principal, rawIntent) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const normalizedIntent = normalizeIntent(rawIntent);
    const existing = read();
    if (existing) {
      if (immutableIntentMatches(existing, normalizedIntent, normalizedPrincipal)) return existing;
      fail("OUTBOX_BUSY", "当前标签页已有另一条待确认 safe_auto 意图");
    }
    const createdAt = now();
    const record = {
      version: GUIDE_SAFE_AUTO_OUTBOX_VERSION,
      principal: normalizedPrincipal,
      request_id: normalizedIntent.requestId,
      agent_id: normalizedIntent.agentId,
      conversation_id: normalizedIntent.conversationId,
      payload: {
        content: normalizedIntent.content,
        file_ids: normalizedIntent.fileIds,
      },
      files: normalizedIntent.files,
      attachment_intent: normalizedIntent.attachmentIntent,
      phase: "prepared",
      created_at: createdAt,
      last_attempt_at: null,
    };
    return write(record);
  }

  function prepareUploads(principal, rawIntent) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const normalizedIntent = normalizeUploadIntent(rawIntent);
    const existing = read();
    if (existing) {
      if (uploadIntentMatches(existing, normalizedIntent, normalizedPrincipal)) return existing;
      fail("OUTBOX_BUSY", "当前标签页已有另一条待确认 safe_auto 意图");
    }
    const record = {
      version: GUIDE_SAFE_AUTO_OUTBOX_VERSION,
      principal: normalizedPrincipal,
      request_id: normalizedIntent.requestId,
      agent_id: normalizedIntent.agentId,
      conversation_id: normalizedIntent.conversationId,
      payload: { content: normalizedIntent.content, file_ids: [] },
      files: [],
      attachment_intent: normalizedIntent.attachmentIntent,
      phase: normalizedIntent.attachmentIntent.length > 0 ? "preparing_uploads" : "prepared",
      created_at: now(),
      last_attempt_at: null,
    };
    return write(record);
  }

  function completeUploads(principal, requestId, { fileIds, files }) {
    const record = requireOwnedRecord(principal, requestId);
    const candidate = normalizeIntent({
      requestId: record.request_id,
      agentId: record.agent_id,
      conversationId: record.conversation_id,
      content: record.payload.content,
      fileIds,
      files,
      attachmentIntent: record.attachment_intent.map((entry) => ({
        token: entry.token,
        name: entry.name,
        sizeBytes: entry.size_bytes,
        mimeType: entry.mime_type,
        lastModified: entry.last_modified,
      })),
    });
    if (record.phase !== "preparing_uploads") {
      if (immutableIntentMatches(record, candidate, normalizePrincipal(principal))) return record;
      fail("OUTBOX_UPLOAD_BINDING_CONFLICT", "附件 file_id 只能完整绑定一次");
    }
    if (
      candidate.files.length !== record.attachment_intent.length ||
      candidate.files.some((file, index) => file.name !== record.attachment_intent[index].name)
    ) {
      fail("OUTBOX_UPLOAD_BINDING_CONFLICT", "上传结果与持久化附件意图不一致");
    }
    return write({
      ...record,
      payload: { ...record.payload, file_ids: candidate.fileIds },
      files: candidate.files,
      phase: "prepared",
    });
  }

  function loadForPrincipal(principal) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const record = read();
    if (!record) return null;
    if (!samePrincipal(record.principal, normalizedPrincipal)) {
      fail("OUTBOX_PRINCIPAL_MISMATCH", "当前认证主体与待恢复意图不一致");
    }
    return record;
  }

  function matchesIntent(principal, rawIntent) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const normalizedIntent = normalizeIntent(rawIntent);
    const record = loadForPrincipal(normalizedPrincipal);
    return record !== null && immutableIntentMatches(record, normalizedIntent, normalizedPrincipal);
  }

  function matchesUploadIntent(principal, rawIntent) {
    const normalizedPrincipal = normalizePrincipal(principal);
    const normalizedIntent = normalizeUploadIntent(rawIntent);
    const record = loadForPrincipal(normalizedPrincipal);
    return record !== null && uploadIntentMatches(record, normalizedIntent, normalizedPrincipal);
  }

  function bindConversation(principal, requestId, conversationId) {
    if (!validId(conversationId)) fail("OUTBOX_CONVERSATION_INVALID", "conversation_id 非法");
    const record = requireOwnedRecord(principal, requestId);
    if (record.conversation_id !== null && record.conversation_id !== conversationId) {
      fail("OUTBOX_CONVERSATION_CONFLICT", "conversation_id 只能从 null 绑定一次");
    }
    if (record.conversation_id === conversationId) return record;
    return write({ ...record, conversation_id: conversationId });
  }

  function markAttempt(principal, requestId, phase) {
    if (!PHASES.has(phase) || phase === "prepared") {
      fail("OUTBOX_PHASE_INVALID", "非法 outbox phase");
    }
    const record = requireOwnedRecord(principal, requestId);
    return write({ ...record, phase, last_attempt_at: now() });
  }

  function clearConfirmed(principal, requestId) {
    requireOwnedRecord(principal, requestId);
    try {
      resolvedStorage.removeItem(key);
    } catch (error) {
      fail("OUTBOX_STORAGE_CLEAR_FAILED", "清除已确认 outbox 失败", error);
    }
    if (readRaw() !== null) fail("OUTBOX_STORAGE_CLEAR_FAILED", "清除 outbox 后回读仍存在");
  }

  return {
    read,
    prepare,
    prepareUploads,
    completeUploads,
    loadForPrincipal,
    matchesIntent,
    matchesUploadIntent,
    bindConversation,
    markAttempt,
    clearConfirmed,
  };
}


export function conversationHasGuideRequest(conversation, requestId) {
  if (!isPlainObject(conversation) || !Array.isArray(conversation.messages)) return false;
  return conversation.messages.some(
    (message) => message?.recommendation?.execution?.request_id === requestId,
  );
}


function requireConversationAuthority(conversation, conversationId) {
  if (
    !isPlainObject(conversation) ||
    conversation.id !== conversationId ||
    !Array.isArray(conversation.messages)
  ) {
    fail("OUTBOX_AUTHORITY_MISMATCH", "权威会话响应与已绑定 conversation_id 不一致");
  }
  return conversation;
}


export function filesFromGuideSafeAutoRecord(record) {
  validateRecord(record);
  if (record.phase === "preparing_uploads") {
    return record.attachment_intent.map((file, index) => ({
      uid: `outbox_pending_${index}_${file.token}`,
      name: file.name,
      raw: null,
      status: "error",
      fileId: null,
      error: "页面已刷新，原始附件不可恢复，已禁止自动重传",
      locked: true,
    }));
  }
  return record.files.map((file, index) => ({
    uid: `outbox_${index}_${file.id}`,
    name: file.name,
    raw: null,
    status: "done",
    fileId: file.id,
    error: "",
    locked: true,
  }));
}


async function createAndBindIfNeeded({ outbox, principal, record, createConversation, onConversationBound }) {
  if (record.phase === "preparing_uploads") {
    fail("OUTBOX_UPLOADS_INCOMPLETE", "附件上传尚未完成，刷新后禁止自动重传或创建会话");
  }
  let current = record;
  if (current.conversation_id === null) {
    outbox.markAttempt(principal, current.request_id, "creating_conversation");
    const conversation = await createConversation({
      agentId: current.agent_id,
      requestId: current.request_id,
      expectedPrincipal: { ...current.principal },
    });
    if (!isPlainObject(conversation) || !validId(conversation.id)) {
      fail("OUTBOX_CREATE_RESPONSE_INVALID", "新会话响应缺少 id");
    }
    current = outbox.bindConversation(principal, current.request_id, conversation.id);
  }
  if (onConversationBound) await onConversationBound(current.conversation_id, current);
  return current;
}


async function postPersistedIntent({ outbox, principal, record, postMessage, getConversation }) {
  outbox.markAttempt(principal, record.request_id, "posting_message");
  const response = await postMessage({
    conversationId: record.conversation_id,
    content: record.payload.content,
    fileIds: [...record.payload.file_ids],
    requestId: record.request_id,
    executionMode: "safe_auto",
    expectedPrincipal: { ...record.principal },
  });
  outbox.markAttempt(principal, record.request_id, "awaiting_confirmation");
  const conversation = requireConversationAuthority(
    await getConversation(record.conversation_id),
    record.conversation_id,
  );
  if (!conversationHasGuideRequest(conversation, record.request_id)) {
    fail("OUTBOX_CONFIRMATION_MISSING", "消息 POST 成功但权威会话尚未出现同一 request_id");
  }
  outbox.clearConfirmed(principal, record.request_id);
  return { response, conversation };
}


export async function dispatchGuideSafeAutoIntent({
  outbox,
  principal,
  intent,
  createConversation,
  postMessage,
  getConversation,
  onConversationBound = null,
}) {
  let record = outbox.prepare(principal, intent);
  record = await createAndBindIfNeeded({
    outbox,
    principal,
    record,
    createConversation,
    onConversationBound,
  });
  return postPersistedIntent({ outbox, principal, record, postMessage, getConversation });
}


export async function recoverGuideSafeAutoOutbox({
  outbox,
  principal,
  createConversation,
  postMessage,
  getConversation,
  onConversationBound = null,
}) {
  let record = null;
  try {
    record = outbox.loadForPrincipal(principal);
    if (!record) return { status: "empty", record: null };
    if (record.phase === "preparing_uploads") {
      fail("OUTBOX_UPLOADS_INCOMPLETE", "附件上传尚未完成，刷新后禁止自动重传或创建会话");
    }
    record = await createAndBindIfNeeded({
      outbox,
      principal,
      record,
      createConversation,
      onConversationBound,
    });

    // Recovery always reads authority before replay. A response may have been lost after the
    // backend committed, in which case this GET proves completion and prevents a second POST.
    const before = requireConversationAuthority(
      await getConversation(record.conversation_id),
      record.conversation_id,
    );
    if (conversationHasGuideRequest(before, record.request_id)) {
      outbox.clearConfirmed(principal, record.request_id);
      return { status: "confirmed", record, conversation: before, replayed: false };
    }

    const { response, conversation } = await postPersistedIntent({
      outbox,
      principal,
      record,
      postMessage,
      getConversation,
    });
    return { status: "confirmed", record, response, conversation, replayed: true };
  } catch (error) {
    // Retention is deliberate. In particular, a 409 never rotates request_id; a later reload
    // rechecks authority with the same stable key. Best-effort phase marking must not hide the
    // original storage/network failure.
    if (record && record.phase !== "preparing_uploads") {
      try {
        outbox.markAttempt(principal, record.request_id, "blocked");
      } catch {
        // The primary error is more useful and the record may still be intact.
      }
    }
    return { status: "blocked", record, error };
  }
}
