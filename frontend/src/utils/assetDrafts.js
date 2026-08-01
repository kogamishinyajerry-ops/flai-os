export function assetDraftEntryPolicy({
  conversationId = "",
  hasSavedUserMessage = false,
  sending = false,
  restoring = false,
  reconciliationRequired = false,
} = {}) {
  if (typeof conversationId !== "string" || conversationId.trim() === "") {
    return {
      canOpen: false,
      reason: "先完成并保存一轮对话，再沉淀为资产。",
    };
  }
  if (hasSavedUserMessage !== true) {
    return {
      canOpen: false,
      reason: "当前会话还没有已保存的工程师工作。",
    };
  }
  if (sending === true) {
    return { canOpen: false, reason: "请等待本轮生成结束后再沉淀。" };
  }
  if (restoring === true) {
    return { canOpen: false, reason: "请等待会话恢复完成后再沉淀。" };
  }
  if (reconciliationRequired === true) {
    return {
      canOpen: false,
      reason: "保存状态待核，请先刷新会话核对。",
    };
  }
  return { canOpen: true, reason: "" };
}

export function seedAssetDraftGeneralization(messages = []) {
  const firstUserContent = Array.isArray(messages)
    ? messages.find(
        (message) =>
          message?.role === "user" &&
          typeof message.content === "string" &&
          message.content.trim() !== "",
      )?.content.trim() || ""
    : "";

  return {
    title: firstUserContent.slice(0, 80),
    trigger: "",
    desired_outcome: firstUserContent,
    inputs: [],
    outputs: [],
    steps: [],
    evidence_requirements: [],
    human_decision_points: [],
    limitations: [],
  };
}

const LIST_FIELDS = [
  "inputs",
  "outputs",
  "steps",
  "evidence_requirements",
  "human_decision_points",
  "limitations",
];

function cleanText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function cleanList(value) {
  const items = typeof value === "string" ? value.split(/\r?\n/) : value;
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function buildAssetDraftPreviewRequest(generalization) {
  if (!generalization || typeof generalization !== "object") {
    throw new TypeError("资产草稿概括必须是对象");
  }

  const normalized = {
    title: cleanText(generalization.title),
    trigger: cleanText(generalization.trigger),
    desired_outcome: cleanText(generalization.desired_outcome),
  };
  for (const field of LIST_FIELDS) normalized[field] = cleanList(generalization[field]);

  return {
    schema_version: "asset_draft_preview_request.v1",
    generalization: normalized,
  };
}

export class AssetDraftContractError extends Error {
  constructor(message) {
    super(message);
    this.name = "AssetDraftContractError";
  }
}

function contract(condition, message) {
  if (!condition) throw new AssetDraftContractError(message);
}

function exactObject(value, keys, label) {
  contract(value && typeof value === "object" && !Array.isArray(value), `${label} 必须是对象`);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  contract(
    actual.length === expected.length && actual.every((key, index) => key === expected[index]),
    `${label} 字段集合不受支持`,
  );
}

function digest(value) {
  return typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);
}

function stringList(
  value,
  { allowEmpty = true, maxItems = 20, maxLength = 1000 } = {},
) {
  return (
    Array.isArray(value) &&
    (allowEmpty || value.length > 0) &&
    value.length <= maxItems &&
    value.every(
      (item) =>
        typeof item === "string" &&
        item.trim() !== "" &&
        item.length <= maxLength,
    )
  );
}

