import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { evaluationCompletionNotice, eventTimelineColor } from "../src/utils/format.js";

test("event timeline colors follow domain trust meaning, not generic severity", () => {
  assert.equal(eventTimelineColor({ event_type: "review_approved", level: "info" }), "var(--trust-signed)");
  assert.equal(eventTimelineColor({ event_type: "review_rejected", level: "warning" }), "var(--trust-fail)");
  assert.equal(eventTimelineColor({ event_type: "task_failed", level: "error" }), "var(--trust-fail)");
  assert.equal(eventTimelineColor({ event_type: "review_requested", level: "info" }), "var(--trust-pending)");
  assert.equal(eventTimelineColor({ event_type: "tool_started", level: "info" }), "var(--clay)");
  assert.equal(eventTimelineColor({ event_type: "task_completed", level: "info" }), "var(--ink-soft)");
  assert.equal(eventTimelineColor({ event_type: "feedback_received", level: "info" }), "var(--ink-faint)");
});

test("subjective good feedback is rendered with a neutral tag", async () => {
  const source = await readFile(new URL("../src/views/FeedbackPage.vue", import.meta.url), "utf8");
  assert.match(source, /f\.rating === ['"]good['"]\s*\?\s*['"]info['"]\s*:\s*['"]danger['"]/);
  assert.doesNotMatch(source, /f\.rating === ['"]good['"]\s*\?\s*['"]success['"]/);
  assert.match(source, /ElMessage\.info\(['"]反馈已提交['"]\)/);
  assert.doesNotMatch(source, /ElMessage\.success\(['"]反馈已提交['"]\)/);
});

test("switching feedback tasks clears the draft and rejects stale list responses", async () => {
  const source = await readFile(new URL("../src/views/FeedbackPage.vue", import.meta.url), "utf8");
  const switchBody = source.match(/function handleTaskChange\([^)]*\)\s*\{([\s\S]*?)\n\}/)?.[1] || "";
  assert.match(switchBody, /feedbackForm\.rating\s*=\s*['"]['"]/);
  assert.match(switchBody, /feedbackForm\.category\s*=\s*['"]['"]/);
  assert.match(switchBody, /feedbackForm\.message\s*=\s*['"]['"]/);
  assert.match(source, /let feedbackEpoch\s*=\s*0/);
  assert.match(source, /epoch\s*!==\s*feedbackEpoch\s*\|\|\s*taskId\.value\s*!==\s*requestedTaskId/);
});

test("a completed evaluation is green only when every case passed and none were skipped", () => {
  assert.deepEqual(
    evaluationCompletionNotice({ status: "completed", passed: 2, failed: 1, skipped: 0, total: 3 }),
    { type: "warning", message: "评测完成，但存在未通过或跳过：通过 2/3 · 失败 1 · 跳过 0" },
  );
  assert.equal(
    evaluationCompletionNotice({ status: "completed", passed: 2, failed: 0, skipped: 1, total: 3 }).type,
    "warning",
  );
  assert.equal(
    evaluationCompletionNotice({ status: "completed", passed: 3, failed: 0, skipped: 0, total: 3 }).type,
    "success",
  );
});

test("promotion success commits L1 locally before any refresh can fail", async () => {
  const dialog = await readFile(new URL("../src/components/AgentGovernanceDialog.vue", import.meta.url), "utf8");
  assert.match(dialog, /const localMaturity\s*=\s*ref\(/);
  assert.match(dialog, /agentMaturity/);
  const promoteBody = dialog.match(/async function promoteToL1\(\)\s*\{([\s\S]*?)\n\}/)?.[1] || "";
  const localCommit = promoteBody.indexOf('localMaturity.value = "L1"');
  const refresh = promoteBody.indexOf("await loadGovernance(agentId)");
  assert.ok(localCommit >= 0, "promotion must set local maturity to L1");
  assert.ok(refresh < 0 || localCommit < refresh, "local L1 must be visible before governance refresh");
  assert.match(dialog, /async function loadGovernance[\s\S]*?return true;[\s\S]*?catch \(err\)[\s\S]*?return false;/);
  assert.match(
    promoteBody,
    /const refreshed = await loadGovernance\(agentId\);\s*if \(!refreshed\) \{\s*ElMessage\.warning\("晋升已成功，但治理信息刷新失败"\);\s*return;/,
  );

  const portal = await readFile(new URL("../src/views/AgentPortal.vue", import.meta.url), "utf8");
  assert.match(portal, /async function onGovernanceChanged\(change\)/);
  assert.match(portal, /govAgent\.value\s*=\s*\{[\s\S]*maturity:\s*change\.maturity/);
});

test("ErrorState delegates the single alert live region to Element Plus", async () => {
  const source = await readFile(new URL("../src/components/ErrorState.vue", import.meta.url), "utf8");
  assert.doesNotMatch(source, /class="error-state"\s+role="alert"/);
  assert.match(source, /<el-alert\b[^>]*type="error"/);
});

test("human review outcomes never use the green REAL success toast", async () => {
  const source = await readFile(new URL("../src/composables/useTaskReview.js", import.meta.url), "utf8");
  assert.doesNotMatch(source, /ElMessage\.success\s*\(/);
  assert.match(source, /action === "approve"\s*\?\s*ElMessage\.info\s*:\s*ElMessage\.error/);
});
