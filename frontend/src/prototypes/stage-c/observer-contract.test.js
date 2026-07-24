import assert from "node:assert/strict";
import test from "node:test";

import {
  OBSERVER_CONTRACT_VERSION,
  projectObserverEvents,
} from "./observer-contract.js";

function workingEvent(overrides = {}) {
  return {
    contractVersion: OBSERVER_CONTRACT_VERSION,
    source: "control-kernel",
    eventId: "observer-cfd-3",
    taskId: "task-cfd-042",
    taskRevision: "rev-1",
    executionEpoch: "epoch-7",
    sequence: 3,
    observedAt: "2026-07-23T05:00:00.000Z",
    reality: "REAL",
    kind: "working",
    action: "inspect",
    title: "正在交叉核对",
    detail: "正在检查入口湍流量、壁面处理与近壁分辨率。",
    step: { current: 3, total: 4 },
    preview: {
      kind: "cfd-case",
      title: "APU 入口 · 算例剖面",
      caption: "6 个边界 · solver 启动 0",
      primary: "入口湍流量与近壁分辨率",
      secondary: "规则与结构投影正在交叉高亮",
    },
    evidenceRefs: [
      "reality-witness:REAL:witness-cfd-3",
      "knowledge:synthetic-cfd-rules-v1",
    ],
    ...overrides,
  };
}

test("observer projection stays unknown and settled without a trusted event", () => {
  const snapshot = projectObserverEvents([], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.title, "等待可靠状态");
  assert.equal(snapshot.reasonCode, "observation_missing");
});

test("an observation without an explicit execution reality fails closed", () => {
  const event = workingEvent();
  delete event.reality;

  const snapshot = projectObserverEvents([event], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(event.observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_invalid");
  assert.equal(snapshot.reality, "UNKNOWN");
});

test("a reality marker without a witness identity is not evidence", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({
      observedAt,
      evidenceRefs: ["reality-witness:REAL:"],
    }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_invalid");
  assert.equal(snapshot.reality, "UNKNOWN");
});

test("a fresh working event projects a visible object and motion from its kind", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([workingEvent({ observedAt })], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 2_000,
  });

  assert.equal(snapshot.mode, "working");
  assert.equal(snapshot.motion, true);
  assert.equal(snapshot.title, "正在交叉核对");
  assert.equal(snapshot.stepLabel, "可见步骤 3/4");
  assert.equal(snapshot.preview.title, "APU 入口 · 算例剖面");
  assert.equal(snapshot.reasonCode, "observed");
  assert.equal(snapshot.reality, "REAL");
});

test("a stale active event becomes unknown and cannot keep animation alive", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([workingEvent({ observedAt })], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 31_000,
    staleAfterMs: 30_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.title, "等待可靠心跳");
  assert.equal(snapshot.reasonCode, "observation_stale");
  assert.equal(snapshot.preview.title, "APU 入口 · 算例剖面");
  assert.equal(snapshot.source, "control-kernel");
  assert.equal(snapshot.reality, "REAL");
});

test("one execution epoch cannot switch between REAL and MOCK observations", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt }),
    workingEvent({
      observedAt,
      eventId: "observer-cfd-mock-4",
      sequence: 4,
      reality: "MOCK",
      evidenceRefs: ["reality-witness:MOCK:witness-cfd-mock-4"],
    }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_reality_conflict");
  assert.equal(snapshot.reality, "UNKNOWN");
});

test("conflicting events at the same sequence fail closed instead of choosing a story", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt }),
    workingEvent({
      observedAt,
      eventId: "observer-cfd-conflict",
      title: "已经完成全部检查",
    }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_sequence_conflict");
});

test("an event from another execution epoch never animates the current task", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt, executionEpoch: "epoch-6" }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_identity_mismatch");
});

test("an active event too far in the future is not treated as a live heartbeat", () => {
  const observedAt = "2026-07-23T05:00:10.000Z";
  const snapshot = projectObserverEvents([workingEvent({ observedAt })], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse("2026-07-23T05:00:00.000Z"),
    maxFutureSkewMs: 5_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_clock_invalid");
  assert.equal(snapshot.source, "control-kernel");
});

test("an event cannot directly command animation or report percentage progress", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const context = {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  };

  const motionSnapshot = projectObserverEvents([
    workingEvent({ observedAt, motion: true }),
  ], context);
  const percentageSnapshot = projectObserverEvents([
    workingEvent({ observedAt, step: { current: 3, total: 4, label: "75% 完成" } }),
  ], context);

  assert.equal(motionSnapshot.reasonCode, "observation_invalid");
  assert.equal(motionSnapshot.motion, false);
  assert.equal(percentageSnapshot.reasonCode, "observation_invalid");
  assert.equal(percentageSnapshot.motion, false);
});

test("out-of-order delivery keeps the highest sequence and terminal kinds stay settled", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({
      observedAt,
      eventId: "observer-cfd-4",
      sequence: 4,
      kind: "attention",
      action: "hold",
      title: "结果已降级为建议",
      detail: "缺少任务工况依据，不能进入交付。",
      step: { current: 4, total: 4, label: "等待补充依据" },
    }),
    workingEvent({ observedAt, sequence: 3 }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.eventId, "observer-cfd-4");
  assert.equal(snapshot.mode, "attention");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.stepLabel, "等待补充依据");
});

test("a byte-order-only replay of the same event is idempotent", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const original = workingEvent({ observedAt });
  const reordered = Object.fromEntries(Object.entries(original).reverse());
  const snapshot = projectObserverEvents([original, reordered], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "working");
  assert.equal(snapshot.reasonCode, "observed");
  assert.equal(snapshot.eventId, "observer-cfd-3");
});

test("one event id cannot be rewritten at a later sequence", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt }),
    workingEvent({
      observedAt,
      sequence: 4,
      title: "已经完成全部检查",
    }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_event_id_conflict");
});

test("a working kind cannot carry a terminal action glyph", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt, action: "stop" }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_invalid");
});

test("an active observation without an evidence reference cannot appear as work", () => {
  const observedAt = "2026-07-23T05:00:00.000Z";
  const snapshot = projectObserverEvents([
    workingEvent({ observedAt, evidenceRefs: [] }),
  ], {
    expectedTaskId: "task-cfd-042",
    expectedRevision: "rev-1",
    expectedEpoch: "epoch-7",
    nowMs: Date.parse(observedAt) + 1_000,
  });

  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
  assert.equal(snapshot.reasonCode, "observation_invalid");
});
