<template>
  <div class="agent-portal">
    <div class="page-header">
      <BackLink label="任务台" fallback="/tasks" />
      <h2>Agent 门户</h2>
      <p class="page-sub">选择一个 Agent 创建任务</p>
      <p class="portal-legend">
        卡片左侧色条 = Agent 类型；<b>状态</b>标签（草案态/试运行/已发布）表示发布程度；<b>成熟度</b>
        L0→L3 表示可信程度（L0 为原型，勿依赖其结论）。悬停任一徽章可看释义。
      </p>
    </div>

    <ErrorState v-if="loadError" :message="loadError" :retry="load" class="page-alert" />

    <!-- 首载骨架（A3）：只在「从未加载完成且无错误」时撑卡片栅格轮廓，轮询期间
         /带旧值刷新绝不回骨架（本页无轮询，loading 天然只在首载为真）；失败态
         走上面 el-alert，骨架不吞错误。 -->
    <div v-if="loading && !loadError" class="portal-skel-grid">
      <div v-for="i in 6" :key="i" class="portal-skel-card">
        <SkeletonBlock height="18px" width="60%" />
        <SkeletonBlock height="13px" width="40%" />
        <SkeletonBlock height="13px" width="90%" />
        <SkeletonBlock height="13px" width="75%" />
      </div>
    </div>

    <EmptyState v-else-if="!loadError && agents.length === 0" description="暂无可用 Agent" />

    <el-row v-else :gutter="16" class="fx-stagger">
      <el-col v-for="agent in agents" :key="agent.id" :xs="24" :sm="12" :md="8" class="agent-col">
        <el-card class="agent-card" shadow="never" :body-style="{ padding: '0' }">
          <div class="cat-bar" :style="{ background: categoryColor(agent.category) }"></div>
          <div class="card-inner">
            <div class="agent-card-header">
              <span class="agent-name">{{ agent.name }}</span>
              <el-tag
                :type="statusTagType(agent.status)"
                size="small"
                effect="light"
                :title="agentStatusTip(agent.status)"
              >{{ agentStatusLabel(agent.status) }}</el-tag>
            </div>

            <div class="agent-tags">
              <span
                class="cat-pill"
                :style="{ color: categoryColor(agent.category), background: categoryColor(agent.category) + '18' }"
                :title="categoryTip(agent.category)"
              >{{ categoryLabel(agent.category) }}</span>
              <el-tag
                v-if="agent.maturity"
                type="info"
                effect="plain"
                size="small"
                :title="maturityTip(agent.maturity)"
              >{{ agent.maturity }}</el-tag>
              <button type="button" class="gov-entry" @click="openGovernance(agent)">治理</button>
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
              <el-button
                v-if="agent.mode === 'interactive'"
                type="primary"
                :disabled="agent.status === 'disabled'"
                @click="startConversationFor(agent)"
              >
                开始对话
              </el-button>
              <el-button
                v-else
                type="primary"
                :disabled="agent.status === 'disabled'"
                @click="createTaskFor(agent)"
              >
                创建任务
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <AgentGovernanceDialog v-model:visible="govVisible" :agent="govAgent" @changed="onGovernanceChanged" />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import BackLink from "../components/BackLink.vue";
import ErrorState from "../components/ErrorState.vue";
import { listAgents } from "../api/agents";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import AgentGovernanceDialog from "../components/AgentGovernanceDialog.vue";
import {
  statusTagType,
  agentStatusLabel,
  agentStatusTip,
  maturityTip,
  categoryLabel,
  categoryColor,
  categoryTip,
} from "../utils/format";

const router = useRouter();
const agents = ref([]);
const loading = ref(true);
const loadError = ref("");
const govVisible = ref(false);
const govAgent = ref(null);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    agents.value = await listAgents();
    return true;
  } catch (err) {
    loadError.value = err.detail || err.message;
    return false;
  } finally {
    loading.value = false;
  }
}

function createTaskFor(agent) {
  router.push({ path: "/tasks/new", query: { agent_id: agent.id } });
}

// interactive 型（导引）不是一次性任务——引到对话入口（M6/ADR-0012）。
function startConversationFor() {
  router.push({ path: "/" });
}

function openGovernance(agent) {
  govAgent.value = agent;
  govVisible.value = true;
}

// 治理操作致 agent 数据变化：重拉列表，并把弹窗内展示的 agent 同步到最新行
// （晋升 L1 后徽章/成熟度阶梯/晋升区消失都派生自这一份 prop）
async function onGovernanceChanged(change) {
  const currentId = change?.agentId || govAgent.value?.id;
  if (!currentId) return;
  // 子弹窗的 POST 已成功：先同步本地列表/当前 prop，确保刷新失败也不把 L1 翻回 L0。
  if (change?.maturity && govAgent.value?.id === currentId) {
    govAgent.value = { ...govAgent.value, maturity: change.maturity };
    agents.value = agents.value.map((agent) => (
      agent.id === currentId ? { ...agent, maturity: change.maturity } : agent
    ));
  }
  const refreshedOk = await load();
  if (!refreshedOk) return;
  const refreshed = agents.value.find((a) => a.id === currentId);
  if (refreshed) govAgent.value = refreshed;
}

onMounted(load);
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  font-family: var(--serif);
  font-size: var(--fs-title);
  font-weight: 600;
  letter-spacing: 0.2px;
  margin: 0 0 6px;
}
.page-sub {
  margin: 0;
  color: var(--ink-faint);
  font-size: 13px;
}
.portal-legend {
  margin: 8px 0 0;
  padding: 8px 12px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  color: var(--ink-soft);
  font-size: 12.5px;
  line-height: 1.6;
  max-width: 760px;
}
.portal-legend b {
  color: var(--ink);
}
.page-alert {
  margin-bottom: 16px;
}
.portal-skel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
.portal-skel-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 18px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
}
.agent-col {
  margin-bottom: 16px;
}
.agent-card {
  height: 100%;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: var(--shadow-card);
  /* P4 纸感抬升：统一走动效系统 tokens（--motion-fast + --ease-out-soft），
   * 悬停终态（阴影/位移量）不变，只是过渡节奏与全站微交互对齐。 */
  transition: border-color var(--motion-fast) var(--ease-out-soft),
    box-shadow var(--motion-fast) var(--ease-out-soft),
    transform var(--motion-fast) var(--ease-out-soft);
}
.agent-card:hover {
  border-color: var(--clay-softer);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-2px);
}
@media (prefers-reduced-motion: reduce) {
  .agent-card:hover {
    transform: none;
  }
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
  font-family: var(--mono);
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
.gov-entry {
  border: none;
  background: transparent;
  color: var(--ink-mid);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}
.gov-entry:hover,
.gov-entry:focus-visible {
  color: var(--ink);
  text-decoration: underline;
}
.agent-summary {
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
}
.limitations-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--ink-soft);
}
.agent-actions {
  margin-top: auto;
  padding-top: 12px;
  text-align: right;
}
</style>
