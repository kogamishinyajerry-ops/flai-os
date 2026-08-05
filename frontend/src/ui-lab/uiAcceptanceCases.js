const VIEWPORTS = {
  desktop: { width: 1440, height: 900, label: "Desktop · 1440 × 900" },
  mobile: { width: 375, height: 812, label: "Mobile · 375 × 812" },
};

const APP_FIXTURE = {
  displayName: "验收工程师",
  conversations: [
    {
      id: "ui-cfd",
      created_by: "验收工程师",
      updated_at: "2026-07-31T06:26:00Z",
      recommendation: {
        decision: "orchestrate",
        goal: "CFD 稳态计算前检查",
      },
    },
    {
      id: "ui-standard",
      created_by: "验收工程师",
      updated_at: "2026-07-30T08:10:00Z",
      recommendation: {
        decision: "orchestrate",
        goal: "标准条款核对",
      },
    },
    {
      id: "ui-mesh",
      created_by: "验收工程师",
      updated_at: "2026-07-29T02:40:00Z",
      recommendation: {
        decision: "orchestrate",
        goal: "网格质量复核",
      },
    },
  ],
};

const LANDING_GUIDE = {
  started: false,
  conversationId: "",
  conversationStatus: null,
  messages: [],
  sending: false,
  reconciliationRequired: false,
};

const ROUTING_RECOMMENDATION = {
  decision: "orchestrate",
  goal: "完成稳态算例开算前复核并形成可签认清单",
  analysis: "系统已从你的描述中识别出输入核对与报告整理两段工作，并自动选择可用能力。",
  workflow: "先核对算例输入与边界条件，再把已核结果整理为工程师可签认的复核清单。",
  agents: [
    {
      agent_id: "cfd_input_check",
      agent_name: "CFD 参数核对 Agent",
      role: "核对输入、边界与求解设置",
      rationale: "任务首先需要结构化检查开算条件。",
      prefilled_inputs: {
        case_scope: "本轮上传的稳态算例",
        review_goal: "开算前完整性复核",
      },
      attachments: [
        { file_id: "file-routing-case", filename: "稳态算例输入表.xlsx" },
      ],
      stripped_fields: [],
      after: [],
    },
    {
      agent_id: "report_draft",
      agent_name: "工程报告草拟 Agent",
      role: "整理可签认的复核清单",
      rationale: "核对结果需要形成统一、可审阅的工程交付物。",
      prefilled_inputs: {
        deliverable: "稳态算例开算前复核清单",
      },
      attachments: [],
      stripped_fields: [],
      after: [0],
    },
  ],
  ignored_attachments: [
    { file_id: "file-routing-note", filename: "旧版背景说明.pdf" },
  ],
  dropped_agents: [],
  capped: false,
};

const ROUTING_SCHEMAS = {
  cfd_input_check: {
    loaded: true,
    version: "0.1.0",
    packageDigest: "a".repeat(64),
    inputMode: "params",
    schema: {
      type: "object",
      required: ["case_scope", "review_goal"],
      properties: {
        case_scope: { type: "string" },
        review_goal: { type: "string" },
      },
    },
  },
  report_draft: {
    loaded: true,
    version: "0.1.0",
    packageDigest: "b".repeat(64),
    inputMode: "params",
    schema: {
      type: "object",
      required: ["deliverable"],
      properties: { deliverable: { type: "string" } },
    },
  },
};

const ROUTING_GUIDE = {
  started: true,
  conversationId: "ui-auto-routing",
  conversationStatus: "active",
  sending: false,
  reconciliationRequired: false,
  agentSchemas: ROUTING_SCHEMAS,
  messages: [
    {
      role: "user",
      content: "帮我核对这批稳态算例能不能开算，并整理一份可签认清单。",
      createdAt: "2026-07-31T06:28:00Z",
      attachments: [
        { id: "file-routing-case", filename: "稳态算例输入表.xlsx" },
        { id: "file-routing-note", filename: "旧版背景说明.pdf" },
      ],
    },
    {
      role: "assistant",
      content: "我已经整理好协作方案。执行前请核对目标，其余能力由系统在后台安排。",
      recommendation: ROUTING_RECOMMENDATION,
      createdAt: "2026-07-31T06:28:12Z",
      fresh: true,
    },
  ],
};

const STREAMING_GUIDE = {
  started: true,
  conversationId: "ui-streaming",
  conversationStatus: "active",
  sending: true,
  reconciliationRequired: false,
  messages: [
    {
      role: "user",
      content: "帮我检查这次稳态计算的输入边界，并告诉我下一步应该怎么做。",
      createdAt: "2026-07-31T06:31:08Z",
    },
    {
      role: "assistant",
      content: "我会按三步推进：\n\n- 核对输入和边界\n- 检查求解控制与收敛判据\n- 标出需要工程师确认的缺口",
      createdAt: "2026-07-31T06:31:10Z",
      streaming: true,
      transient: true,
    },
  ],
};

const PERSISTENCE_UNKNOWN_GUIDE = {
  started: true,
  conversationId: "ui-persistence-unknown",
  conversationStatus: "active",
  sending: false,
  reconciliationRequired: true,
  messages: [
    {
      role: "user",
      content: "继续检查入口总压和温度边界。",
      createdAt: "2026-07-31T06:34:20Z",
      persistenceUnknown: true,
    },
    {
      role: "assistant",
      content: "我正在核对入口条件和约束范围。",
      createdAt: "2026-07-31T06:34:21Z",
      streaming: false,
      persistenceUnknown: true,
      streamError: true,
      streamErrorTitle: "流式中断 · 保存状态待核",
      streamErrorDetail: "网络连接已断开，服务端是否已经保存本轮暂时未知。",
      streamErrorAction: "请刷新会话核对后再继续。",
    },
  ],
};

