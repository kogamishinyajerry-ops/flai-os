// Prototype-only read-model projector. `source` is provenance, not
// authentication: a production adapter must create these objects only after
// verifying the control-kernel channel, task revision, and execution epoch.
export const OBSERVER_CONTRACT_VERSION = "flai.stage-c.observer.v2";

const ACTIVE_KINDS = new Set(["receiving", "working", "validating", "recovering"]);
const ALLOWED_SOURCES = new Set(["control-kernel", "synthetic-fixture"]);
const EXECUTION_REALITIES = new Set(["REAL", "MOCK", "TEST"]);
const ALLOWED_ACTIONS = new Set([
  "idle",
  "receive",
  "guard",
  "inspect",
  "rewrite",
  "map",
  "render",
  "hold",
  "stop",
  "deny",
  "signal",
]);
const KIND_COPY = {
  idle: { mode: "idle", overline: "准备开始" },
  receiving: { mode: "scanning", overline: "正在发生" },
  working: { mode: "working", overline: "正在发生" },
  validating: { mode: "working", overline: "正在验证" },
  recovering: { mode: "working", overline: "正在恢复" },
  attention: { mode: "attention", overline: "当前关注" },
  preview: { mode: "preview", overline: "当前可看" },
  failed: { mode: "failed", overline: "执行监控" },
  unknown: { mode: "unknown", overline: "执行监控" },
  stopped: { mode: "stopped", overline: "执行监控" },
  denied: { mode: "failed", overline: "权限边界" },
};
const ACTIONS_BY_KIND = {
  idle: new Set(["idle"]),
  receiving: new Set(["receive"]),
  working: new Set(["inspect", "rewrite", "map"]),
  validating: new Set(["guard", "inspect"]),
  recovering: new Set(["signal", "guard"]),
  attention: new Set(["hold"]),
  preview: new Set(["render"]),
  failed: new Set(["stop"]),
  unknown: new Set(["signal"]),
  stopped: new Set(["stop"]),
  denied: new Set(["deny"]),
};
const EVENT_KEYS = new Set([
  "contractVersion",
  "source",
  "eventId",
  "taskId",
  "taskRevision",
  "executionEpoch",
  "sequence",
  "observedAt",
  "reality",
  "kind",
  "action",
  "title",
  "detail",
  "step",
  "preview",
  "evidenceRefs",
]);
const PREVIEW_KEYS = new Set(["kind", "title", "caption", "primary", "secondary"]);
const STEP_KEYS = new Set(["current", "total", "label"]);

function unknownSnapshot(reasonCode = "observation_missing") {
  return {
    contractVersion: OBSERVER_CONTRACT_VERSION,
    reality: "UNKNOWN",
    mode: "unknown",
    overline: "实时观察",
    title: "等待可靠状态",
    detail: "没有收到可验证的控制内核观察，因此不会猜测 Agent 仍在工作。",
    action: "signal",
    stepLabel: "没有可靠进度",
    motion: false,
    preview: {
      kind: "unknown",
      title: "当前工作对象不可用",
      caption: "没有可验证的预览",
      primary: "未知",
      secondary: "等待可靠状态",
    },
    reasonCode,
  };
}

function hasOnlyKeys(value, allowed) {
  return Object.keys(value).every((key) => allowed.has(key));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
  );
}

function eventFingerprint(event) {
  return JSON.stringify(canonicalize(event));
}

function isText(value, maxLength = 240) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maxLength;
}

function isValidStep(step) {
  if (!step || typeof step !== "object" || Array.isArray(step) || !hasOnlyKeys(step, STEP_KEYS)) {
    return false;
  }
  if (!Number.isInteger(step.current) || !Number.isInteger(step.total)) return false;
  if (step.current < 0 || step.total < 1 || step.current > step.total || step.total > 20) return false;
  if (step.label === undefined) return true;
  return isText(step.label, 64) && !step.label.includes("%");
}

function isValidPreview(preview) {
  if (!preview || typeof preview !== "object" || Array.isArray(preview)) return false;
  if (!hasOnlyKeys(preview, PREVIEW_KEYS)) return false;
  return (
    isText(preview.kind, 40)
    && isText(preview.title, 120)
    && isText(preview.caption, 160)
    && isText(preview.primary, 160)
    && isText(preview.secondary, 200)
  );
}

function isValidEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) return false;
  if (!hasOnlyKeys(event, EVENT_KEYS)) return false;
  if (event.contractVersion !== OBSERVER_CONTRACT_VERSION || !ALLOWED_SOURCES.has(event.source)) return false;
  if (!isText(event.eventId, 120) || !isText(event.taskId, 120)) return false;
  if (!isText(event.taskRevision, 120) || !isText(event.executionEpoch, 120)) return false;
  if (!Number.isInteger(event.sequence) || event.sequence < 0) return false;
  if (!Number.isFinite(Date.parse(event.observedAt))) return false;
  if (!EXECUTION_REALITIES.has(event.reality)) return false;
  if (!Object.hasOwn(KIND_COPY, event.kind) || !ALLOWED_ACTIONS.has(event.action)) return false;
  if (!ACTIONS_BY_KIND[event.kind].has(event.action)) return false;
  if (!isText(event.title, 160) || !isText(event.detail, 500)) return false;
  if (!isValidStep(event.step) || !isValidPreview(event.preview)) return false;
  if (!Array.isArray(event.evidenceRefs) || !event.evidenceRefs.every((item) => isText(item, 200))) return false;
  if (event.kind !== "idle" && event.evidenceRefs.length === 0) return false;
  const realityWitnessPrefix = `reality-witness:${event.reality}:`;
  if (!event.evidenceRefs.some((ref) => (
    ref.startsWith(realityWitnessPrefix) && ref.length > realityWitnessPrefix.length
  ))) {
    return false;
  }
  return true;
}

function matchesExpectedIdentity(event, context) {
  const expectedSource = context.expectedSource || "control-kernel";
  return (
    event.source === expectedSource
    && event.taskId === context.expectedTaskId
    && event.taskRevision === context.expectedRevision
    && event.executionEpoch === context.expectedEpoch
  );
}

export function projectObserverEvents(events, context = {}) {
  if (!Array.isArray(events) || events.length === 0) {
    return unknownSnapshot();
  }
  if (!events.every((event) => isValidEvent(event))) {
    return unknownSnapshot("observation_invalid");
  }
  if (!events.every((event) => matchesExpectedIdentity(event, context))) {
    return unknownSnapshot("observation_identity_mismatch");
  }
  if (new Set(events.map((event) => event.reality)).size !== 1) {
    return unknownSnapshot("observation_reality_conflict");
  }

  const bySequence = new Map();
  const byEventId = new Map();
  for (const event of events) {
    const eventIdExisting = byEventId.get(event.eventId);
    if (eventIdExisting && eventFingerprint(eventIdExisting) !== eventFingerprint(event)) {
      return unknownSnapshot("observation_event_id_conflict");
    }
    byEventId.set(event.eventId, event);

    const existing = bySequence.get(event.sequence);
    if (existing && eventFingerprint(existing) !== eventFingerprint(event)) {
      return unknownSnapshot("observation_sequence_conflict");
    }
    bySequence.set(event.sequence, event);
  }

  const latest = [...events].sort((left, right) => right.sequence - left.sequence)[0];
  const nowMs = Number.isFinite(context.nowMs) ? context.nowMs : Date.now();
  const maxFutureSkewMs = Number.isFinite(context.maxFutureSkewMs) && context.maxFutureSkewMs >= 0
    ? context.maxFutureSkewMs
    : 5_000;
  const staleAfterMs = Number.isFinite(context.staleAfterMs) && context.staleAfterMs > 0
    ? context.staleAfterMs
    : 30_000;
  const observationAgeMs = nowMs - Date.parse(latest.observedAt);
  if (observationAgeMs < -maxFutureSkewMs) {
    return {
      ...unknownSnapshot("observation_clock_invalid"),
      title: "观察时间不可确认",
      detail: "最近事件时间超出允许时钟偏差；界面不会据此显示正在执行。",
      preview: latest.preview,
      eventId: latest.eventId,
      observedAt: latest.observedAt,
      evidenceRefs: [...latest.evidenceRefs],
      source: latest.source,
      reality: latest.reality,
    };
  }
  if (ACTIVE_KINDS.has(latest.kind) && observationAgeMs > staleAfterMs) {
    return {
      ...unknownSnapshot("observation_stale"),
      title: "等待可靠心跳",
      detail: "最近一次活动观察已经过期；界面停止动画并保留最后可信工作对象。",
      preview: latest.preview,
      eventId: latest.eventId,
      observedAt: latest.observedAt,
      evidenceRefs: [...latest.evidenceRefs],
      source: latest.source,
      reality: latest.reality,
    };
  }
  const copy = KIND_COPY[latest.kind];
  return {
    contractVersion: OBSERVER_CONTRACT_VERSION,
    mode: copy.mode,
    overline: copy.overline,
    title: latest.title,
    detail: latest.detail,
    action: latest.action,
    stepLabel: latest.step.label || `可见步骤 ${latest.step.current}/${latest.step.total}`,
    motion: ACTIVE_KINDS.has(latest.kind),
    preview: latest.preview,
    reasonCode: "observed",
    eventId: latest.eventId,
    observedAt: latest.observedAt,
    evidenceRefs: [...latest.evidenceRefs],
    source: latest.source,
    reality: latest.reality,
  };
}
