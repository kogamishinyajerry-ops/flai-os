// Workspace Shell 原型合成夹具（SYNTHETIC ONLY）。
// 只构造符合 observer-contract v2（只读 import，不分叉）的合成观察事件，
// 经 projectObserverEvents 投影快照驱动 UI；不连接任何真实后端，
// 不证明任何真实执行，所有工作流、对象、摘要与见证引用均为合成样例。
import {
  OBSERVER_CONTRACT_VERSION,
  projectObserverEvents,
} from "../stage-c/observer-contract.js";

const SOURCE = "synthetic-fixture";
const BASE_TIME = Date.parse("2026-07-24T06:00:00.000Z");
const sha = (ch) => `${ch}`.repeat(64);

// 三个合成黄金工作流。runKind/runAction 决定 running 态最新观察事件，
// 从而决定中央动作 glyph（见 workspace-view.js 的动作→glyph 映射）。
export const WORKFLOWS = Object.freeze({
  docx: {
    label: "报告润色",
    title: "润色气动周报并生成对照稿",
    goal: "把本周气动记录整理成可印发的周报，并保留逐段对照",
    object: "气动周报-草稿.docx",
    runKind: "working",
    runAction: "rewrite",
    runStepLabel: "生成可逆润色稿",
    artifact: {
      filename: "气动周报-润色稿.docx",
      digest: sha("a"),
      classification: "internal",
      rendererKind: "docx",
      bytes: 18_432,
    },
    witnessId: "witness-ws-docx-1",
  },
  meeting: {
    label: "纪要整理",
    title: "整理评审纪要并提取行动项",
    goal: "汇总评审会议录音稿，提取决议、行动项与负责人",
    object: "评审纪要-0717.md",
    runKind: "working",
    runAction: "inspect",
    runStepLabel: "检索发言段落与决议句",
    artifact: {
      filename: "评审纪要-行动项.md",
      digest: sha("b"),
      classification: "internal",
      rendererKind: "table",
      bytes: 6_204,
    },
    witnessId: "witness-ws-meeting-1",
  },
  cfd: {
    label: "算例体检",
    title: "体检 APU 进气道算例设置",
    goal: "核对边界条件、网格质量与规则命中，给出受控建议",
    object: "APU_inlet_case.zip",
    runKind: "validating",
    runAction: "guard",
    runStepLabel: "解析算例设置与规则",
    artifact: {
      filename: "APU_inlet-体检报告.html",
      digest: sha("c"),
      classification: "sensitive",
      rendererKind: "cfd",
      bytes: 92_160,
    },
    witnessId: "witness-ws-cfd-1",
  },
});

// 96 矩阵的八个观察状态。stale 是矩阵外的显式过期叠加态。
export const WORKSPACE_STATES = Object.freeze([
  "running",
  "waiting_review",
  "completed",
  "failed",
  "cancelled",
  "evidence-missing",
  "permission-denied",
  "observation-invalid",
]);
export const OVERLAY_STATES = Object.freeze(["stale"]);

// 四种请求显示形态。REAL/MOCK/TEST 是合法 execution reality；
// UNKNOWN 不是合法 reality，只是 UI 请求形态，一律 fail-closed 到观察缺口。
export const DISPLAY_FORMS = Object.freeze(["REAL", "MOCK", "TEST", "UNKNOWN"]);
export const LEGAL_REALITIES = Object.freeze(["REAL", "MOCK", "TEST"]);

// 每个状态的公开事实：终态/边界文案与公开原因码（不属于观察 fail-closed
// 原因码；观察缺口的原因码由 projector 给出并原样展示）。
const STATE_FACTS = Object.freeze({
  waiting_review: {
    kind: "attention",
    action: "hold",
    title: "可逆工作已完成，等待真人检查",
    detail: "对照稿与证据摘要已就绪；系统不会把草稿自动升级为正式交付。",
    step: { current: 4, total: 4, label: "等待真人检查" },
  },
  completed: {
    kind: "preview",
    action: "render",
    title: "任务终态已记录，产物可检查",
    detail: "任务终态与产物引用一致；正式签发仍只由真人完成。",
    step: { current: 4, total: 4, label: "产物已冻结" },
  },
  failed: {
    kind: "failed",
    action: "stop",
    title: "执行已经失败并停止",
    detail: "失败事实被保留；界面不会播放仍在执行的动画。",
    step: { current: 3, total: 4, label: "失败事实已冻结" },
    publicCode: "EXECUTION_FAILED_SYNTHETIC",
  },
  cancelled: {
    kind: "stopped",
    action: "stop",
    title: "执行已经停止",
    detail: "取消事实被保留；已有只读对象仍可用于检查。",
    step: { current: 3, total: 4, label: "终止事实已冻结" },
    publicCode: "EXECUTION_CANCELLED_SYNTHETIC",
  },
  "permission-denied": {
    kind: "denied",
    action: "deny",
    title: "执行被权限边界拒绝",
    detail: "对当前工作对象的访问被权限边界拒绝；执行不会悄悄降级继续。",
    step: { current: 1, total: 4, label: "权限边界已记录" },
    publicCode: "PERMISSION_DENIED_SYNTHETIC",
  },
});

function evidenceRefs(reality, workflow, seq) {
  return [
    `read-snapshot:sha256:${sha("d")}`,
    `task-event:evt-ws-${workflow}-${seq}@ordinal:${seq}`,
    `execution:run-ws-${workflow}-1@observation:${seq}`,
    `backend:ws-${workflow}-synthetic@adapter:fixture-adapter:1`,
    `reality-witness:${reality}:${WORKFLOWS[workflow].witnessId}-${reality.toLowerCase()}`,
    `artifact:file-ws-${workflow}-1@sha256:${WORKFLOWS[workflow].artifact.digest}`,
  ];
}

