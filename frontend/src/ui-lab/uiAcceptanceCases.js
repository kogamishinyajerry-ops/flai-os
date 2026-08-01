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
      content: "我已经整理好协作方案。执行前请核对目标，其余能力由系统在后台编排。",
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
    suggested_id: "task_pattern_candidate_528a3dbbf28d",
    content_digest: "sha256:528a3dbbf28d65ff2bb0f3fc069189cdccdb0fe84635fdb744cc5863f32a0cd5",
    ...ASSET_DRAFT_GENERALIZATION,
  },
  skill: {
    schema_version: "skill_draft.v1",
    status: "draft",
    operationalizes_task_pattern_digest: "sha256:528a3dbbf28d65ff2bb0f3fc069189cdccdb0fe84635fdb744cc5863f32a0cd5",
    suggested_id: "skill_candidate_8ea5d04c38ee",
    content_digest: "sha256:8ea5d04c38ee98d275224f8904d591bfd9f50223668b5298287a69215798a61b",
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
  draft_digest: "sha256:ac82e6b78fd1dfbdb314837c63fcbd2ab482403708c91ce698f4c68d2082518d",
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

function acceptanceCase({
  id,
  label,
  summary,
  viewport,
  guide,
  reviewPoints,
}) {
  return {
    id,
    label,
    summary,
    viewport,
    reviewPoints,
    app: APP_FIXTURE,
    guide,
  };
}

export const UI_ACCEPTANCE_CASES = [
  acceptanceCase({
    id: "landing-desktop",
    label: "桌面 · 起手页",
    summary: "单一文字/附件入口与后台编排承诺",
    viewport: VIEWPORTS.desktop,
    guide: LANDING_GUIDE,
    reviewPoints: [
      "首屏是否在 900px 高度内保持足够内容容量",
      "首屏是否只有一个主任务和一个主输入",
      "文字与附件入口是否清晰且没有执行单元或字段选择",
      "后台编排与人工确认边界是否一句说清",
    ],
  }),
  acceptanceCase({
    id: "routing-desktop",
    label: "桌面 · 自动路由待确认",
    summary: "编排摘要常驻，执行单元与输入依据按需披露",
    viewport: VIEWPORTS.desktop,
    guide: ROUTING_GUIDE,
    reviewPoints: [
      "默认是否只展示目标、解释摘要与一个开工动作",
      "执行能力是否没有手工选择入口",
      "路由依据与边界是否默认折叠且可键盘展开",
      "单执行单元与多执行单元是否走同一原地确认链",
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
    summary: "375px 下的折叠编排依据与单一治理动作",
    viewport: VIEWPORTS.mobile,
    guide: ROUTING_GUIDE,
    reviewPoints: [
      "默认折叠态是否只保留目标、摘要与主动作",
      "展开路由依据后是否仍无横向溢出",
      "折叠控件与开工按钮是否守住 44px 触控目标",
      "composer 是否始终只有文字与附件入口",
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
