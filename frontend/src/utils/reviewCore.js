// Human review decision contract shared by TaskDetail and StatusCenter.
// Identity never enters this module: reviewer/advisor are derived by the server
// from the authenticated session.

export const REVIEW_COMMENT_MAX_LENGTH = 2000;

export const REVIEW_REASON_OPTIONS = Object.freeze([
  Object.freeze({ value: "source_doubt", label: "数据源疑点" }),
  Object.freeze({ value: "method_error", label: "方法错误" }),
  Object.freeze({ value: "conclusion_overreach", label: "结论越界" }),
  Object.freeze({ value: "insufficient_evidence", label: "证据不足" }),
  Object.freeze({ value: "classification_issue", label: "密级问题" }),
  Object.freeze({ value: "other", label: "其他" }),
]);

const REVIEW_REASON_CODES = new Set(REVIEW_REASON_OPTIONS.map((option) => option.value));

export class ReviewValidationError extends Error {
  constructor(field, message) {
    super(message);
    this.name = "ReviewValidationError";
    this.field = field;
  }
}

// Any confirmation await creates a context-switch window. Re-check the exact
// task and its still-waiting review surface before crossing the write boundary.
export function isReviewContextCurrent({
  expectedTaskId,
  currentTaskId,
  waiting,
  visible = true,
} = {}) {
  return (
    typeof expectedTaskId === "string" &&
    expectedTaskId.length > 0 &&
    currentTaskId === expectedTaskId &&
    waiting === true &&
    visible === true
  );
}

function commentValue(value) {
  if (value == null) return { raw: "", normalized: "" };
  if (typeof value !== "string") return null;
  return { raw: value, normalized: value.trim() };
}

export function validateReviewDecision({ action, reasonCode = null, comment = "" } = {}) {
  if (action !== "approve" && action !== "reject") {
    return { ok: false, field: "action", message: "签发动作无效" };
  }
  const parsedComment = commentValue(comment);
  if (!parsedComment) {
    return { ok: false, field: "comment", message: "意见必须是文本" };
  }
  if ([...parsedComment.raw].length > REVIEW_COMMENT_MAX_LENGTH) {
    return {
      ok: false,
      field: "comment",
      message: `意见不能超过 ${REVIEW_COMMENT_MAX_LENGTH} 字`,
    };
  }
  if (action === "approve" && reasonCode !== null) {
    return { ok: false, field: "reasonCode", message: "批准不得携带驳回原因" };
  }
  if (action === "reject" && !REVIEW_REASON_CODES.has(reasonCode)) {
    return { ok: false, field: "reasonCode", message: "请选择驳回原因" };
  }
  if (action === "reject" && reasonCode === "other" && !parsedComment.normalized) {
    return {
      ok: false,
      field: "comment",
      message: "选择“其他”时，请填写具体原因",
    };
  }
  return {
    ok: true,
    reasonCode: action === "approve" ? null : reasonCode,
    comment: parsedComment.normalized || null,
  };
}

export function buildReviewPayload(decision = {}) {
  const validation = validateReviewDecision(decision);
  if (validation.ok !== true) {
    throw new ReviewValidationError(validation.field, validation.message);
  }
  return {
    action: decision.action,
    reason_code: validation.reasonCode,
    comment: validation.comment,
    // P2.5 v1 has no paired advice selection surface. Keep the field explicit
    // and null rather than accepting caller-provided identity or guessed links.
    paired_advice_id: null,
  };
}
