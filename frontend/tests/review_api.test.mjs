import test from "node:test";
import assert from "node:assert/strict";

import { reviewTask } from "../src/api/tasks.js";

test("review API emits only the frozen judgment fields and no identity text", async () => {
  const originalFetch = globalThis.fetch;
  let seen = null;
  globalThis.fetch = async (path, init) => {
    seen = { path, init };
    return { ok: true, json: async () => ({ status: "rejected" }) };
  };
  try {
    await reviewTask("task_1", {
      action: "reject",
      reasonCode: "insufficient_evidence",
      comment: "缺少原始测量记录",
      pairedAdviceId: null,
      reviewer: "forged-user",
      advisor: "forged-advisor",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen.path, "/api/tasks/task_1/review");
  assert.deepEqual(JSON.parse(seen.init.body), {
    action: "reject",
    reason_code: "insufficient_evidence",
    comment: "缺少原始测量记录",
    paired_advice_id: null,
  });
});
