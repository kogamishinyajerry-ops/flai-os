/**
 * life_guide_agent 待审候选（generalization_draft）的纯函数核。
 *
 * 只做确定性形状校验与展示投影，不做任何签发语义（人审唯一签发）。
 * 校验口径与后端 agents/life_guide_agent/workflow.py 的 _validate_draft、
 * backend/app/ontology/asset_builder.py 的 _normalize_generalization 对齐：
 *   - 3 个标量字段非空且限长（title≤160，trigger/desired_outcome≤2000）；
 *   - 6 个列表字段非空、≤20 项、单项 ≤1000 字符；
 *   - steps 必须 ≥ 2 条；
 *   - 任一字段残缺/越界 → 整体不可渲染（fail-closed），绝不降级展示半份候选。
 */

export const LIFE_DRAFT_SCALAR_LIMITS = Object.freeze({
  title: 160,
  trigger: 2000,
  desired_outcome: 2000,
});

export const LIFE_DRAFT_LIST_MAX_ITEMS = 20;
export const LIFE_DRAFT_LIST_ITEM_MAX_CHARS = 1000;

/** 9 字段顺序与教学标签（与 prompt.md 的投影格式一致，顺序不可变）。 */
export const LIFE_DRAFT_FIELDS = Object.freeze([
  { id: "title", label: "名称", hint: "这类事叫什么", kind: "text" },
  { id: "trigger", label: "触发条件", hint: "什么时候用", kind: "text" },
  {
    id: "desired_outcome",
    label: "交付结果",
    hint: "最后交出什么",
    kind: "text",
  },
  { id: "inputs", label: "所需输入", hint: "开工前要有什么", kind: "list" },
  { id: "outputs", label: "产出", hint: "做完留下什么", kind: "list" },
  { id: "steps", label: "步骤", hint: "按什么顺序做", kind: "list" },
  {
    id: "evidence_requirements",
    label: "成功证据",
    hint: "怎么算做成了",
    kind: "list",
  },
  {
    id: "human_decision_points",
    label: "人工判断点",
    hint: "哪里必须停下来等人",
    kind: "list",
  },
  {
    id: "limitations",
    label: "不适用边界",
    hint: "什么时候不能用",
    kind: "list",
  },
]);

const SCALAR_IDS = LIFE_DRAFT_FIELDS.filter((f) => f.kind === "text").map(
  (f) => f.id,
);
const LIST_IDS = LIFE_DRAFT_FIELDS.filter((f) => f.kind === "list").map(
  (f) => f.id,
);

const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
const RECORD_ID_RE = /^gdr_[0-9a-f]{32}$/;

export class LifeDraftContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "LifeDraftContractError";
  }
}

function contract(condition, message) {
  if (!condition) throw new LifeDraftContractError(message);
}

function exactObject(value, keys, label) {
  contract(
    value && typeof value === "object" && !Array.isArray(value),
    `${label}必须是对象`,
  );
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  contract(
    actual.length === expected.length &&
      actual.every((key, index) => key === expected[index]),
    `${label}字段集合不受支持`,
  );
}

function nonblank(value, maxLength = 2000) {
  return (
    typeof value === "string" &&
    value.trim() !== "" &&
    value.length <= maxLength
  );
}

function isCanonicalText(value) {
  return (
    typeof value === "string" &&
    value === value.trim() &&
    value === value.normalize("NFC")
  );
}

function isBoundedText(value) {
  return (
    isCanonicalText(value) &&
    value !== "" &&
    value.length <= LIFE_DRAFT_LIST_ITEM_MAX_CHARS
  );
}

/**
 * fail-closed 形状校验：9 字段齐全且全部合规才返回 true。
 * 与后端 _validate_draft 同口径；前端凭它决定渲不渲染卡片。
 */
