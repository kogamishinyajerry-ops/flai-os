<template>
  <div class="wb-session">
    <div class="wb-back">
      <el-button text @click="$router.push('/workbench')">← 协作工作台</el-button>
      <div class="wb-back-actions">
        <el-button
          v-if="conversation && conversation.status === 'active'"
          text
          @click="concludeSession"
        >结束协作</el-button>
        <el-button text :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <!-- 三态降级：加载中 / 出错 / 就绪 -->
    <div v-if="loading && !conversation" class="wb-state" v-loading="true" style="min-height: 200px"></div>

    <el-alert
      v-else-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
    />

    <template v-else-if="conversation">
      <!-- 会话头 -->
      <div class="sess-hero">
        <div class="sess-hero-main">
          <div class="sess-title-row">
            <h2>协作会话</h2>
            <el-tag :type="conversation.status === 'active' ? 'primary' : 'info'" effect="plain" size="small">
              {{ conversation.status === "active" ? "进行中" : "已归档" }}
            </el-tag>
          </div>
          <p v-if="goal" class="sess-goal"><strong>目标：</strong>{{ goal }}</p>
          <p v-else class="sess-goal muted">本次会话尚未形成明确的协作目标。</p>
          <div class="sess-meta">
            <span>发起人：{{ conversation.created_by }}</span>
            <span>· 会话 {{ conversation.id.slice(0, 16) }}</span>
          </div>
        </div>
        <div class="sess-progress">
          <div class="prog-num">{{ summonedCount }} / {{ rosterAgents.length }}</div>
          <div class="prog-label">已召集 Agent</div>
          <div class="prog-sub">{{ completedCount }} 个任务已完成 · 共 {{ memberTasks.length }} 个任务</div>
        </div>
      </div>

      <!-- refuse：会话以显式拒绝收尾 -->
      <el-alert
        v-if="plan && plan.decision === 'refuse'"
        type="warning"
        :closable="false"
        show-icon
        class="sess-block"
        :title="'本次会话未形成协作——导引判断平台接不住：' + (plan.reason || '')"
      />

      <!-- orchestrate：分工架构（蓝图）+ 召集台 -->
      <template v-if="plan && plan.decision === 'orchestrate'">
        <div v-if="plan.analysis || plan.workflow" class="sess-block blueprint">
          <div class="block-label">分工架构</div>
          <p v-if="plan.analysis" class="bp-line">{{ plan.analysis }}</p>
          <p v-if="plan.workflow" class="bp-line"><span class="bp-tag">协作方式</span>{{ plan.workflow }}</p>
        </div>

        <div class="roster">
          <div v-for="(a, ai) in rosterAgents" :key="ai" class="member">
            <div class="member-bar" :style="{ background: categoryColor(a.category) }"></div>
            <div class="member-inner">
              <div class="member-head">
                <span class="member-name">{{ a.agent_name }}</span>
                <span class="member-pill" :style="{ color: categoryColor(a.category), background: categoryColor(a.category) + '18' }">
                  {{ categoryLabel(a.category) }}
                </span>
                <span v-if="tasksFor(a).length" class="member-state summoned">已召集 · {{ tasksFor(a).length }} 个任务</span>
                <span v-else class="member-state pending">尚未召集</span>
              </div>
              <p v-if="a.role" class="member-role"><strong>分工：</strong>{{ a.role }}</p>

              <!-- 已召集：成员任务（到席灯 + 状态 + 详情链接；waiting_review 醒目提示放行） -->
              <div v-if="tasksFor(a).length" class="task-chips">
                <div
                  v-for="t in tasksFor(a)"
                  :key="t.id"
                  :class="['task-chip', { review: t.status === 'waiting_review' }]"
                  @click="goTask(t)"
                >
                  <span class="chip-lamp" :style="{ background: taskLampColor(t.status) }"></span>
                  <span class="chip-name">{{ t.name || t.id.slice(0, 12) }}</span>
                  <span class="chip-status" :style="{ color: taskLampColor(t.status) }">{{ statusLabel(t.status) }}</span>
                  <span v-if="t.status === 'waiting_review'" class="chip-review">待人工放行 →</span>
                </div>
              </div>

              <!-- 未召集：会话进行中才可从蓝图召集（人签发；导引不代召集）；
                   会话已归档则只读，不再召集（结束协作 = 真的结束）。 -->
              <div v-else-if="conversation.status === 'active'" class="member-action">
                <el-button size="small" type="primary" plain @click="summon(a)">去创建此任务</el-button>
                <span class="member-hint">用导引预填的草案创建任务，由你补全并亲手提交。</span>
              </div>
              <div v-else class="member-action">
                <span class="member-hint">会话已归档，未召集——如需继续，请从智能导引开启新协作。</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <div v-else-if="!plan" class="sess-block">
        <p class="muted">本次会话没有形成结构化协作方案（可能仍在澄清需求，或以纯对话收尾）。</p>
      </div>

      <!-- 方案之外的会话内任务（防漏：归到本会话但不在蓝图 roster 里的任务） -->
      <div v-if="otherTasks.length" class="sess-block">
        <div class="block-label">其它归属本会话的任务</div>
        <div class="task-chips">
          <div v-for="t in otherTasks" :key="t.id" :class="['task-chip', { review: t.status === 'waiting_review' }]" @click="goTask(t)">
            <span class="chip-lamp" :style="{ background: taskLampColor(t.status) }"></span>
            <span class="chip-name">{{ t.name || t.agent_id }}</span>
            <span class="chip-status" :style="{ color: taskLampColor(t.status) }">{{ statusLabel(t.status) }}</span>
          </div>
        </div>
      </div>

      <p class="sess-foot">
        签发权在你——协作里每个任务都由你在创建页补全并亲手提交，导引只做分流与预填，不代签、不代召集。
      </p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { getConversation, listConversationTasks, concludeConversation } from "../api/conversations";
