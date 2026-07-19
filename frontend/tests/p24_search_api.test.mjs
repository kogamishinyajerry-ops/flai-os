import test from "node:test";
import assert from "node:assert/strict";

import { searchAddresses } from "../src/api/search.js";

test("search API sends only the frozen addressing parameters and bypasses cache", async () => {
  const originalFetch = globalThis.fetch;
  let seen = null;
  globalThis.fetch = async (path, init) => {
    seen = { path, init };
    return {
      ok: true,
      json: async () => ({
        schema_version: "search-page/v1",
        scope: "artifact",
        query: "100%_报告",
        snapshot_at: "2026-07-19T00:00:00Z",
        items: [],
        has_more: false,
        next_cursor: null,
      }),
    };
  };
  try {
    await searchAddresses({
      q: "  100%_报告  ",
      scope: "artifact",
      limit: 6,
      cursor: "opaque_cursor",
      status: "running",
      agentId: "hello_agent",
      taskScope: "mine",
      owner: "bob",
      username: "bob",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(seen.init.cache, "no-store");
  assert.equal(
    seen.path,
    "/api/search?q=100%25_%E6%8A%A5%E5%91%8A&scope=artifact&limit=6&cursor=opaque_cursor&status=running&agent_id=hello_agent&task_scope=mine",
  );
});

test("search API rejects invalid inputs before opening the network boundary", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCount = 0;
  globalThis.fetch = async () => {
    fetchCount += 1;
    throw new Error("network must not be reached");
  };
  try {
    const invalidCalls = [
      { q: "x", scope: "message" },
      { q: "ab\u0085cd", scope: "message" },
      { q: "valid", scope: "message", limit: 0 },
      { q: "valid", scope: "message", cursor: "not+opaque" },
      { q: "valid", scope: "message", status: "running" },
      { q: "valid", scope: "task", status: "not-a-status" },
      { q: "valid", scope: "artifact", agentId: "Bad Agent" },
      { q: "valid", scope: "task", taskScope: "foreign" },
    ];
    for (const params of invalidCalls) {
      await assert.rejects(searchAddresses(params), TypeError);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(fetchCount, 0);
});
