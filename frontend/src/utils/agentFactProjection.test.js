import assert from "node:assert/strict";
import test from "node:test";

import {
  advanceAgentFactRuntimeFloors,
  confirmAgentFactResnapshot,
  evaluateAgentFactContinuity,
  factsForAgentIds,
  groupMonitorTasks,
  summarizeAgentFacts,
  validateAgentFactSnapshot,
  waitPresentation,
} from "./agentFactProjection.js";

const NOW = Date.parse("2026-07-20T04:00:00.000Z");

function emptySnapshot(overrides = {}) {
  return {
    schemaVersion: "agent_fact_projection.v1",
    conversationId: "conv-001",
    generatedAt: "2026-07-20T03:59:00.000Z",
    taskCount: 0,
    tasksTruncated: false,
    tasks: [],
    ...overrides,
  };
}

function taskFact(overrides = {}) {
  return {
    taskId: "task-001",
    agentId: "solver_agent",
    status: "running",
    createdAt: "2026-07-20T03:55:00.000Z",
    updatedAt: "2026-07-20T03:59:00.000Z",
    phase: "working",
    dependencies: [],
    wait: null,
    handoffs: [],
    signoff: {
      state: "pending_result",
      requestedFrom: null,
      reviewer: null,
      decidedAt: null,
    },
    runtime: {
      adapter: "jerryagent_sidecar",
      reported: true,
      reason: "reported",
      sourceEpoch: "a".repeat(64),
      revision: 7,
      status: "running",
      wait: null,
      delegationHold: null,
      subagentCount: 1,
      subagentsTruncated: false,
      subagents: [{
        ordinal: 1,
        status: "running",
        retryOfOrdinal: null,
        createdAt: "2026-07-20T03:56:00.000Z",
        updatedAt: "2026-07-20T03:59:00.000Z",
      }],
    },
    ...overrides,
  };
}

function subagentFact(ordinal, overrides = {}) {
  return {
    ordinal,
    status: "running",
    retryOfOrdinal: null,
    createdAt: "2026-07-20T03:56:00.000Z",
    updatedAt: "2026-07-20T03:59:00.000Z",
    ...overrides,
  };
}

function unavailableRuntime(overrides = {}) {
  return {
    ...taskFact().runtime,
    reported: false,
    reason: "unreachable",
    sourceEpoch: null,
    revision: null,
    status: null,
    wait: null,
    delegationHold: null,
    subagentCount: 0,
    subagentsTruncated: false,
    subagents: [],
    ...overrides,
  };
}

function snapshotWith(tasks) {
  return emptySnapshot({ taskCount: tasks.length, tasks });
}

test("validateAgentFactSnapshot accepts the exact empty v1 envelope", () => {
  const result = validateAgentFactSnapshot(emptySnapshot());

  assert.equal(result.valid, true);
  assert.equal(result.snapshot.conversationId, "conv-001");
});

test("validateAgentFactSnapshot fails closed for an unknown version", () => {
  const result = validateAgentFactSnapshot(emptySnapshot({ schemaVersion: "agent_fact_projection.v2" }));

  assert.deepEqual(result, {
    valid: false,
    renderable: false,
    error: "不支持的 Agent 事实版本：agent_fact_projection.v2",
  });
});

test("validateAgentFactSnapshot rejects inconsistent counts instead of inventing omitted tasks", () => {
  const result = validateAgentFactSnapshot(emptySnapshot({ taskCount: 2 }));

  assert.equal(result.valid, false);
  assert.equal(result.renderable, false);
  assert.match(result.error, /taskCount/);
});

test("validateAgentFactSnapshot accepts the complete TaskFact contract", () => {
  const result = validateAgentFactSnapshot(snapshotWith([taskFact()]));

  assert.equal(result.valid, true);
});

test("validateAgentFactSnapshot accepts canonical +00:00 UTC timestamps", () => {
  const plusUtc = JSON.parse(JSON.stringify(snapshotWith([taskFact()])).replaceAll("Z\"", "+00:00\""));

  const result = validateAgentFactSnapshot(plusUtc);

  assert.equal(result.valid, true);
});

