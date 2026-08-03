import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  batchCreateErrorCode,
  batchCreatePersistenceUnknown,
  createBatchOperationId,
  createTasksBatch,
} from "../src/api/tasks.js";

const guideSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
  "utf8",
);

test("batch API carries one stable operation id and the exact validated versions", async () => {
  const originalFetch = globalThis.fetch;
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return new Response(JSON.stringify({
      operation_id: "guide_batch_fixed_001",
      replayed: false,
      tasks: [{
        id: "task_1",
        agent_id: "hello_agent",
        agent_version: "0.1.0",
        conversation_id: "conv_1",
        retry_of: null,
        depends_on: [],
        metadata: { package_snapshot_digest: "a".repeat(64) },
      }],
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    await createTasksBatch({
      conversationId: "conv_1",
      operationId: "guide_batch_fixed_001",
      pinnedVersions: { hello_agent: "0.1.0" },
      pinnedPackageDigests: { hello_agent: "a".repeat(64) },
      items: [{ agentId: "hello_agent", inputs: { name: "x" } }],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(observed.path, "/api/tasks/batch");
  const body = JSON.parse(observed.init.body);
  assert.equal(body.operation_id, "guide_batch_fixed_001");
  assert.deepEqual(body.pinned_versions, { hello_agent: "0.1.0" });
  assert.deepEqual(body.pinned_package_digests, { hello_agent: "a".repeat(64) });
});

test("batch API only carries the matched Agent hidden Skill Package reference", async () => {
  const originalFetch = globalThis.fetch;
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return new Response(JSON.stringify({
      operation_id: "guide_batch_skill_reuse_001",
      replayed: false,
      tasks: [
        {
          id: "task_1",
          agent_id: "hello_agent",
          agent_version: "0.1.0",
          conversation_id: "conv_1",
          retry_of: null,
          depends_on: [],
          metadata: {
            package_snapshot_digest: "a".repeat(64),
            skill_package_ref: skillPackageRef,
          },
        },
        {
          id: "task_2",
          agent_id: "standards_qa_agent",
          agent_version: "0.2.0",
          conversation_id: "conv_1",
          retry_of: null,
          depends_on: [],
          metadata: { package_snapshot_digest: "d".repeat(64) },
        },
      ],
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const skillPackageRef = {
    schema_version: "skill_reuse_ref.v1",
    package_id: `skill_package_${"b".repeat(24)}`,
    package_version: "0.1.0",
    package_digest: `sha256:${"c".repeat(64)}`,
    candidate_digest: `sha256:${"e".repeat(64)}`,
    skill_digest: `sha256:${"f".repeat(64)}`,
    skill_name: "entry-review-method",
    matched_agent_id: "hello_agent",
    review_state: "approved",
    match_policy_version: "skill_reuse_match.v1",
    match_basis_digest: `sha256:${"1".repeat(64)}`,
  };
  try {
    await createTasksBatch({
      conversationId: "conv_1",
      operationId: "guide_batch_skill_reuse_001",
      pinnedVersions: {
        hello_agent: "0.1.0",
        standards_qa_agent: "0.2.0",
      },
      pinnedPackageDigests: {
        hello_agent: "a".repeat(64),
        standards_qa_agent: "d".repeat(64),
      },
      items: [
        { agentId: "hello_agent", inputs: { name: "x" }, skillPackageRef },
        { agentId: "standards_qa_agent", inputs: { question: "x" } },
      ],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  const body = JSON.parse(observed.init.body);
  assert.deepEqual(body.items[0].skill_package_ref, skillPackageRef);
  assert.equal(Object.hasOwn(body.items[1], "skill_package_ref"), false);
});

test("Guide renders reuse only inside the existing plan card and binds it to one matching item", () => {
  assert.match(
    guideSource,
    /class="route-summary"[\s\S]*class="skill-reuse-inline"[\s\S]*计划复用 · \{\{[^}]*skill_name[^}]*\}\}/,
  );
  assert.match(
    guideSource,
    /class="route-disclosure-body"[\s\S]*class="skill-reuse-detail"/,
  );
  assert.match(
    guideSource,
    /skillPackageRef:[\s\S]*matched_agent_id === a\.agent_id/,
  );
  assert.doesNotMatch(guideSource, /复用这个 Skill|选择 Skill|skill-reuse-(?:card|panel|action)/);

  const planStart = guideSource.indexOf('class="plan-card"');
  const planEnd = guideSource.indexOf("<!-- 垂类问答依据卡", planStart);
  const planSource = guideSource.slice(planStart, planEnd);
  assert.ok(planStart >= 0 && planEnd > planStart);
  assert.equal((planSource.match(/按方案开工/g) || []).length, 1);
  assert.doesNotMatch(planSource, /<input\b|<textarea\b|<select\b|<form\b|contenteditable=/);
});

test("server-side Skill reuse rejection stays amber and states zero task writes", () => {
  assert.match(
    guideSource,
    /structuredDetail\?\.code === "skill_package_reuse_invalid"[\s\S]*ElMessage\.warning\([\s\S]*本次确定未创建任务/,
  );
});

test("非法 Skill 复用引用显式 amber 阻断整批开工，不静默降级为无引用", () => {
  assert.match(guideSource, /function skillReuseStateForPlan\(plan\)/);
  assert.match(
    guideSource,
    /planHasInvalidSkillReuse\(m\.recommendation\)[\s\S]*复用证据无法核验，本次禁止开工/,
  );
  assert.match(
    guideSource,
    /function planOpenable\(plan\)[\s\S]*planHasInvalidSkillReuse\(plan\) === true[\s\S]*return false/,
  );
  assert.match(
    guideSource,
    /async function openPlan\(plan\)[\s\S]*planHasInvalidSkillReuse\(plan\)[\s\S]*本次未创建任务/,
  );
  assert.match(
    guideSource,
    /v-(?:else-)?if="planHasInvalidSkillReuse\(m\.recommendation\)"[\s\S]*继续对话让系统重新编排/,
  );
});

test("2xx batch response must prove the full requested task set before success", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    operation_id: "guide_batch_fixed_002",
    tasks: [],
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  try {
    await assert.rejects(
      createTasksBatch({
        conversationId: "conv_1",
        operationId: "guide_batch_fixed_002",
        pinnedVersions: { hello_agent: "0.1.0" },
        pinnedPackageDigests: { hello_agent: "b".repeat(64) },
        items: [{ agentId: "hello_agent", inputs: { name: "x" } }],
      }),
      /响应.*任务数量|任务数量.*响应/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("2xx batch response validates order, lineage, versions, and package digests", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    operation_id: "guide_batch_fixed_003",
    tasks: [
      {
        id: "task_parent",
        agent_id: "hello_agent",
        agent_version: "0.1.0",
        conversation_id: "conv_1",
        retry_of: null,
        depends_on: [],
        metadata: { package_snapshot_digest: "c".repeat(64) },
      },
      {
        id: "task_child",
        agent_id: "standards_qa_agent",
        agent_version: "9.9.9",
        conversation_id: "conv_1",
        retry_of: "task_failed_1",
        depends_on: ["task_parent"],
        metadata: { package_snapshot_digest: "d".repeat(64) },
      },
    ],
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  try {
    await assert.rejects(
      createTasksBatch({
        conversationId: "conv_1",
        operationId: "guide_batch_fixed_003",
        pinnedVersions: {
          hello_agent: "0.1.0",
          standards_qa_agent: "0.2.0",
        },
        pinnedPackageDigests: {
          hello_agent: "c".repeat(64),
          standards_qa_agent: "d".repeat(64),
        },
        items: [
          { agentId: "hello_agent", inputs: { name: "x" } },
          {
            agentId: "standards_qa_agent",
            inputs: { question: "x" },
            retryOf: "task_failed_1",
            after: [0],
          },
        ],
      }),
      /Agent 版本/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("batch operation ids are bounded browser-safe values", () => {
  const first = createBatchOperationId();
  const second = createBatchOperationId();
  assert.match(first, /^[A-Za-z0-9_-]{1,64}$/);
  assert.notEqual(first, second);
});

test("batch operation id uses secure 128-bit fallback when randomUUID is unavailable", () => {
  let calls = 0;
  const cryptoWithoutRandomUUID = {
    getRandomValues(bytes) {
      calls += 1;
      assert.equal(bytes.byteLength, 16);
      for (let index = 0; index < bytes.length; index += 1) bytes[index] = index;
      return bytes;
    },
  };

  const operationId = createBatchOperationId(cryptoWithoutRandomUUID);

  assert.equal(calls, 1);
  assert.equal(operationId, "guide_batch_00010203-0405-4607-8809-0a0b0c0d0e0f");
});

test("only response-ambiguous failures enter creation reconciliation", () => {
  assert.equal(batchCreatePersistenceUnknown({ status: 0 }), true);
  assert.equal(batchCreatePersistenceUnknown({ status: 500 }), true);
  assert.equal(batchCreatePersistenceUnknown({ status: 503 }), true);
  assert.equal(batchCreatePersistenceUnknown(new SyntaxError("bad response")), true);
  const idempotencyConflict = {
    status: 409,
    detail: JSON.stringify({
      detail: { code: "batch_operation_conflict", message: "partial" },
    }),
  };
  const concluded = {
    status: 409,
    detail: JSON.stringify({
      detail: { code: "conversation_not_active", message: "concluded" },
    }),
  };
  assert.equal(batchCreateErrorCode(idempotencyConflict), "batch_operation_conflict");
  assert.equal(batchCreatePersistenceUnknown(idempotencyConflict), true);
  assert.equal(batchCreatePersistenceUnknown(concluded), false);
  assert.equal(batchCreatePersistenceUnknown({ status: 409 }), false);
  assert.equal(batchCreatePersistenceUnknown({ status: 422 }), false);
});

test("Guide refreshes schema/version/digest at click and locks only ambiguous creation state", () => {
  assert.match(guideSource, /refreshAgentSchemasForPlan/);
  assert.match(guideSource, /force:\s*true/);
  assert.match(guideSource, /pinnedVersions/);
  assert.match(guideSource, /package_snapshot_digest/);
  assert.match(guideSource, /pinnedPackageDigests/);
  assert.match(guideSource, /创建状态待核/);
  assert.match(guideSource, /reconcileBatchCreation/);
  assert.doesNotMatch(guideSource, /err\?\.status\s*===\s*409/);
});

test("Guide keeps one conversation-level reconciliation CTA outside latest-plan gating", () => {
  const composerStart = guideSource.indexOf('<div class="composer"');
  const composerEnd = guideSource.indexOf("<!-- 回到底部浮钮", composerStart);
  assert.ok(composerStart >= 0 && composerEnd > composerStart);
  const composerSource = guideSource.slice(composerStart, composerEnd);
  assert.match(composerSource, /v-if="batchCreationNeedsReconciliation"/);
  assert.match(composerSource, /class="batch-reconcile-bar"/);
  assert.match(composerSource, /@click="reconcileBatchCreation"/);
  assert.doesNotMatch(composerSource, /latestPlanIdx/);
});

test("deterministic batch failure clears before a conversation switch guard while ambiguous state stays locked", () => {
  const openPlanStart = guideSource.indexOf("async function openPlan(plan)");
  const catchStart = guideSource.indexOf("  } catch (err) {", openPlanStart);
  const finallyStart = guideSource.indexOf("  } finally {", catchStart);
  assert.ok(openPlanStart >= 0 && catchStart > openPlanStart && finallyStart > catchStart);

  const catchSource = guideSource.slice(catchStart, finallyStart);
  const deterministicBranchStart = catchSource.indexOf(
    "const structuredDetail = unwrapDetail(err?.detail);",
  );
  assert.ok(deterministicBranchStart >= 0, "deterministic failure branch must exist");
  assert.doesNotMatch(
    catchSource.slice(0, deterministicBranchStart),
    /clearDurableBatchCreation\(batchAttempt\)/,
    "response-ambiguous failures must return with the submitted journal intact",
  );

  const deterministicBranch = catchSource.slice(deterministicBranchStart);
  const clearIndex = deterministicBranch.indexOf(
    "clearDurableBatchCreation(batchAttempt);",
  );
  const viewGuardIndex = deterministicBranch.indexOf(
    "if (!conversationSnapshotMatches(submittedPlanSnapshot, {",
  );
  assert.ok(clearIndex >= 0, "submitted operation journal must be cleared");
  assert.ok(viewGuardIndex >= 0, "current-view guard must remain in place");
  assert.ok(
    clearIndex < viewGuardIndex,
    "conversation A journal must clear before an A→B switch can return early",
  );
});
