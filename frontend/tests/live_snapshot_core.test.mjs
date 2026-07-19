import test from "node:test";
import assert from "node:assert/strict";

import {
  acknowledgeFullSnapshot,
  describeLiveConnection,
  initialResyncClock,
  isSnapshotRequestCurrent,
  evaluateTaskLiveSnapshot,
  nextLiveConnection,
  planTaskSnapshotRequest,
  requestFullSnapshot,
} from "../src/stores/liveSnapshotCore.js";

const event = (id, taskId = "task_1") => ({
  event_id: id,
  task_id: taskId,
  event_type: "agent_log",
  level: "info",
});

const envelope = ({
  baseSequence = 0,
  baseEventId = null,
  items = [],
  cursorSequence = items.length,
  cursorEventId = items.length ? items.at(-1).event.event_id : null,
  resyncRequired = false,
  resyncReason = null,
} = {}) => ({
  schema_version: "task-live-snapshot/v1",
  task: { id: "task_1", status: "running" },
  base: { sequence: baseSequence, event_id: baseEventId },
  cursor: { sequence: cursorSequence, event_id: cursorEventId },
  events: items,
  resync_required: resyncRequired,
  resync_reason: resyncReason,
});

test("cold snapshot replaces local projection only when sequence is contiguous", () => {
  const payload = envelope({
    items: [
      { sequence: 1, event: event("evt_1") },
      { sequence: 2, event: event("evt_2") },
    ],
    cursorSequence: 2,
    cursorEventId: "evt_2",
  });

  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, payload),
    {
      action: "replace",
      task: payload.task,
      events: [event("evt_1"), event("evt_2")],
      cursor: { sequence: 2, eventId: "evt_2" },
    },
  );
});

test("incremental snapshot appends from the exact current anchor", () => {
  const payload = envelope({
    baseSequence: 2,
    baseEventId: "evt_2",
    items: [{ sequence: 3, event: event("evt_3") }],
    cursorSequence: 3,
    cursorEventId: "evt_3",
  });

  assert.equal(
    evaluateTaskLiveSnapshot({ sequence: 2, eventId: "evt_2", taskId: "task_1" }, payload).action,
    "append",
  );
});

test("server anchor rejection forces a full resnapshot without applying events", () => {
  const payload = envelope({
    baseSequence: 2,
    baseEventId: "evt_2",
    cursorSequence: 3,
    cursorEventId: "evt_3",
    resyncRequired: true,
    resyncReason: "anchor_mismatch",
  });

  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 2, eventId: "evt_2", taskId: "task_1" }, payload),
    { action: "resnapshot", reason: "anchor_mismatch" },
  );
});

test("a missing event sequence is a gap and no partial delta is returned", () => {
  const payload = envelope({
    items: [
      { sequence: 1, event: event("evt_1") },
      { sequence: 3, event: event("evt_3") },
    ],
    cursorSequence: 3,
    cursorEventId: "evt_3",
  });

  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, payload),
    { action: "resnapshot", reason: "event_gap" },
  );
});

test("base mismatch, final cursor mismatch, and unknown schema all fail closed", () => {
  const baseMismatch = envelope({ baseSequence: 1, baseEventId: "evt_1" });
  assert.equal(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, baseMismatch).action,
    "resnapshot",
  );

  const cursorMismatch = envelope({
    items: [{ sequence: 1, event: event("evt_1") }],
    cursorSequence: 2,
    cursorEventId: "evt_2",
  });
  assert.equal(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, cursorMismatch).action,
    "resnapshot",
  );

  const unknownSchema = { ...envelope(), schema_version: "task-live-snapshot/v2" };
  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, unknownSchema),
    { action: "resnapshot", reason: "unsupported_schema" },
  );
});

test("duplicate identities and cross-task events fail closed before any append", () => {
  const duplicate = envelope({
    baseSequence: 2,
    baseEventId: "evt_2",
    items: [
      { sequence: 3, event: event("evt_1") },
      { sequence: 4, event: event("evt_4") },
    ],
    cursorSequence: 4,
    cursorEventId: "evt_4",
  });
  assert.deepEqual(
    evaluateTaskLiveSnapshot({
      sequence: 2,
      eventId: "evt_2",
      taskId: "task_1",
      eventIds: new Set(["evt_1", "evt_2"]),
    }, duplicate),
    { action: "resnapshot", reason: "duplicate_event" },
  );

  const wrongTask = envelope({
    items: [{ sequence: 1, event: event("evt_1", "task_other") }],
    cursorSequence: 1,
    cursorEventId: "evt_1",
  });
  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, wrongTask),
    { action: "resnapshot", reason: "task_mismatch" },
  );

  const emptyIdentity = envelope({
    items: [
      { sequence: 1, event: event("") },
      { sequence: 2, event: event("evt_2") },
    ],
    cursorSequence: 2,
    cursorEventId: "evt_2",
  });
  assert.deepEqual(
    evaluateTaskLiveSnapshot({ sequence: 0, eventId: null, taskId: "task_1" }, emptyIdentity),
    { action: "resnapshot", reason: "event_gap" },
  );
});