test("validateAgentFactSnapshot rejects unknown task and nested runtime enums", () => {
  const badTaskStatus = validateAgentFactSnapshot(snapshotWith([taskFact({ status: "done" })]));
  const badRuntimeStatus = validateAgentFactSnapshot(snapshotWith([
    taskFact({ runtime: { ...taskFact().runtime, status: "thinking" } }),
  ]));

  assert.equal(badTaskStatus.valid, false);
  assert.match(badTaskStatus.error, /tasks\[0\]\.status/);
  assert.equal(badRuntimeStatus.valid, false);
  assert.match(badRuntimeStatus.error, /tasks\[0\]\.runtime\.status/);
});

test("validateAgentFactSnapshot rejects missing nested facts and extra raw detail", () => {
  const missingWait = taskFact();
  delete missingWait.wait;
  const leakedDetail = taskFact({
    runtime: {
      ...taskFact().runtime,
      subagents: [{ ...taskFact().runtime.subagents[0], objective: "should never cross projection" }],
    },
  });

  const missingResult = validateAgentFactSnapshot(snapshotWith([missingWait]));
  const leakResult = validateAgentFactSnapshot(snapshotWith([leakedDetail]));

  assert.equal(missingResult.valid, false);
  assert.match(missingResult.error, /tasks\[0\]\.wait/);
  assert.equal(leakResult.valid, false);
  assert.match(leakResult.error, /subagents\[0\].*字段/);
});

test("validateAgentFactSnapshot rejects unavailable runtime fields that pretend to be reported", () => {
  const runtime = {
    ...taskFact().runtime,
    reported: false,
    reason: "unreachable",
  };

  const result = validateAgentFactSnapshot(snapshotWith([taskFact({ runtime })]));

  assert.equal(result.valid, false);
  assert.match(result.error, /reported=false/);
});

test("validateAgentFactSnapshot rejects facts inside an unavailable runtime envelope", () => {
  const runtimeWait = {
    kind: "subagent_completion",
    since: "2026-07-20T03:58:00.000Z",
    subjectOrdinal: null,
    pendingCount: 1,
    continueWhen: "subagents_terminal",
  };
  const hold = {
    phase: "armed",
    requestedAt: "2026-07-20T03:58:00.000Z",
    resolvedAt: null,
    satisfiedByOrdinal: null,
  };
  const variants = [
    unavailableRuntime({ wait: runtimeWait }),
    unavailableRuntime({ delegationHold: hold }),
    unavailableRuntime({ subagentCount: 1, subagents: [subagentFact(1)] }),
  ];

  for (const runtime of variants) {
    const result = validateAgentFactSnapshot(snapshotWith([taskFact({ runtime })]));
    assert.equal(result.valid, false);
    assert.match(result.error, /reported=false/);
  }
});

test("validateAgentFactSnapshot binds native and reported runtime facts to their only legal adapters", () => {
  const nativeUnavailable = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: unavailableRuntime({ adapter: "native_python", reason: "disabled" }),
  })]));
  const nativeReported = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, adapter: "native_python" },
  })]));

  assert.equal(nativeUnavailable.valid, false);
  assert.match(nativeUnavailable.error, /native_python/);
  assert.equal(nativeReported.valid, false);
  assert.match(nativeReported.error, /jerryagent_sidecar/);
});

test("validateAgentFactSnapshot accepts only an exact 64-row truncated subagent window", () => {
  const sixtyFour = Array.from({ length: 64 }, (_, index) => subagentFact(index + 1));
  const valid = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: {
      ...taskFact().runtime,
      subagentCount: 65,
      subagentsTruncated: true,
      subagents: sixtyFour,
    },
  })]));
  const falseTruncation = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: {
      ...taskFact().runtime,
      subagentCount: 64,
      subagentsTruncated: true,
      subagents: sixtyFour,
    },
  })]));
  const shortWindow = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: {
      ...taskFact().runtime,
      subagentCount: 65,
      subagentsTruncated: true,
      subagents: sixtyFour.slice(0, 63),
    },
  })]));

  assert.equal(valid.valid, true);
  assert.equal(falseTruncation.valid, false);
  assert.equal(shortWindow.valid, false);
});

