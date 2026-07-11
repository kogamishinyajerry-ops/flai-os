import { createRouter, createWebHistory } from "vue-router";

// 路由（任务书 §12.3 + 范式 Phase 2b 双 Surface）。组件懒加载保持首屏轻。
// 2b 骨架手术：应用收敛为「对话（/）| 任务台（/tasks）」双 Surface——
// WorkbenchHome/TaskHistory 一级页面退役（功能并入任务台三栏），/workbench
// 重定向保深链不断；TaskDetail 降级为任务台中栏组件（/tasks/:taskId 仍达
// 同一任务视图，旧深链全兼容）；Agent 门户退出一级导航，/portal 保留深链。
const routes = [
  { path: "/", name: "guide", component: () => import("../views/GuidePage.vue"), meta: { title: "对话" } },
  { path: "/portal", name: "portal", component: () => import("../views/AgentPortal.vue"), meta: { title: "Agent 门户" } },
  { path: "/workbench", redirect: "/tasks" },
  { path: "/workbench/:sessionId", name: "workbench-session", component: () => import("../views/WorkbenchSession.vue"), meta: { title: "协作会话" } },
  { path: "/tasks/new", name: "task-create", component: () => import("../views/TaskCreate.vue"), meta: { title: "创建任务" } },
  // 任务台（Codex 三栏）：/tasks=列表+空态；/tasks/:taskId=选中任务的叙事流
  // +输出/来源面板。两路由同组件，meta.pageKey 让 page-turn 过渡不因选中
  // 切换整页重挂（中栏 TaskDetail 靠 :key=taskId 自行重建）。
  { path: "/tasks", name: "task-console", component: () => import("../views/TaskConsole.vue"), meta: { title: "任务台", pageKey: "console" } },
  { path: "/tasks/:taskId", name: "task-detail", component: () => import("../views/TaskConsole.vue"), meta: { title: "任务详情", pageKey: "console" } },
  { path: "/feedback", name: "feedback", component: () => import("../views/FeedbackPage.vue"), meta: { title: "反馈" } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · FLAi-OS` : "FLAi-OS";
});

export default router;