test("resnapshot generation cannot be swallowed by an older in-flight request", () => {
  const clock0 = initialResyncClock();
  const first = planTaskSnapshotRequest(clock0, { sequence: 7, eventId: "evt_7" });
  assert.deepEqual(first.base, { sequence: 0, eventId: null });

  const clock1 = requestFullSnapshot(clock0);
  assert.equal(isSnapshotRequestCurrent(clock1, first.generation), false);
  const afterOldFull = acknowledgeFullSnapshot(clock1, first.generation);
  const second = planTaskSnapshotRequest(afterOldFull, { sequence: 8, eventId: "evt_8" });

  assert.equal(second.full, true);
  assert.equal(second.generation, clock1.requested);
  assert.deepEqual(second.base, { sequence: 0, eventId: null });
});

test("connection truth keeps warm data stale and cold failures empty", () => {
  const cold = nextLiveConnection(
    { connection: "idle", lastSuccessAt: null },
    { type: "failure", error: "offline" },
  );
  assert.deepEqual(cold, {
    connection: "disconnected",
    lastSuccessAt: null,
    stale: true,
    resyncing: false,
    error: "offline",
  });

  const connected = nextLiveConnection(cold, { type: "success", at: 1234 });
  assert.deepEqual(connected, {
    connection: "connected",
    lastSuccessAt: 1234,
    stale: false,
    resyncing: false,
    error: "",
  });

  const warm = nextLiveConnection(connected, { type: "failure", error: "timeout" });
  assert.deepEqual(warm, {
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: false,
    error: "timeout",
  });

  const gap = nextLiveConnection(warm, { type: "resync", error: "event_gap" });
  assert.deepEqual(gap, {
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: true,
    error: "event_gap",
  });
});

test("connection notice distinguishes cold, warm, and gap recovery truth", () => {
  assert.deepEqual(describeLiveConnection({
    loaded: false,
    connection: "disconnected",
    lastSuccessAt: null,
    stale: true,
    resyncing: false,
    error: "后端繁忙，请稍后重试",
  }), {
    kind: "cold",
    title: "当前无法同步",
    detail: "尚未取得可显示的真实快照；系统会自动重试。",
    error: "后端繁忙",
    lastSuccessAt: null,
  });

  const manual = describeLiveConnection({
    loaded: true,
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: true,
    error: "manual_resnapshot",
  });
  assert.equal(manual.error, "");
  assert.equal(manual.detail, "已按你的操作发起完整核对；完成前保留上次成功内容。");

  assert.equal(describeLiveConnection({
    loaded: true,
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: true,
    error: "event_gap",
  }).error, "检测到事件序列缺口");

  assert.equal(describeLiveConnection({
    loaded: true,
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: false,
    error: "timeout",
  }).detail, "连接恢复后将先重新核对权威数据，再恢复同步；系统会自动重试。");

  assert.deepEqual(describeLiveConnection({
    loaded: true,
    connection: "disconnected",
    lastSuccessAt: 1234,
    stale: true,
    resyncing: true,
    error: "event_gap",
  }), {
    kind: "resync",
    title: "正在重新核对完整快照",
    detail: "可疑增量已丢弃；核对完成前仅保留上次成功内容。",
    error: "检测到事件序列缺口",
    lastSuccessAt: 1234,
  });

  assert.deepEqual(describeLiveConnection({
    loaded: false,
    connection: "disconnected",
    lastSuccessAt: null,
    stale: true,
    resyncing: true,
    error: "event_gap",
  }), {
    kind: "resync",
    title: "正在重新核对完整快照",
    detail: "可疑增量已丢弃；尚无可显示的真实快照。",
    error: "检测到事件序列缺口",
    lastSuccessAt: null,
  });

  assert.equal(describeLiveConnection({
    loaded: true,
    connection: "connected",
    stale: false,
    resyncing: false,
  }), null);
});
