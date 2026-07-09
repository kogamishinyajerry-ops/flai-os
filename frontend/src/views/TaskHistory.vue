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
        <el-empty description="暂无任务" />
      </template>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { listTasks } from "../api/tasks";
import { listAgents } from "../api/agents";
import { statusLabel, statusTagType, formatTime, TASK_STATUS } from "../utils/format";

const router = useRouter();
const tasks = ref([]);
const agents = ref([]);
const loading = ref(false);
const loadError = ref("");

const filters = reactive({ status: "", agentId: "" });

async function load() {
  loading.value = true;
  try {
    tasks.value = await listTasks({
      status: filters.status || undefined,
      agentId: filters.agentId || undefined,
    });
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loading.value = false;
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
</style>
