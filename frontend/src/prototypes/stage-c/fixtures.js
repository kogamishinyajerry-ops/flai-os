// Stage C 原型合成夹具（SYNTHETIC ONLY）。
// 只构造符合 observer-contract v2 的合成观察事件，经 projectObserverEvents
// 投影出快照驱动 UI；不连接任何真实后端，不证明任何真实执行。
import {
  OBSERVER_CONTRACT_VERSION,
  projectObserverEvents,
} from "./observer-contract.js";

const SOURCE = "synthetic-fixture";
const BASE_TIME = Date.parse("2026-07-24T06:00:00.000Z");
const sha = (ch) => `${ch}`.repeat(64);

export const FIXTURE_SCENARIOS = Object.freeze({
  docx: {
    label: "文档整理",
    goal: "把本周项目记录整理成可印发的周报文档",
    object: "周报草稿.docx",
    runAction: "rewrite",
    runKind: "working",
    runStepLabel: "生成可逆文档草稿",
    preview: {
      kind: "docx-draft",
      title: "周报草稿.docx（可逆稿）",
      caption: "文档 · internal · 18 432 B",
      primary: `SHA-256 ${sha("a").slice(0, 12)}…`,
      secondary: "只读对象元数据；内容结论仍须经过产物、依据与交付门核验。",
    },
  },
  meeting: {
    label: "会议纪要",
    goal: "汇总评审会议纪要并提取行动项与负责人",
    object: "评审纪要-0717.md",
    runAction: "map",
    runKind: "working",
    runStepLabel: "整理行动项与负责人关系",
    preview: {
      kind: "meeting-notes",
      title: "评审纪要-0717.md（结构化稿）",
      caption: "纪要 · internal · 6 204 B",
      primary: `SHA-256 ${sha("b").slice(0, 12)}…`,
      secondary: "只读对象元数据；行动项归属仍须真人确认。",
    },
  },
  cfd: {
    label: "算例核验",
    goal: "核验 APU 进气道算例的边界条件与规则命中",
    object: "APU_inlet_case.zip",
    runAction: "inspect",
    runKind: "working",
    runStepLabel: "检查边界条件与网格质量",
    preview: {
      kind: "artifact-input",
      title: "APU_inlet_case.zip（输入对象）",
      caption: "算例输入 · internal · 192 937 984 B",
      primary: `SHA-256 ${sha("c").slice(0, 12)}…`,
      secondary: "只读对象元数据；内容结论仍须经过产物、依据与交付门核验。",
    },
  },
});

export const FIXTURE_STATES = Object.freeze([
  "running",
  "validating",
  "waiting_review",
  "completed",
  "failed",
  "cancelled",
  "evidence-missing",
  "permission-denied",
  "unknown",
  "stale",
]);

// 工作项要求的九个验证状态（validating 为额外交互状态，不在九态矩阵内）。
export const REQUIRED_STATES = Object.freeze([
  "running",
  "waiting_review",
  "completed",
  "failed",
  "cancelled",
  "evidence-missing",
  "permission-denied",
  "unknown",
  "stale",
]);

// REAL / MOCK / TEST 形态可通过 `${scene}:${state}@${reality}` 显式取 fixture；
// UNKNOWN 形态由 evidence-missing / unknown / stale 的 fail-closed 分支给出。
export const FIXTURE_REALITIES = Object.freeze(["REAL", "MOCK", "TEST"]);

const STATE_COPY = Object.freeze({
  waiting_review: {
    kind: "attention",
    action: "hold",
    title: "可逆工作已完成，等待真人检查",
    detail: "系统不会把待评审草稿自动升级为正式交付。",
    step: { current: 4, total: 4, label: "等待真人检查" },
  },
  completed: {
    kind: "preview",
    action: "render",
    title: "可查看已冻结的任务产物",
    detail: "任务终态与当前产物引用一致；正式签发仍只由真人完成。",
    step: { current: 4, total: 4, label: "任务终态已记录" },
  },
  failed: {
    kind: "failed",
    action: "stop",
    title: "执行已经失败并停止",
    detail: "失败事实被保留；界面不会播放仍在执行的动画。",
    step: { current: 3, total: 4, label: "失败事实已冻结" },
  },
  cancelled: {
    kind: "stopped",
    action: "stop",
    title: "执行已经停止",
    detail: "取消事实被保留；已有只读对象仍可用于检查。",
    step: { current: 3, total: 4, label: "终止事实已冻结" },
  },
  "permission-denied": {
    kind: "denied",
    action: "deny",
    title: "执行被权限边界拒绝",
    detail: "控制内核记录了对当前工作对象的拒绝事实；界面保持静止。",
    step: { current: 1, total: 4, label: "权限边界已记录" },
  },
});

