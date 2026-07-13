// frontend/src/stores/liveFeedCore.js —— liveFeed 的纯函数核（零 Vue/DOM 依赖,
// node --test 可测）。语义出处：spec 批A §二；ADR-0013「整包作废」推广为
// epoch 守卫；waiting_review 改降频不停轮（修跨会话放行手动刷新缺陷）。
export const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

export function diffTransitions(prevList, nextList) {
  const prevById = new Map((prevList || []).map((t) => [t.id, t.status]));
  const out = [];
  for (const task of nextList || []) {
    const from = prevById.has(task.id) ? prevById.get(task.id) : null;
    if (from !== task.status) out.push({ id: task.id, from, to: task.status, task });
  }
  return out;
}

export function nextInterval(status) {
  if (TERMINAL_STATUSES.includes(status)) return null;
  if (status === "waiting_review") return 8000;
  return 2000;
}

export function makeEpochGuard() {
  let epoch = 0;
  return {
    current: () => epoch,
    bump: () => { epoch += 1; },
    wrap: (epochAtStart, fn) => (...args) => {
      if (epochAtStart !== epoch) return undefined; // 旧世代整包作废
      return fn(...args);
    },
  };
}

// join 去重（Task 3 网络自证发现）：channel 已 loaded 且 3s 内刚成功拉过
// → join 不再补拉（下一 tick ≤5s 兜底）；否则保持「acquire 即时 refresh」
// 原语义（新订阅者不吃陈旧窗口）。
export const JOIN_FRESH_MS = 3000;
export function shouldRefreshOnJoin(loaded, lastFetchAt, now) {
  if (loaded !== true) return true;
  if (typeof lastFetchAt !== "number") return true;
  return now - lastFetchAt >= JOIN_FRESH_MS;
}
