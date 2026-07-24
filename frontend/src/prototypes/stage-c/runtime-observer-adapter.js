import {
  OBSERVER_CONTRACT_VERSION,
} from "./observer-contract.js";

// Pure, prototype-only boundary. This module performs no I/O and cannot
// authenticate `control-kernel` by inspecting a string. A future production
// composition root must call it only with records read through an authenticated,
// authorization-checked control-kernel channel.
export const RUNTIME_OBSERVER_ADAPTER_VERSION = "flai.stage-c.runtime-observer-adapter.v3";

const TASK_EVENT_TYPES = new Set([
  "task_created",
  "validation_started",
  "validation_failed",
  "case_generated",
  "tool_started",
  "tool_finished",
  "tool_failed",
  "model_call",
  "review_requested",
  "review_approved",
  "review_rejected",
  "summary_generated",
  "task_completed",
  "task_failed",
  "task_cancelled",
  "feedback_received",
  "knowledge_search",
  "warning",
  "error",
  "agent_log",
]);
const TASK_EVENT_LEVELS = new Set(["info", "warning", "error"]);
const ACTIVE_ACTIONS = new Set(["inspect", "rewrite", "map"]);
const VALIDATING_ACTIONS = new Set(["guard", "inspect"]);
const TASK_STATUSES = new Set([
  "created",
  "queued",
  "validating",
  "running",
  "waiting_review",
  "parsing",
  "analyzing",
  "completed",
  "failed",
  "cancelled",
]);
const EVENT_TYPES_BY_STATUS = {
  created: new Set(["task_created"]),
  queued: new Set(["task_created"]),
  validating: new Set(["validation_started"]),
  running: new Set([
    "case_generated",
    "tool_started",
    "tool_finished",
    "model_call",
    "knowledge_search",
    "summary_generated",
    "agent_log",
    "warning",
  ]),
  parsing: new Set(["case_generated", "tool_started", "tool_finished", "agent_log", "warning"]),
  analyzing: new Set([
    "model_call",
    "knowledge_search",
    "summary_generated",
    "agent_log",
    "warning",
  ]),
  waiting_review: new Set(["review_requested"]),
  completed: new Set(["task_completed", "review_approved"]),
  failed: new Set(["task_failed"]),
  cancelled: new Set(["task_cancelled"]),
};
const STATUS_COPY = {
  created: {
    kind: "attention",
    action: "hold",
    title: "任务已记录，尚未进入执行",
    detail: "控制内核尚未提供可验证的活动观察；界面保持静止。",
  },
  queued: {
    kind: "attention",
    action: "hold",
    title: "任务正在等待执行资源",
    detail: "当前只有排队事实，没有正在执行的可靠心跳。",
  },
  validating: {
    kind: "validating",
    title: "正在核验执行边界",
    detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
  },
  running: {
    kind: "working",
    title: "正在处理受控工作对象",
    detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
  },
  parsing: {
    kind: "working",
    title: "正在解析受控工作对象",
    detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
  },
  analyzing: {
    kind: "working",
    title: "正在分析受控工作对象",
    detail: "当前观察绑定了任务修订、执行世代和只读工作对象。",
  },
  waiting_review: {
    kind: "attention",
    action: "hold",
    title: "可逆工作已完成，等待真人检查",
    detail: "系统不会把待评审草稿自动升级为正式交付。",
  },
  completed: {
    kind: "preview",
    action: "render",
    title: "可查看已冻结的任务产物",
    detail: "任务终态与当前产物引用一致；正式签发仍只由真人完成。",
  },
  failed: {
    kind: "failed",
    action: "stop",
    title: "执行已经失败并停止",
    detail: "失败事实被保留；界面不会播放仍在执行的动画。",
  },
  cancelled: {
    kind: "stopped",
    action: "stop",
    title: "执行已经停止",
    detail: "取消事实被保留；已有只读对象仍可用于检查。",
  },
};
const ACTION_COPY = {
  guard: "正在核验受控工作对象",
  inspect: "正在核对受控工作对象",
  rewrite: "正在生成可逆修改稿",
  map: "正在整理可追溯关系",
};
const SHA256 = /^[a-f0-9]{64}$/i;
const SHA256_REF = /^sha256:[a-f0-9]{64}$/i;
const EXECUTION_REALITIES = new Set(["REAL", "MOCK", "TEST"]);
const BACKEND_KINDS = new Set(["execution-broker", "mock", "test"]);
const REALITY_WITNESS_REF = /^(backend-receipt|sandbox-witness|mock-seal|test-fixture|admission-receipt|running-witness|collect-witness|result-witness|failure-witness|termination-witness):sha256:[a-f0-9]{64}$/i;
const REALITY_POLICIES = {
  REAL: {
    backendKind: "execution-broker",
    verification: "verified",
    requiredRefPrefixes: ["backend-receipt:", "sandbox-witness:"],
  },
  MOCK: {
    backendKind: "mock",
    verification: "declared",
    requiredRefPrefixes: ["mock-seal:"],
  },
  TEST: {
    backendKind: "test",
    verification: "declared",
    requiredRefPrefixes: ["test-fixture:"],
  },
};
const WITNESS_PHASE_BY_STATUS = {
  created: "admission",
  queued: "admission",
  validating: "activity",
  running: "activity",
  parsing: "activity",
  analyzing: "activity",
  waiting_review: "review-ready",
  completed: "result",
  failed: "failure",
  cancelled: "termination",
};
const REAL_PHASE_REF_PREFIX = {
  admission: "admission-receipt:",
  activity: "running-witness:",
  "review-ready": "collect-witness:",
  result: "result-witness:",
  failure: "failure-witness:",
  termination: "termination-witness:",
};

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isText(value, maxLength = 200) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maxLength;
}

