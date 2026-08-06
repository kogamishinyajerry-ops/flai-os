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

function isBoundedText(value) {
  return (
    typeof value === "string" &&
    value.trim() !== "" &&
    value.length <= LIFE_DRAFT_LIST_ITEM_MAX_CHARS
  );
}

/**
 * fail-closed 形状校验：9 字段齐全且全部合规才返回 true。
 * 与后端 _validate_draft 同口径；前端凭它决定渲不渲染卡片。
 */
export function isLifeDraftShape(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  for (const id of SCALAR_IDS) {
    const text = value[id];
    if (typeof text !== "string" || text.trim() === "") return false;
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
