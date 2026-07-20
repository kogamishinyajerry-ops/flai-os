const SNAPSHOT_VERSION = "agent_fact_projection.v1";

const TASK_STATUSES = new Set([
  "created", "queued", "validating", "running", "waiting_review",
  "parsing", "analyzing", "completed", "failed", "cancelled",
]);
const PHASES = new Set([
  "waiting_upstream", "queued", "working", "awaiting_signoff",
  "settled", "failed", "cancelled",
]);
const TASK_PHASE_BY_STATUS = new Map([
  ["created", "queued"],
  ["queued", "queued"],
  ["validating", "working"],
  ["running", "working"],
  ["parsing", "working"],
  ["analyzing", "working"],
  ["waiting_review", "awaiting_signoff"],
  ["completed", "settled"],
  ["failed", "failed"],
  ["cancelled", "cancelled"],
]);
const DEPENDENCY_GATES = new Set([
  "human_signed", "deterministic_provenance", "pending", "failed", "unknown",
]);
const WAIT_CONTINUATIONS = new Map([
  ["dependency", "dependency_gate_satisfied"],
  ["human_signoff", "human_decision_recorded"],
  ["runtime_approval", "approval_resolved"],
  ["delegation_hold", "subagent_created_or_hold_released"],
  ["subagent_completion", "subagents_terminal"],
  ["subagent_retry", "retry_lineage_completed_or_task_stopped"],
]);
const JERRY_WAIT_KINDS = new Set([
  "runtime_approval", "delegation_hold", "subagent_completion", "subagent_retry",
]);
const SIGNOFF_STATES = new Set([
  "pending_result", "awaiting_human", "approved", "rejected", "not_required", "unknown",
]);
const RUNTIME_ADAPTERS = new Set(["native_python", "jerryagent_sidecar"]);
const RUNTIME_REASONS = new Set([
  "reported", "not_applicable", "disabled", "unreachable", "not_found", "malformed",
]);
const RUNTIME_STATUSES = new Set([
  "queued", "running", "awaiting_approval", "completed", "failed", "cancelled",
]);
const HOLD_PHASES = new Set(["armed", "released", "satisfied"]);
const SUBAGENT_STATUSES = new Set([
  "queued", "running", "completed", "failed", "cancelled", "interrupted",
]);

const TOP_KEYS = ["schemaVersion", "conversationId", "generatedAt", "taskCount", "tasksTruncated", "tasks"];
const TASK_KEYS = [
  "taskId", "agentId", "status", "createdAt", "updatedAt", "phase",
  "dependencies", "wait", "handoffs", "signoff", "runtime",
];
const DEPENDENCY_KEYS = ["taskId", "agentId", "status", "gate"];
const WAIT_KEYS = [
  "kind", "since", "subjectTaskId", "subjectAgentId", "subjectOrdinal",
  "pendingCount", "continueWhen",
];
const JERRY_WAIT_KEYS = ["kind", "since", "subjectOrdinal", "pendingCount", "continueWhen"];
const HANDOFF_KEYS = ["fromTaskId", "toTaskId", "at"];
const SIGNOFF_KEYS = ["state", "requestedFrom", "reviewer", "decidedAt"];
const RUNTIME_KEYS = [
  "adapter", "reported", "reason", "sourceEpoch", "revision", "status", "wait",
  "delegationHold", "subagentCount", "subagentsTruncated", "subagents",
];
const HOLD_KEYS = ["phase", "requestedAt", "resolvedAt", "satisfiedByOrdinal"];
const SUBAGENT_KEYS = ["ordinal", "status", "retryOfOrdinal", "createdAt", "updatedAt"];

