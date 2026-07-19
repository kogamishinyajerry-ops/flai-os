import test from "node:test";
import assert from "node:assert/strict";

import { acquireChannel } from "../src/stores/liveFeed.js";

const taskId = "task_terminal_join";

function terminalSnapshot() {
  return {
    schema_version: "task-live-snapshot/v1",
    task: { id: taskId, status: "completed" },
    base: { sequence: 0, event_id: null },
    cursor: { sequence: 1, event_id: "evt_terminal" },
    events: [{
      sequence: 1,
      event: {
        event_id: "evt_terminal",
        task_id: taskId,
        event_type: "task_completed",
        level: "info",
        message: "done",
        payload: {},
      },
    }],
    resync_required: false,
    resync_reason: null,
  };
}

async function flushUntil(predicate) {
  for (let i = 0; i < 100; i += 1) {
    if (predicate()) return;
    await Promise.resolve();
  }
  assert.fail("condition did not settle");
}

test("join-triggered terminal refresh failure replaces the old 30s timer with 5s", async () => {
  globalThis.document = { hidden: false };
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  let timerId = 0;
  const activeTimers = new Map();
  globalThis.setTimeout = (_callback, delay) => {
    const id = ++timerId;
    activeTimers.set(id, delay);
    return id;
  };
  globalThis.clearTimeout = (id) => activeTimers.delete(id);

  let liveCalls = 0;
  globalThis.fetch = async (path) => {
    if (String(path).includes("/live-snapshot")) {
      liveCalls += 1;
      if (liveCalls === 1) {
        return { ok: true, status: 200, json: async () => terminalSnapshot() };
      }
      throw new TypeError("join refresh offline");
    }
    throw new Error(`unexpected request: ${path}`);
  };

  const light = acquireChannel(`task:${taskId}`);
  let detail = null;
  try {
    await flushUntil(() => light.state.loaded.value === true);
    await flushUntil(() => [...activeTimers.values()].includes(30_000));
    assert.deepEqual([...activeTimers.values()], [30_000]);

    detail = acquireChannel(`task:${taskId}`, { modelCalls: true });
    await flushUntil(() => detail.state.connection.value === "disconnected");
    await flushUntil(() => [...activeTimers.values()].includes(5_000));

    assert.equal(liveCalls, 2);
    assert.deepEqual([...activeTimers.values()], [5_000]);
  } finally {
    detail?.release();
    light.release();
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});