export function isLifeDraftShape(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const expectedKeys = LIFE_DRAFT_FIELDS.map(({ id }) => id).sort();
  const actualKeys = Object.keys(value).sort();
  if (
    actualKeys.length !== expectedKeys.length ||
    !actualKeys.every((key, index) => key === expectedKeys[index])
  ) {
    return false;
  }
  for (const id of SCALAR_IDS) {
    const text = value[id];
    if (!isCanonicalText(text) || text === "") return false;
    if (text.length > LIFE_DRAFT_SCALAR_LIMITS[id]) return false;
  }
  for (const id of LIST_IDS) {
    const list = value[id];
    if (!Array.isArray(list) || list.length === 0) return false;
    if (list.length > LIFE_DRAFT_LIST_MAX_ITEMS) return false;
    if (!list.every(isBoundedText)) return false;
  }
  // steps ≥ 2 是 asset_builder 的硬要求（一步成不了可复用方法）
  return value.steps.length >= 2;
}

/**
 * 把草稿投影成渲染条目；形状不合规返回空数组（fail-closed，不渲染半份）。
 */
export function lifeDraftFieldEntries(value) {
  if (!isLifeDraftShape(value)) return [];
  return LIFE_DRAFT_FIELDS.map((field) => ({
    id: field.id,
    label: field.label,
    hint: field.hint,
    kind: field.kind,
    value: field.kind === "text" ? value[field.id] : [...value[field.id]],
  }));
}

/**
 * 校验服务端持久化的、不可由 workflow 自报的 Generalization Draft record。
 * 这只验证公开包络与当前消息血缘；digest 的逐字节复算由服务端冷读 verifier 负责。
 */
export function normalizeGeneralizationDraftRecord(
  value,
  { conversationId = "", assistantMessageId = null } = {},
) {
  exactObject(
    value,
    [
      "id",
      "schema_version",
      "payload_schema_version",
      "state",
      "review_status",
      "payload",
      "content_digest",
      "record_digest",
      "source_context_digest",
      "model_attribution",
      "lineage",
      "created_at",
    ],
    "草稿记录",
  );
  contract(RECORD_ID_RE.test(value.id), "草稿记录 id 不合法");
  contract(
    value.schema_version === "generalization_draft_record.v1" &&
      value.payload_schema_version === "life_generalization.v1",
    "草稿记录版本不受支持",
  );
  contract(
    value.state === "model_draft" && value.review_status === "waiting_review",
    "草稿记录包含越权状态",
  );
  contract(isLifeDraftShape(value.payload), "草稿记录 payload 不合法");
  contract(
    DIGEST_RE.test(value.content_digest) &&
      DIGEST_RE.test(value.record_digest) &&
      DIGEST_RE.test(value.source_context_digest),
    "草稿记录 digest 不合法",
  );

  exactObject(
    value.model_attribution,
    [
      "model_call_id",
      "kind",
      "agent_id",
      "agent_version",
      "profile",
      "model_name",
    ],
    "模型归因",
  );
  const model = value.model_attribution;
  contract(
    Number.isInteger(model.model_call_id) &&
      model.model_call_id > 0 &&
      model.kind === "chat" &&
      model.agent_id === "life_guide_agent" &&
      nonblank(model.agent_version, 128) &&
      nonblank(model.profile, 128) &&
      nonblank(model.model_name, 256),
    "模型归因不合法",
  );

  exactObject(
    value.lineage,
    [
      "conversation_id",
      "user_message_id",
      "assistant_message_id",
      "task_id",
    ],
    "草稿血缘",
  );
  const lineage = value.lineage;
  contract(
    nonblank(lineage.conversation_id, 128) &&
      Number.isInteger(lineage.user_message_id) &&
      lineage.user_message_id > 0 &&
      Number.isInteger(lineage.assistant_message_id) &&
      lineage.assistant_message_id > 0 &&
      lineage.user_message_id !== lineage.assistant_message_id &&
      lineage.task_id === null,
    "草稿血缘不合法",
  );
  if (conversationId !== "") {
    contract(
      lineage.conversation_id === conversationId,
      "草稿血缘与当前会话不一致",
    );
  }
  if (assistantMessageId !== null) {
    contract(
      lineage.assistant_message_id === assistantMessageId,
      "草稿血缘与当前助手消息不一致",
    );
  }
  contract(
    nonblank(value.created_at, 64) && Number.isFinite(Date.parse(value.created_at)),
    "草稿记录创建时间不合法",
  );
  return value;
}

