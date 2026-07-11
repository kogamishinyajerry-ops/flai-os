// 会话「已读」标记（本地存储，B2）：驱动协作工作台首页会话卡片的完成未读徽章。
// 纯前端便利标记，不改变任何签发/审核语义——只回答"这次会话我看过之后有没有新进展"。
// 隐私模式/禁用 storage 时静默降级：不记录、不阻断页面，效果等同于"从未 seen"。

const KEY = "flai_session_seen";

function readMap() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeMap(map) {
  try {
    localStorage.setItem(KEY, JSON.stringify(map));
  } catch {
    /* 隐私模式/容量满：静默降级，不阻断页面 */
  }
}

// 标记某会话「已看过」：记当前时间。进入 WorkbenchSession 页面 onMounted 即调用。
export function markSeen(sessionId) {
  if (!sessionId) return;
  const map = readMap();
  map[sessionId] = new Date().toISOString();
  writeMap(map);
}

// 该会话是否有未读进展：任一成员任务 updated_at 晚于上次 seen 时间，且状态属于
// 「有信息量的终态」（completed/failed/waiting_review——中间过程态不算"新进展"，
// 避免频闪）→ true。从未 seen 过的会话诚实返回 false（不是"没有未读"，而是
// "无从判断"——避免老会话首次上线/首次访问就被误标成一堆新进展）。
const NOTABLE_STATUSES = new Set(["completed", "failed", "waiting_review"]);

export function hasUnseen(sessionId, tasks) {
  if (!sessionId) return false;
  const map = readMap();
  const seenAt = map[sessionId];
  if (!seenAt) return false;
  const seenMs = Date.parse(seenAt);
  if (Number.isNaN(seenMs)) return false;
  return (tasks || []).some((t) => {
    if (!t || !NOTABLE_STATUSES.has(t.status) || !t.updated_at) return false;
    const updatedMs = Date.parse(t.updated_at);
    return !Number.isNaN(updatedMs) && updatedMs > seenMs;
  });
}