function previewFor(workflow, suffix) {
  const wf = WORKFLOWS[workflow];
  const art = wf.artifact;
  return {
    kind: `${art.rendererKind}-${suffix}`.slice(0, 40),
    title: suffix === "final" ? art.filename : `${wf.object}（处理中）`,
    caption: `合成对象 · ${art.classification} · ${art.bytes} B`,
    primary: `SHA-256 ${art.digest.slice(0, 12)}…`,
    secondary: "只读合成元数据；内容结论仍须经过产物、依据与交付门核验。",
  };
}

function makeEvent(workflow, state, { reality = "REAL", seq, observedAt } = {}) {
  const wf = WORKFLOWS[workflow];
  const copy = state === "running"
    ? {
        kind: wf.runKind,
        action: wf.runAction,
        title: `正在处理：${wf.object}`,
        detail: "当前观察绑定了任务修订、执行世代和只读合成工作对象。",
        step: { current: 2, total: 4, label: wf.runStepLabel },
      }
    : STATE_FACTS[state];
  const suffix = state === "completed" ? "final" : state === "waiting_review" ? "diff" : "draft";
  return {
    contractVersion: OBSERVER_CONTRACT_VERSION,
    source: SOURCE,
    eventId: `observer:run-ws-${workflow}-1:${seq}`,
    taskId: `task-ws-${workflow}-001`,
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
    preview: previewFor(workflow, suffix),
    evidenceRefs: evidenceRefs(reality, workflow, seq),
  };
}

// running 态的紧凑执行历史：receive(read) → inspect/guard(parse) → 当前动作。
// 历史事件与最新事件共用同一 reality、任务绑定与递增 sequence。
function runningTimeline(workflow, reality) {
  const wf = WORKFLOWS[workflow];
  const first = makeEvent(workflow, "running", { reality, seq: 11 });
  first.kind = "receiving";
  first.action = "receive";
  first.title = `接收只读工作对象：${wf.object}`;
  first.step = { current: 1, total: 4, label: "接收工作对象" };
  const second = makeEvent(workflow, "running", { reality, seq: 13 });
  second.kind = "validating";
  second.action = "guard";
  second.title = "解析对象结构与执行边界";
  second.step = { current: 1, total: 4, label: "解析对象结构" };
  const latest = makeEvent(workflow, "running", { reality, seq: 17 });
  return [first, second, latest];
}

function contextFor(workflow, nowMs) {
  return {
    expectedSource: SOURCE,
    expectedTaskId: `task-ws-${workflow}-001`,
    expectedRevision: "task-revision-3",
    expectedEpoch: "execution-epoch-2",
    nowMs,
  };
}

function buildObservation(workflow, state, realityOverride) {
  const reality = realityOverride || "REAL";
  // UNKNOWN 请求形态：不是合法 reality，不构造观察事件，
  // 一律 fail-closed 到观察缺口（observation_missing）。
  if (realityOverride === "UNKNOWN") {
    return { events: [], nowMs: BASE_TIME + 60_000 };
  }
  // evidence-missing：没有任何可验证观察/证据，fail closed（observation_missing）。
  if (state === "evidence-missing") {
    return { events: [], nowMs: BASE_TIME + 60_000 };
  }
  // observation-invalid：观察记录被篡改（step 越界），fail closed
  // （observation_invalid）。UNKNOWN 显示形态复用同一缺口语义。
  if (state === "observation-invalid") {
    const bad = makeEvent(workflow, "running", { reality, seq: 17 });
    bad.step = { current: 9, total: 4, label: "越界的合成步骤" };
    return { events: [bad], nowMs: BASE_TIME + 30_000 };
  }
  // stale：最近一次活动观察已过期，projector 给出 observation_stale 并停动画。
  if (state === "stale") {
    const old = makeEvent(workflow, "running", {
      reality,
      seq: 17,
      observedAt: new Date(BASE_TIME - 120_000).toISOString(),
    });
    return { events: [old], nowMs: BASE_TIME };
  }
  if (state === "running") {
    return { events: runningTimeline(workflow, reality), nowMs: BASE_TIME + 30_000 };
  }
  return {
    events: [makeEvent(workflow, state, { reality, seq: 17 })],
    nowMs: BASE_TIME + 30_000,
  };
}

export function getWorkspaceFixture(key) {
  const [workflow, state, form] = key.split(/[:@]/);
  if (!WORKFLOWS[workflow]) throw new Error(`unknown workflow: ${key}`);
  if (![...WORKSPACE_STATES, ...OVERLAY_STATES].includes(state)) {
    throw new Error(`unknown state: ${key}`);
  }
  if (form !== undefined && !DISPLAY_FORMS.includes(form)) {
    throw new Error(`unknown display form: ${key}`);
  }
  const { events, nowMs } = buildObservation(workflow, state, form);
  return {
    key,
    workflow,
    state,
    form: form || "REAL",
    scenario: WORKFLOWS[workflow],
    events,
    snapshot: projectObserverEvents(events, contextFor(workflow, nowMs)),
    stateFacts: STATE_FACTS[state] || null,
  };
}

// 96 个矩阵 key：3 工作流 × 8 状态 × 4 显示形态。
// UNKNOWN 形态不构造观察事件，fixture 层等价于 observation-invalid 缺口。
export function listMatrixKeys() {
  const keys = [];
  for (const workflow of Object.keys(WORKFLOWS)) {
    for (const state of WORKSPACE_STATES) {
      for (const form of DISPLAY_FORMS) {
        keys.push(`${workflow}:${state}@${form}`);
      }
    }
  }
  return keys;
}
