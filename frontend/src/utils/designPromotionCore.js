const REQUEST_ID_RE = /^req_[a-f0-9]{32}$/;
const SHA256_RE = /^[a-f0-9]{64}$/;
const CANDIDATE_ID_RE = /^odc-[a-f0-9]{32}$/;
const COMPARISON_ID_RE = /^comparison_[a-f0-9]{32}$/;
const FRAME_ID_RE = /^frame_[a-f0-9]{32}$/;
const SELECTION_ID_RE = /^selection_[a-f0-9]{32}$/;
const TASK_DECISION_ID_RE = /^decision_[a-f0-9]{32}$/;
const RELEASE_REQUEST_ID_RE = /^release_[a-f0-9]{32}$/;
const RELEASE_DECISION_ID_RE = /^release_decision_[a-f0-9]{32}$/;
const PROMOTION_EVENT_ID_RE = /^promotion_event_[a-f0-9]{32}$/;
const DESIGN_TARGETS = Object.freeze({
  task_review_summary: Object.freeze({
    targetId: "open_design_task_review_summary_v1",
    relativePath: "frontend/src/assets/open-design/task-review-summary.png",
  }),
  agent_activity_indicator: Object.freeze({
    targetId: "open_design_agent_activity_indicator_v1",
    relativePath: "frontend/src/assets/open-design/agent-activity-indicator.png",
  }),
  workflow_monitor_sidebar: Object.freeze({
    targetId: "open_design_workflow_monitor_sidebar_v1",
    relativePath: "frontend/src/assets/open-design/workflow-monitor-sidebar.png",
  }),
});
const DESIGN_TARGET_IDS = new Set(Object.values(DESIGN_TARGETS).map((target) => target.targetId));
export const DESIGN_REJECTION_REASON_OPTIONS = Object.freeze([
  Object.freeze({ value: "visual_mismatch", label: "视觉不一致" }),
  Object.freeze({ value: "trust_semantics", label: "信任语义不符" }),
  Object.freeze({ value: "accessibility", label: "可访问性问题" }),
  Object.freeze({ value: "incomplete_matrix", label: "比较矩阵不完整" }),
  Object.freeze({ value: "other", label: "其他" }),
]);
const REJECTION_REASONS = new Set(DESIGN_REJECTION_REASON_OPTIONS.map((option) => option.value));

export class DesignPromotionValidationError extends Error {
  constructor(message, field = null) {
    super(message);
    this.name = "DesignPromotionValidationError";
    this.field = field;
  }
}

function requireRequestId(value) {
  if (typeof value !== "string" || !REQUEST_ID_RE.test(value)) {
    throw new DesignPromotionValidationError(
      "request_id 必须是 req_ 加 32 位小写十六进制字符",
      "request_id",
    );
  }
  return value;
}

function requireOpaqueId(value, field, maxLength = 160) {
  if (typeof value !== "string" || value.length < 1 || value.length > maxLength) {
    throw new DesignPromotionValidationError(`${field} 无效`, field);
  }
  return value;
}

function requireExactPublicId(value, field, pattern) {
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new DesignPromotionValidationError(`${field} 格式无效`, field);
  }
  return value;
}

export function validateDesignPathId(value, field) {
  const pattern = field === "comparison_id"
    ? COMPARISON_ID_RE
    : field === "release_request_id"
      ? RELEASE_REQUEST_ID_RE
      : null;
  if (!pattern) {
    throw new DesignPromotionValidationError(`${field} 不是受支持的路径标识`, field);
  }
  return requireExactPublicId(value, field, pattern);
}

function requirePlainObject(value, field) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new DesignPromotionValidationError(`${field} 必须是对象`, field);
  }
  return value;
}

function requireExactKeys(value, keys, field) {
  requirePlainObject(value, field);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new DesignPromotionValidationError(`${field} 字段不完整或含未声明字段`, field);
  }
  return value;
}

function requireNonemptyString(value, field, maxLength = 512) {
  if (
    typeof value !== "string" ||
    value.trim() !== value ||
    value.length < 1 ||
    value.length > maxLength
  ) {
    throw new DesignPromotionValidationError(`${field} 无效`, field);
  }
  return value;
}

function requirePositiveInteger(value, field) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new DesignPromotionValidationError(`${field} 必须是正整数`, field);
  }
  return value;
}

function requireBoundedPositiveInteger(value, field, max) {
  requirePositiveInteger(value, field);
  if (value > max) {
    throw new DesignPromotionValidationError(`${field} 超出封闭上限`, field);
  }
  return value;
}

function requireSha256(value, field) {
  if (typeof value !== "string" || !SHA256_RE.test(value)) {
    throw new DesignPromotionValidationError(`${field} 必须是 64 位小写十六进制摘要`, field);
  }
  return value;
}

function normalizeComment(value) {
  if (value == null) return null;
  if (typeof value !== "string") {
    throw new DesignPromotionValidationError("comment 必须是文本或 null", "comment");
  }
  const normalized = value.trim();
  if (Array.from(normalized).length > 2000) {
    throw new DesignPromotionValidationError("comment 不能超过 2000 个字符", "comment");
  }
  return normalized || null;
}

