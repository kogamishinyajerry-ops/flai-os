import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  archiveConversation,
  concludeConversation,
  listConversations,
  renameConversation,
} from "../src/api/conversations.js";
import {
  ConversationRuntimeContractError,
  validateConversationListProjection,
  validateConversationSnapshot,
  validateConversationSummaryProjection,
} from "../src/utils/conversationRuntimeCore.js";

const CONVERSATION_ID = `conv_${"a".repeat(32)}`;

function lifecycleSnapshot(overrides = {}) {
  return {
    id: CONVERSATION_ID,
    agent_id: "guide_agent",
    status: "active",
    created_by: "Alice",
    title: null,
    lifecycle_revision: 0,
    archived_at: null,
    recommendation: null,
    messages: [],
    ...overrides,
  };
}

test("conversation lifecycle API sends explicit visibility and exact CAS bodies", async () => {
  const originalFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (path, init = {}) => {
    seen.push({ path, init });
    return { ok: true, json: async () => [] };
  };

  try {
    await listConversations({ visibility: "visible", limit: 30 });
    await listConversations({ visibility: "archived", limit: 30 });
    await renameConversation("conv_1", {
      lifecycleRevision: 4,
      title: "风洞试验复核",
    });
    await archiveConversation("conv_1", { lifecycleRevision: 5 });
    await concludeConversation("conv_1", { lifecycleRevision: 6 });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(
    seen.map(({ path, init }) => ({
      path,
      method: init.method || "GET",
      cache: init.cache,
      body: init.body ? JSON.parse(init.body) : null,
    })),
    [
      {
        path: "/api/conversations?visibility=visible&limit=30",
        method: "GET",
        cache: "no-store",
        body: null,
      },
      {
        path: "/api/conversations?visibility=archived&limit=30",
        method: "GET",
        cache: "no-store",
        body: null,
      },
      {
        path: "/api/conversations/conv_1/title",
        method: "PATCH",
        cache: undefined,
        body: { lifecycle_revision: 4, title: "风洞试验复核" },
      },
      {
        path: "/api/conversations/conv_1/archive",
        method: "POST",
        cache: undefined,
        body: { lifecycle_revision: 5 },
      },
      {
        path: "/api/conversations/conv_1/conclude",
        method: "POST",
        cache: undefined,
        body: { lifecycle_revision: 6 },
      },
    ],
  );
});

test("conversation lifecycle API rejects invalid CAS inputs before the network boundary", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCount = 0;
  globalThis.fetch = async () => {
    fetchCount += 1;
    throw new Error("network must not be reached");
  };
  try {
    for (const call of [
      () => listConversations({ visibility: "all" }),
      () => renameConversation("conv_1", { lifecycleRevision: 0, title: "" }),
      () => renameConversation("conv_1", { lifecycleRevision: 0, title: " 前后留白" }),
      () => renameConversation("conv_1", { lifecycleRevision: 0, title: "含\n换行" }),
      () => archiveConversation("conv_1", { lifecycleRevision: true }),
      () => concludeConversation("conv_1", { lifecycleRevision: -1 }),
    ]) {
      await assert.rejects(async () => call(), TypeError);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(fetchCount, 0);
});

test("conversation runtime accepts lifecycle and visibility as orthogonal trusted fields", () => {
  const activeArchived = lifecycleSnapshot({
    title: "风洞试验复核",
    lifecycle_revision: 3,
    archived_at: "2026-07-20T10:00:00+08:00",
  });
  const concludedVisible = lifecycleSnapshot({
    status: "concluded",
    lifecycle_revision: 7,
  });

  assert.equal(validateConversationSnapshot(activeArchived, CONVERSATION_ID), activeArchived);
  assert.equal(validateConversationSnapshot(concludedVisible, CONVERSATION_ID), concludedVisible);

  const summary = lifecycleSnapshot();
  delete summary.messages;
  assert.equal(validateConversationSummaryProjection(summary, CONVERSATION_ID), summary);
  const list = [summary];
  assert.equal(validateConversationListProjection(list), list);
});

test("conversation runtime rejects missing or non-canonical lifecycle projection fields", () => {
  const invalid = [
    lifecycleSnapshot({ status: "paused" }),
    lifecycleSnapshot({ title: "" }),
    lifecycleSnapshot({ title: " 前后留白" }),
    lifecycleSnapshot({ title: "含\n换行" }),
    lifecycleSnapshot({ title: "长".repeat(61) }),
    lifecycleSnapshot({ lifecycle_revision: true }),
    lifecycleSnapshot({ lifecycle_revision: -1 }),
    lifecycleSnapshot({ lifecycle_revision: 1.5 }),
    lifecycleSnapshot({ archived_at: "not-a-timestamp" }),
  ];
  for (const field of ["title", "lifecycle_revision", "archived_at"]) {
    const missing = lifecycleSnapshot();
    delete missing[field];
    invalid.push(missing);
  }

  for (const snapshot of invalid) {
    assert.throws(
      () => validateConversationSnapshot(snapshot, CONVERSATION_ID),
      ConversationRuntimeContractError,
    );
  }
});

test("conversation list projection rejects malformed items before they reach UI or CAS", async () => {
  const validSummary = lifecycleSnapshot();
  delete validSummary.messages;
  const malformed = lifecycleSnapshot({ lifecycle_revision: "4" });
  delete malformed.messages;

  for (const list of [
    {},
    [malformed],
    [validSummary, { ...validSummary }],
  ]) {
    assert.throws(
      () => validateConversationListProjection(list),
      ConversationRuntimeContractError,
    );
  }

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => [malformed] });
  try {
    await assert.rejects(
      () => listConversations({ visibility: "visible" }),
      ConversationRuntimeContractError,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("sidebar exposes honest visible and archived lifecycle controls", () => {
  const app = read("../src/App.vue");
  const titleBranch = app.indexOf("if (c.title)");
  const recommendationBranch = app.indexOf("const r = c.recommendation", titleBranch);

  assert.match(app, /loadConvoBucket\(["']visible["']/);
  assert.match(app, /loadConvoBucket\(["']archived["']/);
  assert.match(app, /最近对话/);
  assert.match(app, /已归档/);
  assert.match(app, /role=["']alert["']/);
  assert.match(app, /重命名/);
  assert.match(app, /不可撤销/);
  assert.ok(titleBranch >= 0 && recommendationBranch > titleBranch, "真实 title 必须先于 recommendation fallback");
  assert.match(app, /err\?\.status === 409/);
  assert.match(app, /const refreshed = await loadConvos\(\)/);
  assert.match(app, /权威列表刷新失败/);
  assert.match(app, /class="convo-item"[\s\S]*?<button type="button" class="convo-open"/);
  assert.doesNotMatch(app, /class="convo-item"[^>]*role="button"/);
  assert.match(app, /@media \(hover: none\)\s*\{\s*\.convo-menu\s*\{\s*opacity:\s*1;/);
  assert.match(app, /\.sb-convos\.is-archived\s*\{[^}]*max-height:/);
  assert.match(app, /\.convo-menu,\s*\.convo-item,\s*\.sb-archive-toggle,\s*\.sb-foot-btn\s*\{\s*transition:\s*none;/);
});

test("conclusion surfaces submit the observed revision and call it ended", () => {
  const workbench = read("../src/views/WorkbenchSession.vue");
  const guide = read("../src/views/GuidePage.vue");
  const taskCreate = read("../src/views/TaskCreate.vue");

  assert.match(workbench, /已结束/);
  assert.match(workbench, /concludeConversation\(sessionId,\s*\{\s*lifecycleRevision:/);
  assert.match(workbench, /err\?\.status === 409[\s\S]*?await pokeConversation\(sessionId\)/);
  assert.match(workbench, /权威状态刷新失败/);
  assert.match(guide, /lifecycle_revision:\s*conversationLifecycleRevision\.value/);
  assert.match(taskCreate, /prefillLifecycleRevision/);
  assert.match(taskCreate, /await concludeConversation\([\s\S]*?lifecycleRevision:\s*prefillLifecycleRevision\.value/);
  assert.match(taskCreate, /任务已创建，但会话因状态变化未结束/);
  assert.match(taskCreate, /任务已创建，但未能确认会话是否已结束/);
  assert.doesNotMatch(taskCreate, /concludeConversation\([^\n]+\.catch\(\(\) => \{\}\)/);
});

test("QuickSwitcher prefers a human title before machine fallback", () => {
  const quickSwitcher = read("../src/components/QuickSwitcher.vue");
  const titleBranch = quickSwitcher.indexOf("if (c.title)");
  const recommendationBranch = quickSwitcher.indexOf("const r = c.recommendation", titleBranch);

  assert.ok(titleBranch >= 0 && recommendationBranch > titleBranch);
});