function isIsoDate(value) {
  return isText(value, 64) && Number.isFinite(Date.parse(value));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map((item) => canonicalize(item));
  if (!isObject(value)) return value;
  return Object.fromEntries(
    Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
  );
}

function fingerprint(value) {
  return JSON.stringify(canonicalize(value));
}

function addDiagnostic(diagnostics, code, severity, source, blocksObservation) {
  if (diagnostics.some((item) => item.code === code && item.source === source)) return;
  diagnostics.push({ code, severity, source, blocksObservation });
}

function hasBlockingDiagnostic(diagnostics) {
  return diagnostics.some((item) => item.blocksObservation === true);
}

function validBinding(binding) {
  return (
    isObject(binding)
    && binding.source === "control-kernel"
    && isText(binding.taskId, 120)
    && isText(binding.taskRevision, 120)
    && isText(binding.executionEpoch, 120)
  );
}

function validStep(step) {
  if (!isObject(step)) return false;
  if (!Number.isInteger(step.current) || !Number.isInteger(step.total)) return false;
  if (step.current < 0 || step.total < 1 || step.current > step.total || step.total > 20) return false;
  return (
    step.label === undefined
    || (isText(step.label, 64) && !step.label.includes("%"))
  );
}

function validSnapshotExecutionFact(executionFact) {
  if (
    !isObject(executionFact)
    || !["partial", "verified"].includes(executionFact.availability)
    || !(
      executionFact.executionId === null
      || isText(executionFact.executionId, 80)
    )
    || !(
      executionFact.observationRevision === null
      || (
        Number.isSafeInteger(executionFact.observationRevision)
        && executionFact.observationRevision >= 0
      )
    )
    || !(executionFact.backendId === null || isText(executionFact.backendId, 120))
    || !(executionFact.backendKind === null || BACKEND_KINDS.has(executionFact.backendKind))
    || !(
      executionFact.backendAdapterId === null
      || isText(executionFact.backendAdapterId, 120)
    )
    || !(
      executionFact.backendAdapterVersion === null
      || isText(executionFact.backendAdapterVersion, 80)
    )
    || !(executionFact.reality === null || EXECUTION_REALITIES.has(executionFact.reality))
    || !(
      executionFact.realityWitnessId === null
      || isText(executionFact.realityWitnessId, 120)
    )
    || !(
      executionFact.realityWitnessPhase === null
      || isText(executionFact.realityWitnessPhase, 40)
    )
    || !(
      executionFact.realityWitnessVerification === null
      || ["verified", "declared"].includes(executionFact.realityWitnessVerification)
    )
    || !(
      executionFact.realityWitnessObservedAt === null
      || isIsoDate(executionFact.realityWitnessObservedAt)
    )
    || !(
      executionFact.realityWitnessRefs === null
      || (
        Array.isArray(executionFact.realityWitnessRefs)
        && executionFact.realityWitnessRefs.length > 0
        && executionFact.realityWitnessRefs.length <= 20
        && executionFact.realityWitnessRefs.every((ref) => (
          isText(ref, 200) && REALITY_WITNESS_REF.test(ref)
        ))
      )
    )
  ) {
    return false;
  }
  const witnessFields = [
    executionFact.executionId,
    executionFact.observationRevision,
    executionFact.backendId,
    executionFact.backendKind,
    executionFact.backendAdapterId,
    executionFact.backendAdapterVersion,
    executionFact.reality,
    executionFact.realityWitnessId,
    executionFact.realityWitnessPhase,
    executionFact.realityWitnessVerification,
    executionFact.realityWitnessObservedAt,
    executionFact.realityWitnessRefs,
  ];
  return executionFact.availability === "verified"
    ? witnessFields.every((value) => value !== null)
    : witnessFields.every((value) => value === null);
}