function normalizeDecision({ action, reasonCode, comment, candidateId, candidateRequired }) {
  const normalizedComment = normalizeComment(comment);
  if (action === "approve") {
    if (reasonCode != null) {
      throw new DesignPromotionValidationError("批准时 reason_code 必须为 null", "reason_code");
    }
    if (candidateRequired) {
      if (typeof candidateId !== "string" || !CANDIDATE_ID_RE.test(candidateId)) {
        throw new DesignPromotionValidationError("批准候选时必须绑定精确 candidate_id", "candidate_id");
      }
    }
    return { action, reason_code: null, comment: normalizedComment };
  }
  if (action !== "reject") {
    throw new DesignPromotionValidationError("action 只能是 approve 或 reject", "action");
  }
  if (candidateRequired && candidateId != null) {
    throw new DesignPromotionValidationError("驳回不得绑定 candidate_id", "candidate_id");
  }
  if (!REJECTION_REASONS.has(reasonCode)) {
    throw new DesignPromotionValidationError("请选择冻结的驳回原因", "reason_code");
  }
  if (reasonCode === "other" && normalizedComment === null) {
    throw new DesignPromotionValidationError("选择其他时必须填写具体原因", "comment");
  }
  return { action, reason_code: reasonCode, comment: normalizedComment };
}

function normalizeExpectedTarget(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new DesignPromotionValidationError("expected_target 无效", "expected_target");
  }
  const keys = Object.keys(value).sort();
  if (value.kind === "absent" && keys.length === 1 && keys[0] === "kind") {
    return { kind: "absent" };
  }
  if (
    value.kind === "present" &&
    keys.length === 2 &&
    keys[0] === "kind" &&
    keys[1] === "sha256"
  ) {
    return { kind: "present", sha256: requireSha256(value.sha256, "expected_target.sha256") };
  }
  throw new DesignPromotionValidationError(
    "expected_target 必须是 absent，或带精确 sha256 的 present",
    "expected_target",
  );
}

function validateExpectedTarget(value, field) {
  try {
    normalizeExpectedTarget(value);
  } catch (error) {
    if (error instanceof DesignPromotionValidationError) {
      throw new DesignPromotionValidationError(error.message, field);
    }
    throw error;
  }
  return value;
}

function validateIdentity(value, field) {
  requireExactKeys(value, ["username", "display_name"], field);
  requireNonemptyString(value.username, `${field}.username`, 128);
  requireNonemptyString(value.display_name, `${field}.display_name`, 256);
  return value;
}

function validateTimestamp(value, field) {
  requireNonemptyString(value, field, 64);
  if (Number.isNaN(Date.parse(value))) {
    throw new DesignPromotionValidationError(`${field} 不是有效时间`, field);
  }
  return value;
}

function validateNullableSha256(value, field) {
  if (value === null) return value;
  return requireSha256(value, field);
}

function validateNullableComment(value, field) {
  if (value === null) return value;
  if (typeof value !== "string" || Array.from(value).length > 2000) {
    throw new DesignPromotionValidationError(`${field} 必须是至多 2000 字的文本或 null`, field);
  }
  return value;
}

function validateDecisionReason({ action, reasonCode, comment, field }) {
  validateNullableComment(comment, `${field}.comment`);
  if (action === "approve") {
    if (reasonCode !== null) {
      throw new DesignPromotionValidationError("批准记录的 reason_code 必须为 null", `${field}.reason_code`);
    }
    return;
  }
  if (action !== "reject" || !REJECTION_REASONS.has(reasonCode)) {
    throw new DesignPromotionValidationError("驳回记录缺少冻结原因", `${field}.reason_code`);
  }
  if (reasonCode === "other" && (typeof comment !== "string" || comment.trim() === "")) {
    throw new DesignPromotionValidationError("其他原因必须附具体说明", `${field}.comment`);
  }
}

function validateAttributionRecord(value, field, decisionIdPattern) {
  requireExactKeys(value, ["decision_id", "username", "display_name", "at"], field);
  requireExactPublicId(value.decision_id, `${field}.decision_id`, decisionIdPattern);
  requireNonemptyString(value.username, `${field}.username`, 128);
  requireNonemptyString(value.display_name, `${field}.display_name`, 256);
  validateTimestamp(value.at, `${field}.at`);
  return value;
}

function validateRelativePath(value, field) {
  requireNonemptyString(value, field, 512);
  if (
    value.startsWith("/") ||
    value.includes("\\") ||
    value.includes(":") ||
    !value.endsWith(".png") ||
    value.split("/").some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new DesignPromotionValidationError(`${field} 不是受控相对路径`, field);
  }
  return value;
}

