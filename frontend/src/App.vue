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
      <el-menu mode="horizontal" :default-active="activeMenu" router :ellipsis="false" class="nav-menu">
        <el-menu-item index="/">Agent 门户</el-menu-item>
        <el-menu-item index="/tasks/new">创建任务</el-menu-item>
        <el-menu-item index="/tasks">任务历史</el-menu-item>
        <el-menu-item index="/feedback">反馈</el-menu-item>
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
// 任务详情页归属「任务历史」高亮
const activeMenu = computed(() =>
  route.path.startsWith("/tasks/") && route.name === "task-detail" ? "/tasks" : route.path
);
</script>

<style>
/* 全局设计变量：clay 暖橙作品牌与强调锚点，暖白背景，收敛的语义色。 */
:root {
  --clay: #c15f3c;
  --clay-soft: #f3e5de;
  --ink: #2b2622;
  --ink-soft: #6b6259;
  --page-bg: #faf7f2;
  --card-bg: #ffffff;
  --hairline: #ece5db;
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
