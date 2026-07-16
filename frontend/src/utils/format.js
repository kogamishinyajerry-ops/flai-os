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
// 同一份工作态集合对外导出（勿重复定义第二份，避免两处口径漂移）。
export const TASK_WORK_STATES = _TASK_WORK_STATES;
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

// 相对时间 SSOT（批B /today Agent 动态）：近期事件用人话距离，7 天以上回落
// formatTime 绝对时间；非法/未来时间戳诚实降级为 formatTime，不编「刚刚」。
export const formatRelativeTime = (iso, nowMs = Date.now()) => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t) || t > nowMs) return formatTime(iso);
  const diff = nowMs - t;
  const min = 60_000;
  if (diff < min) return "刚刚";
  if (diff < 60 * min) return `${Math.floor(diff / min)} 分钟前`;
  if (diff < 24 * 60 * min) return `${Math.floor(diff / (60 * min))} 小时前`;
  if (diff < 7 * 24 * 60 * min) return `${Math.floor(diff / (24 * 60 * min))} 天前`;
  return formatTime(iso);
};

// 毫秒 → 人话时长（工作态氛围展示用；非法/负值一律诚实降级为「—」，不编造）。
// 数字格式对表（disclosure-grammar §三，批次二 F1）：<60s 纯秒；≥60s 分+秒
// **补零两位**（`2 分 05 秒`——次级单位定宽，活跳递增时数字不抖）；小时档
// 分钟补零同理（既有口径）。
export const formatDuration = (ms) => {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0) return "—";
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours} 小时 ${String(minutes).padStart(2, "0")} 分`;
  if (minutes > 0) return `${minutes} 分 ${String(seconds).padStart(2, "0")} 秒`;
  return `${seconds} 秒`;
};

// 紧凑绝对时钟（批次三 G4，家族轴「完成态=绝对时间戳」的行级形态）：同日
// `HH:MM`、跨日 `MM-DD HH:MM`、非法/缺失=「—」。todayKey（toDateString() 串）
// 由调用方**响应式供给**——承袭 CompletionSeal 午夜翻页教训（Codex R1-P3）：
// 纯函数绝不裸读 new Date()，否则终态面停轮询后跨午夜永不重算，「昨日完成」
// 的裸 HH:MM 会被误读成今天。SSOT：CompletionSeal 落定时刻与 StatusCenter
// 收件箱行共用，绝不各自再造第二套同日判据。
export const formatClockCompact = (iso, todayKey) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (d.toDateString() === todayKey) return hm;
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${hm}`;
};

// token 用量 → 千位压缩（disclosure-grammar §三「判断依据精确 · 量级感受
// 压缩」——token 属量级感受轴，1 位小数、整值去尾零：12345→12.3k、12000→12k、
// 3400000→3.4M；<1000 保持精确）。SSOT：TaskDetail rail / DeliveryCard 尾行 /
// StatusCenter 速览三处共用，绝不各自再造。非法输入降级「—」与 formatDuration
// 同款诚实口径（调用方通常已 v-if 守住，这里兜底不编数）。
export const formatTokens = (n) => {
  if (typeof n !== "number" || !Number.isFinite(n) || n < 0) return "—";
  const compress = (v) => {
    const s = v.toFixed(1);
    return s.endsWith(".0") ? s.slice(0, -2) : s;
  };
  if (n >= 1_000_000) return `${compress(n / 1_000_000)}M`;
  if (n >= 1000) {
    // 进位穿透守卫（3-lens 三镜头齐咬）：n∈[999950,999999] 时 toFixed(1) 会把
    // k 档压成 "1000"（四位数假 k 值，不在格式表任何合法形态里）——以**渲染
    // 结果本身**为判据升 M 档（同一套 toFixed 舍入，不会与判档规则再打架）。
    const kStr = compress(n / 1000);
    return kStr === "1000" ? `${compress(n / 1_000_000)}M` : `${kStr}k`;
  }
  return String(n);
};

// ── 产物类型标签（批次二 F6，Codex R6「文档 · MD」语法）：类型词查表+格式
// 大写，未知扩展名归「文件」——只译类型词，格式永远如实透出。SSOT：TaskDetail
// 产物卡与 StatusCenter 速览共用（3-lens 抓过孪生点漏改，绝不各自再造）。 ──
const ARTIFACT_TYPE_WORD = {
  md: "文档", markdown: "文档", txt: "文档", pdf: "文档", html: "文档", doc: "文档", docx: "文档",
  csv: "数据", json: "数据", yaml: "数据", yml: "数据", xml: "数据", xlsx: "数据",
  png: "图像", jpg: "图像", jpeg: "图像", svg: "图像", gif: "图像", webp: "图像",
  zip: "归档", tar: "归档", gz: "归档",
};
export const artifactTypeLabel = (ext) => {
  const e = String(ext || "").toLowerCase();
  return `${ARTIFACT_TYPE_WORD[e] || "文件"} · ${e.toUpperCase()}`;
};

// ── 人工签发口播派生（批次二 F3 收口，3-lens trust P1 + Codex R0-P2）：
// WorkLog 与 VerificationCard 唯一同源谓词+同一措辞（此前两处各自拼字符串，
// 措辞漂移「依据/已由」被 paradigm 镜头抓获）。四态：
// - null                → events 里**不存在** review_* 事件（真·未经签发流程）
// - { redacted: true }  → 存在 review_* 事件且带后端遮蔽标记（ADR-0025
//   redact_rows：payload→null + content_withheld=true）——绝不把「已签发但
//   内容受限」呈现成「未经签发」（对已发生事实的确信性否定）
// - { unknown: true }   → 存在 review_* 事件、无遮蔽标记但 payload 缺
//   reviewer（畸形/存量数据）——只说「不完整」，**不编造「受限」这个没
//   发生的原因**（Codex R0-P2：受限判定只认后端真标记，不从缺字段推断）
// - { approved, reviewer, comment } → 完整签发记录
export const deriveSignoff = (events) => {
  const list = events || [];
  for (let i = list.length - 1; i >= 0; i--) {
    const e = list[i];
    if (e.event_type === "review_approved" || e.event_type === "review_rejected") {
      if (!e.payload?.reviewer) {
        return e.content_withheld === true ? { redacted: true } : { unknown: true };
      }
      return {
        approved: e.event_type === "review_approved",
        reviewer: e.payload.reviewer,
        comment: e.payload.comment || "",
      };
    }
  }
  return null;
};
// 完整记录的口播文案（对称句式；redacted/null 由调用方按各自版式渲染）。
export const signoffText = (s) =>
  s.approved ? `✓ 由 ${s.reviewer} 批准放行` : `✕ 由 ${s.reviewer} 驳回`;

// 任务已耗时（毫秒）：无 started_at 诚实返回 null（不编造耗时）；
// 有 started_at 则用 (finished_at 或 nowMs) - started_at；解析失败同样返回 null。
export const taskElapsedMs = (task, nowMs) => {
  if (!task || !task.started_at) return null;
  const startMs = Date.parse(task.started_at);
  if (Number.isNaN(startMs)) return null;
  const endMs = task.finished_at ? Date.parse(task.finished_at) : nowMs;
  if (Number.isNaN(endMs)) return null;
  return endMs - startMs;
};

// 文件尺寸 → 人话（B/KB/MB/GB 四档）；非法/非正值返回空串由调用方 v-if 省略。
// SSOT：StatusCenter 与 TaskDetail 共用此份——绝不各自再造（设计哲学批教训：
// 自建第二套 formatter 会在同屏打脸）。
export const formatFileSize = (bytes) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
};