function validateFrameImage(value, { field, comparisonId, frameId, side, candidate }) {
  const keys = candidate
    ? ["sha256", "width", "height", "url", "scan"]
    : ["sha256", "width", "height", "url"];
  requireExactKeys(value, keys, field);
  requireSha256(value.sha256, `${field}.sha256`);
  requireBoundedPositiveInteger(value.width, `${field}.width`, 4096);
  requireBoundedPositiveInteger(value.height, `${field}.height`, 4096);
  if (candidate && value.scan !== "passed") {
    throw new DesignPromotionValidationError("候选 PNG 未通过被动预览扫描", `${field}.scan`);
  }
  const expectedUrl = `/api/design-comparisons/${encodeURIComponent(comparisonId)}/frames/${encodeURIComponent(frameId)}/${side}.png`;
  if (value.url !== expectedUrl) {
    throw new DesignPromotionValidationError(
      `${field}.url 必须是服务端给出的同源 PNG 帧地址`,
      `${field}.url`,
    );
  }
  return value;
}

export function validateDesignComparisonEnvelope(value) {
  requireExactKeys(value, [
    "schema_version",
    "comparison_id",
    "comparison_sha256",
    "task_id",
    "candidate",
    "target",
    "phase",
    "provenance",
    "frames",
    "workflow",
    "created_by",
    "created_at",
  ], "comparison");
  if (value.schema_version !== "flai-design-comparison/v1") {
    throw new DesignPromotionValidationError("comparison schema_version 不受支持", "schema_version");
  }
  const comparisonId = requireExactPublicId(
    value.comparison_id,
    "comparison_id",
    COMPARISON_ID_RE,
  );
  requireSha256(value.comparison_sha256, "comparison_sha256");
  requireOpaqueId(value.task_id, "task_id");

  requireExactKeys(value.candidate, [
    "candidate_id",
    "asset_slot",
    "asset_file_id",
    "asset_sha256",
    "media_type",
    "execution_trust",
  ], "candidate");
  if (!CANDIDATE_ID_RE.test(value.candidate.candidate_id)) {
    throw new DesignPromotionValidationError("candidate_id 无效", "candidate.candidate_id");
  }
  requireNonemptyString(value.candidate.asset_slot, "candidate.asset_slot", 128);
  const targetContract = DESIGN_TARGETS[value.candidate.asset_slot];
  if (!targetContract) {
    throw new DesignPromotionValidationError(
      "candidate.asset_slot 不在发布目标 allowlist",
      "candidate.asset_slot",
    );
  }
  requireOpaqueId(value.candidate.asset_file_id, "candidate.asset_file_id");
  requireSha256(value.candidate.asset_sha256, "candidate.asset_sha256");
  if (value.candidate.media_type !== "image/png") {
    throw new DesignPromotionValidationError("候选资产只能是 image/png", "candidate.media_type");
  }
  if (value.candidate.execution_trust !== "untrusted_generated") {
    throw new DesignPromotionValidationError(
      "候选执行信任语义无效",
      "candidate.execution_trust",
    );
  }

  requireExactKeys(value.target, ["target_id", "relative_path", "preimage"], "target");
  requireOpaqueId(value.target.target_id, "target.target_id");
  validateRelativePath(value.target.relative_path, "target.relative_path");
  if (
    value.target.target_id !== targetContract.targetId ||
    value.target.relative_path !== targetContract.relativePath
  ) {
    throw new DesignPromotionValidationError(
      "target 与 candidate.asset_slot 的服务端 allowlist 不一致",
      "target",
    );
  }
  validateExpectedTarget(value.target.preimage, "target.preimage");

  if (![
    "candidate_pending",
    "candidate_rejected",
    "candidate_approved",
    "release_pending",
    "release_rejected",
    "publish_ready",
    "published",
    "rolled_back",
    "manual_intervention",
  ].includes(value.phase)) {
    throw new DesignPromotionValidationError("comparison phase 无效", "phase");
  }

  requireExactKeys(value.provenance, [
    "mock",
    "project_id",
    "run_id",
    "result_package_sha256",
    "design_reference_package_sha256",
    "file_set_sha256",
    "production_readiness",
  ], "provenance");
  if (value.provenance.mock !== false) {
    throw new DesignPromotionValidationError("比较只接受明确的非 mock 来源", "provenance.mock");
  }
  requireOpaqueId(value.provenance.project_id, "provenance.project_id", 160);
  requireOpaqueId(value.provenance.run_id, "provenance.run_id", 160);
  requireSha256(value.provenance.result_package_sha256, "provenance.result_package_sha256");
  requireSha256(
    value.provenance.design_reference_package_sha256,
    "provenance.design_reference_package_sha256",
  );
  requireSha256(value.provenance.file_set_sha256, "provenance.file_set_sha256");
  if (value.provenance.production_readiness !== "trial_not_attested") {
    throw new DesignPromotionValidationError(
      "比较来源必须明确声明窄试运行且未证明生产就绪",
      "provenance.production_readiness",
    );
  }

  if (!Array.isArray(value.frames) || value.frames.length < 1 || value.frames.length > 16) {
    throw new DesignPromotionValidationError("比较必须包含 1 至 16 组 PNG 帧", "frames");
  }
  const frameIds = new Set();
  const matrixKeys = new Set();
  for (let index = 0; index < value.frames.length; index++) {
    const frame = value.frames[index];
    const field = `frames[${index}]`;
    requireExactKeys(frame, [
      "frame_id",
      "slot_id",
      "viewport",
      "state",
      "theme",
      "locale",
      "current",
      "candidate",
    ], field);
    const frameId = requireExactPublicId(frame.frame_id, `${field}.frame_id`, FRAME_ID_RE);
    if (frameIds.has(frameId)) {
      throw new DesignPromotionValidationError("frame_id 重复", `${field}.frame_id`);
    }
    frameIds.add(frameId);
    requireNonemptyString(frame.slot_id, `${field}.slot_id`, 128);
    requireExactKeys(frame.viewport, ["width", "height", "dpr"], `${field}.viewport`);
    requireBoundedPositiveInteger(frame.viewport.width, `${field}.viewport.width`, 4096);
    requireBoundedPositiveInteger(frame.viewport.height, `${field}.viewport.height`, 4096);
    requireBoundedPositiveInteger(frame.viewport.dpr, `${field}.viewport.dpr`, 4);
    requireNonemptyString(frame.state, `${field}.state`, 64);
    if (!["light", "dark"].includes(frame.theme)) {
      throw new DesignPromotionValidationError(`${field}.theme 无效`, `${field}.theme`);
    }
    requireNonemptyString(frame.locale, `${field}.locale`, 32);
    const matrixKey = [
      frame.slot_id,
      frame.viewport.width,
      frame.viewport.height,
      frame.viewport.dpr,
      frame.state,
      frame.theme,
      frame.locale,
    ].join("|");
    if (matrixKeys.has(matrixKey)) {
      throw new DesignPromotionValidationError("比较矩阵帧重复", field);
    }
    matrixKeys.add(matrixKey);
    validateFrameImage(frame.current, {
      field: `${field}.current`,
      comparisonId,
      frameId,
      side: "current",
      candidate: false,
    });
    validateFrameImage(frame.candidate, {
      field: `${field}.candidate`,
      comparisonId,
      frameId,
      side: "candidate",
      candidate: true,
    });
  }
  validateIdentity(value.created_by, "created_by");
  validateTimestamp(value.created_at, "created_at");
  validateWorkflowProjection(value.workflow, value);
  return value;
}

