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

// 事件 level → timeline 颜色
export const LEVEL_COLOR = { info: "#409EFF", warning: "#E6A23C", error: "#F56C6C" };

export const formatTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
};