function readSnapshotManifest(
  readSnapshot,
  binding,
  taskEvents,
  executionRun,
  artifacts,
  knowledgeEvidence,
  diagnostics,
) {
  if (
    !isObject(readSnapshot)
    || !SHA256_REF.test(readSnapshot.factSetDigest || "")
    || !isIsoDate(readSnapshot.capturedAt)
    || readSnapshot.taskId !== binding.taskId
    || readSnapshot.taskRevision !== binding.taskRevision
    || readSnapshot.executionEpoch !== binding.executionEpoch
    || !isObject(readSnapshot.taskEventWindow)
    || !Number.isSafeInteger(readSnapshot.taskEventWindow.offset)
    || readSnapshot.taskEventWindow.offset < 0
    || !Array.isArray(readSnapshot.taskEventWindow.eventIds)
    || !readSnapshot.taskEventWindow.eventIds.every((eventId) => isText(eventId, 120))
    || !validSnapshotExecutionFact(readSnapshot.executionFact)
    || !Array.isArray(readSnapshot.artifactFacts)
    || readSnapshot.artifactFacts.length > 100
    || !readSnapshot.artifactFacts.every((artifact) => (
      isObject(artifact)
      && isText(artifact.artifactId, 120)
      && (artifact.sha256 === null || SHA256.test(artifact.sha256))
    ))
    || !Array.isArray(readSnapshot.knowledgeRefs)
    || readSnapshot.knowledgeRefs.length > 400
    || !readSnapshot.knowledgeRefs.every((ref) => isText(ref, 200))
  ) {
    addDiagnostic(diagnostics, "snapshot_invalid", "error", "snapshot", true);
    return null;
  }
  const actualEventIds = isObject(taskEvents) && Array.isArray(taskEvents.items)
    ? taskEvents.items.map((event) => event?.event_id)
    : null;
  if (
    !isObject(taskEvents)
    || taskEvents.offset !== readSnapshot.taskEventWindow.offset
    || fingerprint(actualEventIds) !== fingerprint(readSnapshot.taskEventWindow.eventIds)
  ) {
    addDiagnostic(diagnostics, "snapshot_manifest_mismatch", "error", "snapshot", true);
  }
  const actualExecutionFact = {
    availability: executionRun?.availability,
    executionId: executionRun?.execution_id ?? null,
    observationRevision: executionRun?.observation_revision ?? null,
    backendId: executionRun?.backend?.backend_id ?? null,
    backendKind: executionRun?.backend?.backend_kind ?? null,
    backendAdapterId: executionRun?.backend?.adapter_id ?? null,
    backendAdapterVersion: executionRun?.backend?.adapter_version ?? null,
    reality: executionRun?.reality_witness?.reality ?? null,
    realityWitnessId: executionRun?.reality_witness?.witness_id ?? null,
    realityWitnessPhase: executionRun?.reality_witness?.phase ?? null,
    realityWitnessVerification: executionRun?.reality_witness?.verification ?? null,
    realityWitnessObservedAt: executionRun?.reality_witness?.observed_at ?? null,
    realityWitnessRefs: executionRun?.reality_witness?.evidence_refs ?? null,
  };
  if (fingerprint(actualExecutionFact) !== fingerprint(readSnapshot.executionFact)) {
    addDiagnostic(diagnostics, "snapshot_manifest_mismatch", "error", "snapshot", true);
  }
  const actualArtifactFacts = Array.isArray(artifacts)
    ? artifacts.map((artifact) => ({
      artifactId: artifact?.id,
      sha256: SHA256.test(artifact?.sha256 || "") ? artifact.sha256.toLowerCase() : null,
    }))
    : null;
  const expectedArtifactFacts = readSnapshot.artifactFacts.map((artifact) => ({
    artifactId: artifact.artifactId,
    sha256: artifact.sha256?.toLowerCase() ?? null,
  }));
  if (fingerprint(actualArtifactFacts) !== fingerprint(expectedArtifactFacts)) {
    addDiagnostic(diagnostics, "snapshot_manifest_mismatch", "error", "snapshot", true);
  }
  const actualKnowledgeRefs = Array.isArray(knowledgeEvidence)
    ? knowledgeEvidence.flatMap((evidence) => {
      if (
        !isObject(evidence?.payload)
        || !isText(evidence.payload.scope_id, 120)
        || !Array.isArray(evidence.payload.hit_citations)
      ) {
        return [null];
      }
      return evidence.payload.hit_citations.map((rawCitation) => {
        const citation = normalizeCitation(rawCitation);
        return citation ? knowledgeRef(evidence.payload.scope_id, citation) : null;
      });
    })
    : null;
  if (fingerprint(actualKnowledgeRefs) !== fingerprint(readSnapshot.knowledgeRefs)) {
    addDiagnostic(diagnostics, "snapshot_manifest_mismatch", "error", "snapshot", true);
  }
  const capturedAtMs = Date.parse(readSnapshot.capturedAt);
  const factTimes = [
    executionRun?.observed_at,
    executionRun?.reality_witness?.observed_at,
    ...(Array.isArray(taskEvents?.items)
      ? taskEvents.items.map((event) => event?.created_at)
      : []),
    ...(Array.isArray(artifacts)
      ? artifacts.map((artifact) => artifact?.created_at)
      : []),
  ].filter(isIsoDate);
  if (factTimes.some((value) => Date.parse(value) > capturedAtMs)) {
    addDiagnostic(diagnostics, "snapshot_time_inconsistent", "error", "snapshot", true);
  }
  return readSnapshot;
}