const FEATURE_ASSET_MAP_SNAPSHOT = {
  schema_version: "feature_asset_map.v1",
  source: {
    kind: "owner_scoped_cold_projection",
    owner_username: "user-ui-acceptance",
    owner_scoped: true,
    read_only: true,
  },
  summary: {
    capability_count: 2,
    asset_candidate_count: 1,
    accepted_candidate_count: 1,
    skill_package_count: 1,
    approved_skill_package_count: 1,
    unresolved_reference_count: 0,
  },
  functionality: {
    work_types: [
      { id: "analysis", total_count: 1 },
      { id: "knowledge", total_count: 1 },
    ],
    domains: [
      { id: "cfd", total_count: 1 },
      { id: "standards", total_count: 1 },
    ],
    capabilities: [
      {
        agent_id: "cfd_input_check",
        name: "CFD 参数核对 Agent",
        summary: "核对输入、边界与求解设置，保留人工裁决点。",
        category: "analysis",
        domain: "cfd",
        specialty: "steady-state",
        launch_kind: "task",
        status: "active",
        maturity: "L1",
        requires_human_review: true,
        tool_count: 1,
        knowledge_scope_count: 1,
        unresolved_reference_count: 0,
        mock_tool_count: 0,
      },
      {
        agent_id: "standard_answer",
        name: "标准条款问答 Agent",
        summary: "依据已审定知识范围回答标准条款问题。",
        category: "knowledge",
        domain: "standards",
        specialty: null,
        launch_kind: "conversation",
        status: "active",
        maturity: "L1",
        requires_human_review: true,
        tool_count: 0,
        knowledge_scope_count: 1,
        unresolved_reference_count: 0,
        mock_tool_count: 0,
      },
    ],
  },
  assets: [
    {
      candidate_id: "asset_candidate_b6f68526b3fdf4a3253f192c",
      candidate_digest: `sha256:${"1".repeat(64)}`,
      revision: 1,
      state: "accepted",
      source: {
        task_id: "task-ui-asset-candidate",
        conversation_id: "ui-asset-work-case",
        agent_id: "cfd_input_check",
        finished_at: "2026-07-31T06:46:30Z",
      },
      task_pattern: {
        title: "稳态算例入口边界复核",
        state: "approved_revision",
        digest: `sha256:${"2".repeat(64)}`,
      },
      skill: {
        name: "入口边界复核方法",
        description: "逐项核对入口总压、总温并保留可签认依据。",
        state: "approved_revision",
        digest: `sha256:${"3".repeat(64)}`,
      },
      skill_package: {
        id: "skill_package_919191919191919191919191",
        name: "cfd-inlet-boundary-review",
        version: "0.1.0",
        package_digest: `sha256:${"4".repeat(64)}`,
        state: "approved",
        reuse_eligible: true,
      },
      workflow: {
        state: "not_formed",
        digest: null,
        gate: "需要组合证据",
      },
      agent: {
        state: "not_formed",
        digest: null,
        gate: "需要 Workflow 与晋级门",
      },
      updated_at: "2026-07-31T06:52:00Z",
    },
  ],
  effects: {
    writes_database: false,
    executes_work: false,
    registers_asset: false,
    promotes_asset: false,
  },
};

const FEATURE_ASSET_MAP_READY = {
  kind: "snapshot",
  snapshot: FEATURE_ASSET_MAP_SNAPSHOT,
  refresh_snapshot: {
    ...FEATURE_ASSET_MAP_SNAPSHOT,
    summary: {
      ...FEATURE_ASSET_MAP_SNAPSHOT.summary,
      asset_candidate_count: 2,
    },
    assets: [
      ...FEATURE_ASSET_MAP_SNAPSHOT.assets,
      {
        candidate_id: "asset_candidate_565656565656565656565656",
        candidate_digest: `sha256:${"5".repeat(64)}`,
        revision: 1,
        state: "awaiting_human_review",
        source: {
          task_id: "task-ui-new-asset-candidate",
          conversation_id: "ui-auto-routing",
          agent_id: "standard_answer",
          finished_at: "2026-07-31T07:01:00Z",
        },
        task_pattern: {
          title: "标准条款依据核对",
          state: "candidate_revision",
          digest: `sha256:${"6".repeat(64)}`,
        },
        skill: {
          name: "条款依据核对方法",
          description: "逐条绑定知识范围与原始条款位置，等待工程师审核。",
          state: "candidate_revision",
          digest: `sha256:${"7".repeat(64)}`,
        },
        skill_package: null,
        workflow: {
          state: "not_formed",
          digest: null,
          gate: "需要接受 Candidate 后再形成隔离包",
        },
        agent: {
          state: "not_formed",
          digest: null,
          gate: "需要 Workflow 与晋级门",
        },
        updated_at: "2026-07-31T07:02:00Z",
      },
    ],
  },
};

const FEATURE_ASSET_MAP_UNAVAILABLE = {
  kind: "error",
  status: 503,
  detail: "来源完整性核验失败（503）",
};

const ASSET_DRAFT_GENERALIZATION = {
  title: "稳态算例入口边界复核",
  trigger: "收到一批待计算的稳态算例，需要在开算前核对入口边界",
  desired_outcome: "形成可逐项签认的入口边界复核清单",
  inputs: ["算例清单", "入口边界条件表"],
  outputs: ["入口边界复核清单"],
  steps: [
    "逐项核对入口总压、总温与工况标识",
    "记录缺失、冲突和需要工程师裁决的边界",
  ],
  evidence_requirements: ["每项结论保留原始表格位置"],
  human_decision_points: ["冲突边界由责任工程师确认采用值"],
  limitations: ["不适用于瞬态工况或未冻结的边界版本"],
};