function invalid(error) {
  return { valid: false, renderable: false, error };
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function isNullableString(value) {
  return value === null || isNonEmptyString(value);
}

function isNonNegativeInt(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

function isNullableOrdinal(value) {
  return value === null || (Number.isSafeInteger(value) && value > 0);
}

function isUtcTime(value) {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function exactKeys(value, keys, path) {
  if (!isRecord(value)) return `${path} 不是对象`;
  for (const key of keys) {
    if (!Object.hasOwn(value, key)) return `${path}.${key} 缺失`;
  }
  const allowed = new Set(keys);
  const extras = Object.keys(value).filter((key) => !allowed.has(key));
  return extras.length ? `${path} 含未允许字段：${extras.join(", ")}` : null;
}

function validateDependency(value, path) {
  const shapeError = exactKeys(value, DEPENDENCY_KEYS, path);
  if (shapeError) return shapeError;
  if (!isNonEmptyString(value.taskId)) return `${path}.taskId 非法`;
  if (!isNonEmptyString(value.agentId)) return `${path}.agentId 非法`;
  if (!TASK_STATUSES.has(value.status)) return `${path}.status 非法`;
  if (!DEPENDENCY_GATES.has(value.gate)) return `${path}.gate 非法`;
  return null;
}

function validateWait(value, path, { jerryOnly = false } = {}) {
  if (value === null) return null;
  const shapeError = exactKeys(value, jerryOnly ? JERRY_WAIT_KEYS : WAIT_KEYS, path);
  if (shapeError) return shapeError;
  const allowedKinds = jerryOnly ? JERRY_WAIT_KINDS : new Set(WAIT_CONTINUATIONS.keys());
  if (!allowedKinds.has(value.kind)) return `${path}.kind 非法`;
  if (!isUtcTime(value.since)) return `${path}.since 非法`;
  if (!isNullableOrdinal(value.subjectOrdinal)) return `${path}.subjectOrdinal 非法`;
  if (!isNonNegativeInt(value.pendingCount) || value.pendingCount === 0) {
    return `${path}.pendingCount 必须为正整数`;
  }
  if (value.continueWhen !== WAIT_CONTINUATIONS.get(value.kind)) {
    return `${path}.continueWhen 与 kind 不一致`;
  }
  if (!jerryOnly) {
    if (!isNullableString(value.subjectTaskId)) return `${path}.subjectTaskId 非法`;
    if (!isNullableString(value.subjectAgentId)) return `${path}.subjectAgentId 非法`;
  }
  return null;
}

function validateHandoff(value, path) {
  const shapeError = exactKeys(value, HANDOFF_KEYS, path);
  if (shapeError) return shapeError;
  if (!isNonEmptyString(value.fromTaskId)) return `${path}.fromTaskId 非法`;
  if (!isNonEmptyString(value.toTaskId)) return `${path}.toTaskId 非法`;
  if (!isUtcTime(value.at)) return `${path}.at 非法`;
  return null;
}

function validateSignoff(value, path) {
  const shapeError = exactKeys(value, SIGNOFF_KEYS, path);
  if (shapeError) return shapeError;
  if (!SIGNOFF_STATES.has(value.state)) return `${path}.state 非法`;
  if (!isNullableString(value.requestedFrom)) return `${path}.requestedFrom 非法`;
  if (!isNullableString(value.reviewer)) return `${path}.reviewer 非法`;
  if (value.decidedAt !== null && !isUtcTime(value.decidedAt)) return `${path}.decidedAt 非法`;
  if ((value.state === "approved" || value.state === "rejected")
    && (!isNonEmptyString(value.reviewer) || !isUtcTime(value.decidedAt))) {
    return `${path} 已决签发缺少 reviewer 或 decidedAt`;
  }
  if (value.state !== "approved" && value.state !== "rejected" && value.decidedAt !== null) {
    return `${path}.decidedAt 只能用于已决签发`;
  }
  return null;
}

function validateHold(value, path) {
  if (value === null) return null;
  const shapeError = exactKeys(value, HOLD_KEYS, path);
  if (shapeError) return shapeError;
  if (!HOLD_PHASES.has(value.phase)) return `${path}.phase 非法`;
  if (!isUtcTime(value.requestedAt)) return `${path}.requestedAt 非法`;
  if (value.resolvedAt !== null && !isUtcTime(value.resolvedAt)) return `${path}.resolvedAt 非法`;
  if (!isNullableOrdinal(value.satisfiedByOrdinal)) return `${path}.satisfiedByOrdinal 非法`;
  if (value.phase === "armed" && (value.resolvedAt !== null || value.satisfiedByOrdinal !== null)) {
    return `${path} armed 状态不得携带 resolvedAt 或 satisfiedByOrdinal`;
  }
  if (value.phase !== "armed" && value.resolvedAt === null) {
    return `${path} 已解除状态缺少 resolvedAt`;
  }
  if (value.resolvedAt !== null && Date.parse(value.resolvedAt) < Date.parse(value.requestedAt)) {
    return `${path}.resolvedAt 早于 requestedAt`;
  }
  if (value.phase === "satisfied" && value.satisfiedByOrdinal === null) {
    return `${path} satisfied 状态缺少 satisfiedByOrdinal`;
  }
  if (value.phase !== "satisfied" && value.satisfiedByOrdinal !== null) {
    return `${path}.satisfiedByOrdinal 只能用于 satisfied 状态`;
  }
  return null;
}

function validateSubagent(value, path) {
  const shapeError = exactKeys(value, SUBAGENT_KEYS, path);
  if (shapeError) return shapeError;
  if (!isNullableOrdinal(value.ordinal) || value.ordinal === null) return `${path}.ordinal 非法`;
  if (!SUBAGENT_STATUSES.has(value.status)) return `${path}.status 非法`;
  if (!isNullableOrdinal(value.retryOfOrdinal)) return `${path}.retryOfOrdinal 非法`;
  if (value.retryOfOrdinal !== null && value.retryOfOrdinal >= value.ordinal) {
    return `${path}.retryOfOrdinal 必须指向更早 ordinal`;
  }
  if (!isUtcTime(value.createdAt)) return `${path}.createdAt 非法`;
  if (!isUtcTime(value.updatedAt)) return `${path}.updatedAt 非法`;
  if (Date.parse(value.updatedAt) < Date.parse(value.createdAt)) return `${path}.updatedAt 早于 createdAt`;
  return null;
}

function validateRuntime(value, path) {
  const shapeError = exactKeys(value, RUNTIME_KEYS, path);
  if (shapeError) return shapeError;
  if (!RUNTIME_ADAPTERS.has(value.adapter)) return `${path}.adapter 非法`;
  if (typeof value.reported !== "boolean") return `${path}.reported 非法`;
  if (!RUNTIME_REASONS.has(value.reason)) return `${path}.reason 非法`;
  if (value.sourceEpoch !== null && (typeof value.sourceEpoch !== "string" || !/^[0-9a-f]{64}$/i.test(value.sourceEpoch))) {
    return `${path}.sourceEpoch 非法`;
  }
  if (value.revision !== null && !isNonNegativeInt(value.revision)) return `${path}.revision 非法`;
  if (value.status !== null && !RUNTIME_STATUSES.has(value.status)) return `${path}.status 非法`;
  if (value.reported === true && value.adapter !== "jerryagent_sidecar") {
    return `${path} reported=true 只允许 jerryagent_sidecar`;
  }
  if (value.adapter === "native_python" && (value.reported !== false || value.reason !== "not_applicable")) {
    return `${path} native_python 只允许 reported=false 且 reason=not_applicable`;
  }
  if (value.adapter === "jerryagent_sidecar" && value.reported === false && value.reason === "not_applicable") {
    return `${path} jerryagent_sidecar 不允许 reason=not_applicable`;
  }
  if (value.reported === true && value.reason !== "reported") return `${path}.reason 与 reported 不一致`;
  if (value.reported === true && (value.sourceEpoch === null || value.revision === null || value.status === null)) {
    return `${path} 已报告事实缺少 epoch、revision 或 status`;
  }
  if (value.reported === false && value.reason === "reported") return `${path}.reason 与 reported 不一致`;
  if (value.reported === false && (value.sourceEpoch !== null || value.revision !== null || value.status !== null)) {
    return `${path} reported=false 时 epoch、revision 与 status 必须为 null`;
  }
  if (value.reported === false && (
    value.wait !== null
    || value.delegationHold !== null
    || value.subagentCount !== 0
    || value.subagentsTruncated !== false
    || !Array.isArray(value.subagents)
    || value.subagents.length !== 0
  )) {
    return `${path} reported=false 时不得携带 wait、hold 或子智能体事实`;
  }
  const waitError = validateWait(value.wait, `${path}.wait`, { jerryOnly: true });
  if (waitError) return waitError;
  const holdError = validateHold(value.delegationHold, `${path}.delegationHold`);
  if (holdError) return holdError;
  if (["completed", "failed", "cancelled"].includes(value.status) && value.wait !== null) {
    return `${path} 终态不得携带 wait`;
  }
  if (value.wait?.kind === "runtime_approval"
    && (value.status !== "awaiting_approval" || value.wait.subjectOrdinal !== null)) {
    return `${path}.wait runtime_approval 与 status/subjectOrdinal 不一致`;
  }
  if (value.status === "awaiting_approval" && value.wait?.kind !== "runtime_approval") {
    return `${path}.status awaiting_approval 缺少 runtime_approval wait`;
  }
  if (value.wait?.kind === "delegation_hold" && (
    value.wait.subjectOrdinal !== null
    || value.wait.pendingCount !== 1
    || value.delegationHold?.phase !== "armed"
  )) {
    return `${path}.wait delegation_hold 与 hold 不一致`;
  }
  if (value.delegationHold?.phase === "armed"
    && !["runtime_approval", "delegation_hold"].includes(value.wait?.kind)) {
    return `${path}.delegationHold armed 缺少匹配 wait`;
  }
  if (["subagent_completion", "subagent_retry"].includes(value.wait?.kind)
    && value.wait.subjectOrdinal === null) {
    return `${path}.wait 子智能体等待缺少 subjectOrdinal`;
  }
  if (!isNonNegativeInt(value.subagentCount)) return `${path}.subagentCount 非法`;
  if (typeof value.subagentsTruncated !== "boolean") return `${path}.subagentsTruncated 非法`;
  if (!Array.isArray(value.subagents) || value.subagents.length > 64) return `${path}.subagents 非法`;
  if (value.subagentsTruncated === false && value.subagentCount !== value.subagents.length) {
    return `${path}.subagentCount 与 subagents 数量不一致`;
  }
  if (value.subagentsTruncated === true
    && (value.subagentCount <= 64 || value.subagents.length !== 64)) {
    return `${path}.subagentsTruncated=true 需要总数大于 64 且恰好返回 64 条`;
  }
  if (value.wait?.subjectOrdinal !== null && value.wait?.subjectOrdinal > value.subagentCount) {
    return `${path}.wait.subjectOrdinal 超过 subagentCount`;
  }
  if (value.delegationHold?.satisfiedByOrdinal !== null
    && value.delegationHold?.satisfiedByOrdinal > value.subagentCount) {
    return `${path}.delegationHold.satisfiedByOrdinal 超过 subagentCount`;
  }
  for (let index = 0; index < value.subagents.length; index += 1) {
    const subagentError = validateSubagent(value.subagents[index], `${path}.subagents[${index}]`);
    if (subagentError) return subagentError;
    if (value.subagents[index].ordinal !== index + 1) {
      return `${path}.subagents ordinal 必须连续为 1..N`;
    }
  }
  return null;
}

function validateTask(value, path) {
  const shapeError = exactKeys(value, TASK_KEYS, path);
  if (shapeError) return shapeError;
  if (!isNonEmptyString(value.taskId)) return `${path}.taskId 非法`;
  if (!isNonEmptyString(value.agentId)) return `${path}.agentId 非法`;
  if (!TASK_STATUSES.has(value.status)) return `${path}.status 非法`;
  if (!isUtcTime(value.createdAt)) return `${path}.createdAt 非法`;
  if (!isUtcTime(value.updatedAt)) return `${path}.updatedAt 非法`;
  if (Date.parse(value.updatedAt) < Date.parse(value.createdAt)) return `${path}.updatedAt 早于 createdAt`;
  if (!PHASES.has(value.phase)) return `${path}.phase 非法`;
  if (!Array.isArray(value.dependencies)) return `${path}.dependencies 非数组`;
  for (let index = 0; index < value.dependencies.length; index += 1) {
    const dependencyError = validateDependency(value.dependencies[index], `${path}.dependencies[${index}]`);
    if (dependencyError) return dependencyError;
  }
  const waitError = validateWait(value.wait, `${path}.wait`);
  if (waitError) return waitError;
  if (!Array.isArray(value.handoffs)) return `${path}.handoffs 非数组`;
  for (let index = 0; index < value.handoffs.length; index += 1) {
    const handoffError = validateHandoff(value.handoffs[index], `${path}.handoffs[${index}]`);
    if (handoffError) return handoffError;
  }
  const signoffError = validateSignoff(value.signoff, `${path}.signoff`);
  if (signoffError) return signoffError;
  const runtimeError = validateRuntime(value.runtime, `${path}.runtime`);
  if (runtimeError) return runtimeError;
  const expectedPhase = value.status === "created" && value.dependencies.length > 0
    ? "waiting_upstream"
    : TASK_PHASE_BY_STATUS.get(value.status);
  if (value.phase !== expectedPhase) {
    return `${path}.phase 与 status/dependencies 不一致`;
  }
  if (value.status === "waiting_review" && value.signoff.state !== "awaiting_human") {
    return `${path}.signoff 与 waiting_review 不一致`;
  }
  if (value.signoff.state === "awaiting_human" && value.status !== "waiting_review") {
    return `${path}.signoff awaiting_human 与 status 不一致`;
  }
  if (value.signoff.state === "approved" && value.status !== "completed") {
    return `${path}.signoff approved 只允许 completed`;
  }
  if (value.signoff.state === "rejected" && value.status !== "failed") {
    return `${path}.signoff rejected 只允许 failed`;
  }

  const unsettledDependencies = value.dependencies.filter(
    (dependency) => !["human_signed", "deterministic_provenance"].includes(dependency.gate),
  );
  if (value.phase === "waiting_upstream") {
    if (unsettledDependencies.length === 0 && value.wait !== null) {
      return `${path}.wait 已无未满足 dependency`;
    }
    if (unsettledDependencies.length > 0) {
      if (value.wait?.kind !== "dependency") return `${path}.wait 缺少 dependency wait`;
      const subject = unsettledDependencies.find((dependency) => (
        dependency.taskId === value.wait.subjectTaskId
        && dependency.agentId === value.wait.subjectAgentId
      ));
      if (!subject) return `${path}.wait dependency subject 不在未满足集合`;
      if (value.wait.subjectOrdinal !== null) return `${path}.wait dependency 不允许 subjectOrdinal`;
      if (value.wait.pendingCount !== unsettledDependencies.length) {
        return `${path}.wait dependency pendingCount 不准确`;
      }
    }
  } else if (value.wait?.kind === "dependency") {
    return `${path}.wait dependency 与 phase 不一致`;
  }

  if (value.status === "waiting_review") {
    if (value.wait?.kind !== "human_signoff") return `${path}.wait 缺少 human_signoff`;
    if (value.wait.subjectTaskId !== null
      || value.wait.subjectAgentId !== null
      || value.wait.subjectOrdinal !== null
      || value.wait.pendingCount !== 1) {
      return `${path}.wait human_signoff 字段不一致`;
    }
  } else if (value.wait?.kind === "human_signoff") {
    return `${path}.wait human_signoff 与 status 不一致`;
  }

  const taskRuntimeWait = value.wait !== null && JERRY_WAIT_KINDS.has(value.wait.kind)
    ? value.wait
    : null;
  const lowerPriorityWaitOwnsTask = value.phase === "waiting_upstream" || value.status === "waiting_review";
  if (taskRuntimeWait !== null) {
    const runtimeWait = value.runtime.reported === true ? value.runtime.wait : null;
    if (runtimeWait === null
      || taskRuntimeWait.subjectTaskId !== null
      || taskRuntimeWait.subjectAgentId !== null
      || taskRuntimeWait.kind !== runtimeWait.kind
      || taskRuntimeWait.since !== runtimeWait.since
      || taskRuntimeWait.subjectOrdinal !== runtimeWait.subjectOrdinal
      || taskRuntimeWait.pendingCount !== runtimeWait.pendingCount
      || taskRuntimeWait.continueWhen !== runtimeWait.continueWhen) {
      return `${path}.wait 与 runtime wait 不一致`;
    }
  } else if (!lowerPriorityWaitOwnsTask && value.runtime.wait !== null) {
    return `${path}.wait 缺少 runtime wait`;
  }
  if (value.wait?.subjectOrdinal !== null && value.wait?.subjectOrdinal > value.runtime.subagentCount) {
    return `${path}.wait.subjectOrdinal 超过 runtime.subagentCount`;
  }
  return null;
}

export function validateAgentFactSnapshot(snapshot) {
  const shapeError = exactKeys(snapshot, TOP_KEYS, "Agent 事实快照");
  if (shapeError) return invalid(shapeError);
  if (snapshot.schemaVersion !== SNAPSHOT_VERSION) {
    return invalid(`不支持的 Agent 事实版本：${String(snapshot.schemaVersion)}`);
  }
  if (!isNonEmptyString(snapshot.conversationId)) return invalid("Agent 事实快照 conversationId 非法");
  if (!isUtcTime(snapshot.generatedAt)) return invalid("Agent 事实快照 generatedAt 非法");
  if (!isNonNegativeInt(snapshot.taskCount)) return invalid("Agent 事实快照 taskCount 非法");
  if (typeof snapshot.tasksTruncated !== "boolean") return invalid("Agent 事实快照 tasksTruncated 非法");
  if (!Array.isArray(snapshot.tasks) || snapshot.tasks.length > 100) return invalid("Agent 事实快照 tasks 非法");
  if (snapshot.tasksTruncated === false && snapshot.taskCount !== snapshot.tasks.length) {
    return invalid("Agent 事实快照 taskCount 与 tasks 数量不一致");
  }
  if (snapshot.tasksTruncated === true && snapshot.taskCount <= snapshot.tasks.length) {
    return invalid("Agent 事实快照 tasksTruncated=true 但没有被省略的任务");
  }
  const taskIds = new Set();
  for (let index = 0; index < snapshot.tasks.length; index += 1) {
    const taskError = validateTask(snapshot.tasks[index], `tasks[${index}]`);
    if (taskError) return invalid(taskError);
    if (taskIds.has(snapshot.tasks[index].taskId)) return invalid("Agent 事实快照 taskId 重复");
    taskIds.add(snapshot.tasks[index].taskId);
  }
  return { valid: true, renderable: true, snapshot };
}

function validatedProjection(snapshot) {
  const validation = validateAgentFactSnapshot(snapshot);
  return validation.valid ? null : validation;
}

function normalizedAgentIds(ids) {
  if (ids == null) return { valid: true, selected: null };
  if (!Array.isArray(ids) || ids.some((id) => !isNonEmptyString(id))) {
    return invalid("Agent id 筛选条件非法");
  }
  return { valid: true, selected: new Set(ids) };
}

export function factsForAgentIds(snapshot, ids) {
  const failure = validatedProjection(snapshot);
  if (failure) return failure;
  const normalized = normalizedAgentIds(ids);
  if (!normalized.valid) return normalized;
  const tasks = normalized.selected === null
    ? snapshot.tasks.slice()
    : snapshot.tasks.filter((task) => normalized.selected.has(task.agentId));
  return { valid: true, renderable: tasks.length > 0, tasks };
}

export function summarizeAgentFacts(snapshot, ids, nowMs = Date.now()) {
  const facts = factsForAgentIds(snapshot, ids);
  if (!facts.valid) return facts;
  if (typeof nowMs !== "number" || !Number.isFinite(nowMs)) return invalid("摘要时钟非法");

  const failed = facts.tasks.filter((task) => task.phase === "failed" || task.signoff.state === "rejected");
  const waiting = facts.tasks.filter((task) => task.wait !== null || task.phase === "awaiting_signoff");
  const working = facts.tasks.filter((task) => task.phase === "working");
  const queued = facts.tasks.filter((task) => task.phase === "queued");
  const signed = facts.tasks.filter((task) => task.signoff.state === "approved");
  const reportedRuntimeCount = facts.tasks.filter((task) => task.runtime.reported === true).length;
  const applicableRuntimeCount = facts.tasks.filter(
    (task) => task.runtime.adapter === "jerryagent_sidecar",
  ).length;
  const unavailableRuntimeCount = facts.tasks.filter(
    (task) => task.runtime.adapter === "jerryagent_sidecar" && task.runtime.reported === false,
  ).length;
  const notApplicableRuntimeCount = facts.tasks.filter(
    (task) => task.runtime.reason === "not_applicable",
  ).length;
  const subagentCount = facts.tasks.reduce(
    (sum, task) => sum + (task.runtime.reported === true ? task.runtime.subagentCount : 0),
    0,
  );
  const partial = snapshot.tasksTruncated === true;
  const scopedHeadline = (text) => partial ? `最近 ${facts.tasks.length} 项中${text}` : text;

  let state = "settled";
  let headline = facts.tasks.length
    ? (partial ? `仅显示最近 ${facts.tasks.length} / 共 ${snapshot.taskCount} 个任务` : `${facts.tasks.length} 个任务已落定`)
    : "";
  if (signed.length) {
    state = "signed";
    headline = scopedHeadline(`${signed.length} 个任务已由人工签发`);
  }
  if (queued.length) {
    state = "queued";
    headline = scopedHeadline(`${queued.length} 个任务待运行`);
  }
  if (working.length) {
    state = "working";
    headline = scopedHeadline(`${working.length} 个任务运行中`);
  }
  if (waiting.length) {
    const awaitingHuman = waiting.filter((task) => task.signoff.state === "awaiting_human").length;
    state = "waiting";
    headline = scopedHeadline(awaitingHuman
      ? `${awaitingHuman} 个任务等待人工签发`
      : `${waiting.length} 个任务正在等待`);
  }
  if (failed.length) {
    state = "failure";
    headline = scopedHeadline(`${failed.length} 个任务失败`);
  }

  return {
    valid: true,
    renderable: facts.tasks.length > 0,
    state,
    headline,
    taskCount: facts.tasks.length,
    totalTaskCount: snapshot.taskCount,
    tasksTruncated: partial,
    agentCount: new Set(facts.tasks.map((task) => task.agentId)).size,
    subagentCount,
    reportedRuntimeCount,
    applicableRuntimeCount,
    unavailableRuntimeCount,
    notApplicableRuntimeCount,
    workingCount: working.length,
    queuedCount: queued.length,
    waitingCount: waiting.length,
    signedCount: signed.length,
    failedCount: failed.length,
    generatedAt: snapshot.generatedAt,
  };
}

const WAIT_LABELS = {
  dependency: "等待上游依赖",
  human_signoff: "等待人工签发",
  runtime_approval: "等待运行批准",
  delegation_hold: "等待委派继续",
  subagent_completion: "等待子智能体完成",
  subagent_retry: "等待子智能体重试链",
};

const CONTINUE_LABELS = {
  dependency_gate_satisfied: "依赖门满足后继续",
  human_decision_recorded: "人工决定记录后继续",
  approval_resolved: "运行批准落定后继续",
  subagent_created_or_hold_released: "子智能体创建或委派解除后继续",
  subagents_terminal: "子智能体全部落定后继续",
  retry_lineage_completed_or_task_stopped: "重试链落定或任务停止后继续",
};

const WAIT_ACTORS = {
  dependency: "上游依赖",
  human_signoff: "人工签发",
  runtime_approval: "运行批准",
  delegation_hold: "子智能体集合",
  subagent_completion: "子智能体集合",
  subagent_retry: "子智能体重试链",
};

export function waitPresentation(wait, signoff) {
  if (signoff?.state === "approved") {
    return {
      tone: "signed",
      label: signoff.reviewer ? `${signoff.reviewer} 已签` : "人工已签",
      detail: signoff.decidedAt || "",
      actor: signoff.reviewer || "",
      continueWhen: "",
      signed: true,
    };
  }
  if (signoff?.state === "rejected") {
    return {
      tone: "failure",
      label: signoff.reviewer ? `${signoff.reviewer} 已驳回` : "人工已驳回",
      detail: signoff.decidedAt || "",
      actor: signoff.reviewer || "",
      continueWhen: "",
      signed: false,
    };
  }
  if (signoff?.state === "awaiting_human") {
    const actor = signoff.requestedFrom || "";
    return {
      tone: "waiting",
      label: actor ? `等待 ${actor} 签收` : "等待人工签收",
      detail: actor ? `点名签收对象：${actor}` : "",
      actor,
      continueWhen: "人工决定记录后继续",
      signed: false,
    };
  }
  if (wait) {
    let actor = wait.subjectAgentId || WAIT_ACTORS[wait.kind] || "";
    let detail = "";
    if (wait.subjectAgentId && wait.subjectTaskId) detail = `等待 ${wait.subjectAgentId}（${wait.subjectTaskId}）`;
    else if (wait.subjectAgentId) detail = `等待 ${wait.subjectAgentId}`;
    else if (wait.subjectTaskId) {
      actor = wait.subjectTaskId;
      detail = `等待任务 ${wait.subjectTaskId}`;
    } else if (wait.subjectOrdinal != null) {
      actor = `子智能体 #${wait.subjectOrdinal}`;
      detail = `等待子智能体 #${wait.subjectOrdinal}`;
    } else if (wait.pendingCount > 0) {
      detail = `${actor} · 尚有 ${wait.pendingCount} 项未落定`;
    } else if (actor) {
      detail = `等待 ${actor}`;
    }
    return {
      tone: "waiting",
      label: WAIT_LABELS[wait.kind],
      detail,
      actor,
      continueWhen: CONTINUE_LABELS[wait.continueWhen],
      signed: false,
    };
  }
  return {
    tone: "neutral",
    label: "无等待事实",
    detail: "",
    actor: "",
    continueWhen: "",
    signed: false,
  };
}

export function groupMonitorTasks(snapshot) {
  const failure = validatedProjection(snapshot);
  if (failure) return failure;
  const current = [];
  const waiting = [];
  const settled = [];
  for (const task of snapshot.tasks) {
    if (task.wait !== null || task.phase === "waiting_upstream" || task.phase === "awaiting_signoff") {
      waiting.push(task);
    } else if (task.phase === "settled" || task.phase === "failed" || task.phase === "cancelled") {
      settled.push(task);
    } else {
      current.push(task);
    }
  }
  return {
    valid: true,
    renderable: snapshot.tasks.length > 0,
    current,
    waiting,
    settled,
    counts: { current: current.length, waiting: waiting.length, settled: settled.length },
  };
}

function canonicalJsonValue(value) {
  if (Array.isArray(value)) return value.map(canonicalJsonValue);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalJsonValue(value[key])]),
  );
}

