// 页面动态 import 的单一出处：生产路由与 speculative prefetch 必须复用同一
// loader，浏览器才能把 hover/idle 预取与真实导航折叠为同一模块请求。
export const routeLoaders = Object.freeze({
  guide: () => import("../views/GuidePage.vue"),
  today: () => import("../views/TodayPage.vue"),
  me: () => import("../views/MePage.vue"),
  portal: () => import("../views/AgentPortal.vue"),
  workbenchSession: () => import("../views/WorkbenchSession.vue"),
  taskConsole: () => import("../views/TaskConsole.vue"),
  feedback: () => import("../views/FeedbackPage.vue"),
  lifeDemo: () => import("../views/LifeDemoPage.vue"),
});

function normalizedPath(rawPath) {
  if (typeof rawPath !== "string") return null;
  const path = rawPath.split(/[?#]/, 1)[0];
  if (!path.startsWith("/")) return null;
  if (path.length > 1 && path.endsWith("/")) return path.slice(0, -1);
  return path;
}

export function routeKeyForPath(rawPath) {
  const path = normalizedPath(rawPath);
  if (!path) return null;
  if (path === "/" || path === "/tasks/new") return "guide";
  if (path === "/today") return "today";
  if (path === "/me") return "me";
  if (path === "/portal") return "portal";
  if (path === "/workbench") return "taskConsole";
  if (path.startsWith("/workbench/")) return "workbenchSession";
  if (path === "/tasks" || path.startsWith("/tasks/")) return "taskConsole";
  if (path === "/feedback") return "feedback";
  if (path === "/demo") return "lifeDemo";
  return null;
}

export function createRoutePrefetcher(loaders = routeLoaders) {
  const requests = new Map();

  return function prefetch(rawPath) {
    const key = routeKeyForPath(rawPath);
    const loader = key ? loaders[key] : null;
    if (typeof loader !== "function") return Promise.resolve(false);

    const existing = requests.get(key);
    if (existing) return existing;

    const request = Promise.resolve()
      .then(loader)
      .then(() => true)
      .catch((error) => {
        // speculative 失败不能毒化真实导航；删掉缓存，点击时由 vue-router 重试。
        requests.delete(key);
        throw error;
      });
    requests.set(key, request);
    return request;
  };
}

export const prefetchRoute = createRoutePrefetcher();

export function shouldPrefetchRoutes({
  acceptanceMode = false,
  isDev = false,
  pathname = "",
} = {}) {
  if (acceptanceMode) return false;
  // UI Lab 是 DEV ONLY 的只读 fixture 面；即使 App 被单独嵌入，也不得提前
  // import 产品路由 chunk，避免验收边界被无关模块串台。
  if (isDev && /(?:^|\/)ui-lab\.html$/.test(pathname)) return false;
  return true;
}

const noop = () => {};

export function scheduleIdleRoutePrefetch(paths, {
  enabled = true,
  prefetch = prefetchRoute,
  requestIdleCallback = globalThis.requestIdleCallback?.bind(globalThis),
  cancelIdleCallback = globalThis.cancelIdleCallback?.bind(globalThis),
  setTimeoutFn = globalThis.setTimeout?.bind(globalThis),
  clearTimeoutFn = globalThis.clearTimeout?.bind(globalThis),
  timeoutMs = 1_200,
} = {}) {
  const uniquePaths = [...new Set((paths || []).filter((path) => typeof path === "string"))];
  if (!enabled || !uniquePaths.length) return noop;

  let active = true;
  const warm = async () => {
    if (!active) return;
    // 预取永远是 best effort：失败只意味着点击时重试，不能制造控制台未处理拒绝。
    await Promise.allSettled(uniquePaths.map((path) => prefetch(path)));
  };

  if (typeof requestIdleCallback === "function") {
    const idleId = requestIdleCallback(warm, { timeout: timeoutMs });
    return () => {
      active = false;
      if (typeof cancelIdleCallback === "function") cancelIdleCallback(idleId);
    };
  }

  if (typeof setTimeoutFn !== "function") return noop;
  const timerId = setTimeoutFn(warm, timeoutMs);
  return () => {
    active = false;
    if (typeof clearTimeoutFn === "function") clearTimeoutFn(timerId);
  };
}
