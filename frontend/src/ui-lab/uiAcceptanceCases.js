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

const AGENTS = [
  {
    id: "cfd_input_check",
    name: "CFD 参数核对 Agent",
    category: "tool_automation",
    summary: "核对算例输入、边界和求解设置",
    limitations: ["产物需工程师复核"],
    maturity: "试运行",
    status: "active",
  },
  {
    id: "standard_qa",
    name: "标准问答 Agent",
    category: "knowledge_qa",
    summary: "检索已接入标准并返回依据",
    limitations: ["缺少受控依据时如实拒答"],
    maturity: "试运行",
    status: "active",
  },
  {
    id: "fta_assist",
    name: "FTA 分析 Agent",
    category: "reasoning_assist",
    summary: "辅助拆解顶事件和失效路径",
    limitations: ["不替代工程判断或签发"],
    maturity: "候选",
    status: "active",
  },
  {
    id: "report_draft",
    name: "工程报告草拟 Agent",
    category: "structured_gen",
    summary: "按受控模板生成可审阅草案",
    limitations: ["只生成草案，不代提交"],
    maturity: "候选",
    status: "active",
  },
];

const WORK_TYPE_IDS = [
  "tool_automation",
  "knowledge_qa",
  "structured_gen",
  "reasoning_assist",
];

function unavailableSchema(filename) {
  return {
    state: "unavailable",
    reason: "file_missing",
    filename,
    property_count: 0,
    required_count: 0,
  };
}

// 真实 AgentShellCatalog 响应的静态验收快照。UiLab 只做可视状态，不联网、
// 不替代 API 契约测试；字段完整保留“只读本体”与人工门语义。
const AGENT_SHELL = {
  schema_version: "agent_shell.v1",
  source: { kind: "registry_snapshot", read_only: true },
  summary: {
    agent_count: AGENTS.length,
    work_type_count: WORK_TYPE_IDS.length,
    domain_count: 0,
    unresolved_reference_count: 0,
    defaulted_clearance_count: AGENTS.length,
    mock_tool_reference_count: 0,
  },
  facets: {
    work_types: WORK_TYPE_IDS.map((id) => ({
      id,
      total_count: AGENTS.filter((agent) => agent.category === id).length,
      task_count: AGENTS.filter((agent) => agent.category === id).length,
      conversation_count: 0,
      unknown_launch_count: 0,
    })),
    domains: [],
    launch_kinds: [
      {
        id: "task",
        total_count: AGENTS.length,
        task_count: AGENTS.length,
        conversation_count: 0,
        unknown_launch_count: 0,
      },
      {
        id: "conversation",
        total_count: 0,
        task_count: 0,
        conversation_count: 0,
        unknown_launch_count: 0,
      },
      {
        id: "unknown",
        total_count: 0,
        task_count: 0,
        conversation_count: 0,
        unknown_launch_count: 0,
      },
    ],
  },
  agents: AGENTS.map((agent) => ({
    identity: {
      agent_id: agent.id,
      name: agent.name,
      version: "0.1.0",
      summary: agent.summary,
    },
    classification: {
      category: agent.category,
      domain: null,
      specialty: null,
      usefulness_level: null,
    },
    capability: {
      input: { type: "params", schema: unavailableSchema("input_schema.json") },
      output: {
        formats: [".json"],
        schema: unavailableSchema("output_schema.json"),
      },
      tools: [],
      knowledge_scopes: [],
    },
    trust: {
      status: "draft",
      maturity: "L0",
      limitations: [...agent.limitations],
      visibility: "all",
      allowed_roles: ["business_user"],
      clearance: { effective: "internal", source: "defaulted" },
      requires_human_review: true,
      evidence: { required: false, kinds: [] },
    },
    launch: { kind: "task" },
  })),
  diagnostics: [],
};

const LANDING_GUIDE = {
  started: false,
  conversationId: "",
  conversationStatus: null,
  messages: [],
  sending: false,
  reconciliationRequired: false,
  agentPickerOpen: false,
  agents: AGENTS,
  agentShell: AGENT_SHELL,
};

const STREAMING_GUIDE = {
  started: true,
  conversationId: "ui-streaming",
  conversationStatus: "active",
  sending: true,
  reconciliationRequired: false,
  agentPickerOpen: false,
  agents: AGENTS,
  agentShell: AGENT_SHELL,
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
  agentPickerOpen: false,
  agents: AGENTS,
  agentShell: AGENT_SHELL,
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
  agentPickerOpen: false,
  agents: AGENTS,
  agentShell: AGENT_SHELL,
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
    summary: "784px 对话主线与 296px 本体上下文轨道",
    viewport: VIEWPORTS.desktop,
    guide: LANDING_GUIDE,
    reviewPoints: [
      "首屏是否在 900px 高度内保持足够内容容量",
      "一排紧凑意图条目（图标+短标签）是否清晰可扫读",
      "输入栏是否足够轻，且发送与附件目标仍可点",
      "右侧轨道是否只展示 Registry 快照、未知关系与人工边界",
    ],
  }),
  acceptanceCase({
    id: "picker-desktop",
    label: "桌面 · Agent 选择器",
    summary: "320px 本体快选与一行边界说明",
    viewport: VIEWPORTS.desktop,
    guide: {
      ...LANDING_GUIDE,
      agentPickerOpen: true,
    },
    reviewPoints: [
      "弹层是否只占必要空间，不变成第二个门户",
      "名称、成熟度和一条边界信息是否可快速扫读",
      "搜索和完整门户入口是否保持明确层级",
      "选择 Agent 是否只暂存草稿，不发送、不建任务",
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
      "发送、附件和 Agent 入口是否共同锁定",
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
      "2×2 紧凑意图条目是否守住触控目标且可扫读",
      "44px 触控目标与内容容量是否平衡",
    ],
  }),
  acceptanceCase({
    id: "picker-mobile",
    label: "移动端 · Agent 选择器",
    summary: "375px 下左右各 12px 的本体快选与内部滚动",
    viewport: VIEWPORTS.mobile,
    guide: {
      ...LANDING_GUIDE,
      agentPickerOpen: true,
    },
    reviewPoints: [
      "弹层边缘是否留出足够安全区",
      "四个 Agent 是否可在内部滚动中快速辨认",
      "关闭弹层后 composer 是否仍保持上下文",
      "工作类型筛选是否在窄屏内无横向溢出",
    ],
  }),
  acceptanceCase({
    id: "asset-intake-desktop",
    label: "桌面 · 资产沉淀起步",
    summary: "从已保存 Work Case 进入三步 Asset Builder",
    viewport: VIEWPORTS.desktop,
    guide: {
      ...ASSET_WORK_GUIDE,
      assetBuilderOpen: true,
      assetBuilderStep: 1,
      assetDraftGeneralization: ASSET_DRAFT_GENERALIZATION,
    },
    reviewPoints: [
      "抽屉是否明确绑定真实会话来源而非一张空白表",
      "标题、触发与结果是否能在第一屏清楚完成",
      "是否明确说明不会自动猜测触发条件",
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