function runtimeFactsEqual(left, right) {
  return JSON.stringify(canonicalJsonValue(left)) === JSON.stringify(canonicalJsonValue(right));
}

export function advanceAgentFactRuntimeFloors(runtimeFloors, snapshot, maxEntries = 256) {
  const floors = runtimeFloors instanceof Map ? new Map(runtimeFloors) : new Map();
  const validation = validateAgentFactSnapshot(snapshot);
  if (!validation.valid) return floors;
  const limit = Number.isSafeInteger(maxEntries) && maxEntries > 0 ? maxEntries : 256;

  for (const task of snapshot.tasks) {
    if (task.runtime.reported !== true) continue;
    const current = floors.get(task.taskId);
    if (current?.sourceEpoch === task.runtime.sourceEpoch
      && current.revision >= task.runtime.revision) {
      // A full unavailable snapshot never erases this floor. An equal revision
      // is immutable too; continuity validation must approve any replacement.
      floors.delete(task.taskId);
      floors.set(task.taskId, current);
      continue;
    }
    floors.delete(task.taskId);
    floors.set(task.taskId, {
      sourceEpoch: task.runtime.sourceEpoch,
      revision: task.runtime.revision,
      runtime: canonicalJsonValue(task.runtime),
    });
  }
  while (floors.size > limit) floors.delete(floors.keys().next().value);
  return floors;
}