test("validateAgentFactSnapshot requires continuous ordinals and backward-only retry lineage", () => {
  const skippedOrdinal = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: {
      ...taskFact().runtime,
      subagentCount: 2,
      subagents: [subagentFact(1), subagentFact(3)],
    },
  })]));
  const selfRetry = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: {
      ...taskFact().runtime,
      subagentCount: 2,
      subagents: [subagentFact(1), subagentFact(2, { retryOfOrdinal: 2 })],
    },
  })]));

  assert.equal(skippedOrdinal.valid, false);
  assert.match(skippedOrdinal.error, /连续/);
  assert.equal(selfRetry.valid, false);
  assert.match(selfRetry.error, /retryOfOrdinal/);
});

test("validateAgentFactSnapshot bounds wait and hold ordinals by the reported subagent count", () => {
  const wait = {
    kind: "subagent_completion",
    since: "2026-07-20T03:58:00.000Z",
    subjectOrdinal: 2,
    pendingCount: 1,
    continueWhen: "subagents_terminal",
  };
  const hold = {
    phase: "satisfied",
    requestedAt: "2026-07-20T03:57:00.000Z",
    resolvedAt: "2026-07-20T03:58:00.000Z",
    satisfiedByOrdinal: 2,
  };
  const badWait = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, wait },
  })]));
  const badHold = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, delegationHold: hold },
  })]));

  assert.equal(badWait.valid, false);
  assert.match(badWait.error, /subjectOrdinal/);
  assert.equal(badHold.valid, false);
  assert.match(badHold.error, /satisfiedByOrdinal/);
});

test("validateAgentFactSnapshot rejects impossible runtime wait combinations", () => {
  const approvalWait = {
    kind: "runtime_approval",
    since: "2026-07-20T03:58:00.000Z",
    subjectOrdinal: null,
    pendingCount: 1,
    continueWhen: "approval_resolved",
  };
  const zeroDependencyWait = {
    kind: "dependency",
    since: "2026-07-20T03:58:00.000Z",
    subjectTaskId: null,
    subjectAgentId: null,
    subjectOrdinal: null,
    pendingCount: 0,
    continueWhen: "dependency_gate_satisfied",
  };
  const terminalApproval = validateAgentFactSnapshot(snapshotWith([taskFact({
    status: "completed",
    phase: "settled",
    runtime: { ...taskFact().runtime, status: "completed", wait: approvalWait },
  })]));
  const runningApproval = validateAgentFactSnapshot(snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, status: "running", wait: approvalWait },
  })]));
  const zeroWait = validateAgentFactSnapshot(snapshotWith([taskFact({
    status: "created",
    phase: "waiting_upstream",
    wait: zeroDependencyWait,
  })]));

  assert.equal(terminalApproval.valid, false);
  assert.equal(runningApproval.valid, false);
  assert.equal(zeroWait.valid, false);
  assert.match(terminalApproval.error, /终态|runtime_approval/);
  assert.match(runningApproval.error, /runtime_approval/);
  assert.match(zeroWait.error, /pendingCount/);
});

test("validateAgentFactSnapshot binds task status to its only legal phase and signoff state", () => {
  const wrongPhase = validateAgentFactSnapshot(snapshotWith([
    taskFact({ status: "running", phase: "settled" }),
  ]));
  const wrongAwaitingSignoff = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      status: "waiting_review",
      phase: "awaiting_signoff",
      wait: {
        kind: "human_signoff",
        since: "2026-07-20T03:59:00.000Z",
        subjectTaskId: null,
        subjectAgentId: null,
        subjectOrdinal: null,
        pendingCount: 1,
        continueWhen: "human_decision_recorded",
      },
    }),
  ]));
  const falseApproval = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      signoff: {
        state: "approved",
        requestedFrom: "reviewer",
        reviewer: "Reviewer",
        decidedAt: "2026-07-20T03:59:00.000Z",
      },
    }),
  ]));

  assert.equal(wrongPhase.valid, false);
  assert.match(wrongPhase.error, /phase/);
  assert.equal(wrongAwaitingSignoff.valid, false);
  assert.match(wrongAwaitingSignoff.error, /signoff/);
  assert.equal(falseApproval.valid, false);
  assert.match(falseApproval.error, /approved/);
});

