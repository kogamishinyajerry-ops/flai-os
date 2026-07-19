import test from "node:test";
import assert from "node:assert/strict";

import { getTaskLiveSnapshot, listTasks } from "../src/api/tasks.js";
import { getConversation, listConversationTasks } from "../src/api/conversations.js";

test("task live authority bypasses browser cache and carries the exact cursor", async () => {
  let seen = null;
  globalThis.fetch = async (path, init) => {
    seen = { path, init };
    return { ok: true, json: async () => ({ schema_version: "task-live-snapshot/v1" }) };
  };

  await getTaskLiveSnapshot("task_1", { afterSequence: 7, anchorEventId: "evt_7" });

  assert.equal(seen.init.cache, "no-store");
  assert.equal(
    seen.path,
    "/api/tasks/task_1/live-snapshot?after_sequence=7&anchor_event_id=evt_7",
  );
});

test("list and conversation authorities also bypass browser cache", async () => {
  const seen = [];
  globalThis.fetch = async (path, init) => {
    seen.push({ path, cache: init.cache });
    return { ok: true, json: async () => [] };
  };

  await listTasks({ limit: 100 });
  await getConversation("conv_1");
  await listConversationTasks("conv_1");

  assert.deepEqual(seen, [
    { path: "/api/tasks?limit=100", cache: "no-store" },
    { path: "/api/conversations/conv_1", cache: "no-store" },
    { path: "/api/conversations/conv_1/tasks", cache: "no-store" },
  ]);
});
