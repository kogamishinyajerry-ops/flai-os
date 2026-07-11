// ⌘K 快速切换面板的开合状态源（美化批）：与 statusCenter.js 同款模块级
// reactive 单例。此前 isOpen 是 QuickSwitcher 组件内局部状态、只有键盘能
// 唤起——提到 store 后侧栏可挂可见入口（可点性 + 快捷键教学）。
import { reactive } from "vue";

export const quickSwitcher = reactive({ open: false });

export function openQuickSwitcher() {
  quickSwitcher.open = true;
}

export function closeQuickSwitcher() {
  quickSwitcher.open = false;
}