const ASSET_INTAKE_GENERALIZATION = {
  title: ASSET_DRAFT_GENERALIZATION.title,
  trigger: "",
  desired_outcome: ASSET_DRAFT_GENERALIZATION.desired_outcome,
  inputs: [],
  outputs: [],
  steps: [],
  evidence_requirements: [],
  human_decision_points: [],
  limitations: [],
};

const ASSET_DRAFT_PREVIEW = {
  schema_version: "asset_draft_bundle.v1",
  builder_version: "asset_draft_builder.v1",
  status: "draft",
  work_case: {
    source_kind: "conversation",
    source_id: "ui-asset-work-case",
    source_state: "platform_resolved",
    conversation_status: "active",
    message_count: 2,
    user_message_count: 1,
    attachment_reference_count: 1,
    source_revision: "sha256:60ec7e1447ef98d410d7941a36d78f32391462be8d64ae5cd1b97956c12ea687",
  },
  task_pattern: {
    schema_version: "task_pattern_draft.v1",
    status: "draft",
    derived_from_work_case_revision: "sha256:60ec7e1447ef98d410d7941a36d78f32391462be8d64ae5cd1b97956c12ea687",
    suggested_id: "task_pattern_candidate_b64b31dd0a24",
    content_digest: "sha256:b64b31dd0a24299e75356d315cecea28f07c6aa30a41d8dca2424efff2f3a72c",
    ...ASSET_DRAFT_GENERALIZATION,
  },
  skill: {
    schema_version: "skill_draft.v1",
    status: "draft",
    operationalizes_task_pattern_digest: "sha256:b64b31dd0a24299e75356d315cecea28f07c6aa30a41d8dca2424efff2f3a72c",
    suggested_id: "skill_candidate_2d871c0f1db0",
    content_digest: "sha256:2d871c0f1db02afb35aa625dc1289587f06234756fb84f0a2cf6efeceb427dcf",
    name: ASSET_DRAFT_GENERALIZATION.title,
    description: `${ASSET_DRAFT_GENERALIZATION.desired_outcome}；适用于：${ASSET_DRAFT_GENERALIZATION.trigger}`,
    when_to_use: ASSET_DRAFT_GENERALIZATION.trigger,
    when_not_to_use: ASSET_DRAFT_GENERALIZATION.limitations,
    inputs: ASSET_DRAFT_GENERALIZATION.inputs,
    outputs: ASSET_DRAFT_GENERALIZATION.outputs,
    instructions: ASSET_DRAFT_GENERALIZATION.steps,
    verification: ASSET_DRAFT_GENERALIZATION.evidence_requirements,
    human_boundaries: ASSET_DRAFT_GENERALIZATION.human_decision_points,
  },
  validation: {
    schema_version: "asset_draft_validation.v1",
    policy_version: "core.v1",
    state: "ready_for_human_review",
    blocking_count: 0,
    warning_count: 0,
    issues: [],
  },
  review: {
    required: true,
    ready: true,
    state: "awaiting_human_review",
    decision_state: "not_recorded",
    requirements: [
      "核对草稿是否忠实对应原始 Work Case",
      "核对步骤、输入输出与不适用边界是否真的可复用",
      "核对人工判断点与证据要求是否充分",
    ],
  },
  generation: { kind: "deterministic_projection", llm_used: false },
  effects: {
    writes_database: false,
    executes_work: false,
    registers_asset: false,
    promotes_asset: false,
  },
  draft_digest: "sha256:0f3e34cf90fd54358c0bcd2b3beef53821443ceec2ecc87bddca7fb6d759b10f",
};