export function normalizeAssetDraftPreview(
  value,
  { expectedConversationId = "" } = {},
) {
  exactObject(
    value,
    [
      "schema_version",
      "builder_version",
      "status",
      "work_case",
      "task_pattern",
      "skill",
      "validation",
      "review",
      "generation",
      "effects",
      "draft_digest",
    ],
    "资产草稿响应",
  );
  contract(
    value.schema_version === "asset_draft_bundle.v1",
    "资产草稿响应版本不受支持",
  );
  contract(
    value.builder_version === "asset_draft_builder.v1",
    "Asset Builder 版本不受支持",
  );
  contract(value.status === "draft", "资产草稿响应包含越权状态");
  contract(digest(value.draft_digest), "资产草稿 digest 不合法");

  const workCase = value.work_case;
  exactObject(
    workCase,
    [
      "source_kind",
      "source_id",
      "source_state",
      "conversation_status",
      "message_count",
      "user_message_count",
      "attachment_reference_count",
      "source_revision",
    ],
    "Work Case 投影",
  );
  contract(
    workCase.source_kind === "conversation" &&
      workCase.source_state === "platform_resolved" &&
      typeof workCase.source_id === "string" &&
      workCase.source_id.trim() !== "" &&
      workCase.source_id.length <= 128 &&
      ["active", "concluded", "abandoned"].includes(
        workCase.conversation_status,
      ) &&
      Number.isInteger(workCase.message_count) &&
      workCase.message_count > 0 &&
      Number.isInteger(workCase.user_message_count) &&
      workCase.user_message_count > 0 &&
      workCase.user_message_count <= workCase.message_count &&
      Number.isInteger(workCase.attachment_reference_count) &&
      workCase.attachment_reference_count >= 0 &&
      digest(workCase.source_revision),
    "Work Case 必须是平台解析的已保存会话投影",
  );
  if (expectedConversationId !== "") {
    contract(
      workCase.source_id === expectedConversationId,
      "Work Case 来源与当前会话不一致",
    );
  }

  const taskPattern = value.task_pattern;
  exactObject(
    taskPattern,
    [
      "schema_version",
      "status",
      "derived_from_work_case_revision",
      "title",
      "trigger",
      "desired_outcome",
      "inputs",
      "outputs",
      "steps",
      "evidence_requirements",
      "human_decision_points",
      "limitations",
      "suggested_id",
      "content_digest",
    ],
    "Task Pattern 草稿",
  );
  contract(
    taskPattern.schema_version === "task_pattern_draft.v1" &&
      taskPattern.status === "draft" &&
      taskPattern.derived_from_work_case_revision === workCase.source_revision &&
      digest(taskPattern.content_digest) &&
      taskPattern.suggested_id ===
        `task_pattern_candidate_${taskPattern.content_digest.slice(7, 19)}` &&
      typeof taskPattern.title === "string" &&
      taskPattern.title.length <= 160 &&
      typeof taskPattern.trigger === "string" &&
      taskPattern.trigger.length <= 2000 &&
      typeof taskPattern.desired_outcome === "string" &&
      taskPattern.desired_outcome.length <= 2000 &&
      LIST_FIELDS.every((field) => stringList(taskPattern[field])),
    "Task Pattern 草稿契约或来源关系不合法",
  );

  const skill = value.skill;
  exactObject(
    skill,
    [
      "schema_version",
      "status",
      "operationalizes_task_pattern_digest",
      "name",
      "description",
      "when_to_use",
      "when_not_to_use",
      "inputs",
      "outputs",
      "instructions",
      "verification",
      "human_boundaries",
      "suggested_id",
      "content_digest",
    ],
    "Skill 草稿",
  );
  contract(
    skill.schema_version === "skill_draft.v1" &&
      skill.status === "draft" &&
      skill.operationalizes_task_pattern_digest === taskPattern.content_digest &&
      digest(skill.content_digest) &&
      skill.suggested_id === `skill_candidate_${skill.content_digest.slice(7, 19)}` &&
      typeof skill.name === "string" &&
      skill.name.length <= 160 &&
      typeof skill.description === "string" &&
      skill.description.length <= 4200 &&
      typeof skill.when_to_use === "string" &&
      skill.when_to_use.length <= 2000 &&
      [
        "when_not_to_use",
        "inputs",
        "outputs",
        "instructions",
        "verification",
        "human_boundaries",
      ].every((field) => stringList(skill[field])),
    "Skill 草稿契约或 Task Pattern 关系不合法",
  );

  const validation = value.validation;
  exactObject(
    validation,
    [
      "schema_version",
      "policy_version",
      "state",
      "blocking_count",
      "warning_count",
      "issues",
    ],
    "确定性校验结果",
  );
  contract(
    validation.schema_version === "asset_draft_validation.v1" &&
      validation.policy_version === "core.v1",
    "确定性校验版本不受支持",
  );
  contract(
    ["needs_revision", "ready_for_human_review"].includes(validation.state) &&
      Number.isInteger(validation.blocking_count) &&
      validation.blocking_count >= 0 &&
      Number.isInteger(validation.warning_count) &&
      validation.warning_count >= 0 &&
      Array.isArray(validation.issues),
    "确定性校验结果不完整",
  );
  for (const issue of validation.issues) {
    exactObject(issue, ["code", "severity", "path", "message"], "校验问题");
    contract(
      typeof issue.code === "string" &&
      issue.code.trim() !== "" &&
        issue.code.length <= 160 &&
        ["blocking", "warning"].includes(issue.severity) &&
        typeof issue.path === "string" &&
        issue.path.startsWith("/") &&
        typeof issue.message === "string" &&
        issue.message.trim() !== "" &&
        issue.message.length <= 1000,
      "校验问题结构不受支持",
    );
  }
  contract(
    validation.blocking_count ===
      validation.issues.filter((issue) => issue.severity === "blocking").length &&
      validation.warning_count ===
        validation.issues.filter((issue) => issue.severity === "warning").length,
    "校验问题计数与明细不一致",
  );

  const review = value.review;
  exactObject(
    review,
    ["required", "ready", "state", "decision_state", "requirements"],
    "人工审核门",
  );
  contract(
    review.required === true &&
      typeof review.ready === "boolean" &&
      ["not_ready", "awaiting_human_review"].includes(review.state) &&
      review.decision_state === "not_recorded" &&
      stringList(review.requirements, {
        allowEmpty: false,
        maxItems: Number.POSITIVE_INFINITY,
        maxLength: Number.POSITIVE_INFINITY,
      }),
    "人工审核门状态不受支持",
  );
  contract(
    (review.ready === true &&
      review.state === "awaiting_human_review" &&
      validation.state === "ready_for_human_review" &&
      validation.blocking_count === 0) ||
      (review.ready === false &&
        review.state === "not_ready" &&
        validation.state === "needs_revision" &&
        validation.blocking_count > 0),
    "校验结果与人工审核门不一致",
  );

  contract(
    (() => {
      exactObject(value.generation, ["kind", "llm_used"], "生成声明");
      return (
        value.generation.kind === "deterministic_projection" &&
        value.generation.llm_used === false
      );
    })(),
    "Asset Builder v0 只接受非 LLM 的确定性投影",
  );

  const effectKeys = [
    "writes_database",
    "executes_work",
    "registers_asset",
    "promotes_asset",
  ];
  exactObject(value.effects, effectKeys, "副作用声明");
  contract(
    effectKeys.every((key) => value.effects[key] === false),
    "Asset Builder v0 响应声明了未知或非零副作用",
  );

  return value;
}

export function serializeAssetDraftDownload(value) {
  return `${JSON.stringify(normalizeAssetDraftPreview(value), null, 2)}\n`;
}