export function validateDesignSelection(value) {
  requireExactKeys(value, [
    "schema_version",
    "selection_id",
    "comparison_id",
    "comparison_sha256",
    "task_id",
    "action",
    "candidate_id",
    "candidate_sha256",
    "task_decision_id",
    "selected_by",
    "reason_code",
    "comment",
    "created_at",
    "task_status",
  ], "selection");
  if (value.schema_version !== "flai-design-selection/v1") {
    throw new DesignPromotionValidationError("selection schema_version 不受支持", "schema_version");
  }
  requireExactPublicId(value.selection_id, "selection_id", SELECTION_ID_RE);
  requireExactPublicId(value.comparison_id, "comparison_id", COMPARISON_ID_RE);
  requireSha256(value.comparison_sha256, "comparison_sha256");
  requireOpaqueId(value.task_id, "task_id");
  requireExactPublicId(value.task_decision_id, "task_decision_id", TASK_DECISION_ID_RE);
  validateIdentity(value.selected_by, "selected_by");
  validateDecisionReason({
    action: value.action,
    reasonCode: value.reason_code,
    comment: value.comment,
    field: "selection",
  });
  if (value.action === "approve") {
    if (
      typeof value.candidate_id !== "string" ||
      !CANDIDATE_ID_RE.test(value.candidate_id) ||
      value.task_status !== "completed"
    ) {
      throw new DesignPromotionValidationError(
        "候选批准记录必须绑定 candidate_id 且任务已 completed",
        "candidate_id",
      );
    }
    requireSha256(value.candidate_sha256, "candidate_sha256");
  } else if (
    value.candidate_id !== null ||
    value.candidate_sha256 !== null ||
    value.task_status !== "failed"
  ) {
    throw new DesignPromotionValidationError(
      "候选驳回记录不得绑定候选摘要且任务必须 failed",
      "candidate_id",
    );
  }
  validateTimestamp(value.created_at, "created_at");
  return value;
}

