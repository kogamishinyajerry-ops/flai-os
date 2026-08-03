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

export const ASSET_DRAFT_FOCUS_QUESTIONS = Object.freeze([
  {
    id: "work-title",
    field: "title",
    fieldId: "asset-field-title",
    step: 1,
    group: "本次工作",
    label: "工作名称",
    prompt: "如果以后再遇到，这类工作应该叫什么？",
    helper: "用工程师一眼能认出的短名称，不写泛泛的“完成某任务”。",
    placeholder: "例如：稳态算例入口边界复核",
    multiline: false,
    minRows: 1,
    maxRows: 1,
    maxlength: 120,
  },
  {
    id: "work-trigger",
    field: "trigger",
    fieldId: "asset-field-trigger",
    step: 1,
    group: "本次工作",
    label: "复用触发条件",
    prompt: "什么情况下，应该再次启动这套方法？",
    helper: "写清可观察的起点；系统不会从对话里自动猜测触发条件。",
    placeholder: "例如：收到待计算算例，需要在开算前核对入口边界",
    multiline: true,
    minRows: 3,
    maxRows: 6,
  },
  {
    id: "work-outcome",
    field: "desired_outcome",
    fieldId: "asset-field-desired-outcome",
    step: 1,
    group: "本次工作",
    label: "可检查的交付结果",
    prompt: "工作结束时，必须留下什么可检查结果？",
    helper: "描述能复核、能交接的产物，不把“完成任务”本身当作结果。",
    placeholder: "例如：形成可逐项签认的入口边界复核清单",
    multiline: true,
    minRows: 3,
    maxRows: 6,
  },
  {
    id: "method-inputs",
    field: "inputs",
    fieldId: "asset-field-inputs",
    step: 2,
    group: "复用方法",
    label: "所需输入",
    prompt: "开始前，工程师手里必须有哪些输入？",
    helper: "每行一项，只写真实需要的文件、参数或上下文。",
    placeholder: "算例清单\n入口边界条件表",
    multiline: true,
    minRows: 4,
    maxRows: 8,
  },
  {
    id: "method-outputs",
    field: "outputs",
    fieldId: "asset-field-outputs",
    step: 2,
    group: "复用方法",
    label: "必要输出",
    prompt: "这套方法必须留下哪些输出？",
    helper: "每行一项，优先写可检查、可交接的产物。",
    placeholder: "入口边界复核清单",
    multiline: true,
    minRows: 4,
    maxRows: 8,
  },
  {
    id: "method-steps",
    field: "steps",
    fieldId: "asset-field-steps",
    step: 2,
    group: "复用方法",
    label: "复用步骤",
    prompt: "哪些步骤在不同任务中仍然稳定？",
    helper: "每行一个动作；保留可复用骨架，不把本次任务细节硬编码进去。",
    placeholder: "逐项核对入口总压、总温与工况标识\n记录缺失、冲突和需要裁决的边界",
    multiline: true,
    minRows: 5,
    maxRows: 10,
  },
  {
    id: "method-evidence",
    field: "evidence_requirements",
    fieldId: "asset-field-evidence",
    step: 2,
    group: "复用方法",
    label: "核验依据",
    prompt: "靠什么证明工作做过，而且可以复核？",
    helper: "每行一项，写明原始证据、定位或检查记录。",
    placeholder: "每项结论保留原始表格位置",
    multiline: true,
    minRows: 4,
    maxRows: 8,
  },
  {
    id: "method-human-boundaries",
    field: "human_decision_points",
    fieldId: "asset-field-human-boundaries",
    step: 2,
    group: "复用方法",
    label: "人工判断点",
    prompt: "在哪些地方必须停下来，等工程师判断？",
    helper: "把人工裁决写成明确停点；Agent 不能越过这些边界。",
    placeholder: "冲突边界由责任工程师确认采用值",
    multiline: true,
    minRows: 4,
    maxRows: 8,
  },
  {
    id: "method-limitations",
    field: "limitations",
    fieldId: "asset-field-limitations",
    step: 2,
    group: "复用方法",
    label: "不适用边界",
    prompt: "哪些情况绝不能直接套用这套方法？",
    helper: "每行一项，明确会让方法失效或必须重新评估的条件。",
    placeholder: "不适用于瞬态工况或未冻结的边界版本",
    multiline: true,
    minRows: 4,
    maxRows: 8,
  },
].map((question) => Object.freeze(question)));

const ASSET_DRAFT_ISSUE_QUESTIONS = Object.freeze({
  "/task_pattern/title": "work-title",
  "/task_pattern/trigger": "work-trigger",
  "/task_pattern/desired_outcome": "work-outcome",
  "/task_pattern/inputs": "method-inputs",
  "/task_pattern/outputs": "method-outputs",
  "/skill/instructions": "method-steps",
  "/skill/verification": "method-evidence",
  "/skill/human_boundaries": "method-human-boundaries",
  "/skill/when_not_to_use": "method-limitations",
});

function hasAssetDraftAnswer(value) {
  if (typeof value === "string") return value.trim() !== "";
  return (
    Array.isArray(value) &&
    value.some((item) => typeof item === "string" && item.trim() !== "")
  );
}

export function assetDraftFocusState(questionId, generalization = {}) {
  const index = ASSET_DRAFT_FOCUS_QUESTIONS.findIndex(
    (question) => question.id === questionId,
  );
  if (index < 0) throw new RangeError(`未知资产草稿问题：${questionId}`);

  const question = ASSET_DRAFT_FOCUS_QUESTIONS[index];
  const answeredIds = ASSET_DRAFT_FOCUS_QUESTIONS
    .filter((item) => hasAssetDraftAnswer(generalization?.[item.field]))
    .map((item) => item.id);

  return {
    question,
    questionId: question.id,
    step: question.step,
    index,
    position: index + 1,
    total: ASSET_DRAFT_FOCUS_QUESTIONS.length,
    previousId: ASSET_DRAFT_FOCUS_QUESTIONS[index - 1]?.id || null,
    nextId: ASSET_DRAFT_FOCUS_QUESTIONS[index + 1]?.id || null,
    answeredIds,
    answeredCount: answeredIds.length,
  };
}

export function assetDraftQuestionForIssue(path) {
  if (typeof path !== "string") return null;
  return ASSET_DRAFT_ISSUE_QUESTIONS[path] || null;
}

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
