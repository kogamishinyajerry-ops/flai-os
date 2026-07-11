<template>
  <div class="task-history">
    <div class="page-header">
      <h2>任务历史</h2>
    </div>

    <div class="filters">
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 160px" @change="load">
        <el-option v-for="(cfg, key) in TASK_STATUS" :key="key" :label="cfg.label" :value="key" />
      </el-select>
      <el-select
        v-model="filters.agentId"
        placeholder="Agent"
        clearable
        filterable
        style="width: 220px"
        @change="load"
      >
        <el-option v-for="agent in agents" :key="agent.id" :label="`${agent.name}（${agent.id}）`" :value="agent.id" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="page-alert" />

    <!-- el-table 内部行由组件自身虚拟 DOM 管理，.fx-stagger 对其直接子元素不生效
         （硬约束②不 hack el-table 内部结构）；改为外层容器整体 fx-rise 入场——
         容器本身只在页面挂载时创建一次，筛选器 @change="load" 只替换 tasks
         数据不重挂载容器，天然不重播（诚实地板④）。 -->
    <div class="table-card fx-rise">
      <el-table :data="tasks" v-loading="loading" class="task-table" @row-click="goDetail">
        <el-table-column label="ID" width="140">
          <template #default="{ row }">
            <el-link type="primary" :underline="false">{{ row.id.slice(0, 12) }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="名称">
          <template #default="{ row }">{{ row.name || "—" }}</template>
        </el-table-column>
        <el-table-column prop="agent_id" label="Agent" />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="120" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <EmptyState description="暂无任务" :image-size="84" />
        </template>
      </el-table>
    </div>

    <div v-if="hasMore" class="load-more">
      <el-button :loading="loadingMore" @click="loadMore">加载更多</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { listTasks } from "../api/tasks";
import { listAgents } from "../api/agents";
import EmptyState from "../components/EmptyState.vue";
import { statusLabel, statusTagType, formatTime, TASK_STATUS } from "../utils/format";

const router = useRouter();
const tasks = ref([]);
const agents = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const loadError = ref("");
// P2-B「最近任务流」分页：每页 100，append 式加载更多；返回不足一页即到底
// （V0.1 不做总数 COUNT，语义就是往回翻的任务流）。
const PAGE_SIZE = 100;
const hasMore = ref(false);

const filters = reactive({ status: "", agentId: "" });

function _query(offset) {
  return {
    status: filters.status || undefined,
    agentId: filters.agentId || undefined,
    limit: PAGE_SIZE,
    offset,
  };
}

async function load() {
  loading.value = true;
  try {
    const page = await listTasks(_query(0));
    tasks.value = page;
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  loadingMore.value = true;
  try {
    const page = await listTasks(_query(tasks.value.length));
    tasks.value = tasks.value.concat(page);
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loadingMore.value = false;
  }
}

function goDetail(row) {
  router.push(`/tasks/${row.id}`);
}

onMounted(async () => {
  try {
    agents.value = await listAgents();
  } catch {
    // Agent 筛选下拉加载失败不阻塞任务列表本身，静默降级为无 Agent 筛选项。
  }
  await load();
});
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-header h2 {
  font-family: var(--serif);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0;
}
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.page-alert {
  margin-bottom: 16px;
}
.task-table :deep(.el-table__row) {
  cursor: pointer;
}
/* 行 hover 底色已由 Element Plus 内建（--el-table-row-hover-bg-color，中性暖阶，
   见 App.vue 全局映射）；这里只对齐动效系统的过渡节奏，不新增颜色/新增动效。 */
.task-table :deep(.el-table__body td.el-table__cell) {
  transition: background-color var(--motion-fast) var(--ease-out-soft);
}
.load-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
