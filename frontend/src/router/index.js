import { nextTick } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { setTitleBase } from "../utils/titleBadge";
import { PLATFORM_NAME } from "../utils/branding";

// 路由（任务书 §12.3 + 范式 Phase 2b 双 Surface）。组件懒加载保持首屏轻。
// 2b 骨架手术：应用收敛为「对话（/）| 任务台（/tasks）」双 Surface——
// WorkbenchHome/TaskHistory 一级页面退役（功能并入任务台三栏），/workbench
// 重定向保深链不断；TaskDetail 降级为任务台中栏组件（/tasks/:taskId 仍达
// 同一任务视图，旧深链全兼容）；Agent 门户退出一级导航，/portal 保留深链。
const routes = [
  { path: "/", name: "guide", component: () => import("../views/GuidePage.vue"), meta: { title: "对话" } },
  { path: "/today", name: "today", component: () => import("../views/TodayPage.vue"), meta: { title: "今日" } },
  { path: "/me", name: "me", component: () => import("../views/MePage.vue"), meta: { title: "我的贡献" } },
  { path: "/portal", name: "portal", component: () => import("../views/AgentPortal.vue"), meta: { title: "Agent 门户" } },
  { path: "/workbench", redirect: "/tasks" },
  { path: "/workbench/:sessionId", name: "workbench-session", component: () => import("../views/WorkbenchSession.vue"), meta: { title: "协作会话" } },
  // 历史创建页只保留为源码兼容面，不再是工程师可达 Surface。旧书签、旧通知
  // 或手工输入的 /tasks/new 一律丢弃 Agent/参数 query，回到唯一主对话入口。
  { path: "/tasks/new", redirect: () => ({ path: "/", query: {} }) },
  // 任务台（Codex 三栏）：/tasks=列表+空态；/tasks/:taskId=选中任务的叙事流
  // +输出/来源面板。两路由同组件，meta.pageKey 让 page-turn 过渡不因选中
  // 切换整页重挂（中栏 TaskDetail 靠 :key=taskId 自行重建）。
  { path: "/tasks", name: "task-console", component: () => import("../views/TaskConsole.vue"), meta: { title: "任务台", pageKey: "console" } },
  { path: "/tasks/:taskId", name: "task-detail", component: () => import("../views/TaskConsole.vue"), meta: { title: "任务详情", pageKey: "console" } },
  { path: "/feedback", name: "feedback", component: () => import("../views/FeedbackPage.vue"), meta: { title: "反馈" } },
  // 本体论教学 demo(L1):独立于工程任务主线,不进主对话。
  // admin_only 的 life_guide_agent 走 quarantine 隔离区,不污染生产 Registry。
  { path: "/demo", name: "life-demo", component: () => import("../views/LifeDemoPage.vue"), meta: { title: "本体论 demo" } },
];

// 重挂判据（B6-2）：与 App.vue 的 page-turn :key 同式（pageKey||path）——
// 任务台内选中切换、/?c= 回流等「同 Surface」导航不重挂。
const keyOf = (r) => String(r.meta.pageKey || r.path);

const router = createRouter({
  history: createWebHistory(),
  routes,
  // 滚动契约（3-lens a11y 审 P2b）：roving focus 用 preventScroll，滚动归属
  // 权在此处而非 focus 副作用——真翻页回顶；浏览器后退/前进还原既存位置；
  // 同 pageKey 导航不动滚动（任务台选中一行不许跳顶）。
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition;
    if (from.matched.length && keyOf(to) === keyOf(from)) return false;
    return { top: 0 };
  },
});

router.afterEach((to, from, failure) => {
  // 取消/中止的导航（重复导航、被后续导航打断、懒加载失败）不改 title、
  // 不抢焦、不播报未到达的目的页（Codex R0 审 P2——afterEach 对失败导航
  // 也会触发，failure 非空即整体让位）。
  if (failure) return;
  // N5：经 titleBadge 合成（全应用唯一 title 写手），徽章计数不因路由切换丢失。
  setTitleBase(to.meta.title ? `${to.meta.title} · ${PLATFORM_NAME}` : PLATFORM_NAME);

  // roving focus（批次六 B6-2，router 级——批五反采纳单点实现的正确形态）：
  // 页面真重挂时把焦点移交主区容器，键盘/读屏用户从新页内容起 Tab，不从
  // body/文档顶重爬；同拍写 aria-live 播报（3-lens a11y 审 P2a：focus-only
  // 读屏只报 landmark，title 变化不播报）。首载（from 无匹配）保留浏览器
  // 默认焦点行为，也不播报。
  if (!from.matched.length) return;
  if (keyOf(to) === keyOf(from)) return;
  nextTick(() => {
    requestAnimationFrame(() => {
      const main = document.querySelector(".app-main");
      if (main) main.focus({ preventScroll: true });
      const ann = document.querySelector(".sr-announcer");
      if (ann) ann.textContent = `已切换到${to.meta.title || "页面"}`;
    });
  });
});

export default router;
