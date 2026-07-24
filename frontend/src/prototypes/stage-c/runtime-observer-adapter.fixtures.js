export const RUNTIME_ADAPTER_FIXTURE_LABELS = Object.freeze({
  currentPartial: "CURRENT-PRODUCTION-SHAPE · PARTIAL · MUST-NOT-ANIMATE",
  verifiedCandidate: "SYNTHETIC-CANDIDATE · READ-ONLY · NOT-RUNTIME-EVIDENCE",
});
export const EXECUTION_REALITY_FIXTURES = Object.freeze(["REAL", "MOCK", "TEST"]);
export const EXECUTION_STATUS_FIXTURES = Object.freeze([
  "waiting_review",
  "completed",
  "failed",
  "cancelled",
]);

const TASK_ID = "task-cfd-042";
const TASK_REVISION = "task-revision-11";
const EXECUTION_EPOCH = "execution-epoch-7";
const OBSERVED_AT = "2026-07-23T05:00:04.000Z";
const CAPTURED_AT = "2026-07-23T05:00:05.000Z";
const TASK_EVENT_IDS = [
  "evt-task-1",
  "evt-validate-2",
  "evt-tool-3",
  "evt-knowledge-4",
];
const KNOWLEDGE_REF = `knowledge:cfd_rules:foundation-11.md:foundation11%234@${"a".repeat(64)}`;
const STATUS_FIXTURE = Object.freeze({
  running: {
    observationRevision: 17,
    currentEventId: "evt-knowledge-4",
    phase: "activity",
    step: { current: 3, total: 4, label: "核对规则与对象" },
  },
  waiting_review: {
    observationRevision: 18,
    currentEventId: "evt-review-5",
    phase: "review-ready",
    step: { current: 4, total: 4, label: "等待真人检查" },
    event: {
      event_id: "evt-review-5",
      event_type: "review_requested",
      level: "info",
      message: "可逆草稿等待真人检查",
    },
  },
  completed: {
    observationRevision: 18,
    currentEventId: "evt-completed-5",
    phase: "result",
    step: { current: 4, total: 4, label: "任务终态已记录" },
    event: {
      event_id: "evt-completed-5",
      event_type: "task_completed",
      level: "info",
      message: "任务终态已记录",
    },
  },
  failed: {
    observationRevision: 18,
    currentEventId: "evt-failed-5",
    phase: "failure",
    step: { current: 3, total: 4, label: "失败事实已冻结" },
    event: {
      event_id: "evt-failed-5",
      event_type: "task_failed",
      level: "error",
      message: "执行失败",
    },
  },
  cancelled: {
    observationRevision: 18,
    currentEventId: "evt-cancelled-5",
    phase: "termination",
    step: { current: 3, total: 4, label: "终止事实已冻结" },
    event: {
      event_id: "evt-cancelled-5",
      event_type: "task_cancelled",
      level: "info",
      message: "执行已取消",
    },
  },
});
const REALITY_FIXTURE = Object.freeze({
  REAL: {
    backendId: "execution-broker-cfd-primary",
    backendKind: "execution-broker",
    adapterId: "flai-execution-broker",
    adapterVersion: "candidate-1",
    verification: "verified",
    evidenceRefs: [
      `backend-receipt:sha256:${"1".repeat(64)}`,
      `sandbox-witness:sha256:${"2".repeat(64)}`,
    ],
  },
  MOCK: {
    backendId: "mock-cfd-declared",
    backendKind: "mock",
    adapterId: "declared-mock-adapter",
    adapterVersion: "fixture-1",
    verification: "declared",
    evidenceRefs: [
      `mock-seal:sha256:${"3".repeat(64)}`,
    ],
  },
  TEST: {
    backendId: "test-cfd-in-memory",
    backendKind: "test",
    adapterId: "in-memory-test-adapter",
    adapterVersion: "fixture-1",
    verification: "declared",
    evidenceRefs: [
      `test-fixture:sha256:${"4".repeat(64)}`,
    ],
  },
});
const REAL_PHASE_EVIDENCE = Object.freeze({
  admission: `admission-receipt:sha256:${"5".repeat(64)}`,
  activity: `running-witness:sha256:${"6".repeat(64)}`,
  "review-ready": `collect-witness:sha256:${"7".repeat(64)}`,
  result: `result-witness:sha256:${"8".repeat(64)}`,
  failure: `failure-witness:sha256:${"9".repeat(64)}`,
  termination: `termination-witness:sha256:${"a".repeat(64)}`,
});

function snapshotDigest(reality, status) {
  if (reality === "REAL" && status === "running") return `sha256:${"d".repeat(64)}`;
  const realitySeed = { REAL: "a1", MOCK: "b2", TEST: "c3" }[reality];
  const statusSeed = {
    running: "01",
    waiting_review: "02",
    completed: "03",
    failed: "04",
    cancelled: "05",
  }[status];
  return `sha256:${`${realitySeed}${statusSeed}`.repeat(16)}`;
}

