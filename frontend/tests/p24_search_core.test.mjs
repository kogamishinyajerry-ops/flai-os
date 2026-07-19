import test from "node:test";
import assert from "node:assert/strict";

import {
  SearchContractError,
  buildSearchResultRoute,
  isSearchableQuery,
  mergeSearchItems,
  normalizeSearchQuery,
  reconcileSearchSelection,
  validateSearchPage,
} from "../src/utils/searchCore.js";

const basePage = (scope, items = []) => ({
  schema_version: "search-page/v1",
  scope,
  query: "needle",
  snapshot_at: "2026-07-19T00:00:00Z",
  items,
  has_more: false,
  next_cursor: null,
});

test("query gate trims but rejects short, overlong, and control-bearing requests", () => {
  assert.equal(normalizeSearchQuery("  两字  "), "两字");
  assert.equal(isSearchableQuery("两字"), true);
  assert.equal(isSearchableQuery("x"), false);
  assert.equal(isSearchableQuery("x".repeat(129)), false);
  assert.equal(isSearchableQuery("ab\ncd"), false);
  assert.equal(isSearchableQuery("ab\u0085cd"), false);
});

test("typed search pages reject scope drift and false pagination", () => {
  const item = {
    kind: "message",
    id: `msg_${"1".repeat(32)}`,
    conversation_id: `conv_${"2".repeat(32)}`,
    conversation_agent_id: "guide_agent",
    role: "user",
    snippet: "needle",
    snippet_truncated: false,
    created_at: "2026-07-19T00:00:00Z",
    match_kind: "text_prefix",
  };
  assert.equal(validateSearchPage(basePage("message", [item]), { scope: "message", query: "needle" }).items[0], item);
  assert.throws(
    () => validateSearchPage(basePage("message", [{ ...item, kind: "task" }]), { scope: "message", query: "needle" }),
    SearchContractError,
  );
  assert.throws(
    () => validateSearchPage({ ...basePage("message", [item]), has_more: true }),
    /has_more/,
  );
  assert.throws(
    () => validateSearchPage({ ...basePage("message", [item]), next_cursor: "" }),
    /游标/,
  );
  assert.throws(
    () => validateSearchPage(basePage("message", [{ ...item, content: "must-not-leak" }])),
    /未声明字段/,
  );
  assert.throws(
    () => validateSearchPage({ ...basePage("message", [item]), snapshot_at: "not-a-date" }),
    /snapshot_at/,
  );
  assert.throws(
    () => validateSearchPage(basePage("message", [{ ...item, created_at: "not-a-date" }])),
    /created_at/,
  );
  assert.throws(
    () => validateSearchPage(basePage("message", [{ ...item, snippet: "长".repeat(241) }])),
    /长度上限/,
  );
});

test("unknown classification remains explicitly withheld", () => {
  const task = {
    kind: "task",
    id: "task_1",
    name: null,
    agent_id: "hello_agent",
    status: "running",
    data_classification: null,
    content_withheld: true,
    created_at: "2026-07-19T00:00:00Z",
    match_kind: "id_prefix",
  };
  assert.equal(validateSearchPage(basePage("task", [task])).items[0].content_withheld, true);
  assert.throws(
    () => validateSearchPage(basePage("task", [{ ...task, content_withheld: false }])),
    /fail-closed/,
  );
});

test("deep links use stable message and output-file anchors", () => {
  assert.equal(
    buildSearchResultRoute("conversation", { kind: "conversation", id: "conv / 1" }),
    "/?c=conv+%2F+1",
  );
  assert.equal(
    buildSearchResultRoute("message", { kind: "message", id: "msg_2", conversation_id: "conv_1" }),
    "/?c=conv_1&m=msg_2",
  );
  assert.equal(
    buildSearchResultRoute("task", { kind: "task", id: "task/1" }),
    "/tasks/task%2F1",
  );
  assert.equal(
    buildSearchResultRoute("artifact", { kind: "artifact", id: "file_1", task_id: "task_1" }),
    "/tasks/task_1?file=file_1",
  );
});

test("parallel scope settlement preserves selection by stable scope and id", () => {
  const first = reconcileSearchSelection(["message:msg_1"], "");
  assert.deepEqual(first, { index: 0, key: "message:msg_1" });
  assert.deepEqual(
    reconcileSearchSelection(
      ["conversation:conv_1", "message:msg_1", "task:task_1"],
      first.key,
    ),
    { index: 1, key: "message:msg_1" },
  );
  assert.deepEqual(reconcileSearchSelection([], first.key), { index: 0, key: "" });
});

test("recent display-name task supplements server results without duplicate IDs", () => {
  const server = [{ id: "task_1", kind: "task", name: "server" }];
  const recent = [
    { id: "task_1", kind: "task", name: "duplicate" },
    { id: "task_2", kind: "task", name: "display-name hit" },
  ];
  assert.deepEqual(mergeSearchItems(server, recent, 6), [server[0], recent[1]]);
});
