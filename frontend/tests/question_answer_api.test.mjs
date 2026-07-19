import test from "node:test";
import assert from "node:assert/strict";

import { answerQuestion } from "../src/api/conversations.js";

test("answerQuestion posts the frozen revision, stable submission id, and payload to the dedicated route", async () => {
  const originalFetch = globalThis.fetch;
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return {
      ok: true,
      json: async () => ({ replayed: false }),
    };
  };

  const body = {
    question_revision: 1,
    submission_id: "submission-0001",
    payload: { kind: "option", option_id: "option_1" },
  };
  try {
    await answerQuestion("conv_1", "q_1", body);
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(observed.path, "/api/conversations/conv_1/questions/q_1/answer");
  assert.equal(observed.init.method, "POST");
  assert.equal(observed.init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(observed.init.body), body);
});