export function normalizeLifeConversationIdentity(
  value,
  { expectedConversationId = "" } = {},
) {
  contract(
    value && typeof value === "object" && !Array.isArray(value),
    "life demo 会话必须是对象",
  );
  contract(nonblank(value.id, 128), "life demo 会话 id 不合法");
  contract(
    value.agent_id === "life_guide_agent",
    "life demo 只接受 life_guide_agent 会话",
  );
  if (expectedConversationId !== "") {
    contract(
      value.id === expectedConversationId,
      "life demo 会话与 URL c 参数不一致",
    );
  }
  return value;
}

/**
 * 把一条公开会话消息投影成页面可用消息。记录损坏时保留可信的消息正文，
 * 但显式关闭草稿卡片；用户消息携带 record 字段则属于角色包络漂移，直接拒绝。
 */
export function normalizeLifeConversationMessage(
  value,
  { conversationId = "" } = {},
) {
  contract(
    value && typeof value === "object" && !Array.isArray(value),
    "life demo 消息必须是对象",
  );
  contract(Number.isInteger(value.id) && value.id > 0, "消息 id 不合法");
  contract(
    value.role === "user" || value.role === "assistant",
    "消息角色不受支持",
  );
  contract(typeof value.content === "string", "消息正文不合法");
  if (conversationId !== "") {
    contract(
      value.conversation_id === conversationId,
      "消息与当前会话不一致",
    );
  }

  const hasRecord = Object.prototype.hasOwnProperty.call(
    value,
    "generalization_draft_record",
  );
  if (value.role === "user") {
    contract(!hasRecord, "用户消息不得携带草稿记录字段");
    return { ...value, draftRecord: null, draftRecordInvalid: false };
  }

  if (!hasRecord) {
    return { ...value, draftRecord: null, draftRecordInvalid: true };
  }
  if (value.generalization_draft_record === null) {
    return { ...value, draftRecord: null, draftRecordInvalid: false };
  }
  try {
    const draftRecord = normalizeGeneralizationDraftRecord(
      value.generalization_draft_record,
      { conversationId, assistantMessageId: value.id },
    );
    return { ...value, draftRecord, draftRecordInvalid: false };
  } catch (error) {
    if (!(error instanceof LifeDraftContractError)) throw error;
    return { ...value, draftRecord: null, draftRecordInvalid: true };
  }
}

/** GET /conversations/{id} 的 life demo 冷读投影。 */
export function normalizeLifeConversationSnapshot(
  value,
  { expectedConversationId = "" } = {},
) {
  normalizeLifeConversationIdentity(value, { expectedConversationId });
  contract(Array.isArray(value.messages), "life demo 会话缺少消息列表");
  return {
    ...value,
    messages: value.messages.map((message) =>
      normalizeLifeConversationMessage(message, {
        conversationId: value.id,
      }),
    ),
  };
}

/** POST /messages 的投影；废弃的 top-level generalization_draft 永远不会进入结果。 */
export function normalizeLifePostResponse(
  value,
  { expectedConversationId = "" } = {},
) {
  contract(
    value && typeof value === "object" && !Array.isArray(value),
    "life demo POST 响应必须是对象",
  );
  normalizeLifeConversationIdentity(value.conversation, {
    expectedConversationId,
  });
  const message = normalizeLifeConversationMessage(value.message, {
    conversationId: value.conversation.id,
  });
  contract(message.role === "assistant", "life demo POST 必须返回助手消息");
  return { message, conversation: value.conversation };
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalValue(value[key])]),
    );
  }
  return value;
}