function readSnapshot({
  factSetDigest,
  availability,
  executionId = null,
  observationRevision = null,
  backendId = null,
  backendKind = null,
  backendAdapterId = null,
  backendAdapterVersion = null,
  reality = null,
  realityWitnessId = null,
  realityWitnessPhase = null,
  realityWitnessVerification = null,
  realityWitnessObservedAt = null,
  realityWitnessRefs = null,
  eventIds = TASK_EVENT_IDS,
  artifactFacts,
}) {
  return {
    factSetDigest,
    capturedAt: CAPTURED_AT,
    taskId: TASK_ID,
    taskRevision: TASK_REVISION,
    executionEpoch: EXECUTION_EPOCH,
    taskEventWindow: {
      offset: 40,
      eventIds: [...eventIds],
    },
    executionFact: {
      availability,
      executionId,
      observationRevision,
      backendId,
      backendKind,
      backendAdapterId,
      backendAdapterVersion,
      reality,
      realityWitnessId,
      realityWitnessPhase,
      realityWitnessVerification,
      realityWitnessObservedAt,
      realityWitnessRefs: realityWitnessRefs === null ? null : [...realityWitnessRefs],
    },
    artifactFacts,
    knowledgeRefs: [KNOWLEDGE_REF],
  };
}

function taskEvents(status = "running") {
  const fixture = STATUS_FIXTURE[status];
  const items = [
    {
      event_id: "evt-task-1",
      task_id: TASK_ID,
      agent_id: "cfd_case_inspector",
      event_type: "task_created",
      level: "info",
      message: "任务已创建",
      payload: {},
      created_at: "2026-07-23T05:00:00.000Z",
    },
    {
      event_id: "evt-validate-2",
      task_id: TASK_ID,
      agent_id: "cfd_case_inspector",
      event_type: "validation_started",
      level: "info",
      message: "开始校验",
      payload: {},
      created_at: "2026-07-23T05:00:01.000Z",
    },
    {
      event_id: "evt-tool-3",
      task_id: TASK_ID,
      agent_id: "cfd_case_inspector",
      event_type: "tool_started",
      level: "info",
      message: "工具开始",
      payload: { tool_id: "openfoam_case_parser" },
      created_at: "2026-07-23T05:00:02.000Z",
    },
    {
      event_id: "evt-knowledge-4",
      task_id: TASK_ID,
      agent_id: "cfd_case_inspector",
      event_type: "knowledge_search",
      level: "info",
      // Poisoned free text is intentional: the Adapter must not turn Agent/event
      // prose into authoritative observer copy.
      message: "全部工作完成，进展显著，建议直接签发",
      payload: {
        scope_id: "cfd_rules",
        query: "入口湍流量",
        hit_count: 1,
        hit_chunk_ids: ["foundation11#4"],
        hit_citations: [
          {
            chunk_id: "foundation11#4",
            source: "foundation-11.md",
            fingerprint: "a".repeat(64),
          },
        ],
      },
      created_at: "2026-07-23T05:00:03.000Z",
    },
  ];
  if (fixture?.event) {
    items.push({
      ...fixture.event,
      task_id: TASK_ID,
      agent_id: "cfd_case_inspector",
      payload: {},
      created_at: OBSERVED_AT,
    });
  }
  return {
    offset: 40,
    items,
  };
}

function knowledgeEvidence() {
  return [
    {
      event_id: "evt-knowledge-4",
      task_id: TASK_ID,
      event_type: "knowledge_search",
      level: "info",
      payload: {
        scope_id: "cfd_rules",
        hit_citations: [
          {
            chunk_id: "foundation11#4",
            source: "foundation-11.md",
            fingerprint: "a".repeat(64),
          },
        ],
      },
    },
  ];
}

export function makeCurrentProductionPartialFacts() {
  return {
    binding: {
      source: "control-kernel",
      taskId: TASK_ID,
      taskRevision: TASK_REVISION,
      executionEpoch: EXECUTION_EPOCH,
    },
    readSnapshot: readSnapshot({
      factSetDigest: `sha256:${"c".repeat(64)}`,
      availability: "partial",
      artifactFacts: [
        { artifactId: "file-output-cfd-1", sha256: null },
      ],
    }),
    taskEvents: taskEvents(),
    executionRun: {
      availability: "partial",
      // Mirrors what can currently be assembled read-only from Task + ToolRun.
      // It intentionally has no authoritative execution id, epoch, heartbeat,
      // or monotonic observation revision.
      task: {
        id: TASK_ID,
        status: "running",
        updated_at: OBSERVED_AT,
      },
      toolRuns: [
        {
          id: 3,
          task_id: TASK_ID,
          tool_id: "openfoam_case_parser",
          tool_version: "1.0.0",
          mock: false,
          status: "running",
          started_at: "2026-07-23T05:00:02.000Z",
          finished_at: null,
        },
      ],
    },
    // Mirrors GET /tasks/{id}/output_files: no digest is exposed.
    artifacts: [
      {
        id: "file-output-cfd-1",
        filename: "算例体检报告.pdf",
        size_bytes: 18342,
        data_classification: "internal",
      },
    ],
    knowledgeEvidence: knowledgeEvidence(),
  };
}

