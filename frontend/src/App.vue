<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand" @click="$router.push('/')">
        <span class="brand-mark">F</span>
        <span class="brand-text">
          <span class="brand-name">FLAi-OS</span>
          <span class="brand-sub">二所工程智能体运行底座 · V0.1</span>
        </span>
      </div>
      <!-- M8 IA：顶导航收敛为三个真入口——导引(门面)/门户(浏览 Agent)/工作台
           (协作会话)。创建任务从门户+导引进入、反馈在任务详情内、任务历史折入
           工作台，都不再占顶导航（路由仍在，上下文内可达）。 -->
      <el-menu mode="horizontal" :default-active="activeMenu" router :ellipsis="false" class="nav-menu">
        <el-menu-item index="/">智能导引</el-menu-item>
        <el-menu-item index="/portal">Agent 门户</el-menu-item>
        <el-menu-item index="/workbench">协作工作台</el-menu-item>
      </el-menu>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
// 任务相关页（历史/详情/创建）与协作会话子页在 M8 IA 里都归属「协作工作台」高亮。
const activeMenu = computed(() => {
  const p = route.path;
  if (p === "/tasks" || p.startsWith("/tasks/")) return "/workbench";
  if (p.startsWith("/workbench/")) return "/workbench";
  return p;
});
</script>

<style>
/* 全局设计变量：clay 暖橙作品牌与强调锚点，暖白背景，收敛的语义色。
 *
 * 信任色锁（M8，收编自 COMACAgentPlatform 协作面，焊死纪律）：语义色只表状态、
 * 绝不被装饰借用——clay=工作/进行/选中（唯一彩色语法）· 绿=仅真实(REAL)数据/结果
 * · teal=仅人签(改变工程状态的唯一合法通道) · 红=仅真失败/驳回 · amber=仅未核/降级。
 * 装饰要用色一律走中性暖阶（--paper-* / --sand-*），不碰上面五个语义槽。
 */
:root {
  --clay: #c15f3c;
  --clay-softer: #cc785c;
  --clay-soft: #f3e5de;
  --ink: #2b2622;
  --ink-soft: #6b6259;
  --ink-faint: #a39d90;
  --page-bg: #faf7f2;
  --card-bg: #ffffff;
  --hairline: #ece5db;
  --hairline-soft: #f0ece2;
  /* 暖纸阶（协作工作台底色，收编自 team.css）*/
  --paper-canvas-a: #fcfbf7;
  --paper-canvas-b: #f1eee6;
  --paper-surface: #fdfcf9;
  --paper-rail: #f7f4ec;
  --paper-cream: #fbf9f3;
  /* 信任语义锁（只表状态，绝不装饰借用）*/
  --trust-real: #2e8f50;   /* 绿：仅真实数据/结果 */
  --trust-signed: #167d8b; /* teal：仅人签 */
  --trust-fail: #be3a3a;   /* 红：仅真失败/驳回 */
  --trust-pending: #a8761a;/* amber：仅未核/降级 */
  /* elevation：暖调柔阴影（纯工艺层，中性 ink 色不碰语义槽）——静止态极轻、hover 抬升。
   * 卡片从"只有边框的扁平"升为"有纸感的浮起"，是本轮 UI 抬升的主手段。*/
  --shadow-card: 0 1px 2px rgba(43, 38, 34, 0.035), 0 4px 14px rgba(72, 58, 44, 0.05);
  --shadow-card-hover: 0 2px 6px rgba(43, 38, 34, 0.06), 0 12px 30px rgba(72, 58, 44, 0.10);
  --shadow-hero: 0 1px 3px rgba(43, 38, 34, 0.04), 0 10px 34px rgba(72, 58, 44, 0.06);
  --ease-lift: 0.18s cubic-bezier(0.22, 0.61, 0.36, 1);
  --el-color-primary: #c15f3c;
  --el-color-primary-light-3: #d08663;
  --el-color-primary-light-5: #dba489;
  --el-color-primary-light-7: #e8c6b4;
  --el-color-primary-light-8: #f0d9cc;
  --el-color-primary-light-9: #f6e7de;
  --el-color-primary-dark-2: #a54e2f;
}
body {
  margin: 0;
  background: var(--page-bg);
  color: var(--ink);
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
}
.app-shell {
  min-height: 100vh;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 40px;
  background: var(--card-bg);
  border-bottom: 1px solid var(--hairline);
  height: 60px !important;
  padding: 0 28px;
  box-shadow: 0 1px 3px rgba(43, 38, 34, 0.04);
}
.brand {
  cursor: pointer;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--clay);
  color: #fff;
  font-weight: 800;
  font-size: 17px;
  box-shadow: 0 2px 6px rgba(193, 95, 60, 0.32);
}
.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: 0.3px;
}
.brand-sub {
  font-size: 11px;
  color: var(--ink-soft);
}
.nav-menu {
  flex: 1;
  border-bottom: none !important;
  background: transparent !important;
}
.nav-menu .el-menu-item.is-active {
  color: var(--clay) !important;
  border-bottom-color: var(--clay) !important;
  font-weight: 600;
}
.app-main {
  max-width: 1080px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: 24px 20px 48px;
}
</style>