import { categoryColor, categoryLabel, statusLabel, taskLampColor } from "../utils/format";

const route = useRoute();
const router = useRouter();
const sessionId = route.params.sessionId;

const conversation = ref(null);
const memberTasks = ref([]);
const loading = ref(false);
const loadError = ref("");

const plan = computed(() => conversation.value?.recommendation || null);
const goal = computed(() => (plan.value?.decision === "orchestrate" ? plan.value.goal : ""));
const rosterAgents = computed(() => (plan.value?.decision === "orchestrate" ? plan.value.agents || [] : []));
const rosterAgentIds = computed(() => new Set(rosterAgents.value.map((a) => a.agent_id)));

function tasksFor(agent) {
  return memberTasks.value.filter((t) => t.agent_id === agent.agent_id);
}
const summonedCount = computed(() => rosterAgents.value.filter((a) => tasksFor(a).length > 0).length);
const completedCount = computed(() => memberTasks.value.filter((t) => t.status === "completed").length);
const otherTasks = computed(() => memberTasks.value.filter((t) => !rosterAgentIds.value.has(t.agent_id)));

async function load() {
  loading.value = true;
  try {
    const [conv, tasks] = await Promise.all([
      getConversation(sessionId),
      listConversationTasks(sessionId),
    ]);
    conversation.value = conv;
    memberTasks.value = tasks;
    loadError.value = "";
  } catch (err) {
    loadError.value = err.detail || err.message || "加载协作会话失败";
  } finally {
    loading.value = false;
  }
}

function goTask(t) {
  router.push(`/tasks/${t.id}`);
}

