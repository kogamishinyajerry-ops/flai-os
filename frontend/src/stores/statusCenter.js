// 状态中心全局状态源（UI-PARADIGM.md Phase 1）——模块级 reactive 单例，零新依赖。
// StatusDock（右上状态坞）、StatusCenter（抽屉）、各页「速览」入口共享同一份状态；
// 渐进披露层级：inbox（分组清单）⇄ peek（任务速览）。
import { reactive } from "vue";

export const statusCenter = reactive({
  open: false,
  view: "inbox", // 'inbox' | 'peek'
  taskId: null,
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