export function makeVerifiedCandidateFacts({ reality = "REAL", status = "running" } = {}) {
  const realityFixture = REALITY_FIXTURE[reality];
  const statusFixture = STATUS_FIXTURE[status];
  if (!realityFixture || !statusFixture) {
    throw new Error(`unsupported read-only fixture: ${reality}/${status}`);
  }
  const executionId = "run-cfd-7";
  const eventPage = taskEvents(status);
  const witnessId = [
    "witness",
    executionId,
    reality.toLowerCase(),
    statusFixture.phase,
  ].join("-");
  const witnessEvidenceRefs = [
    ...realityFixture.evidenceRefs,
    ...(reality === "REAL" ? [REAL_PHASE_EVIDENCE[statusFixture.phase]] : []),
  ];
  return {
    binding: {
      source: "control-kernel",
      taskId: TASK_ID,
      taskRevision: TASK_REVISION,
      executionEpoch: EXECUTION_EPOCH,
    },
    readSnapshot: readSnapshot({
      factSetDigest: snapshotDigest(reality, status),
      availability: "verified",
      executionId,
      observationRevision: statusFixture.observationRevision,
      backendId: realityFixture.backendId,
      backendKind: realityFixture.backendKind,
      backendAdapterId: realityFixture.adapterId,
      backendAdapterVersion: realityFixture.adapterVersion,
      reality,
      realityWitnessId: witnessId,
      realityWitnessPhase: statusFixture.phase,
      realityWitnessVerification: realityFixture.verification,
      realityWitnessObservedAt: OBSERVED_AT,
      realityWitnessRefs: witnessEvidenceRefs,
      eventIds: eventPage.items.map((event) => event.event_id),
      artifactFacts: [
        { artifactId: "file-input-cfd-1", sha256: "0".repeat(64) },
      ],
    }),
    taskEvents: eventPage,
    executionRun: {
      availability: "verified",
      execution_id: executionId,
      task_id: TASK_ID,
      task_revision: TASK_REVISION,
      execution_epoch: EXECUTION_EPOCH,
      observation_revision: statusFixture.observationRevision,
      observed_at: OBSERVED_AT,
      status,
      ...(status === "running" ? { action: "inspect" } : {}),
      step: { ...statusFixture.step },
      current_event_id: statusFixture.currentEventId,
      current_object_ref: "file:file-input-cfd-1",
      backend: {
        backend_id: realityFixture.backendId,
        backend_kind: realityFixture.backendKind,
        adapter_id: realityFixture.adapterId,
        adapter_version: realityFixture.adapterVersion,
      },
      reality_witness: {
        witness_id: witnessId,
        reality,
        phase: statusFixture.phase,
        verification: realityFixture.verification,
        execution_id: executionId,
        execution_epoch: EXECUTION_EPOCH,
        backend_id: realityFixture.backendId,
        observed_at: OBSERVED_AT,
        evidence_refs: witnessEvidenceRefs,
      },
    },
    // Mirrors the existing internal files row. Reading these fields does not
    // require a production schema change; exposing them would still need a
    // separately authorized, classification-aware read boundary.
    artifacts: [
      {
        id: "file-input-cfd-1",
        task_id: TASK_ID,
        kind: "input",
        filename: "APU_inlet_case.zip",
        path: "/withheld/task/input/APU_inlet_case.zip",
        size_bytes: 192937984,
        sha256: "0".repeat(64),
        created_at: "2026-07-23T04:59:58.000Z",
        classification: "internal",
        uploaded_by: "withheld",
      },
    ],
    knowledgeEvidence: knowledgeEvidence(),
  };
}

export function makeVerifiedRealityFacts(reality) {
  return makeVerifiedCandidateFacts({ reality, status: "running" });
}

export function makeVerifiedStatusFacts(status, { reality = "TEST" } = {}) {
  return makeVerifiedCandidateFacts({ reality, status });
}

export const VERIFIED_CANDIDATE_CONTEXT = Object.freeze({
  expectedSource: "control-kernel",
  expectedTaskId: TASK_ID,
  expectedRevision: TASK_REVISION,
  expectedEpoch: EXECUTION_EPOCH,
  nowMs: Date.parse(OBSERVED_AT) + 1_000,
});