function readTaskEvents(taskEvents, binding, diagnostics) {
  const result = new Map();
  if (
    !isObject(taskEvents)
    || !Number.isSafeInteger(taskEvents.offset)
    || taskEvents.offset < 0
    || !Array.isArray(taskEvents.items)
    || taskEvents.items.length > 2000
  ) {
    addDiagnostic(diagnostics, "task_event_page_invalid", "error", "task_events", true);
    return result;
  }

  taskEvents.items.forEach((event, index) => {
    if (
      !isObject(event)
      || !isText(event.event_id, 120)
      || !isText(event.task_id, 120)
      || !TASK_EVENT_TYPES.has(event.event_type)
      || !TASK_EVENT_LEVELS.has(event.level)
      || !isIsoDate(event.created_at)
    ) {
      addDiagnostic(diagnostics, "task_event_invalid", "error", "task_events", true);
      return;
    }
    if (event.task_id !== binding.taskId) {
      addDiagnostic(diagnostics, "task_event_identity_mismatch", "error", "task_events", true);
      return;
    }
    const existing = result.get(event.event_id);
    if (existing && fingerprint(existing.event) !== fingerprint(event)) {
      addDiagnostic(diagnostics, "task_event_id_conflict", "error", "task_events", true);
      return;
    }
    if (!existing) {
      result.set(event.event_id, {
        event,
        ordinal: taskEvents.offset + index,
      });
    }
  });
  return result;
}

