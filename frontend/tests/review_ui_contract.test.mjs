import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("both human-sign entry points share one structured reject contract", () => {
  const detail = read("../src/views/TaskDetail.vue");
  const center = read("../src/components/StatusCenter.vue");

  for (const source of [detail, center]) {
    assert.match(source, /REVIEW_REASON_OPTIONS/);
    assert.match(source, /validateReviewDecision/);
    assert.match(source, /<el-radio-group/);
    assert.match(source, /v-for="option in REVIEW_REASON_OPTIONS"/);
    assert.match(source, /:maxlength="REVIEW_COMMENT_MAX_LENGTH"/);
    assert.match(source, /pairedAdviceId:\s*null/);
    assert.doesNotMatch(source, /reviewTask\([^)]*reviewer|reviewTask\([^)]*advisor/s);
  }

  assert.match(detail, /@click="openRejectDialog"/);
  assert.match(center, /@click="openPeekRejectDialog"/);
});

test("approve remains direct while reject submit is validation-gated", () => {
  const detail = read("../src/views/TaskDetail.vue");
  const center = read("../src/components/StatusCenter.vue");

  assert.match(detail, /@click="handleReview\('approve'\)"/);
  assert.match(center, /@click="doReview\('approve'\)"/);
  assert.match(detail, /validateReviewDecision\(\{[\s\S]*?action:\s*"reject"/);
  assert.match(center, /validateReviewDecision\(\{[\s\S]*?action:\s*"reject"/);
});

test("reject drafts cannot leak into approval and settlement locks are scoped", () => {
  const detail = read("../src/views/TaskDetail.vue");
  const center = read("../src/components/StatusCenter.vue");

  assert.match(detail, /const rejectForm = reactive\(\{ reasonCode: "", comment: "" \}\)/);
  assert.match(center, /const peekRejectComment = ref\(""\)/);
  assert.match(detail, /watch\(\(\) => route\.params\.taskId,[\s\S]*?reviewSettled\.value = false/);
  assert.match(detail, /:disabled="reviewSettled"[^>]*@click="handleReview\('approve'\)"/);
  assert.match(detail, /destroy-on-close/);
  assert.match(center, /destroy-on-close/);
  assert.match(detail, /v-model="rejectForm\.reasonCode"[\s\S]{0,160}:disabled="reviewing"/);
  assert.match(detail, /v-model="rejectForm\.comment"[\s\S]{0,160}:disabled="reviewing"/);
  assert.match(center, /v-model="peekRejectReasonCode"[\s\S]{0,160}:disabled="reviewing"/);
  assert.match(center, /v-model="peekRejectComment"[\s\S]{0,160}:disabled="reviewing"/);
});
