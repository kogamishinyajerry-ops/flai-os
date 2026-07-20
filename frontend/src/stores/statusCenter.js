// 状态中心全局状态源（UI-PARADIGM.md Phase 1）——模块级 reactive 单例，零新依赖。
// StatusDock（右上状态坞）、StatusCenter（抽屉）、各页「速览」入口共享同一份状态；
// 渐进披露层级：inbox（分组清单）⇄ peek（任务速览）／monitor（会话事实监控）。
import { reactive } from "vue";

export const statusCenter = reactive({
  open: false,
  view: "inbox", // 'inbox' | 'peek' | 'monitor'
  taskId: null,
  conversationId: null,
  focusTaskId: null,
  peekReturnView: "inbox",
  peekReturnConversationId: null,
  peekReturnTaskId: null,
  // 跨模态互斥让位旗（3-lens 回归 P1）：⌘K 打开时互斥关闭本抽屉是「让位不是
  // 归位」——置位后 StatusCenter 的关闭 watcher 跳过一次焦点回还并复位，否则
  // 它的 nextTick 排在 ⌘K 聚焦之后，会把焦点从 qs-input 抢回 dock pill。
  suppressFocusReturn: false,
});

export function openInbox() {
  statusCenter.view = "inbox";
  statusCenter.taskId = null;
  statusCenter.conversationId = null;
  statusCenter.focusTaskId = null;
  statusCenter.peekReturnView = "inbox";
  statusCenter.peekReturnConversationId = null;
  statusCenter.peekReturnTaskId = null;
  statusCenter.open = true;
}

export function openTaskPeek(taskId) {
  if (!taskId) return;
  const fromMonitor = statusCenter.open && statusCenter.view === "monitor" && !!statusCenter.conversationId;
  statusCenter.peekReturnView = fromMonitor ? "monitor" : "inbox";
  statusCenter.peekReturnConversationId = fromMonitor ? statusCenter.conversationId : null;
  statusCenter.peekReturnTaskId = fromMonitor ? taskId : null;
  statusCenter.view = "peek";
  statusCenter.taskId = taskId;
  statusCenter.conversationId = fromMonitor ? statusCenter.conversationId : null;
  statusCenter.focusTaskId = fromMonitor ? taskId : null;
  statusCenter.open = true;
}

export function openAgentMonitor(conversationId, focusTaskId = null) {
  if (!conversationId) return;
  statusCenter.view = "monitor";
  statusCenter.taskId = null;
  statusCenter.conversationId = conversationId;
  statusCenter.focusTaskId = focusTaskId || null;
  statusCenter.peekReturnView = "inbox";
  statusCenter.peekReturnConversationId = null;
  statusCenter.peekReturnTaskId = null;
  statusCenter.open = true;
}

export function backToInbox() {
  statusCenter.view = "inbox";
  statusCenter.taskId = null;
  statusCenter.conversationId = null;
  statusCenter.focusTaskId = null;
  statusCenter.peekReturnView = "inbox";
  statusCenter.peekReturnConversationId = null;
  statusCenter.peekReturnTaskId = null;
}

export function backFromTaskPeek() {
  if (statusCenter.peekReturnView === "monitor" && statusCenter.peekReturnConversationId) {
    statusCenter.view = "monitor";
    statusCenter.taskId = null;
    statusCenter.conversationId = statusCenter.peekReturnConversationId;
    statusCenter.focusTaskId = statusCenter.peekReturnTaskId;
    statusCenter.peekReturnView = "inbox";
    statusCenter.peekReturnConversationId = null;
    statusCenter.peekReturnTaskId = null;
    return;
  }
  backToInbox();
}

export function closeCenter() {
  statusCenter.open = false;
}