const ASSET_CANDIDATE = {
  schema_version: "asset_candidate.v1",
  id: "asset_candidate_b6f68526b3fdf4a3253f192c",
  candidate_digest: "sha256:b6f68526b3fdf4a3253f192c6faaed19c272c1550e01de2ff72bf6c5e7f942be",
  bundle_digest: ASSET_DRAFT_PREVIEW.draft_digest,
  lineage_digest: "sha256:de966446007401a0f122b5c240fff89e4a0b48576ca69ba4dafb82bb169e0833",
  revision: 1,
  supersedes_candidate_digest: null,
  state: "awaiting_human_review",
  source: {
    task_id: "task-ui-asset-candidate",
    conversation_id: "ui-asset-work-case",
    task_status: "completed",
    agent_id: "cfd_input_check",
    agent_version: "0.1.0",
    agent_package_digest: "a".repeat(64),
    initiated_by_username: "user-ui-acceptance",
    finished_at: "2026-07-31T06:46:30Z",
  },
  bundle: ASSET_DRAFT_PREVIEW,
  lineage: {
    schema_version: "asset_candidate_lineage.v1",
    task: {
      task_id: "task-ui-asset-candidate",
      agent_id: "cfd_input_check",
      agent_version: "0.1.0",
      agent_package_digest: "a".repeat(64),
      initiated_by_username: "user-ui-acceptance",
      origin: "user",
      terminal_status: "completed",
      finished_at: "2026-07-31T06:46:30Z",
      data_classification: "internal",
      inputs_digest: `sha256:${"e".repeat(64)}`,
      task_snapshot_digest: `sha256:${"f".repeat(64)}`,
    },
    conversation: {
      conversation_id: "ui-asset-work-case",
      work_case_source_revision: ASSET_DRAFT_PREVIEW.work_case.source_revision,
      segment_message_count: 2,
      segment_user_message_count: 1,
    },
    input_files: [
      {
        file_id: "file-boundaries",
        kind: "input",
        sha256: "1".repeat(64),
        size_bytes: 18240,
        classification: "internal",
        source_kind: "work_segment_upload",
        producer_task_id: null,
      },
    ],
    output_files: [
      {
        file_id: "file-boundary-review",
        kind: "output",
        sha256: "2".repeat(64),
        size_bytes: 9376,
        classification: "internal",
        source_kind: "current_task_output",
        producer_task_id: "task-ui-asset-candidate",
      },
    ],
    execution_snapshot: {
      event_id: "execution-ui-asset-candidate",
      event_digest: `sha256:${"4".repeat(64)}`,
      package_snapshot_contract: "agent_package_snapshot.v1",
      package_snapshot_digest: "a".repeat(64),
      input_file_ids_digest: "sha256:a9387721560c36af768dba5aaceb25057a54061d4fd842dc4d39dd351397c604",
      input_files_digest: `sha256:${"6".repeat(64)}`,
      task_inputs_digest: `sha256:${"e".repeat(64)}`,
      execution_evidence_digest: "sha256:a4a226df97c700c88a75af9dc653dc8b916d7bf43ac7549b16eb1fade6d06148",
    },
    signoff: {
      required: false,
      kind: "deterministic_no_review",
      event_id: "task-completed-ui-asset-candidate",
      event_digest: `sha256:${"7".repeat(64)}`,
      signer_username: null,
      execution_evidence_digest: "sha256:a4a226df97c700c88a75af9dc653dc8b916d7bf43ac7549b16eb1fade6d06148",
    },
  },
  proposal_provenance: {
    schema_version: "generalization_proposal_provenance.v1",
    kind: "deterministic_task_projection",
    policy_version: "asset_candidate_policy.v1",
    llm_used: false,
    sources: [
      "work_case_segment",
      "completed_task",
      "agent_package_snapshot",
      "artifact_digests",
      "signoff_evidence",
    ],
  },
  asset_map: {
    task_pattern: {
      state: "candidate_revision",
      digest: ASSET_DRAFT_PREVIEW.task_pattern.content_digest,
    },
    skill: {
      state: "candidate_revision",
      digest: ASSET_DRAFT_PREVIEW.skill.content_digest,
    },
    workflow: {
      state: "not_formed",
      digest: null,
      gate: "需要组合一个或多个已接受 Skill，并明确顺序、依赖和停止条件",
    },
    agent: {
      state: "not_formed",
      digest: null,
      gate: "需要通过 Workflow、Agent Package、评测与人工晋级门",
    },
  },
  decision: null,
  skill_package: null,
  effects: {
    writes_candidate_store: true,
    executes_work: false,
    writes_package_files: false,
    registers_asset: false,
    promotes_asset: false,
  },
  created_at: "2026-07-31T06:47:00Z",
  updated_at: "2026-07-31T06:47:00Z",
};

const ASSET_CANDIDATE_SKILL_PACKAGE = {
  schema_version: "skill_package_revision.v1",
  id: "skill_package_919191919191919191919191",
  name: "cfd-inlet-boundary-review",
  version: "0.1.0",
  package_digest: `sha256:${"9".repeat(64)}`,
  state: "pending_review",
  source: {
    candidate_id: ASSET_CANDIDATE.id,
    candidate_digest: ASSET_CANDIDATE.candidate_digest,
    bundle_digest: ASSET_CANDIDATE.bundle_digest,
    skill_digest: ASSET_CANDIDATE.bundle.skill.content_digest,
    acceptance_event_digest: `sha256:${"8".repeat(64)}`,
    task_id: ASSET_CANDIDATE.source.task_id,
    agent_id: ASSET_CANDIDATE.source.agent_id,
    initiated_by_username: ASSET_CANDIDATE.source.initiated_by_username,
  },
  storage_relpath: `cfd-inlet-boundary-review/0.1.0/${"9".repeat(64)}`,
  files: [
    {
      path: "SKILL.md",
      size_bytes: 317,
      sha256: "0f87242490b4732d2da814678ccf4884d34f31e3693f9ba89f7d7c3d93a6ce20",
    },
    {
      path: "references/provenance.json",
      size_bytes: 215,
      sha256: "9cff91f410fe150746780c1e3430d38a2554af5342d25ef588f51041f02efa73",
    },
    {
      path: "references/skill-revision.json",
      size_bytes: 1117,
      sha256: "1e18c59a7dc32c48a64a0cef0014bf53d5428c45d6976ccbe9909b859cf62b71",
    },
    {
      path: "references/task-pattern-revision.json",
      size_bytes: 1041,
      sha256: "58f7576184aa59bc7283d1f6f7030f8d9cdb53dbbb0b7263ee197b20209fbec8",
    },
  ],
  review: null,
  isolation: {
    zone: "candidate_quarantine",
    registered: false,
    executable: false,
  },
  reuse_eligible: false,
  formation_evidence: {
    schema_version: "composition_eligibility.v1",
    independent_work_case_count: 0,
    required_independent_work_cases: 2,
    workflow_candidate: {
      state: "not_formed",
      eligible: false,
      reason: "requires_independent_composition_evidence",
    },
    agent_candidate: {
      state: "not_formed",
      eligible: false,
      reason: "requires_approved_workflow_revision",
    },
  },
  created_at: "2026-07-31T06:49:00Z",
  updated_at: "2026-07-31T06:49:00Z",
};

