import { createRouter, createWebHistory } from "vue-router";

// 路由（任务书 §12.3 + M6 导引页）。组件懒加载保持首屏轻。
const routes = [
  { path: "/", name: "guide", component: () => import("../views/GuidePage.vue"), meta: { title: "智能导引" } },
  { path: "/portal", name: "portal", component: () => import("../views/AgentPortal.vue"), meta: { title: "Agent 门户" } },
  // M8：协作工作台是任务相关页的门面（顶导航第三入口）。P1 先承载「最近任务」
  // 总览（旧 /tasks 历史折入此处，路由仍在但从导航撤出），多 Agent 协作会话视图
  // 在 P3/P4 长出。
  { path: "/workbench", name: "workbench", component: () => import("../views/WorkbenchHome.vue"), meta: { title: "协作工作台" } },
  { path: "/tasks/new", name: "task-create", component: () => import("../views/TaskCreate.vue"), meta: { title: "创建任务" } },
  { path: "/tasks", name: "task-history", component: () => import("../views/TaskHistory.vue"), meta: { title: "任务历史" } },
  { path: "/tasks/:taskId", name: "task-detail", component: () => import("../views/TaskDetail.vue"), meta: { title: "任务详情" } },
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