export function evaluateAgentFactContinuity(previous, next, runtimeFloors = null) {
  const nextValidation = validateAgentFactSnapshot(next);
  if (!nextValidation.valid) return { action: "resnapshot", reason: "next_snapshot_invalid" };
  let previousByTaskId = new Map();
  if (previous !== null) {
    const previousValidation = validateAgentFactSnapshot(previous);
    if (!previousValidation.valid) return { action: "resnapshot", reason: "previous_snapshot_invalid" };
    if (previous.conversationId !== next.conversationId) {
      return { action: "resnapshot", reason: "conversation_changed" };
    }
    previousByTaskId = new Map(previous.tasks.map((task) => [task.taskId, task]));
  }

  for (const nextTask of next.tasks) {
    const previousTask = previousByTaskId.get(nextTask.taskId);
    const floor = runtimeFloors instanceof Map ? runtimeFloors.get(nextTask.taskId) : null;
    const previousRuntime = previousTask?.runtime.reported === true
      ? previousTask.runtime
      : null;
    const floorRuntime = floor?.runtime || null;
    const baselineRuntime = previousRuntime && floorRuntime
      && previousRuntime.sourceEpoch === floorRuntime.sourceEpoch
      && floorRuntime.revision >= previousRuntime.revision
      ? floorRuntime
      : previousRuntime || floorRuntime;
    if (!baselineRuntime || nextTask.runtime.reported !== true) continue;
    if (baselineRuntime.sourceEpoch !== nextTask.runtime.sourceEpoch) {
      return { action: "resnapshot", reason: "runtime_source_epoch_changed" };
    }
    if (nextTask.runtime.revision < baselineRuntime.revision) {
      return { action: "resnapshot", reason: "runtime_revision_regressed" };
    }
    if (nextTask.runtime.revision === baselineRuntime.revision
      && !runtimeFactsEqual(baselineRuntime, nextTask.runtime)) {
      return { action: "resnapshot", reason: "runtime_changed_without_revision" };
    }
  }
  return { action: "accept", reason: null };
}

export function confirmAgentFactResnapshot(
  previous,
  suspect,
  replacement,
  reason,
  runtimeFloors = null,
) {
  // A runtime epoch change is the one continuity break that a forced second
  // full snapshot can legitimately confirm: compare the replacement with the
  // first snapshot from the new epoch, not forever with the retired epoch.
  // Every other break must clear against the last accepted snapshot.
  const baseline = reason === "runtime_source_epoch_changed" ? suspect : previous;
  // Preserve every unaffected task's accepted high-water mark while allowing
  // only the task(s) that actually moved epoch to establish a new baseline.
  // Otherwise an epoch break in task A could make task B's regressed suspect
  // snapshot look authoritative during the confirmation read.
  const confirmedFloors = advanceAgentFactRuntimeFloors(runtimeFloors, previous);
  return evaluateAgentFactContinuity(baseline, replacement, confirmedFloors);
}