async function concludeSession() {
  // 结束协作：会话 active→concluded（归档）。已创建的成员任务不受影响、仍可查看；
  // 归档后不再从蓝图召集新 Agent（结束 = 真的结束）。二次确认防误点。
  try {
    await ElMessageBox.confirm(
      "结束后本次协作归档：已创建的任务不受影响、仍可查看，但不再从蓝图召集新的 Agent。确定结束？",
      "结束协作",
      { confirmButtonText: "确定结束", cancelButtonText: "再想想", type: "warning" }
    );
  } catch {
    return; // 用户取消
  }
  try {
    await concludeConversation(sessionId);
    ElMessage.success("协作已归档");
    await load();
  } catch (err) {
    ElMessage.error(err.detail || err.message || "结束协作失败");
  }
}

function summon(agent) {
  // 从蓝图召集：把该 Agent 的预填草案交创建页（带会话 id，回到本会话分组），
  // 人补全后亲手提交。走 sessionStorage 与导引同一接缝，导引不代签、不代召集。
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({
      agent_id: agent.agent_id,
      inputs: agent.prefilled_inputs || {},
      files: [],
      conversation_id: sessionId,
    })
  );
  router.push({ path: "/tasks/new", query: { agent_id: agent.agent_id, from: "guide" } });
}

onMounted(load);
</script>

<style scoped>
.wb-back {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.wb-back-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}
.sess-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  background: linear-gradient(135deg, var(--paper-cream), var(--paper-surface));
  border: 1px solid var(--hairline);
  border-radius: 14px;
  padding: 22px 24px;
  margin-bottom: 18px;
}
.sess-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.sess-title-row h2 {
  margin: 0;
  font-size: 20px;
}
.sess-goal {
  margin: 0 0 8px;
  color: var(--ink);
  line-height: 1.6;
  max-width: 640px;
}
.sess-goal.muted,
.muted {
  color: var(--ink-faint);
}
.sess-meta {
  font-size: 12px;
  color: var(--ink-faint);
  display: flex;
  gap: 6px;
}
.sess-progress {
  text-align: right;
  white-space: nowrap;
}
.prog-num {
  font-size: 26px;
  font-weight: 800;
  color: var(--clay);
}
.prog-label {
  font-size: 12px;
  color: var(--ink-soft);
}
.prog-sub {
  font-size: 11px;
  color: var(--ink-faint);
  margin-top: 6px;
}
.sess-block {
  margin-bottom: 16px;
}
.block-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 8px;
}
.blueprint {
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 10px;
  padding: 14px 16px;
}
.bp-line {
  margin: 0 0 6px;
  color: #4a443d;
  font-size: 13px;
  line-height: 1.6;
}
.bp-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  color: var(--clay);
  background: var(--clay-soft);
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
}
.roster {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}
.member {
  border: 1px solid var(--hairline);
  border-radius: 10px;
  overflow: hidden;
  background: var(--card-bg);
}
.member-bar {
  height: 3px;
  width: 100%;
}
.member-inner {
  padding: 12px 14px;
}
.member-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.member-name {
  font-weight: 700;
  color: var(--ink);
  font-size: 14px;
}
.member-pill {
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.member-state {
  font-size: 12px;
  font-weight: 600;
  margin-left: auto;
}
.member-state.summoned {
  color: var(--clay);
}
.member-state.pending {
  color: var(--ink-faint);
}
.member-role {
  margin: 0 0 8px;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.5;
}
.member-action {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.member-hint {
  font-size: 12px;
  color: var(--ink-faint);
}
.task-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.task-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--paper-cream);
  cursor: pointer;
  transition: border-color 0.15s;
}
.task-chip:hover {
  border-color: var(--clay-softer);
}
.task-chip.review {
  border-color: var(--trust-pending);
  background: #f9f2e2;
}
.chip-lamp {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.chip-name {
  font-size: 13px;
  color: var(--ink);
  font-weight: 600;
}
.chip-status {
  font-size: 12px;
  font-weight: 600;
}
.chip-review {
  font-size: 12px;
  font-weight: 700;
  color: var(--trust-pending);
}
.sess-foot {
  margin-top: 18px;
  padding-top: 12px;
  border-top: 1px solid var(--hairline-soft);
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.6;
}
</style>