function readExecutionReality(executionRun, diagnostics) {
  const backend = executionRun.backend;
  if (!isObject(backend)) {
    addDiagnostic(diagnostics, "execution_backend_missing", "error", "execution_run", true);
    return null;
  }
  if (
    !isText(backend.backend_id, 120)
    || !BACKEND_KINDS.has(backend.backend_kind)
    || !isText(backend.adapter_id, 120)
    || !isText(backend.adapter_version, 80)
  ) {
    addDiagnostic(diagnostics, "execution_backend_invalid", "error", "execution_run", true);
    return null;
  }

  const witness = executionRun.reality_witness;
  if (!isObject(witness)) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_missing",
      "error",
      "execution_run",
      true,
    );
    return null;
  }
  if (
    !isText(witness.witness_id, 120)
    || !EXECUTION_REALITIES.has(witness.reality)
    || !isText(witness.phase, 40)
    || !["verified", "declared"].includes(witness.verification)
    || !isText(witness.execution_id, 80)
    || !isText(witness.execution_epoch, 120)
    || !isText(witness.backend_id, 120)
    || !isIsoDate(witness.observed_at)
    || !Array.isArray(witness.evidence_refs)
    || witness.evidence_refs.length === 0
    || witness.evidence_refs.length > 20
    || !witness.evidence_refs.every((ref) => (
      isText(ref, 200) && REALITY_WITNESS_REF.test(ref)
    ))
  ) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_invalid",
      "error",
      "execution_run",
      true,
    );
    return null;
  }
  if (
    witness.execution_id !== executionRun.execution_id
    || witness.execution_epoch !== executionRun.execution_epoch
    || witness.backend_id !== backend.backend_id
  ) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_identity_mismatch",
      "error",
      "execution_run",
      true,
    );
    return null;
  }

  const policy = REALITY_POLICIES[witness.reality];
  if (
    backend.backend_kind !== policy.backendKind
    || witness.verification !== policy.verification
    || policy.requiredRefPrefixes.some((prefix) => (
      !witness.evidence_refs.some((ref) => ref.startsWith(prefix))
    ))
  ) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_policy_conflict",
      "error",
      "execution_run",
      true,
    );
    return null;
  }
  if (witness.phase !== WITNESS_PHASE_BY_STATUS[executionRun.status]) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_state_conflict",
      "error",
      "execution_run",
      true,
    );
    return null;
  }
  const phaseRefPrefix = REAL_PHASE_REF_PREFIX[witness.phase];
  if (
    witness.reality === "REAL"
    && (
      !phaseRefPrefix
      || !witness.evidence_refs.some((ref) => ref.startsWith(phaseRefPrefix))
    )
  ) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_phase_evidence_missing",
      "error",
      "execution_run",
      true,
    );
    return null;
  }
  if (Date.parse(witness.observed_at) > Date.parse(executionRun.observed_at)) {
    addDiagnostic(
      diagnostics,
      "execution_reality_witness_time_invalid",
      "error",
      "execution_run",
      true,
    );
    return null;
  }

  return { backend, witness };
}

