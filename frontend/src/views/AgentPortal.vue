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
        <el-card class="agent-card" shadow="hover">
          <template #header>
            <div class="agent-card-header">
              <span class="agent-name">{{ agent.name }}</span>
              <el-tag :type="statusTagType(agent.status)" size="small">{{ statusLabel(agent.status) }}</el-tag>
            </div>
          </template>

          <div class="agent-meta">
            <span>{{ agent.id }}</span>
            <span>v{{ agent.version }}</span>
          </div>
          <div class="agent-tags">
            <el-tag type="info" effect="plain" size="small">{{ categoryLabel(agent.category) }}</el-tag>
            <el-tag v-if="agent.maturity" type="info" effect="plain" size="small">{{ agent.maturity }}</el-tag>
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
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { listAgents } from "../api/agents";
import { statusLabel, statusTagType } from "../utils/format";

const router = useRouter();
const agents = ref([]);
const loading = ref(true);
const loadError = ref("");

// Agent category 枚举中文映射（contracts/agent.schema.json 定义的四型，仅本页展示用）。
const CATEGORY_LABEL = {
  tool_automation: "工具自动化",
  knowledge_qa: "知识问答",
  structured_gen: "结构化生成",
  reasoning_assist: "推理辅助",
};
const categoryLabel = (c) => CATEGORY_LABEL[c] ?? c;

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
  display: flex;
  flex-direction: column;
}
.agent-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.agent-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.agent-name {
  font-weight: 600;
  font-size: 15px;
}
.agent-meta {
  display: flex;
  gap: 12px;
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}
.agent-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
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