const ASSET_CANDIDATE_SKILL_PACKAGE_REVIEW_CONTENT = {
  schema_version: "skill_package_review_content.v1",
  package_id: ASSET_CANDIDATE_SKILL_PACKAGE.id,
  package_digest: ASSET_CANDIDATE_SKILL_PACKAGE.package_digest,
  files: [
    {
      path: "SKILL.md",
      text: `---
name: cfd-inlet-boundary-review
description: 在稳态算例开算前核对入口边界并保留可签认依据。
---

# 入口边界复核

1. 逐项核对入口总压、总温与工况标识。
2. 标出缺失、冲突与必须由责任工程师裁决的边界。
3. 为每项结论保留原始材料位置。
`,
    },
    {
      path: "references/provenance.json",
      text: `${JSON.stringify({
        schema_version: "candidate_skill_package_provenance.v1",
        source_candidate_digest: ASSET_CANDIDATE.candidate_digest,
        source_task_id: ASSET_CANDIDATE.source.task_id,
      }, null, 2)}\n`,
    },
    {
      path: "references/skill-revision.json",
      text: `${JSON.stringify(ASSET_CANDIDATE.bundle.skill, null, 2)}\n`,
    },
    {
      path: "references/task-pattern-revision.json",
      text: `${JSON.stringify(ASSET_CANDIDATE.bundle.task_pattern, null, 2)}\n`,
    },
  ],
};

const ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED = {
  ...ASSET_CANDIDATE_SKILL_PACKAGE,
  state: "approved",
  review: {
    action: "approve",
    reviewed_by: "验收工程师",
    reviewed_by_username: "user-ui-acceptance",
    signer_source: "authenticated_session",
    signer_session_bound: true,
    created_at: "2026-07-31T06:52:00Z",
  },
  reuse_eligible: true,
  updated_at: "2026-07-31T06:52:00Z",
};

const ASSET_CANDIDATE_SKILL_PACKAGE_REJECTED = {
  ...ASSET_CANDIDATE_SKILL_PACKAGE,
  state: "rejected",
  review: {
    action: "reject",
    reviewed_by: "验收工程师",
    reviewed_by_username: "user-ui-acceptance",
    signer_source: "authenticated_session",
    signer_session_bound: true,
    created_at: "2026-07-31T06:52:00Z",
  },
  reuse_eligible: false,
  updated_at: "2026-07-31T06:52:00Z",
};

const ASSET_CANDIDATE_ACCEPTED = {
  ...ASSET_CANDIDATE,
  state: "accepted",
  asset_map: {
    ...ASSET_CANDIDATE.asset_map,
    task_pattern: {
      ...ASSET_CANDIDATE.asset_map.task_pattern,
      state: "approved_revision",
    },
    skill: {
      ...ASSET_CANDIDATE.asset_map.skill,
      state: "approved_revision",
    },
  },
  decision: {
    action: "accept",
    decided_by: "验收工程师",
    decided_by_username: "user-ui-acceptance",
    signer_source: "authenticated_session",
    signer_session_bound: true,
    created_at: "2026-07-31T06:49:00Z",
  },
  skill_package: ASSET_CANDIDATE_SKILL_PACKAGE,
  updated_at: "2026-07-31T06:49:00Z",
};

const ASSET_CANDIDATE_PACKAGE_APPROVED = {
  ...ASSET_CANDIDATE_ACCEPTED,
  skill_package: ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED,
  updated_at: "2026-07-31T06:52:00Z",
};

const ASSET_CANDIDATE_PACKAGE_REJECTED = {
  ...ASSET_CANDIDATE_ACCEPTED,
  skill_package: ASSET_CANDIDATE_SKILL_PACKAGE_REJECTED,
  updated_at: "2026-07-31T06:52:00Z",
};

const ASSET_BLOCKED_GENERALIZATION = {
  ...ASSET_DRAFT_GENERALIZATION,
  evidence_requirements: [],
  human_decision_points: [],
};

const ASSET_BLOCKED_PREVIEW = {
  ...ASSET_DRAFT_PREVIEW,
  task_pattern: {
    ...ASSET_DRAFT_PREVIEW.task_pattern,
    ...ASSET_BLOCKED_GENERALIZATION,
    suggested_id: "task_pattern_candidate_555555555555",
    content_digest: "sha256:5555555555555555555555555555555555555555555555555555555555555555",
  },
  skill: {
    ...ASSET_DRAFT_PREVIEW.skill,
    operationalizes_task_pattern_digest: "sha256:5555555555555555555555555555555555555555555555555555555555555555",
    suggested_id: "skill_candidate_666666666666",
    content_digest: "sha256:6666666666666666666666666666666666666666666666666666666666666666",
    verification: [],
    human_boundaries: [],
  },
  validation: {
    schema_version: "asset_draft_validation.v1",
    policy_version: "core.v1",
    state: "needs_revision",
    blocking_count: 2,
    warning_count: 0,
    issues: [
      {
        code: "skill.human_boundary.required",
        severity: "blocking",
        path: "/skill/human_boundaries",
        message: "至少声明一个必须停下来等待工程师判断的位置",
      },
      {
        code: "skill.verification.required",
        severity: "blocking",
        path: "/skill/verification",
        message: "至少声明一项证明工作已做且可核的依据",
      },
    ],
  },
  review: {
    ...ASSET_DRAFT_PREVIEW.review,
    ready: false,
    state: "not_ready",
  },
  draft_digest: "sha256:7777777777777777777777777777777777777777777777777777777777777777",
};