function readExecutionRun(executionRun, binding, taskEventMap, diagnostics) {
  if (!isObject(executionRun)) {
    addDiagnostic(diagnostics, "execution_run_missing", "error", "execution_run", true);
    return null;
  }
  if (executionRun.availability === "partial") {
    addDiagnostic(diagnostics, "execution_run_partial", "error", "execution_run", true);
    return null;
  }
  if (executionRun.availability !== "verified") {
    addDiagnostic(diagnostics, "execution_run_invalid", "error", "execution_run", true);
    return null;
  }
  if (
    !isText(executionRun.execution_id, 80)
    || !isText(executionRun.task_id, 120)
    || !isText(executionRun.task_revision, 120)
    || !isText(executionRun.execution_epoch, 120)
    || !Number.isSafeInteger(executionRun.observation_revision)
    || executionRun.observation_revision < 0
    || !isIsoDate(executionRun.observed_at)
    || !TASK_STATUSES.has(executionRun.status)
    || !validStep(executionRun.step)
    || !isText(executionRun.current_event_id, 120)
    || !isText(executionRun.current_object_ref, 160)
  ) {
    addDiagnostic(diagnostics, "execution_run_invalid", "error", "execution_run", true);
    return null;
  }
  if (
    executionRun.task_id !== binding.taskId
    || executionRun.task_revision !== binding.taskRevision
    || executionRun.execution_epoch !== binding.executionEpoch
  ) {
    addDiagnostic(diagnostics, "execution_run_identity_mismatch", "error", "execution_run", true);
    return null;
  }
  const reality = readExecutionReality(executionRun, diagnostics);
  if (!reality) return null;

  const eventRecord = taskEventMap.get(executionRun.current_event_id);
  if (!eventRecord) {
    addDiagnostic(diagnostics, "execution_event_unresolved", "error", "execution_run", true);
    return null;
  }
  if (!EVENT_TYPES_BY_STATUS[executionRun.status].has(eventRecord.event.event_type)) {
    addDiagnostic(diagnostics, "execution_event_state_conflict", "error", "execution_run", true);
    return null;
  }
  if (Date.parse(executionRun.observed_at) < Date.parse(eventRecord.event.created_at)) {
    addDiagnostic(diagnostics, "execution_observation_precedes_event", "error", "execution_run", true);
    return null;
  }

  if (
    ["running", "parsing", "analyzing"].includes(executionRun.status)
    && !ACTIVE_ACTIONS.has(executionRun.action)
  ) {
    addDiagnostic(diagnostics, "execution_action_invalid", "error", "execution_run", true);
    return null;
  }
  if (executionRun.status === "validating" && !VALIDATING_ACTIONS.has(executionRun.action)) {
    addDiagnostic(diagnostics, "execution_action_invalid", "error", "execution_run", true);
    return null;
  }
  return { run: executionRun, eventRecord, ...reality };
}

function readArtifacts(artifacts, binding, diagnostics) {
  const result = new Map();
  if (!Array.isArray(artifacts) || artifacts.length > 100) {
    addDiagnostic(diagnostics, "artifact_set_invalid", "error", "artifact", true);
    return result;
  }
  for (const artifact of artifacts) {
    if (!isObject(artifact) || !isText(artifact.id, 120) || !isText(artifact.filename, 120)) {
      addDiagnostic(diagnostics, "artifact_invalid", "error", "artifact", true);
      continue;
    }
    if (artifact.task_id === undefined) {
      addDiagnostic(
        diagnostics,
        "artifact_identity_unverifiable",
        "warning",
        "artifact",
        false,
      );
    } else if (artifact.task_id !== binding.taskId) {
      addDiagnostic(diagnostics, "artifact_identity_mismatch", "error", "artifact", true);
      continue;
    }

    const digest = artifact.sha256;
    if (!SHA256.test(digest || "")) {
      addDiagnostic(diagnostics, "artifact_digest_missing", "warning", "artifact", false);
      continue;
    }
    const classification = artifact.classification ?? artifact.data_classification;
    if (
      !Number.isSafeInteger(artifact.size_bytes)
      || artifact.size_bytes < 0
      || !["internal", "sensitive"].includes(classification)
    ) {
      addDiagnostic(diagnostics, "artifact_invalid", "error", "artifact", true);
      continue;
    }

    const key = `file:${artifact.id}`;
    const normalized = {
      id: artifact.id,
      filename: artifact.filename,
      kind: isText(artifact.kind, 40) ? artifact.kind : "output",
      sizeBytes: artifact.size_bytes,
      sha256: digest.toLowerCase(),
      classification,
    };
    const existing = result.get(key);
    if (existing && fingerprint(existing) !== fingerprint(normalized)) {
      addDiagnostic(diagnostics, "artifact_id_conflict", "error", "artifact", true);
      continue;
    }
    result.set(key, normalized);
  }
  return result;
}

