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

const LANDING_GUIDE = {
  started: false,
  conversationId: "",
  conversationStatus: null,
  messages: [],
  sending: false,
  reconciliationRequired: false,
  agentPickerOpen: false,
  agents: AGENTS,
};

const STREAMING_GUIDE = {
  started: true,
  conversationId: "ui-streaming",
  conversationStatus: "active",
  sending: true,
  reconciliationRequired: false,
  agentPickerOpen: false,
  agents: AGENTS,
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
    summary: "引导区、意图卡与 composer 的首屏密度",
    viewport: VIEWPORTS.desktop,
    guide: LANDING_GUIDE,
    reviewPoints: [
      "首屏是否在 900px 高度内保持足够内容容量",
      "一排紧凑意图条目（图标+短标签）是否清晰可扫读",
      "输入栏是否足够轻，且发送与附件目标仍可点",
    ],
  }),
  acceptanceCase({
    id: "picker-desktop",
    label: "桌面 · Agent 选择器",
    summary: "320px 紧凑弹层与一行边界说明",
    viewport: VIEWPORTS.desktop,
    guide: {
      ...LANDING_GUIDE,
      agentPickerOpen: true,
    },
    reviewPoints: [
      "弹层是否只占必要空间，不变成第二个门户",
      "名称、成熟度和一条边界信息是否可快速扫读",
      "搜索和完整门户入口是否保持明确层级",
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
    summary: "375px 下左右各 12px 的贴边弹层与内部滚动",
    viewport: VIEWPORTS.mobile,
    guide: {
      ...LANDING_GUIDE,
      agentPickerOpen: true,
    },
    reviewPoints: [
      "弹层边缘是否留出足够安全区",
      "四个 Agent 是否可在内部滚动中快速辨认",
      "关闭弹层后 composer 是否仍保持上下文",
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