test("validateAgentFactSnapshot binds dependency waits to the unresolved dependency set", () => {
  const dependency = {
    taskId: "task-upstream",
    agentId: "mesh_agent",
    status: "running",
    gate: "pending",
  };
  const baseWait = {
    kind: "dependency",
    since: "2026-07-20T03:58:00.000Z",
    subjectTaskId: dependency.taskId,
    subjectAgentId: dependency.agentId,
    subjectOrdinal: null,
    pendingCount: 1,
    continueWhen: "dependency_gate_satisfied",
  };
  const valid = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      status: "created",
      phase: "waiting_upstream",
      dependencies: [dependency],
      wait: baseWait,
      runtime: unavailableRuntime({ reason: "not_found" }),
    }),
  ]));
  const wrongCount = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      status: "created",
      phase: "waiting_upstream",
      dependencies: [dependency],
      wait: { ...baseWait, pendingCount: 2 },
      runtime: unavailableRuntime({ reason: "not_found" }),
    }),
  ]));
  const wrongSubject = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      status: "created",
      phase: "waiting_upstream",
      dependencies: [dependency],
      wait: { ...baseWait, subjectTaskId: "another-task" },
      runtime: unavailableRuntime({ reason: "not_found" }),
    }),
  ]));

  assert.equal(valid.valid, true);
  assert.equal(wrongCount.valid, false);
  assert.match(wrongCount.error, /pendingCount/);
  assert.equal(wrongSubject.valid, false);
  assert.match(wrongSubject.error, /subject/);
});

test("validateAgentFactSnapshot requires task runtime waits to be the exact projected runtime wait", () => {
  const runtimeWait = {
    kind: "subagent_completion",
    since: "2026-07-20T03:58:00.000Z",
    subjectOrdinal: 1,
    pendingCount: 1,
    continueWhen: "subagents_terminal",
  };
  const taskWait = {
    ...runtimeWait,
    subjectTaskId: null,
    subjectAgentId: null,
  };
  const valid = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      wait: taskWait,
      runtime: { ...taskFact().runtime, wait: runtimeWait },
    }),
  ]));
  const omitted = validateAgentFactSnapshot(snapshotWith([
    taskFact({ runtime: { ...taskFact().runtime, wait: runtimeWait } }),
  ]));
  const mutated = validateAgentFactSnapshot(snapshotWith([
    taskFact({
      wait: { ...taskWait, pendingCount: 2 },
      runtime: { ...taskFact().runtime, wait: runtimeWait },
    }),
  ]));

  assert.equal(valid.valid, true);
  assert.equal(omitted.valid, false);
  assert.match(omitted.error, /runtime wait/);
  assert.equal(mutated.valid, false);
  assert.match(mutated.error, /runtime wait/);
});

test("validateAgentFactSnapshot enforces delegation hold phase and timestamp consistency", () => {
  const base = {
    phase: "armed",
    requestedAt: "2026-07-20T03:58:00.000Z",
    resolvedAt: null,
    satisfiedByOrdinal: null,
  };
  const invalidHolds = [
    { ...base, resolvedAt: "2026-07-20T03:59:00.000Z" },
    { ...base, phase: "released" },
    { ...base, phase: "released", resolvedAt: "2026-07-20T03:59:00.000Z", satisfiedByOrdinal: 1 },
    { ...base, phase: "satisfied", resolvedAt: "2026-07-20T03:59:00.000Z" },
    { ...base, phase: "released", resolvedAt: "2026-07-20T03:57:00.000Z" },
  ];

  for (const delegationHold of invalidHolds) {
    const result = validateAgentFactSnapshot(snapshotWith([taskFact({
      runtime: { ...taskFact().runtime, delegationHold },
    })]));
    assert.equal(result.valid, false);
    assert.match(result.error, /delegationHold/);
  }
});

test("validateAgentFactSnapshot requires a real omission when tasksTruncated is true", () => {
  const result = validateAgentFactSnapshot(emptySnapshot({ tasksTruncated: true }));

  assert.equal(result.valid, false);
  assert.match(result.error, /tasksTruncated/);
});

test("invalid snapshots remain explicitly unrenderable through every projection", () => {
  const invalid = emptySnapshot({ generatedAt: "not-a-time" });

  for (const result of [
    factsForAgentIds(invalid, ["agent-a"]),
    summarizeAgentFacts(invalid, ["agent-a"], NOW),
    groupMonitorTasks(invalid),
  ]) {
    assert.equal(result.valid, false);
    assert.equal(result.renderable, false);
    assert.ok(result.error);
  }
});