const DEFINITELY_UNCOMMITTED_LIFE_POST_STATUSES = new Set([
  401,
  403,
  404,
  413,
  415,
  422,
]);

/**
 * 仅这些由认证、路由或请求包络前置拒绝的状态可证明 life POST 没有进入持久化。
 * 400/409/429 及所有 5xx/网络错误默认都是 ambiguous，不能据此开放盲重发。
 */
export function isDefinitelyUncommittedLifePostError(error) {
  return (
    Number.isInteger(error?.status) &&
    DEFINITELY_UNCOMMITTED_LIFE_POST_STATUSES.has(error.status)
  );
}

/**
 * POST 已发出但响应丢失时，用发送前的完整消息基线核对冷读结果。
 * 只有原基线逐项不变、且恰好追加一条同文 user 与一条 assistant 时才算恢复；
 * 若 assistant 带 record，还必须由 record lineage 指回该 user。
 */
export function reconcileAmbiguousLifePostSnapshot(
  snapshot,
  { baselineMessages = [], submittedText = "" } = {},
) {
  contract(
    snapshot && Array.isArray(snapshot.messages),
    "ambiguous POST 冷读快照不合法",
  );
  contract(Array.isArray(baselineMessages), "ambiguous POST 消息基线不合法");
  contract(
    typeof submittedText === "string" &&
      submittedText !== "" &&
      submittedText.trim() === submittedText,
    "ambiguous POST 本轮正文不合法",
  );

  const persisted = snapshot.messages;
  contract(
    persisted.length === baselineMessages.length + 2,
    "ambiguous POST 无法唯一核对本轮追加消息",
  );
  const messageIds = persisted.map((message) => message?.id);
  contract(
    new Set(messageIds).size === messageIds.length,
    "ambiguous POST 冷读消息 id 不唯一",
  );
  for (let index = 0; index < baselineMessages.length; index += 1) {
    contract(
      JSON.stringify(canonicalValue(persisted[index])) ===
        JSON.stringify(canonicalValue(baselineMessages[index])),
      "ambiguous POST 发送前消息基线发生漂移",
    );
  }

  const userMessage = persisted[baselineMessages.length];
  const assistantMessage = persisted[baselineMessages.length + 1];
  contract(
    userMessage?.role === "user" &&
      userMessage.content === submittedText &&
      assistantMessage?.role === "assistant" &&
      assistantMessage.id > userMessage.id,
    "ambiguous POST 无法唯一核对本轮 user/assistant 消息",
  );
  if (assistantMessage.draftRecord !== null) {
    contract(
      assistantMessage.draftRecord?.lineage?.user_message_id === userMessage.id,
      "ambiguous POST 草稿 record lineage 未指向本轮 user 消息",
    );
  }
  return { userMessage, assistantMessage };
}

/** POST 返回的 canonical assistant 必须能在紧随其后的 GET 中逐字段找到。 */
export function assertLifePostMatchesSnapshot(post, snapshot) {
  contract(
    post?.message && Array.isArray(snapshot?.messages),
    "无法核对 POST/GET 消息投影",
  );
  const persisted = snapshot.messages.find(
    (message) => message?.id === post.message.id,
  );
  contract(persisted, "GET 快照缺少刚保存的助手消息");
  contract(
    JSON.stringify(canonicalValue(persisted)) ===
      JSON.stringify(canonicalValue(post.message)),
    "POST 与 GET 的助手消息投影不一致",
  );
  return true;
}

