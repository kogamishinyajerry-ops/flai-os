// 状态中心全局状态源（UI-PARADIGM.md Phase 1）——模块级 reactive 单例，零新依赖。
// StatusDock（右上状态坞）、StatusCenter（抽屉）、各页「速览」入口共享同一份状态；
// 渐进披露层级：inbox（分组清单）⇄ peek（任务速览）。
import { reactive } from "vue";

export const statusCenter = reactive({
  open: false,
  view: "inbox", // 'inbox' | 'peek'
  taskId: null,
  // 跨模态互斥让位旗（3-lens 回归 P1）：⌘K 打开时互斥关闭本抽屉是「让位不是
  // 归位」——置位后 StatusCenter 的关闭 watcher 跳过一次焦点回还并复位，否则
  // 它的 nextTick 排在 ⌘K 聚焦之后，会把焦点从 qs-input 抢回 dock pill。
  suppressFocusReturn: false,
});

export function openInbox() {
  statusCenter.view = "inbox";
  statusCenter.taskId = null;
  statusCenter.open = true;
}

export function openTaskPeek(taskId) {
  if (!taskId) return;
  statusCenter.view = "peek";
  statusCenter.taskId = taskId;
  statusCenter.open = true;
}

export function backToInbox() {
  statusCenter.view = "inbox";
  statusCenter.taskId = null;
}

export function closeCenter() {
  statusCenter.open = false;
}
