<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="brand" @click="$router.push('/')">
        <span class="brand-name">FLAi-OS</span>
        <span class="brand-sub">二所工程智能体运行底座 V0.1</span>
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
body {
  margin: 0;
  background: #f5f7fa;
}
.app-shell {
  min-height: 100vh;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 32px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 56px !important;
}
.brand {
  cursor: pointer;
  white-space: nowrap;
}
.brand-name {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}
.brand-sub {
  margin-left: 8px;
  font-size: 12px;
  color: #909399;
}
.nav-menu {
  flex: 1;
  border-bottom: none !important;
}
.app-main {
  max-width: 1080px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
</style>