/** 只把 URL query 解析成副作用意图；场景 s 仅用于页面展示，不进入后端。 */
export function resolveLifeDemoRoute(query = {}, allowedScenarioIds = []) {
  const scenarioId = query?.s;
  const conversationId = query?.c;
  if (scenarioId == null && conversationId == null) return { kind: "pick" };
  if (
    typeof scenarioId !== "string" ||
    !allowedScenarioIds.includes(scenarioId)
  ) {
    return { kind: "invalid", reason: "demo 场景参数不受支持" };
  }
  if (conversationId == null) {
    return { kind: "create", scenarioId };
  }
  if (
    typeof conversationId !== "string" ||
    !/^[A-Za-z0-9_-]{1,128}$/.test(conversationId)
  ) {
    return { kind: "invalid", reason: "demo 会话参数不合法" };
  }
  return { kind: "load", scenarioId, conversationId };
}

/** record-bound Asset Draft preview 的来源包络；asset_draft 本体由既有 v1 校验器负责。 */
export function normalizeGeneralizationDraftRecordPreviewEnvelope(
  value,
  { expectedRecord } = {},
) {
  exactObject(
    value,
    ["schema_version", "source_record", "asset_draft"],
    "record-bound preview 响应",
  );
  contract(
    value.schema_version ===
      "generalization_draft_record_preview_response.v1",
    "record-bound preview 响应版本不受支持",
  );
  exactObject(
    value.source_record,
    ["id", "content_digest", "record_digest", "source_context_digest"],
    "record-bound preview 来源",
  );
  contract(
    expectedRecord &&
      value.source_record.id === expectedRecord.id &&
      value.source_record.content_digest === expectedRecord.content_digest &&
      value.source_record.record_digest === expectedRecord.record_digest &&
      value.source_record.source_context_digest ===
        expectedRecord.source_context_digest,
    "record-bound preview 来源绑定与当前草稿记录不一致",
  );
  contract(
    value.asset_draft &&
      typeof value.asset_draft === "object" &&
      !Array.isArray(value.asset_draft),
    "record-bound preview 缺少 Asset Draft",
  );
  return value;
}

/** 四项副作用声明（铁律 1：必须全 False）。 */
export const LIFE_DRAFT_EFFECT_LABELS = Object.freeze([
  { key: "writes_database", label: "写数据库" },
  { key: "executes_work", label: "执行工作" },
  { key: "registers_asset", label: "注册资产" },
  { key: "promotes_asset", label: "晋级资产" },
]);

/**
 * 从 preview bundle 投影卡片展示摘要。
 * 只读已被 normalizeAssetDraftPreview 校验过的响应；任何键缺失 → 诚实返回
 * 可判定的“不可展示”状态，绝不猜测。
 */
export function summarizeLifeDraftPreview(preview) {
  if (!preview || typeof preview !== "object" || Array.isArray(preview)) {
    return null;
  }
  const digest =
    typeof preview.draft_digest === "string" &&
    /^sha256:[0-9a-f]{64}$/.test(preview.draft_digest)
      ? preview.draft_digest
      : "";
  const validation = preview.validation;
  const review = preview.review;
  const effects = preview.effects;
  const generation = preview.generation;
  if (
    digest === "" ||
    !validation ||
    typeof validation.state !== "string" ||
    !Number.isInteger(validation.blocking_count) ||
    !review ||
    typeof review.state !== "string" ||
    !effects ||
    !generation
  ) {
    return null;
  }
  const effectRows = LIFE_DRAFT_EFFECT_LABELS.map(({ key, label }) => ({
    key,
    label,
    value: effects[key] === false ? false : null, // 非 False 一律按“未知”展示
  }));
  return {
    digest,
    digestShort: digest.slice(7, 19),
    validationState: validation.state,
    blockingCount: validation.blocking_count,
    warningCount:
      Number.isInteger(validation.warning_count) ? validation.warning_count : 0,
    reviewState: review.state,
    effectRows,
    effectsAllFalse: effectRows.every((row) => row.value === false),
    deterministic:
      generation.kind === "deterministic_projection" &&
      generation.llm_used === false,
  };
}
