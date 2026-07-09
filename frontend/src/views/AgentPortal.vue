<template>
  <div class="agent-portal">
    <div class="page-header">
      <h2>Agent 门户</h2>
      <p class="page-sub">选择一个 Agent 创建任务</p>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <el-skeleton v-if="loading" :rows="4" animated />

    <el-empty v-else-if="!loadError && agents.length === 0" description="暂无可用 Agent" />

    <el-row v-else :gutter="16">
      <el-col v-for="agent in agents" :key="agent.id" :span="8" class="agent-col">
        <el-card class="agent-card" shadow="hover" :body-style="{ padding: '0' }">
          <div class="cat-bar" :style="{ background: categoryColor(agent.category) }"></div>
          <div class="card-inner">
            <div class="agent-card-header">
              <span class="agent-name">{{ agent.name }}</span>
              <el-tag :type="statusTagType(agent.status)" size="small" effect="light">{{ statusLabel(agent.status) }}</el-tag>
            </div>

            <div class="agent-tags">
              <span
                class="cat-pill"
                :style="{ color: categoryColor(agent.category), background: categoryColor(agent.category) + '18' }"
                :title="categoryTip(agent.category)"
              >{{ categoryLabel(agent.category) }}</span>
              <el-tag v-if="agent.maturity" type="info" effect="plain" size="small">{{ agent.maturity }}</el-tag>
            </div>
            <div class="agent-meta">
              <span>{{ agent.id }}</span>
              <span>v{{ agent.version }}</span>
            </div>

          <p class="agent-summary">{{ agent.summary }}</p>

          <el-collapse v-if="agent.limitations && agent.limitations.length">
            <el-collapse-item title="不适用范围">
              <ul class="limitations-list">
                <li v-for="(item, idx) in agent.limitations" :key="idx">{{ item }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>

            <div class="agent-actions">
              <el-button type="primary" :disabled="agent.status === 'disabled'" @click="createTaskFor(agent)">
                创建任务
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { listAgents } from "../api/agents";
import { statusLabel, statusTagType, categoryLabel, categoryColor, categoryTip } from "../utils/format";

const router = useRouter();
const agents = ref([]);
const loading = ref(true);
const loadError = ref("");

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    agents.value = await listAgents();
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loading.value = false;
  }
}

function createTaskFor(agent) {
  router.push({ path: "/tasks/new", query: { agent_id: agent.id } });
}

onMounted(load);
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0 0 4px;
}
.page-sub {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.page-alert {
  margin-bottom: 16px;
}
.agent-col {
  margin-bottom: 16px;
}
.agent-card {
  height: 100%;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  transition: transform 0.15s ease;
}
.agent-card:hover {
  transform: translateY(-2px);
}
.cat-bar {
  height: 4px;
  width: 100%;
}
.card-inner {
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  height: calc(100% - 4px);
  box-sizing: border-box;
}
.agent-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.agent-name {
  font-weight: 700;
  font-size: 15.5px;
  color: var(--ink);
}
.agent-meta {
  display: flex;
  gap: 12px;
  color: var(--ink-soft);
  font-size: 12px;
  font-family: "SF Mono", ui-monospace, monospace;
  margin-bottom: 10px;
}
.agent-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.cat-pill {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
}
.agent-summary {
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
}
.limitations-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #606266;
}
.agent-actions {
  margin-top: auto;
  padding-top: 12px;
  text-align: right;
}
</style>