function evidenceRefs(reality, scene, seq) {
  return [
    `read-snapshot:sha256:${sha("d")}`,
    `task-event:evt-${scene}-${seq}@ordinal:${seq}`,
    `execution:run-${scene}-1@observation:${seq}`,
    `backend:${scene}-synthetic-backend@adapter:fixture-adapter:1`,
    `reality-witness:${reality}:witness-run-${scene}-1-${reality.toLowerCase()}`,
    `artifact:file-${scene}-1@sha256:${sha("e")}`,
  ];
}

function makeEvent(scene, state, { reality = "REAL", seq = 17, observedAt } = {}) {
  const scenario = FIXTURE_SCENARIOS[scene];
  const copy = state === "running"
    ? {
        kind: scenario.runKind,
        action: scenario.runAction,
        title: `正在处理受控工作对象：${scenario.object}`,
        detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
        step: { current: 2, total: 4, label: scenario.runStepLabel },
      }
    : state === "validating"
      ? {
          kind: "validating",
          action: "guard",
          title: "正在核验执行边界与规则命中",
          detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
          step: { current: 3, total: 4, label: "核对规则与对象" },
        }
      : STATE_COPY[state];
  return {
    contractVersion: OBSERVER_CONTRACT_VERSION,
    source: SOURCE,
    eventId: `observer:run-${scene}-1:${seq}`,
    taskId: `task-${scene}-001`,
    taskRevision: "task-revision-3",
    executionEpoch: "execution-epoch-2",
    sequence: seq,
    observedAt: observedAt || new Date(BASE_TIME + seq * 1000).toISOString(),
    reality,
    kind: copy.kind,
    action: copy.action,
    title: copy.title,
    detail: copy.detail,
    step: { ...copy.step },
    preview: { ...scenario.preview },
    evidenceRefs: evidenceRefs(reality, scene, seq),
  };
}

function contextFor(scene, nowMs) {
  return {
    expectedSource: SOURCE,
    expectedTaskId: `task-${scene}-001`,
    expectedRevision: "task-revision-3",
    expectedEpoch: "execution-epoch-2",
    nowMs,
  };
}

function buildEvents(scene, state, realityOverride) {
  if (state === "unknown") return { events: [], nowMs: BASE_TIME + 60_000 };
  if (state === "evidence-missing") {
    const bad = makeEvent(scene, "running", { reality: realityOverride || "REAL" });
    bad.evidenceRefs = [];
    return { events: [bad], nowMs: BASE_TIME + 30_000 };
  }
  if (state === "stale") {
    const old = makeEvent(scene, "running", {
      reality: realityOverride || "REAL",
      observedAt: new Date(BASE_TIME - 120_000).toISOString(),
    });
    return { events: [old], nowMs: BASE_TIME };
  }
  const reality = realityOverride || (state === "permission-denied" ? "MOCK" : "REAL");
  return { events: [makeEvent(scene, state, { reality })], nowMs: BASE_TIME + 30_000 };
}

export function getFixtureSnapshot(key) {
  const [scene, state, reality] = key.split(/[:@]/);
  if (!FIXTURE_SCENARIOS[scene] || !FIXTURE_STATES.includes(state)) {
    throw new Error(`unknown fixture: ${key}`);
  }
  if (reality !== undefined && !FIXTURE_REALITIES.includes(reality)) {
    throw new Error(`unknown fixture reality: ${key}`);
  }
  const { events, nowMs } = buildEvents(scene, state, reality);
  return projectObserverEvents(events, contextFor(scene, nowMs));
}

export function getFixture(key) {
  const [scene, state] = key.split(/[:@]/);
  return {
    key,
    scene,
    state,
    scenario: FIXTURE_SCENARIOS[scene],
    snapshot: getFixtureSnapshot(key),
  };
}

export function listFixtureKeys() {
  const keys = [];
  for (const scene of Object.keys(FIXTURE_SCENARIOS)) {
    for (const state of FIXTURE_STATES) keys.push(`${scene}:${state}`);
  }
  return keys;
}