const ASSET_WORK_GUIDE = {
  started: true,
  conversationId: "ui-asset-work-case",
  conversationStatus: "active",
  sending: false,
  reconciliationRequired: false,
  messages: [
    {
      id: "ui-asset-user-1",
      role: "user",
      content: "核对这批稳态算例的入口边界，并形成复核清单。",
      createdAt: "2026-07-31T06:42:10Z",
      attachments: [{ id: "file-boundaries", filename: "入口边界条件表.xlsx" }],
    },
    {
      id: "ui-asset-assistant-1",
      role: "assistant",
      content: "已按输入完整性、边界适用性和证据位置整理了检查方法。",
      createdAt: "2026-07-31T06:42:18Z",
    },
  ],
};

const ASSET_CANDIDATE_GUIDE = {
  ...ASSET_WORK_GUIDE,
  conversationTasks: [
    {
      id: "task-ui-asset-candidate",
      conversation_id: "ui-asset-work-case",
      agent_id: "cfd_input_check",
      status: "completed",
      origin: "user",
      finished_at: "2026-07-31T06:46:30Z",
    },
  ],
  assetCandidate: ASSET_CANDIDATE,
};

const ASSET_CANDIDATE_ACCEPTED_GUIDE = {
  ...ASSET_CANDIDATE_GUIDE,
  assetCandidate: ASSET_CANDIDATE_ACCEPTED,
  skillPackageReviewContent: ASSET_CANDIDATE_SKILL_PACKAGE_REVIEW_CONTENT,
};

const ASSET_PACKAGE_APPROVED_GUIDE = {
  ...ASSET_CANDIDATE_GUIDE,
  assetCandidate: ASSET_CANDIDATE_PACKAGE_APPROVED,
  skillPackageReviewContent: ASSET_CANDIDATE_SKILL_PACKAGE_REVIEW_CONTENT,
};

const ASSET_PACKAGE_REJECTED_GUIDE = {
  ...ASSET_CANDIDATE_GUIDE,
  assetCandidate: ASSET_CANDIDATE_PACKAGE_REJECTED,
  skillPackageReviewContent: ASSET_CANDIDATE_SKILL_PACKAGE_REVIEW_CONTENT,
};

const SKILL_REUSE_REF = {
  schema_version: "skill_reuse_ref.v1",
  package_id: ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED.id,
  package_version: ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED.version,
  package_digest: ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED.package_digest,
  candidate_digest: ASSET_CANDIDATE.candidate_digest,
  skill_digest: ASSET_CANDIDATE.bundle.skill.content_digest,
  skill_name: ASSET_CANDIDATE_SKILL_PACKAGE_APPROVED.name,
  matched_agent_id: "cfd_input_check",
  review_state: "approved",
  match_policy_version: "skill_reuse_match.v1",
  match_basis_digest: `sha256:${"7".repeat(64)}`,
};

const SKILL_REUSE_RECOMMENDATION = {
  ...ROUTING_RECOMMENDATION,
  skill_reuse: SKILL_REUSE_REF,
};

const SKILL_REUSE_INVALID_RECOMMENDATION = {
  ...ROUTING_RECOMMENDATION,
  skill_reuse: {
    ...SKILL_REUSE_REF,
    model: "manual-selector-must-never-be-trusted",
  },
};

const SKILL_REUSE_GUIDE = {
  ...ROUTING_GUIDE,
  conversationId: "ui-skill-reuse",
  messages: ROUTING_GUIDE.messages.map((message) => (
    message.recommendation
      ? { ...message, recommendation: SKILL_REUSE_RECOMMENDATION }
      : { ...message }
  )),
};

const SKILL_REUSE_INVALID_GUIDE = {
  ...ROUTING_GUIDE,
  conversationId: "ui-skill-reuse-invalid",
  messages: ROUTING_GUIDE.messages.map((message) => (
    message.recommendation
      ? { ...message, recommendation: SKILL_REUSE_INVALID_RECOMMENDATION }
      : { ...message }
  )),
};

function acceptanceCase({
  id,
  label,
  summary,
  viewport,
  guide,
  reviewPoints,
  featureAssetMap = null,
}) {
  const item = {
    id,
    label,
    summary,
    viewport,
    reviewPoints,
    app: APP_FIXTURE,
    guide,
  };
  if (featureAssetMap) item.featureAssetMap = featureAssetMap;
  return item;
}