function normalizeCitation(citation) {
  if (
    !isObject(citation)
    || !isText(citation.chunk_id, 120)
    || !isText(citation.source, 120)
    || !SHA256.test(citation.fingerprint || "")
  ) {
    return null;
  }
  return {
    chunkId: citation.chunk_id,
    source: citation.source,
    fingerprint: citation.fingerprint.toLowerCase(),
  };
}

function knowledgeRef(scopeId, citation) {
  return [
    "knowledge:",
    encodeURIComponent(scopeId),
    ":",
    encodeURIComponent(citation.source),
    ":",
    encodeURIComponent(citation.chunkId),
    "@",
    citation.fingerprint,
  ].join("");
}

function readKnowledgeEvidence(knowledgeEvidence, binding, taskEventMap, diagnostics) {
  const refsByEvent = new Map();
  if (!Array.isArray(knowledgeEvidence) || knowledgeEvidence.length > 20) {
    addDiagnostic(diagnostics, "knowledge_evidence_set_invalid", "error", "knowledge", true);
    return refsByEvent;
  }

  let hasCitation = false;
  for (const evidence of knowledgeEvidence) {
    if (
      !isObject(evidence)
      || !isText(evidence.event_id, 120)
      || evidence.task_id !== binding.taskId
      || evidence.event_type !== "knowledge_search"
      || !isObject(evidence.payload)
      || !isText(evidence.payload.scope_id, 120)
      || !Array.isArray(evidence.payload.hit_citations)
      || evidence.payload.hit_citations.length > 20
    ) {
      const code = isObject(evidence) && evidence.task_id !== binding.taskId
        ? "knowledge_evidence_identity_mismatch"
        : "knowledge_evidence_invalid";
      addDiagnostic(diagnostics, code, "error", "knowledge", true);
      continue;
    }
    const taskEventRecord = taskEventMap.get(evidence.event_id);
    if (
      !taskEventRecord
      || taskEventRecord.event.event_type !== "knowledge_search"
      || !isObject(taskEventRecord.event.payload)
    ) {
      addDiagnostic(diagnostics, "knowledge_event_unresolved", "error", "knowledge", true);
      continue;
    }

    const citations = evidence.payload.hit_citations.map(normalizeCitation);
    if (citations.some((item) => item === null)) {
      addDiagnostic(diagnostics, "knowledge_citation_invalid", "error", "knowledge", true);
      continue;
    }
    const taskEventCitations = Array.isArray(taskEventRecord.event.payload.hit_citations)
      ? taskEventRecord.event.payload.hit_citations.map(normalizeCitation)
      : [];
    if (
      evidence.payload.scope_id !== taskEventRecord.event.payload.scope_id
      || taskEventCitations.some((item) => item === null)
      || fingerprint(citations) !== fingerprint(taskEventCitations)
    ) {
      addDiagnostic(diagnostics, "knowledge_evidence_event_mismatch", "error", "knowledge", true);
      continue;
    }

    const refs = citations.map((citation) => knowledgeRef(evidence.payload.scope_id, citation));
    if (refs.some((ref) => ref.length > 200)) {
      addDiagnostic(diagnostics, "knowledge_reference_too_long", "error", "knowledge", true);
      continue;
    }
    refsByEvent.set(evidence.event_id, refs);
    hasCitation ||= refs.length > 0;
  }

  // Existing knowledge_search provenance can prove what was retrieved, but it
  // cannot prove KnowledgeVersion effectiveness, issuer authority, or task-time
  // applicability. Keep that limitation visible without blocking observation of
  // the retrieval action itself.
  if (hasCitation) {
    addDiagnostic(
      diagnostics,
      "knowledge_authority_unresolved",
      "warning",
      "knowledge",
      false,
    );
  }
  return refsByEvent;
}

function observerCopy(run) {
  const copy = STATUS_COPY[run.status];
  if (["running", "parsing", "analyzing", "validating"].includes(run.status)) {
    return {
      ...copy,
      action: run.action,
      title: ACTION_COPY[run.action] || copy.title,
    };
  }
  return copy;
}

