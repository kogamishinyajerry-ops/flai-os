/** 展示层共用小工具：状态映射与时间格式（页面间口径统一，改这里一处）。 */

// 任务十态 → Element Plus tag type + 中文标签（docs/05 §1 口径）
export const TASK_STATUS = {
  created: { label: "已创建", type: "info" },
  queued: { label: "排队中", type: "info" },
  validating: { label: "校验中", type: "primary" },
  running: { label: "运行中", type: "primary" },
  waiting_review: { label: "等待人工审核", type: "warning" },
  parsing: { label: "解析中", type: "primary" },
  analyzing: { label: "分析中", type: "primary" },
  completed: { label: "已完成", type: "success" },
  failed: { label: "失败", type: "danger" },
  cancelled: { label: "已取消", type: "info" },
};

export const statusLabel = (s) => TASK_STATUS[s]?.label ?? s;
export const statusTagType = (s) => TASK_STATUS[s]?.type ?? "info";

// 任务状态 → 到席灯颜色（信任色锁，App.vue :root 注释；协作工作台/会话共用一处）：
// - running/validating/parsing/analyzing = clay（工作态/live）
// - waiting_review = amber（未核·待人签；teal 只留给「已签」动作本身，不预支）
// - failed = 红（真失败）
// - completed = 中性墨（**不给绿**——绿仅真实 REAL 结果；当前跑 mock，给绿即假
//   REAL。等真实性能盘接入产出可核结果再解锁绿）
// - 其余（created/queued/cancelled）= 淡墨（待命/终止）
const _TASK_WORK_STATES = new Set(["running", "validating", "parsing", "analyzing"]);
export const taskLampColor = (status) => {
  if (_TASK_WORK_STATES.has(status)) return "var(--clay)";
  if (status === "waiting_review") return "var(--trust-pending)";
  if (status === "failed") return "var(--trust-fail)";
  if (status === "completed") return "var(--ink-soft)";
  return "var(--ink-faint)";
};

// 事件 level → timeline 颜色
export const LEVEL_COLOR = { info: "#409EFF", warning: "#E6A23C", error: "#F56C6C" };

// Agent 类型（agent.schema category 枚举）→ 中文标签 + 主题色 + 一句话定位。
// 分类色标是门户视觉重点：不同类型 Agent 一眼可辨（任务书 §12.6 泛化验证）。
export const AGENT_CATEGORY = {
  tool_automation: { label: "工具自动化型", color: "#2f6fb3", tip: "编排工具批量作业，如性能盘计算" },
  structured_gen: { label: "结构化生成型", color: "#7c5cbf", tip: "按规则生成结构化产物，如控制逻辑" },
  reasoning_assist: { label: "推理辅助型", color: "#c1841f", tip: "LLM 辅助推理出草案，结论需人工确认" },
  knowledge_qa: { label: "知识问答型", color: "#2c8a6f", tip: "基于受控知识范围回答工程问题" },
};

export const categoryLabel = (c) => AGENT_CATEGORY[c]?.label ?? c ?? "未分类";
export const categoryColor = (c) => AGENT_CATEGORY[c]?.color ?? "#8a8f99";
export const categoryTip = (c) => AGENT_CATEGORY[c]?.tip ?? "";

export const formatTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
};
