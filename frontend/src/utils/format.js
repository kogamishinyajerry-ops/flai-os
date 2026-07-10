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
  // completed 用中性 info（**不给 success 绿**）：与到席灯 taskLampColor 同一诚实口径——
  // 绿仅真实 REAL 结果，当前跑 mock，给绿即假 REAL。此前 el-tag 路径漏了这条锁，
  // 任务历史/详情里 completed 显绿而到席灯却中性，同一任务两套矛盾诚实信号；此处收口。
  completed: { label: "已完成", type: "info" },
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

// 事件类型 → 人话标签（详情页时间轴不再直显开发术语；未知类型回退原串）。
export const EVENT_TYPE_LABEL = {
  task_created: "任务已创建",
  validation_started: "开始校验输入",
  validation_failed: "输入校验未通过",
  running_started: "开始运行",
  parsing_started: "开始解析",
  analyzing_started: "开始分析",
  agent_log: "Agent 运行日志",
  model_call: "模型调用",
  tool_started: "工具开始",
  tool_finished: "工具完成",
  knowledge_search: "知识检索",
  summary_generated: "生成汇总",
  review_requested: "请求人工审核",
  review_approved: "人工已批准",
  review_rejected: "人工已拒绝",
  task_completed: "任务完成",
  task_failed: "任务失败",
  task_cancelled: "任务已取消",
};
export const eventTypeLabel = (t) => EVENT_TYPE_LABEL[t] ?? t;

// Agent 类型（agent.schema category 枚举）→ 中文标签 + 主题色 + 一句话定位。
// 分类色标是门户视觉重点：不同类型 Agent 一眼可辨（任务书 §12.6 泛化验证）。
// 配色**刻意避开信任色锁的五个语义槽**（绿=REAL / teal=人签 / amber=待核 /
// 红=失败 / clay=工作态）：分类是「类型」轴、信任是「状态」轴，两轴同屏不得撞色，
// 否则绿药丸会被误读成「已验证」。故四类统一落在冷调 蓝/靛/紫/梅 弧段——
// reasoning_assist 由旧琥珀(撞 amber)、knowledge_qa 由旧绿(撞 REAL) 迁出。
export const AGENT_CATEGORY = {
  tool_automation: { label: "工具自动化型", color: "#2f6fb3", tip: "编排工具批量作业，如性能盘计算" },
  knowledge_qa: { label: "知识问答型", color: "#4a6bb0", tip: "基于受控知识范围回答工程问题" },
  structured_gen: { label: "结构化生成型", color: "#7c5cbf", tip: "按规则生成结构化产物，如控制逻辑" },
  reasoning_assist: { label: "推理辅助型", color: "#b45a86", tip: "LLM 辅助推理出草案，结论需人工确认" },
};

export const categoryLabel = (c) => AGENT_CATEGORY[c]?.label ?? c ?? "未分类";
export const categoryColor = (c) => AGENT_CATEGORY[c]?.color ?? "#8a8f99";
export const categoryTip = (c) => AGENT_CATEGORY[c]?.tip ?? "";

// Agent 发布状态（agent.schema status）→ 中文标签 + 释义（门户不再直显英文 draft）。
export const AGENT_STATUS = {
  draft: { label: "草案态", tip: "开发中的草案版本：功能可用于验证，尚未正式发布。" },
  trial: { label: "试运行", tip: "试运行阶段：可用，但仍在打磨中。" },
  released: { label: "已发布", tip: "正式发布版本。" },
  disabled: { label: "已停用", tip: "已停用，不可创建任务。" },
};
export const agentStatusLabel = (s) => AGENT_STATUS[s]?.label ?? s;
export const agentStatusTip = (s) => AGENT_STATUS[s]?.tip ?? "";

// 成熟度（agent.schema maturity L0-L3）→ 释义（门户 L0 徽章加 tooltip + 图例）。
export const MATURITY = {
  L0: { label: "L0 · 原型", tip: "L0 原型：能力验证阶段，勿依赖其结论。" },
  L1: { label: "L1 · 试用", tip: "L1 试用：小范围试用。" },
  L2: { label: "L2 · 稳定", tip: "L2 稳定：可日常使用。" },
  L3: { label: "L3 · 成熟", tip: "L3 成熟：充分验证。" },
};
export const maturityTip = (m) => MATURITY[m]?.tip ?? m;

export const formatTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
};
