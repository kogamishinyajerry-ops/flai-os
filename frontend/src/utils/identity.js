// 轻量本地身份：记住用户名，全站表单免重填（导引/创建/审核/反馈）。
// 仅便利，不改变红线——签发仍由人亲手点击；这里只预填名字，不代签、不自动提交。
// 内网就绪后此处可替换为域账号/SSO（见 UX 审计 P1-3）。

const KEY = "flai_user_name";

export function getSavedName() {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function saveName(name) {
  const v = (name || "").trim();
  if (!v) return;
  try {
    localStorage.setItem(KEY, v);
  } catch {
    /* 隐私模式/禁用 storage 时静默降级：本次不记住，功能不受影响 */
  }
}