function validateReleaseSummary(value, field = "summary") {
  requireExactKeys(value, ["candidate", "target"], field);
  requireExactKeys(value.candidate, [
    "task_id",
    "candidate_id",
    "asset_slot",
    "asset_sha256",
    "comparison_sha256",
    "candidate_approval",
  ], `${field}.candidate`);
  requireOpaqueId(value.candidate.task_id, `${field}.candidate.task_id`);
  if (!CANDIDATE_ID_RE.test(value.candidate.candidate_id)) {
    throw new DesignPromotionValidationError(
      "release summary candidate_id 无效",
      `${field}.candidate.candidate_id`,
    );
  }
  requireNonemptyString(value.candidate.asset_slot, `${field}.candidate.asset_slot`, 128);
  const targetContract = DESIGN_TARGETS[value.candidate.asset_slot];
  if (!targetContract) {
    throw new DesignPromotionValidationError(
      "release summary asset_slot 不在 allowlist",
      `${field}.candidate.asset_slot`,
    );
  }
  requireSha256(value.candidate.asset_sha256, `${field}.candidate.asset_sha256`);
  requireSha256(value.candidate.comparison_sha256, `${field}.candidate.comparison_sha256`);
  validateAttributionRecord(
    value.candidate.candidate_approval,
    `${field}.candidate.candidate_approval`,
    TASK_DECISION_ID_RE,
  );

  requireExactKeys(value.target, [
    "target_id",
    "relative_path",
    "preimage",
    "postimage_sha256",
  ], `${field}.target`);
  requireOpaqueId(value.target.target_id, `${field}.target.target_id`);
  validateRelativePath(value.target.relative_path, `${field}.target.relative_path`);
  if (
    value.target.target_id !== targetContract.targetId ||
    value.target.relative_path !== targetContract.relativePath
  ) {
    throw new DesignPromotionValidationError(
      "release summary target 与 asset_slot 不一致",
      `${field}.target`,
    );
  }
  validateExpectedTarget(value.target.preimage, `${field}.target.preimage`);
  requireSha256(value.target.postimage_sha256, `${field}.target.postimage_sha256`);
  return value;
}

export function validateDesignReleaseRequest(value) {
  requireExactKeys(value, [
    "schema_version",
    "release_request_id",
    "selection_id",
    "comparison_id",
    "state",
    "summary",
    "summary_sha256",
    "requested_by",
    "created_at",
  ], "release_request");
  if (value.schema_version !== "flai-design-release-request/v1") {
    throw new DesignPromotionValidationError(
      "release request schema_version 不受支持",
      "schema_version",
    );
  }
  requireExactPublicId(value.release_request_id, "release_request_id", RELEASE_REQUEST_ID_RE);
  requireExactPublicId(value.selection_id, "selection_id", SELECTION_ID_RE);
  requireExactPublicId(value.comparison_id, "comparison_id", COMPARISON_ID_RE);
  if (value.state !== "awaiting_release_approval") {
    throw new DesignPromotionValidationError("release request state 无效", "state");
  }
  validateReleaseSummary(value.summary);
  requireSha256(value.summary_sha256, "summary_sha256");
  validateIdentity(value.requested_by, "requested_by");
  validateTimestamp(value.created_at, "created_at");
  return value;
}

function validateReleasePackage(value) {
  requireExactKeys(value, [
    "schema_version",
    "release_package_sha256",
    "summary",
    "release_approval",
  ], "release_package");
  if (value.schema_version !== "flai-design-release-package/v1") {
    throw new DesignPromotionValidationError(
      "release package schema_version 不受支持",
      "release_package.schema_version",
    );
  }
  requireSha256(value.release_package_sha256, "release_package.release_package_sha256");
  validateReleaseSummary(value.summary, "release_package.summary");
  validateAttributionRecord(
    value.release_approval,
    "release_package.release_approval",
    RELEASE_DECISION_ID_RE,
  );
  return value;
}

export function validateDesignReleaseDecision(value) {
  requireExactKeys(value, [
    "schema_version",
    "release_request_id",
    "state",
    "decision_id",
    "action",
    "summary_sha256",
    "decided_by",
    "reason_code",
    "comment",
    "created_at",
    "release_package",
  ], "release_decision");
  if (value.schema_version !== "flai-design-release-decision/v1") {
    throw new DesignPromotionValidationError(
      "release decision schema_version 不受支持",
      "schema_version",
    );
  }
  requireExactPublicId(value.release_request_id, "release_request_id", RELEASE_REQUEST_ID_RE);
  requireExactPublicId(value.decision_id, "decision_id", RELEASE_DECISION_ID_RE);
  requireSha256(value.summary_sha256, "summary_sha256");
  validateIdentity(value.decided_by, "decided_by");
  validateDecisionReason({
    action: value.action,
    reasonCode: value.reason_code,
    comment: value.comment,
    field: "release_decision",
  });
  validateTimestamp(value.created_at, "created_at");
  if (value.action === "approve") {
    if (value.state !== "release_approved") {
      throw new DesignPromotionValidationError("发布批准状态不一致", "state");
    }
    validateReleasePackage(value.release_package);
  } else if (value.state !== "release_rejected" || value.release_package !== null) {
    throw new DesignPromotionValidationError("发布驳回状态不一致", "state");
  }
  return value;
}