test("factsForAgentIds filters only requested Agent ids", () => {
  const snapshot = snapshotWith([
    taskFact(),
    taskFact({ taskId: "task-002", agentId: "review_agent" }),
  ]);

  const result = factsForAgentIds(snapshot, ["review_agent"]);

  assert.equal(result.valid, true);
  assert.deepEqual(result.tasks.map((task) => task.taskId), ["task-002"]);
});

test("summarizeAgentFacts gives failures priority and reports task and subagent counts", () => {
  const snapshot = snapshotWith([
    taskFact(),
    taskFact({
      taskId: "task-002",
      agentId: "review_agent",
      status: "failed",
      phase: "failed",
      runtime: {
        ...taskFact().runtime,
        status: "failed",
        subagentCount: 0,
        subagents: [],
      },
    }),
  ]);

  const result = summarizeAgentFacts(snapshot, null, NOW);

  assert.equal(result.state, "failure");
  assert.equal(result.headline, "1 个任务失败");
  assert.equal(result.taskCount, 2);
  assert.equal(result.subagentCount, 1);
  assert.equal(result.reportedRuntimeCount, 2);
  assert.equal(result.unavailableRuntimeCount, 0);
});

test("summarizeAgentFacts does not turn an unavailable runtime envelope into a confirmed zero", () => {
  const unavailableRuntime = {
    ...taskFact().runtime,
    reported: false,
    reason: "unreachable",
    sourceEpoch: null,
    revision: null,
    status: null,
    wait: null,
    delegationHold: null,
    subagentCount: 0,
    subagents: [],
  };

  const result = summarizeAgentFacts(snapshotWith([
    taskFact(),
    taskFact({ taskId: "task-002", runtime: unavailableRuntime }),
  ]), null, NOW);

  assert.equal(result.subagentCount, 1);
  assert.equal(result.reportedRuntimeCount, 1);
  assert.equal(result.unavailableRuntimeCount, 1);
});

test("summarizeAgentFacts keeps queued neutral and native runtime not-applicable", () => {
  const nativeRuntime = unavailableRuntime({
    adapter: "native_python",
    reason: "not_applicable",
  });
  const result = summarizeAgentFacts(snapshotWith([
    taskFact({ status: "queued", phase: "queued", runtime: nativeRuntime }),
  ]), null, NOW);

  assert.equal(result.state, "queued");
  assert.equal(result.headline, "1 个任务待运行");
  assert.equal(result.workingCount, 0);
  assert.equal(result.queuedCount, 1);
  assert.equal(result.applicableRuntimeCount, 0);
  assert.equal(result.unavailableRuntimeCount, 0);
  assert.equal(result.notApplicableRuntimeCount, 1);
});

test("summarizeAgentFacts discloses a truncated recent window without claiming the whole conversation", () => {
  const result = summarizeAgentFacts(emptySnapshot({
    taskCount: 101,
    tasksTruncated: true,
    tasks: [taskFact({ status: "completed", phase: "settled" })],
  }), null, NOW);

  assert.equal(result.tasksTruncated, true);
  assert.equal(result.taskCount, 1);
  assert.equal(result.totalTaskCount, 101);
  assert.equal(result.headline, "仅显示最近 1 / 共 101 个任务");
  assert.doesNotMatch(result.headline, /^101 个任务已落定$/);
});

test("groupMonitorTasks separates current, waiting and settled without losing failed facts", () => {
  const waiting = taskFact({
    taskId: "task-wait",
    status: "created",
    phase: "waiting_upstream",
    dependencies: [{
      taskId: "task-upstream",
      agentId: "mesh_agent",
      status: "running",
      gate: "pending",
    }],
    wait: {
      kind: "dependency",
      since: "2026-07-20T03:58:00.000Z",
      subjectTaskId: "task-upstream",
      subjectAgentId: "mesh_agent",
      subjectOrdinal: null,
      pendingCount: 1,
      continueWhen: "dependency_gate_satisfied",
    },
    runtime: {
      ...taskFact().runtime,
      reported: false,
      reason: "not_found",
      sourceEpoch: null,
      revision: null,
      status: null,
      subagentCount: 0,
      subagents: [],
    },
  });
  const failed = taskFact({
    taskId: "task-failed",
    status: "failed",
    phase: "failed",
    runtime: { ...taskFact().runtime, status: "failed" },
  });

  const result = groupMonitorTasks(snapshotWith([taskFact(), waiting, failed]));

  assert.deepEqual(result.current.map((task) => task.taskId), ["task-001"]);
  assert.deepEqual(result.waiting.map((task) => task.taskId), ["task-wait"]);
  assert.deepEqual(result.settled.map((task) => task.taskId), ["task-failed"]);
});

