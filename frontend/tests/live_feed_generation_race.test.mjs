import test from "node:test";
import assert from "node:assert/strict";

import {
  acquireChannel,
  onTransition,
  resnapshotTask,
} from "../src/stores/liveFeed.js";

const taskId = "task_generation_race";

function snapshot(status, eventId, message) {
  return {
    schema_version: "task-live-snapshot/v1",
    task: { id: taskId, status },
    base: { sequence: 0, event_id: null },
    cursor: { sequence: 1, event_id: eventId },
    events: [{
      sequence: 1,
      event: {
        event_id: eventId,
        task_id: taskId,
        event_type: "agent_log",
        level: "info",
        message,
        payload: {},
      },
    }],
    resync_required: false,
    resync_reason: null,
  };
}

test("a superseded in-flight snapshot cannot mutate state or emit a transition", async () => {
  globalThis.document = { hidden: false };
  let releaseOldResponse;
  let liveCalls = 0;
  globalThis.fetch = (path) => {
    assert.match(String(path), /\/api\/tasks\/task_generation_race\/live-snapshot/);
    liveCalls += 1;
    if (liveCalls === 1) {
      return new Promise((resolve) => {
        releaseOldResponse = () => resolve({
          ok: true,
          status: 200,
          json: async () => snapshot("running", "evt_old", "OLD-SENTINEL"),
        });
      });
    }
    assert.equal(liveCalls, 2);
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => snapshot("completed", "evt_new", "NEW-AUTHORITY"),
    });
  };

  const transitions = [];
  const unsubscribe = onTransition((event) => transitions.push(event));
  const handle = acquireChannel(`task:${taskId}`);
  try {
    for (let i = 0; i < 50 && !releaseOldResponse; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    assert.equal(typeof releaseOldResponse, "function");

    const forced = resnapshotTask(taskId);
    releaseOldResponse();
    await forced;

    assert.equal(liveCalls, 2);
    assert.equal(handle.state.loaded.value, true);
    assert.equal(handle.state.task.value.status, "completed");
    assert.deepEqual(handle.state.events.value.map((event) => event.message), ["NEW-AUTHORITY"]);
    assert.equal(handle.state.events.value.some((event) => event.message === "OLD-SENTINEL"), false);
    assert.deepEqual(transitions, []);
  } finally {
    unsubscribe();
    handle.release();
  }
});