export function validateDesignPublishResult(value) {
  requireExactKeys(value, [
    "schema_version",
    "release_request_id",
    "state",
    "publish_event_id",
    "target_id",
    "before_sha256",
    "after_sha256",
    "backup_sha256",
    "release_package_sha256",
    "published_by",
    "published_at",
  ], "publish_result");
  if (value.schema_version !== "flai-design-publish-result/v1" || value.state !== "published") {
    throw new DesignPromotionValidationError("publish result schema/state 无效", "state");
  }
  requireExactPublicId(value.release_request_id, "release_request_id", RELEASE_REQUEST_ID_RE);
  requireExactPublicId(value.publish_event_id, "publish_event_id", PROMOTION_EVENT_ID_RE);
  requireOpaqueId(value.target_id, "target_id");
  if (!DESIGN_TARGET_IDS.has(value.target_id)) {
    throw new DesignPromotionValidationError("发布目标不在 allowlist", "target_id");
  }
  validateNullableSha256(value.before_sha256, "before_sha256");
  requireSha256(value.after_sha256, "after_sha256");
  validateNullableSha256(value.backup_sha256, "backup_sha256");
  requireSha256(value.release_package_sha256, "release_package_sha256");
  validateIdentity(value.published_by, "published_by");
  validateTimestamp(value.published_at, "published_at");
  return value;
}

export function validateDesignRollbackResult(value) {
  requireExactKeys(value, [
    "schema_version",
    "release_request_id",
    "state",
    "rollback_event_id",
    "target_id",
    "before_sha256",
    "after_sha256",
    "backup_sha256",
    "release_package_sha256",
    "rolled_back_by",
    "rolled_back_at",
  ], "rollback_result");
  if (value.schema_version !== "flai-design-publish-result/v1" || value.state !== "rolled_back") {
    throw new DesignPromotionValidationError("rollback result schema/state 无效", "state");
  }
  requireExactPublicId(value.release_request_id, "release_request_id", RELEASE_REQUEST_ID_RE);
  requireExactPublicId(value.rollback_event_id, "rollback_event_id", PROMOTION_EVENT_ID_RE);
  requireOpaqueId(value.target_id, "target_id");
  if (!DESIGN_TARGET_IDS.has(value.target_id)) {
    throw new DesignPromotionValidationError("回退目标不在 allowlist", "target_id");
  }
  requireSha256(value.before_sha256, "before_sha256");
  validateNullableSha256(value.after_sha256, "after_sha256");
  validateNullableSha256(value.backup_sha256, "backup_sha256");
  requireSha256(value.release_package_sha256, "release_package_sha256");
  validateIdentity(value.rolled_back_by, "rolled_back_by");
  validateTimestamp(value.rolled_back_at, "rolled_back_at");
  return value;
}

function requireWorkflowLink(condition, message, field) {
  if (!condition) {
    throw new DesignPromotionValidationError(message, field);
  }
}

function expectedTargetsEqual(left, right) {
  return Boolean(
    left &&
    right &&
    left.kind === right.kind &&
    (left.kind === "absent" || left.sha256 === right.sha256),
  );
}

function attributionsEqual(left, right) {
  return Boolean(
    left &&
    right &&
    left.decision_id === right.decision_id &&
    left.username === right.username &&
    left.display_name === right.display_name &&
    left.at === right.at,
  );
}

function summariesEqual(left, right) {
  return Boolean(
    left &&
    right &&
    left.candidate.task_id === right.candidate.task_id &&
    left.candidate.candidate_id === right.candidate.candidate_id &&
    left.candidate.asset_slot === right.candidate.asset_slot &&
    left.candidate.asset_sha256 === right.candidate.asset_sha256 &&
    left.candidate.comparison_sha256 === right.candidate.comparison_sha256 &&
    attributionsEqual(left.candidate.candidate_approval, right.candidate.candidate_approval) &&
    left.target.target_id === right.target.target_id &&
    left.target.relative_path === right.target.relative_path &&
    expectedTargetsEqual(left.target.preimage, right.target.preimage) &&
    left.target.postimage_sha256 === right.target.postimage_sha256,
  );
}