export const UI_ACCEPTANCE_CASES = [
  acceptanceCase({
    id: "landing-desktop",
    label: "桌面 · 起手页",
    summary: "单一文字/附件入口与后台安排承诺",
    viewport: VIEWPORTS.desktop,
    guide: LANDING_GUIDE,
    reviewPoints: [
      "首屏是否在 900px 高度内保持足够内容容量",
      "首屏是否只有一个主任务和一个主输入",
      "文字与附件入口是否清晰且没有成员或字段选择",
      "后台安排与人工确认边界是否一句说清",
    ],
  }),
  acceptanceCase({
    id: "routing-desktop",
    label: "桌面 · 自动路由待确认",
    summary: "安排摘要常驻，成员与输入依据按需披露",
    viewport: VIEWPORTS.desktop,
    guide: ROUTING_GUIDE,
    reviewPoints: [
      "默认是否只展示目标、解释摘要与一个开始动作",
      "执行能力是否没有手工选择入口",
      "路由依据与边界是否默认折叠且可键盘展开",
      "单成员与多成员是否走同一原地确认链",
    ],
  }),
  acceptanceCase({
    id: "streaming-desktop",
    label: "桌面 · 流式中",
    summary: "真实 delta 中途状态的静态快照，不做假打字机",
    viewport: VIEWPORTS.desktop,
    guide: STREAMING_GUIDE,
    reviewPoints: [
      "正文宽度、字号和行距能否支撑长对话阅读",
      "旋转标记是否只表达正在生成，不抢正文",
      "固定 composer 是否遮挡最后一段输出",
    ],
  }),
  acceptanceCase({
    id: "persistence-unknown-desktop",
    label: "桌面 · 保存待核",
    summary: "网络中断且落库未知时的 amber 锁定状态",
    viewport: VIEWPORTS.desktop,
    guide: PERSISTENCE_UNKNOWN_GUIDE,
    reviewPoints: [
      "保存未知是否与真正失败明确区分",
      "刷新核对动作是否比错误说明更容易找到",
      "发送与附件入口是否共同锁定",
    ],
  }),
  acceptanceCase({
    id: "landing-mobile",
    label: "移动端 · 起手页",
    summary: "375px 下的首屏密度与触控目标",
    viewport: VIEWPORTS.mobile,
    guide: LANDING_GUIDE,
    reviewPoints: [
      "375px 宽度是否无横向溢出",
      "首屏是否没有分类卡与候选列表",
      "44px 触控目标与内容容量是否平衡",
    ],
  }),
  acceptanceCase({
    id: "routing-mobile",
    label: "移动端 · 自动路由待确认",
    summary: "375px 下的折叠安排依据与单一治理动作",
    viewport: VIEWPORTS.mobile,
    guide: ROUTING_GUIDE,
    reviewPoints: [
      "默认折叠态是否只保留目标、摘要与主动作",
      "展开路由依据后是否仍无横向溢出",
      "折叠控件与开始按钮是否守住 44px 触控目标",
      "composer 是否始终只有文字与附件入口",
    ],
  }),
  acceptanceCase({
    id: "feature-asset-map-closed-desktop",
    label: "桌面 · 功能与资产地图默认收起",
    summary: "地图留在主会话，未展开前不读取、不展示资产",
    viewport: VIEWPORTS.desktop,
    guide: ROUTING_GUIDE,
    featureAssetMap: FEATURE_ASSET_MAP_READY,
    reviewPoints: [
      "地图是否默认收起且不分叉到新页面",
      "摘要是否只说明按需披露，不提前冒充完整地图",
      "主对话、单一 composer 与开始动作是否保持原位",
    ],
  }),
  acceptanceCase({
    id: "feature-asset-map-ready-desktop",
    label: "桌面 · 功能与资产地图已展开",
    summary: "owner-scoped 冷读快照与真实资产形成阶梯",
    viewport: VIEWPORTS.desktop,
    guide: ROUTING_GUIDE,
    featureAssetMap: FEATURE_ASSET_MAP_READY,
    reviewPoints: [
      "展开后是否只显示当前账号的冷读快照",
      "Candidate、包级人审、Workflow 与 Agent 是否使用各自真实语义",
      "是否可原地重新读取而没有执行、注册或晋级动作",
    ],
  }),
  acceptanceCase({
    id: "feature-asset-map-error-desktop",
    label: "桌面 · 功能与资产地图停披露",
    summary: "来源完整性 503 时整体停披露，不降级为空地图",
    viewport: VIEWPORTS.desktop,
    guide: ROUTING_GUIDE,
    featureAssetMap: FEATURE_ASSET_MAP_UNAVAILABLE,
    reviewPoints: [
      "503 是否明确显示地图暂不可用",
      "失败时是否完全隐藏指标、能力卡和资产卡",
      "是否只提供重新读取而不提供旁路数据或操作",
    ],
  }),
  acceptanceCase({
    id: "feature-asset-map-ready-mobile",
    label: "移动端 · 功能与资产地图已展开",
    summary: "375px 下的 owner 快照、形成阶梯与重新读取",
    viewport: VIEWPORTS.mobile,
    guide: ROUTING_GUIDE,
    featureAssetMap: FEATURE_ASSET_MAP_READY,
    reviewPoints: [
      "375px 下是否无横向溢出",
      "能力卡、资产阶梯与边界标签是否保持可扫读",
      "重新读取是否保持 44px 触控目标",
    ],
  }),
  acceptanceCase({
    id: "asset-candidate-desktop",
    label: "桌面 · 已完成任务资产候选",
    summary: "completed 单任务在对话轴自动长出一张只读候选卡",
    viewport: VIEWPORTS.desktop,
    guide: ASSET_CANDIDATE_GUIDE,
    reviewPoints: [
      "完成任务是否只长出一张候选卡，不增加常驻字段面板",
      "候选抽屉是否只读，工程师只需用按钮接受、不保留、下载或返回",
      "Task Pattern 与 Skill 是否如实形成，Workflow 与 Agent 是否继续受门控",
    ],
  }),
  acceptanceCase({
    id: "asset-candidate-accepted-desktop",
    label: "桌面 · 隔离包待复核",
    summary: "Candidate 接受后自动材化隔离包，真实四文件按需读取后才可批准",
    viewport: VIEWPORTS.desktop,
    guide: ASSET_CANDIDATE_ACCEPTED_GUIDE,
    reviewPoints: [
      "Candidate 接受与包级批准是否明确分成两道人工门",
      "批准复用是否在真实四文件内容加载并核对前保持禁用",
      "Task Pattern 与 Skill 是否成为 approved revision，Workflow 与 Agent 是否仍未形成",
    ],
  }),
  acceptanceCase({
    id: "asset-package-approved-desktop",
    label: "桌面 · 隔离包已批准",
    summary: "精确包修订经人工批准后以 teal 中性签发态展示，不冒充执行成功",
    viewport: VIEWPORTS.desktop,
    guide: ASSET_PACKAGE_APPROVED_GUIDE,
    reviewPoints: [
      "批准是否使用人签 teal 而不是运行成功绿色",
      "是否只说明相似任务可自动匹配，不声称已注册、发布或执行",
      "Workflow 与 Agent Candidate 是否仍保持未形成",
    ],
  }),
  acceptanceCase({
    id: "asset-package-rejected-desktop",
    label: "桌面 · 隔离包未批准",
    summary: "包级拒绝回到中性记录态，不回落到 Candidate 接受的 teal 圆点",
    viewport: VIEWPORTS.desktop,
    guide: ASSET_PACKAGE_REJECTED_GUIDE,
    reviewPoints: [
      "拒绝包是否以中性空心标记展示，而不是人签 teal 或失败红",
      "是否保留 Candidate、原任务与包级复核审计记录",
      "是否不再提供批准或拒绝动作",
    ],
  }),
  acceptanceCase({
    id: "skill-reuse-desktop",
    label: "桌面 · 已自动复用方法",
    summary: "已审核 Skill 只在当前方案主对话内联说明，不增加资产面板",
    viewport: VIEWPORTS.desktop,
    guide: SKILL_REUSE_GUIDE,
    reviewPoints: [
      "复用来源是否只占用既有方案摘要和按需披露区",
      "是否仍只有一个按方案开始主动作，没有 Skill 选择或复用按钮",
      "复用精确摘要是否在开始与运行时继续由后端核对",
    ],
  }),
  acceptanceCase({
    id: "skill-reuse-invalid-desktop",
    label: "桌面 · 复用证据待核",
    summary: "非法 Skill 引用显式 amber 阻断，绝不静默按无复用方案开始",
    viewport: VIEWPORTS.desktop,
    guide: SKILL_REUSE_INVALID_GUIDE,
    reviewPoints: [
      "非法引用是否出现 amber 明示而不是消失",
      "按方案开始是否被替换为继续对话重新安排",
      "验收边界内是否保持零任务 POST",
    ],
  }),
  acceptanceCase({
    id: "asset-intake-desktop",
    label: "桌面 · 资产沉淀单焦点",
    summary: "从已保存 Work Case 进入九问线性 Asset Builder",
    viewport: VIEWPORTS.desktop,
    guide: {
      ...ASSET_WORK_GUIDE,
      assetBuilderOpen: true,
      assetBuilderStep: 1,
      assetDraftGeneralization: ASSET_INTAKE_GENERALIZATION,
    },
    reviewPoints: [
      "任一时刻是否只有一个可编辑问题与一个主行动",
      "问题进度和已整理摘要是否足够安静，不与当前回答争抢注意力",
      "跨越本次工作与复用方法时是否继续保留回答和输入焦点",
    ],
  }),
  acceptanceCase({
    id: "asset-review-desktop",
    label: "桌面 · 待审资产草稿",
    summary: "Task Pattern + Skill + 校验 + 人工门的受治理草稿包",
    viewport: VIEWPORTS.desktop,
    guide: {
      ...ASSET_WORK_GUIDE,
      assetBuilderOpen: true,
      assetBuilderStep: 3,
      assetDraftGeneralization: ASSET_DRAFT_GENERALIZATION,
      assetDraftPreview: ASSET_DRAFT_PREVIEW,
    },
    reviewPoints: [
      "Task Pattern、Skill 和校验是否构成一条可扫读的资产链",
      "待审状态是否只用 amber/中性而没有伪绿色",
      "下载不等于注册、未执行/未晋级是否常驻可见",
    ],
  }),
  acceptanceCase({
    id: "asset-review-mobile",
    label: "移动端 · 待审资产草稿",
    summary: "375px 全屏抽屉中的固定头、滚动正文与底栏",
    viewport: VIEWPORTS.mobile,
    guide: {
      ...ASSET_WORK_GUIDE,
      assetBuilderOpen: true,
      assetBuilderStep: 3,
      assetDraftGeneralization: ASSET_DRAFT_GENERALIZATION,
      assetDraftPreview: ASSET_DRAFT_PREVIEW,
    },
    reviewPoints: [
      "抽屉是否在 375px 下全屏且无横向溢出",
      "固定头、滚动内容与下载底栏是否互不遮挡",
      "44px 触控目标与待审边界文案是否保留",
    ],
  }),
  acceptanceCase({
    id: "asset-blocked-mobile",
    label: "移动端 · 草稿阻断待补",
    summary: "缺人工判断点与证据时 needs_revision，禁止下载",
    viewport: VIEWPORTS.mobile,
    guide: {
      ...ASSET_WORK_GUIDE,
      assetBuilderOpen: true,
      assetBuilderStep: 3,
      assetDraftGeneralization: ASSET_BLOCKED_GENERALIZATION,
      assetDraftPreview: ASSET_BLOCKED_PREVIEW,
    },
    reviewPoints: [
      "缺人工判断点与证据时是否出现红色阻断摘要",
      "阻断草稿的下载按钮是否禁用且没有旁路",
      "375px 全屏抽屉是否无横向溢出",
    ],
  }),
];

export function getUiAcceptanceCase(id) {
  if (id === null || id === undefined || id === "") {
    return UI_ACCEPTANCE_CASES[0];
  }

  const acceptanceCase = UI_ACCEPTANCE_CASES.find((item) => item.id === id);
  if (!acceptanceCase) {
    throw new RangeError(`未知 UI 验收场景：${id}`);
  }
  return acceptanceCase;
}
