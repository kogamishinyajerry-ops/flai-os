import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  isReviewRequestedFrom,
  validateReviewInboxPage,
} from "../src/utils/reviewInboxCore.js";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(here, path), "utf8");

test("same display name never collapses exact review-route usernames", () => {
  const task = {
    id: "task-1",
    review_requested_from_username: "alice",
    reviewer_display_name: "同名工程师",
  };
  assert.equal(isReviewRequestedFrom(task, "alice"), true);
  assert.equal(isReviewRequestedFrom(task, "bob"), false);
  assert.equal(isReviewRequestedFrom(task, "同名工程师"), false);
});

test("personal inbox has a server-derived endpoint and identity-change reset", () => {
  const api = read("../src/api/me.js");
  const store = read("../src/stores/reviewInbox.js");
  assert.match(api, /\/api\/me\/review-inbox/);
  assert.match(store, /currentUser\.value\?\.username/);
  assert.match(store, /releaseHandle\(\);\s*resetProjection\(\)/s);
});

test("review inbox envelope fails closed and keeps one snapshot generation", () => {
  const valid = {
    schema_version: "review-inbox/v1",
    items: [{ id: "t1" }],
    has_more: true,
    next_offset: 1,
    snapshot_id: "a".repeat(64),
    total: 2,
  };
  assert.deepEqual(validateReviewInboxPage(valid, { expectedOffset: 0 }), valid);
  assert.throws(
    () => validateReviewInboxPage({ ...valid, has_more: undefined }, { expectedOffset: 0 }),
    /has_more/,
  );
  assert.throws(
    () => validateReviewInboxPage({ ...valid, snapshot_id: "b".repeat(64) }, {
      expectedOffset: 0,
      expectedSnapshotId: "a".repeat(64),
    }),
    /snapshot/,
  );
  assert.throws(
    () => validateReviewInboxPage({ ...valid, items: [{ id: "seen" }] }, {
      expectedOffset: 0,
      seenIds: new Set(["seen"]),
    }),
    /duplicate/,
  );
});

test("warm review-inbox failure is rendered as stale without hiding the last rows", () => {
  const sources = [
    "../src/components/StatusCenter.vue",
    "../src/views/TodayPage.vue",
    "../src/views/TaskConsole.vue",
  ].map(read).join("\n");
  assert.match(sources, /reviewInboxStale/);
  assert.match(sources, /上次成功快照/);
  assert.doesNotMatch(sources, /reviewInboxError \|\| reviewInboxSyncError[^]*v-else-if/);
});

test("global UI does not call every waiting task '待你签发'", () => {
  const sources = [
    "../src/components/StatusDock.vue",
    "../src/components/StatusCenter.vue",
    "../src/views/TodayPage.vue",
    "../src/views/TaskConsole.vue",
    "../src/views/TaskDetail.vue",
    "../src/views/WorkbenchSession.vue",
    "../src/views/GuidePage.vue",
    "../src/views/MePage.vue",
    "../src/utils/squad.js",
  ].map(read).join("\n");
  assert.doesNotMatch(sources, /待你签发|等你签发|需要你签发|等待你审阅|待我跟进/);
  assert.match(sources, /点名请你签/);
  assert.match(sources, /待人工签发/);
});
