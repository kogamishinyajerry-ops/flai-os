import test from "node:test";
import assert from "node:assert/strict";

import {
  REVIEW_REASON_OPTIONS,
  ReviewValidationError,
  buildReviewPayload,
  isReviewContextCurrent,
  validateReviewDecision,
} from "../src/utils/reviewCore.js";

test("reject reasons are the six frozen structured judgment categories", () => {
  assert.deepEqual(REVIEW_REASON_OPTIONS, [
    { value: "source_doubt", label: "数据源疑点" },
    { value: "method_error", label: "方法错误" },
    { value: "conclusion_overreach", label: "结论越界" },
    { value: "insufficient_evidence", label: "证据不足" },
    { value: "classification_issue", label: "密级问题" },
    { value: "other", label: "其他" },
  ]);
  assert.equal(Object.isFrozen(REVIEW_REASON_OPTIONS), true);
});

test("approve stays direct, identity-free, and fails closed on any reject reason", () => {
  assert.deepEqual(
    buildReviewPayload({ action: "approve", reasonCode: null, comment: "核对通过" }),
    {
      action: "approve",
      reason_code: null,
      comment: "核对通过",
      paired_advice_id: null,
    },
  );
  assert.throws(
    () => buildReviewPayload({ action: "approve", reasonCode: "method_error", comment: "核对通过" }),
    ReviewValidationError,
  );
});

test("reject fails closed until a declared reason is selected", () => {
  for (const reasonCode of ["", null, "guessed_reason", true]) {
    const result = validateReviewDecision({ action: "reject", reasonCode, comment: "" });
    assert.equal(result.ok, false);
    assert.equal(result.field, "reasonCode");
    assert.throws(
      () => buildReviewPayload({ action: "reject", reasonCode, comment: "" }),
      ReviewValidationError,
    );
  }
});

test("other requires text while the five named reasons keep text optional", () => {
  for (const comment of ["", "   ", "\n\t"]) {
    const result = validateReviewDecision({ action: "reject", reasonCode: "other", comment });
    assert.equal(result.ok, false);
    assert.equal(result.field, "comment");
  }
  assert.deepEqual(
    buildReviewPayload({ action: "reject", reasonCode: "other", comment: "  需要补充具体原因  " }),
    {
      action: "reject",
      reason_code: "other",
      comment: "需要补充具体原因",
      paired_advice_id: null,
    },
  );
  assert.deepEqual(
    buildReviewPayload({ action: "reject", reasonCode: "method_error", comment: "" }),
    {
      action: "reject",
      reason_code: "method_error",
      comment: null,
      paired_advice_id: null,
    },
  );
});

test("comment is bounded at 2000 Unicode code points", () => {
  assert.equal(
    validateReviewDecision({ action: "reject", reasonCode: "other", comment: "判".repeat(2000) }).ok,
    true,
  );
  const invalid = validateReviewDecision({
    action: "reject",
    reasonCode: "method_error",
    comment: "判".repeat(2001),
  });
  assert.equal(invalid.ok, false);
  assert.equal(invalid.field, "comment");
});

test("an awaited confirmation cannot settle a hidden, switched, or terminal task", () => {
  const current = {
    expectedTaskId: "task_a",
    currentTaskId: "task_a",
    waiting: true,
    visible: true,
  };
  assert.equal(isReviewContextCurrent(current), true);
  assert.equal(isReviewContextCurrent({ ...current, currentTaskId: "task_b" }), false);
  assert.equal(isReviewContextCurrent({ ...current, waiting: false }), false);
  assert.equal(isReviewContextCurrent({ ...current, visible: false }), false);
  assert.equal(isReviewContextCurrent({ ...current, expectedTaskId: "" }), false);
});