function validateWorkflowProjection(value, comparison) {
  requireExactKeys(value, [
    "selection",
    "release_request",
    "release_decision",
    "latest_publish",
  ], "workflow");

  const selection = value.selection === null
    ? null
    : validateDesignSelection(value.selection);
  const releaseRequest = value.release_request === null
    ? null
    : validateDesignReleaseRequest(value.release_request);
  const releaseDecision = value.release_decision === null
    ? null
    : validateDesignReleaseDecision(value.release_decision);
  let latestPublish = null;
  if (value.latest_publish !== null) {
    requirePlainObject(value.latest_publish, "workflow.latest_publish");
    if (value.latest_publish.state === "published") {
      latestPublish = validateDesignPublishResult(value.latest_publish);
    } else if (value.latest_publish.state === "rolled_back") {
      latestPublish = validateDesignRollbackResult(value.latest_publish);
    } else {
      throw new DesignPromotionValidationError(
        "workflow.latest_publish 状态无效",
        "workflow.latest_publish.state",
      );
    }
  }

  if (selection) {
    requireWorkflowLink(
      selection.comparison_id === comparison.comparison_id &&
        selection.comparison_sha256 === comparison.comparison_sha256 &&
        selection.task_id === comparison.task_id,
      "候选判断未绑定当前比较快照",
      "workflow.selection",
    );
    if (selection.action === "approve") {
      requireWorkflowLink(
        selection.candidate_id === comparison.candidate.candidate_id &&
          selection.candidate_sha256 === comparison.candidate.asset_sha256,
        "候选批准记录未绑定当前候选摘要",
        "workflow.selection.candidate_id",
      );
    }
  }

  if (releaseRequest) {
    requireWorkflowLink(
      selection?.action === "approve" &&
        releaseRequest.selection_id === selection.selection_id &&
        releaseRequest.comparison_id === comparison.comparison_id,
      "发布申请缺少当前比较的候选批准记录",
      "workflow.release_request",
    );
    const summary = releaseRequest.summary;
    requireWorkflowLink(
      summary.candidate.task_id === comparison.task_id &&
        summary.candidate.candidate_id === comparison.candidate.candidate_id &&
        summary.candidate.asset_slot === comparison.candidate.asset_slot &&
        summary.candidate.asset_sha256 === comparison.candidate.asset_sha256 &&
        summary.candidate.comparison_sha256 === comparison.comparison_sha256 &&
        summary.target.target_id === comparison.target.target_id &&
        summary.target.relative_path === comparison.target.relative_path &&
        expectedTargetsEqual(summary.target.preimage, comparison.target.preimage) &&
        summary.target.postimage_sha256 === comparison.candidate.asset_sha256,
      "发布摘要未绑定当前候选与目标前像",
      "workflow.release_request.summary",
    );
    requireWorkflowLink(
      attributionsEqual(summary.candidate.candidate_approval, {
        decision_id: selection.task_decision_id,
        username: selection.selected_by.username,
        display_name: selection.selected_by.display_name,
        at: selection.created_at,
      }),
      "发布摘要中的候选批准归因不一致",
      "workflow.release_request.summary.candidate.candidate_approval",
    );
  }

  if (releaseDecision) {
    requireWorkflowLink(
      releaseRequest &&
        releaseDecision.release_request_id === releaseRequest.release_request_id &&
        releaseDecision.summary_sha256 === releaseRequest.summary_sha256,
      "发布判断未绑定当前发布摘要",
      "workflow.release_decision",
    );
    if (releaseDecision.action === "approve") {
      requireWorkflowLink(
        summariesEqual(releaseDecision.release_package.summary, releaseRequest.summary),
        "发布包摘要与发布申请不一致",
        "workflow.release_decision.release_package.summary",
      );
      requireWorkflowLink(
        attributionsEqual(releaseDecision.release_package.release_approval, {
          decision_id: releaseDecision.decision_id,
          username: releaseDecision.decided_by.username,
          display_name: releaseDecision.decided_by.display_name,
          at: releaseDecision.created_at,
        }),
        "发布包中的具名批准归因不一致",
        "workflow.release_decision.release_package.release_approval",
      );
    }
  }

  if (latestPublish) {
    const releasePackage = releaseDecision?.release_package;
    requireWorkflowLink(
      releaseDecision?.action === "approve" &&
        latestPublish.release_request_id === releaseRequest.release_request_id &&
        latestPublish.release_package_sha256 === releasePackage.release_package_sha256 &&
        latestPublish.target_id === comparison.target.target_id,
      "发布或回退记录未绑定当前已批准发布包",
      "workflow.latest_publish",
    );
    const preimageSha256 = comparison.target.preimage.kind === "present"
      ? comparison.target.preimage.sha256
      : null;
    if (latestPublish.state === "published") {
      requireWorkflowLink(
        latestPublish.before_sha256 === preimageSha256 &&
          latestPublish.after_sha256 === comparison.candidate.asset_sha256,
        "发布结果与目标前像或候选摘要不一致",
        "workflow.latest_publish",
      );
    } else {
      requireWorkflowLink(
        latestPublish.before_sha256 === comparison.candidate.asset_sha256 &&
          latestPublish.after_sha256 === preimageSha256,
        "回退结果与已发布候选或目标前像不一致",
        "workflow.latest_publish",
      );
    }
  }

  const hasApprovedSelection = selection?.action === "approve";
  const phaseMatches = {
    candidate_pending: !selection && !releaseRequest && !releaseDecision && !latestPublish,
    candidate_rejected:
      selection?.action === "reject" && !releaseRequest && !releaseDecision && !latestPublish,
    candidate_approved:
      hasApprovedSelection && !releaseRequest && !releaseDecision && !latestPublish,
    release_pending:
      hasApprovedSelection && Boolean(releaseRequest) && !releaseDecision && !latestPublish,
    release_rejected:
      hasApprovedSelection &&
      Boolean(releaseRequest) &&
      releaseDecision?.action === "reject" &&
      !latestPublish,
    publish_ready:
      hasApprovedSelection &&
      Boolean(releaseRequest) &&
      releaseDecision?.action === "approve" &&
      !latestPublish,
    manual_intervention:
      hasApprovedSelection &&
      Boolean(releaseRequest) &&
      releaseDecision?.action === "approve" &&
      !latestPublish,
    published:
      hasApprovedSelection &&
      Boolean(releaseRequest) &&
      releaseDecision?.action === "approve" &&
      latestPublish?.state === "published",
    rolled_back:
      hasApprovedSelection &&
      Boolean(releaseRequest) &&
      releaseDecision?.action === "approve" &&
      latestPublish?.state === "rolled_back",
  }[comparison.phase];
  requireWorkflowLink(
    phaseMatches === true,
    "comparison.phase 与服务端工作流投影不一致",
    "phase",
  );
  return value;
}