function previewForArtifact(artifact) {
  const objectKind = artifact.kind === "input" ? "输入对象" : "产物对象";
  return {
    kind: `artifact-${artifact.kind}`.slice(0, 40),
    title: artifact.filename,
    caption: `${objectKind} · ${artifact.classification} · ${artifact.sizeBytes} B`,
    primary: `SHA-256 ${artifact.sha256.slice(0, 12)}…`,
    secondary: "只读对象元数据；内容结论仍须经过产物、依据与交付门核验。",
  };
}

export function adaptRuntimeFactsToObserver(facts) {
  const diagnostics = [];
  if (!isObject(facts) || !validBinding(facts.binding)) {
    addDiagnostic(diagnostics, "binding_invalid", "error", "binding", true);
    return { observerEvents: [], diagnostics };
  }

  const { binding } = facts;
  const readSnapshot = readSnapshotManifest(
    facts.readSnapshot,
    binding,
    facts.taskEvents,
    facts.executionRun,
    facts.artifacts,
    facts.knowledgeEvidence,
    diagnostics,
  );
  const taskEventMap = readTaskEvents(facts.taskEvents, binding, diagnostics);
  const execution = readExecutionRun(
    facts.executionRun,
    binding,
    taskEventMap,
    diagnostics,
  );
  const artifactMap = readArtifacts(facts.artifacts, binding, diagnostics);
  const knowledgeRefs = readKnowledgeEvidence(
    facts.knowledgeEvidence,
    binding,
    taskEventMap,
    diagnostics,
  );

  if (!execution) return { observerEvents: [], diagnostics };
  const artifact = artifactMap.get(execution.run.current_object_ref);
  if (!artifact) {
    addDiagnostic(diagnostics, "current_object_unresolved", "error", "artifact", true);
  }
  if (hasBlockingDiagnostic(diagnostics) || !artifact) {
    return { observerEvents: [], diagnostics };
  }

  const copy = observerCopy(execution.run);
  const taskEventRef = [
    "task-event:",
    execution.eventRecord.event.event_id,
    "@ordinal:",
    execution.eventRecord.ordinal,
  ].join("");
  const executionRef = [
    "execution:",
    execution.run.execution_id,
    "@observation:",
    execution.run.observation_revision,
  ].join("");
  const backendRef = [
    "backend:",
    execution.backend.backend_id,
    "@adapter:",
    execution.backend.adapter_id,
    ":",
    execution.backend.adapter_version,
  ].join("");
  const realityRef = [
    "reality-witness:",
    execution.witness.reality,
    ":",
    execution.witness.witness_id,
  ].join("");
  const artifactRef = [
    "artifact:",
    artifact.id,
    "@sha256:",
    artifact.sha256,
  ].join("");
  const snapshotRef = [
    "read-snapshot:",
    readSnapshot.factSetDigest,
  ].join("");
  const evidenceRefs = [...new Set([
    snapshotRef,
    taskEventRef,
    executionRef,
    backendRef,
    realityRef,
    ...execution.witness.evidence_refs,
    artifactRef,
    ...(knowledgeRefs.get(execution.run.current_event_id) || []),
  ])];
  if (evidenceRefs.some((ref) => !isText(ref, 200))) {
    addDiagnostic(
      diagnostics,
      "observer_reference_too_long",
      "error",
      "adapter",
      true,
    );
    return { observerEvents: [], diagnostics };
  }

  return {
    observerEvents: [
      {
        contractVersion: OBSERVER_CONTRACT_VERSION,
        source: "control-kernel",
        eventId: `observer:${execution.run.execution_id}:${execution.run.observation_revision}`,
        taskId: binding.taskId,
        taskRevision: binding.taskRevision,
        executionEpoch: binding.executionEpoch,
        sequence: execution.run.observation_revision,
        observedAt: execution.run.observed_at,
        reality: execution.witness.reality,
        kind: copy.kind,
        action: copy.action,
        title: copy.title,
        detail: copy.detail,
        step: { ...execution.run.step },
        preview: previewForArtifact(artifact),
        evidenceRefs,
      },
    ],
    diagnostics,
  };
}
