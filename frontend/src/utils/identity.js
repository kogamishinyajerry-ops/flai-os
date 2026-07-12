// 轻量本地身份：记住用户名，全站表单免重填（导引/创建/审核/反馈）。
// 仅便利，不改变红线——签发仍由人亲手点击；这里只预填名字，不代签、不自动提交。
// 内网就绪后此处可替换为域账号/SSO（见 UX 审计 P1-3）。

const KEY = "flai_user_name";

// 内存态兜底（Codex 审 P1）：隐私模式下 localStorage 写失败曾形成身份门
// 死循环（门 emit done 但名字没存住→发不出→刷新又见门）。内存变量保证
// 会话内身份闭环——「本次会话有效」；刷新丢失重新留名是诚实语义。
// 设计选择：另一标签页清空 localStorage 不打断本标签页（会话身份延续，
// 不做 storage 事件重开门——打断工作比边缘不一致代价更高，记录在案）。
let memoryName = "";

export function getSavedName() {
  try {
    return localStorage.getItem(KEY) || memoryName;
  } catch {
    return memoryName;
  }
}

// 返回是否已持久化：false=仅内存（调用方可提示「本次会话有效」）。
export function saveName(name) {
  const v = (name || "").trim();
  if (!v) return false;
  memoryName = v;
  try {
    localStorage.setItem(KEY, v);
    return localStorage.getItem(KEY) === v;
  } catch {
    return false;
  }
}
