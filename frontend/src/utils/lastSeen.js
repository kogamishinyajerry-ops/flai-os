// 会话「已读」标记（本地存储，B2）：驱动协作工作台首页会话卡片的完成未读徽章。
// 纯前端便利标记，不改变任何签发/审核语义——只回答"这次会话我看过之后有没有新进展"。
// 隐私模式/禁用 storage 时静默降级：不记录、不阻断页面，效果等同于"从未 seen"。

const KEY = "flai_session_seen";

function readMap(storageKey = KEY) {
  try {
    const raw = localStorage.getItem(storageKey);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeMap(map, storageKey = KEY) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(map));
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

// ── 任务级未读（范式 2c，任务台左栏「完成未读点」）──────────────────────
// 与会话版同哲学、不同锚：任务没有「进入会话即 seen」的天然锚点，改用
// baseline——首次进入任务台时锚定当下。此前的历史终态一律不标（避免首访
// 被存量任务刷成满屏点），此后新到达终态、且还没打开过详情的任务亮点。
// waiting_review 不进未读点：它已有 amber 置顶组强 CTA，双信号即噪声。
const TASK_KEY = "flai_task_seen";
const TASK_BASELINE_KEY = "flai_task_seen_baseline";
const NOTABLE_TASK_FINALS = new Set(["completed", "failed"]);
const TASK_SEEN_CAP = 200; // localStorage 防膨胀：超上限按 seen 时间淘汰最旧

// 首次进入任务台时调用：已有锚不动（幂等）。
export function ensureTaskBaseline() {
  try {
    if (!localStorage.getItem(TASK_BASELINE_KEY)) {
      localStorage.setItem(TASK_BASELINE_KEY, new Date().toISOString());
    }
  } catch {
    /* 隐私模式静默降级：效果等同「从未锚定」，未读点整体不启用 */
  }
}

// 打开任务详情/速览即视为「已看过」。
export function markTaskSeen(taskId) {
  if (!taskId) return;
  const map = readMap(TASK_KEY);
  map[taskId] = new Date().toISOString();
  const ids = Object.keys(map);
  if (ids.length > TASK_SEEN_CAP) {
    // 已知边界：条目被外部篡改成非法日期时比较器返 NaN（sort 视作相等、留在
    // 原位），可能误淘汰一条合法旧记录——正常写入路径永远是合法 ISO，且读路径
    // taskHasUnseen 对坏时间戳 fail 向「不标」，影响面可接受。
    ids.sort((a, b) => Date.parse(map[a]) - Date.parse(map[b]));
    for (const id of ids.slice(0, ids.length - TASK_SEEN_CAP)) delete map[id];
  }
  writeMap(map, TASK_KEY);
}

// 该任务是否「完成后你还没看过」：终态 + 晚于 baseline + 晚于（或没有）
// seen 记录。任何一环无从判断（没锚/时间戳坏）诚实返回 false——不标 ≠
// 没有新进展，而是「无证据不标」。
export function taskHasUnseen(task) {
  if (!task || !NOTABLE_TASK_FINALS.has(task.status) || !task.updated_at) return false;
  let baseline = null;
  try {
    baseline = localStorage.getItem(TASK_BASELINE_KEY);
  } catch {
    return false;
  }
  if (!baseline) return false;
  const updatedMs = Date.parse(task.updated_at);
  const baseMs = Date.parse(baseline);
  if (Number.isNaN(updatedMs) || Number.isNaN(baseMs) || updatedMs <= baseMs) return false;
  const seenAt = readMap(TASK_KEY)[task.id];
  if (!seenAt) return true;
  const seenMs = Date.parse(seenAt);
  return !Number.isNaN(seenMs) && updatedMs > seenMs;
}