test("waitPresentation makes waiting, rejected and human-approved truth visually distinct", () => {
  const wait = {
    kind: "dependency",
    since: "2026-07-20T03:58:00.000Z",
    subjectTaskId: "task-upstream",
    subjectAgentId: "mesh_agent",
    subjectOrdinal: null,
    pendingCount: 1,
    continueWhen: "dependency_gate_satisfied",
  };

  assert.deepEqual(waitPresentation(wait, null), {
    tone: "waiting",
    label: "等待上游依赖",
    detail: "等待 mesh_agent（task-upstream）",
    actor: "mesh_agent",
    continueWhen: "依赖门满足后继续",
    signed: false,
  });
  assert.equal(waitPresentation(null, {
    state: "approved", requestedFrom: "王工", reviewer: "王工", decidedAt: "2026-07-20T03:59:00.000Z",
  }).tone, "signed");
  assert.equal(waitPresentation(null, {
    state: "rejected", requestedFrom: "王工", reviewer: "王工", decidedAt: "2026-07-20T03:59:00.000Z",
  }).tone, "failure");
  assert.deepEqual(waitPresentation(null, {
    state: "awaiting_human", requestedFrom: "李工", reviewer: null, decidedAt: null,
  }), {
    tone: "waiting",
    label: "等待 李工 签收",
    detail: "点名签收对象：李工",
    actor: "李工",
    continueWhen: "人工决定记录后继续",
    signed: false,
  });
});

test("waitPresentation never upgrades missing wait or signoff facts", () => {
  assert.deepEqual(waitPresentation(null, null), {
    tone: "neutral",
    label: "无等待事实",
    detail: "",
    actor: "",
    continueWhen: "",
    signed: false,
  });
});

test("waitPresentation supplies a closed-class object when runtime wait has no subject", () => {
  const result = waitPresentation({
    kind: "runtime_approval",
    since: "2026-07-20T03:58:00.000Z",
    subjectTaskId: null,
    subjectAgentId: null,
    subjectOrdinal: null,
    pendingCount: 2,
    continueWhen: "approval_resolved",
  }, null);

  assert.equal(result.actor, "运行批准");
  assert.equal(result.detail, "运行批准 · 尚有 2 项未落定");
  assert.equal(result.continueWhen, "运行批准落定后继续");
});

test("evaluateAgentFactContinuity accepts the first strict snapshot", () => {
  assert.deepEqual(evaluateAgentFactContinuity(null, snapshotWith([taskFact()])), {
    action: "accept",
    reason: null,
  });
});

test("evaluateAgentFactContinuity resnapshots invalid next payloads", () => {
  const result = evaluateAgentFactContinuity(
    snapshotWith([taskFact()]),
    emptySnapshot({ schemaVersion: "agent_fact_projection.v2" }),
  );

  assert.deepEqual(result, { action: "resnapshot", reason: "next_snapshot_invalid" });
});

test("evaluateAgentFactContinuity resnapshots runtime epoch changes and revision regressions", () => {
  const previous = snapshotWith([taskFact()]);
  const epochChanged = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 8 },
  })]);
  const regressed = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 6 },
  })]);

  assert.deepEqual(evaluateAgentFactContinuity(previous, epochChanged), {
    action: "resnapshot",
    reason: "runtime_source_epoch_changed",
  });
  assert.deepEqual(evaluateAgentFactContinuity(previous, regressed), {
    action: "resnapshot",
    reason: "runtime_revision_regressed",
  });
});

test("evaluateAgentFactContinuity rejects same-revision runtime mutation but accepts a higher revision", () => {
  const previous = snapshotWith([taskFact()]);
  const mutated = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, status: "completed" },
  })]);
  const advanced = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 8, status: "completed" },
  })]);

  assert.deepEqual(evaluateAgentFactContinuity(previous, mutated), {
    action: "resnapshot",
    reason: "runtime_changed_without_revision",
  });
  assert.deepEqual(evaluateAgentFactContinuity(previous, advanced), {
    action: "accept",
    reason: null,
  });
});