export function isOpenDesignProductionCandidateTask(task) {
  if (!task || typeof task !== "object") return false;
  if (task.agent_id !== "open_design_daemon_candidate_agent") return false;
  if (!["waiting_review", "completed", "failed"].includes(task.status)) return false;
  const metadata = task.metadata;
  return Boolean(
    metadata &&
    typeof metadata === "object" &&
    metadata.review_contract === "open-design-candidate/v1" &&
    metadata.generator_kind === "open_design_daemon" &&
    typeof metadata.candidate_manifest_sha256 === "string" &&
    SHA256_RE.test(metadata.candidate_manifest_sha256),
  );
}

export function blocksGenericTaskReview(task) {
  if (!task || typeof task !== "object" || task.status !== "waiting_review") return false;
  return Boolean(
    task.agent_id === "open_design_daemon_candidate_agent" ||
    task.metadata?.review_contract === "open-design-candidate/v1",
  );
}

export function createDesignPromotionRequestId(bytes = null) {
  let source = bytes;
  if (source === null) {
    source = new Uint8Array(16);
    if (!globalThis.crypto || typeof globalThis.crypto.getRandomValues !== "function") {
      throw new DesignPromotionValidationError("当前环境不能生成安全请求标识", "request_id");
    }
    globalThis.crypto.getRandomValues(source);
  }
  if (!(source instanceof Uint8Array) || source.length !== 16) {
    throw new DesignPromotionValidationError("请求标识随机源必须恰好为 16 字节", "request_id");
  }
  return `req_${Array.from(source, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export function buildComparisonCreatePayload({ requestId, taskId }) {
  return {
    request_id: requireRequestId(requestId),
    task_id: requireOpaqueId(taskId, "task_id"),
  };
}

export function buildCandidateSelectionPayload({
  requestId,
  action,
  expectedComparisonSha256,
  candidateId,
  reasonCode = null,
  comment = null,
}) {
  const decision = normalizeDecision({
    action,
    reasonCode,
    comment,
    candidateId,
    candidateRequired: true,
  });
  return {
    request_id: requireRequestId(requestId),
    action: decision.action,
    expected_comparison_sha256: requireSha256(
      expectedComparisonSha256,
      "expected_comparison_sha256",
    ),
    candidate_id: action === "approve" ? candidateId : null,
    reason_code: decision.reason_code,
    comment: decision.comment,
  };
}

export function buildReleaseRequestPayload({
  requestId,
  selectionId,
  expectedComparisonSha256,
  expectedCandidateSha256,
  expectedTarget,
}) {
  return {
    request_id: requireRequestId(requestId),
    selection_id: requireExactPublicId(selectionId, "selection_id", SELECTION_ID_RE),
    expected_comparison_sha256: requireSha256(
      expectedComparisonSha256,
      "expected_comparison_sha256",
    ),
    expected_candidate_sha256: requireSha256(
      expectedCandidateSha256,
      "expected_candidate_sha256",
    ),
    expected_target: normalizeExpectedTarget(expectedTarget),
  };
}

export function buildReleaseDecisionPayload({
  requestId,
  action,
  expectedSummarySha256,
  reasonCode = null,
  comment = null,
}) {
  const decision = normalizeDecision({
    action,
    reasonCode,
    comment,
    candidateId: null,
    candidateRequired: false,
  });
  return {
    request_id: requireRequestId(requestId),
    action: decision.action,
    expected_summary_sha256: requireSha256(expectedSummarySha256, "expected_summary_sha256"),
    reason_code: decision.reason_code,
    comment: decision.comment,
  };
}

export function buildPublishPayload({
  requestId,
  expectedReleasePackageSha256,
  expectedTarget,
  confirm,
}) {
  if (confirm !== true) {
    throw new DesignPromotionValidationError("发布必须显式确认", "confirm");
  }
  return {
    request_id: requireRequestId(requestId),
    expected_release_package_sha256: requireSha256(
      expectedReleasePackageSha256,
      "expected_release_package_sha256",
    ),
    expected_target: normalizeExpectedTarget(expectedTarget),
    confirm: true,
  };
}

export function buildRollbackPayload({
  requestId,
  expectedReleasePackageSha256,
  expectedCurrentSha256,
  confirm,
}) {
  if (confirm !== true) {
    throw new DesignPromotionValidationError("回退必须显式确认", "confirm");
  }
  return {
    request_id: requireRequestId(requestId),
    expected_release_package_sha256: requireSha256(
      expectedReleasePackageSha256,
      "expected_release_package_sha256",
    ),
    expected_current_sha256: requireSha256(expectedCurrentSha256, "expected_current_sha256"),
    confirm: true,
  };
}