test("confirmAgentFactResnapshot accepts one stable new epoch without looping against the old epoch", () => {
  const previous = snapshotWith([taskFact()]);
  const suspect = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 1 },
  })]);
  const replacement = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 2 },
  })]);

  assert.deepEqual(confirmAgentFactResnapshot(
    previous,
    suspect,
    replacement,
    "runtime_source_epoch_changed",
  ), { action: "accept", reason: null });
});

test("confirmAgentFactResnapshot rejects a second epoch flip and repeated same-epoch regression", () => {
  const previous = snapshotWith([taskFact()]);
  const epochSuspect = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 1 },
  })]);
  const epochFlippedAgain = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, sourceEpoch: "c".repeat(64), revision: 1 },
  })]);
  const regressed = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 6 },
  })]);

  assert.deepEqual(confirmAgentFactResnapshot(
    previous,
    epochSuspect,
    epochFlippedAgain,
    "runtime_source_epoch_changed",
  ), { action: "resnapshot", reason: "runtime_source_epoch_changed" });
  assert.deepEqual(confirmAgentFactResnapshot(
    previous,
    regressed,
    regressed,
    "runtime_revision_regressed",
  ), { action: "resnapshot", reason: "runtime_revision_regressed" });
});

test("an epoch change in one task cannot mask another task revision regression", () => {
  const previous = snapshotWith([
    taskFact({ taskId: "task-epoch" }),
    taskFact({ taskId: "task-regressed", runtime: { ...taskFact().runtime, revision: 10 } }),
  ]);
  const suspect = snapshotWith([
    taskFact({
      taskId: "task-epoch",
      runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 1 },
    }),
    taskFact({ taskId: "task-regressed", runtime: { ...taskFact().runtime, revision: 9 } }),
  ]);
  const replacement = snapshotWith([
    taskFact({
      taskId: "task-epoch",
      runtime: { ...taskFact().runtime, sourceEpoch: "b".repeat(64), revision: 2 },
    }),
    taskFact({ taskId: "task-regressed", runtime: { ...taskFact().runtime, revision: 9 } }),
  ]);

  assert.deepEqual(confirmAgentFactResnapshot(
    previous,
    suspect,
    replacement,
    "runtime_source_epoch_changed",
  ), { action: "resnapshot", reason: "runtime_revision_regressed" });
});

test("runtime revision floors survive an unavailable gap and remain bounded", () => {
  const revisionSeven = snapshotWith([taskFact()]);
  const unavailable = snapshotWith([taskFact({ runtime: unavailableRuntime() })]);
  const revisionSix = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 6 },
  })]);
  const revisionEight = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 8 },
  })]);

  let floors = advanceAgentFactRuntimeFloors(new Map(), revisionSeven, 2);
  floors = advanceAgentFactRuntimeFloors(floors, unavailable, 2);
  assert.equal(floors.get("task-001").revision, 7);
  assert.deepEqual(evaluateAgentFactContinuity(unavailable, revisionSix, floors), {
    action: "resnapshot",
    reason: "runtime_revision_regressed",
  });
  assert.deepEqual(evaluateAgentFactContinuity(unavailable, revisionEight, floors), {
    action: "accept",
    reason: null,
  });

  floors = advanceAgentFactRuntimeFloors(floors, snapshotWith([
    taskFact({ taskId: "task-002" }),
    taskFact({ taskId: "task-003" }),
  ]), 2);
  assert.deepEqual([...floors.keys()], ["task-002", "task-003"]);
});

test("forced resnapshot cannot confirm a regression hidden by an unavailable gap", () => {
  const revisionSeven = snapshotWith([taskFact()]);
  const unavailable = snapshotWith([taskFact({ runtime: unavailableRuntime() })]);
  const regressed = snapshotWith([taskFact({
    runtime: { ...taskFact().runtime, revision: 6 },
  })]);
  const floors = advanceAgentFactRuntimeFloors(new Map(), revisionSeven);

  assert.deepEqual(confirmAgentFactResnapshot(
    unavailable,
    regressed,
    regressed,
    "runtime_revision_regressed",
    floors,
  ), { action: "resnapshot", reason: "runtime_revision_regressed" });
});
