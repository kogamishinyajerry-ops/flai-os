<template>
  <div class="wb-session">
    <div class="wb-back">
      <el-button text @click="$router.push('/workbench')">← 任务台</el-button>
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
          <div v-if="goal" class="sess-goal-kicker">协作目标</div>
          <p v-if="goal" class="sess-goal">{{ goal }}</p>
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
          <span v-if="waitingReviewCount > 0" class="pill-amber">待你签发 {{ waitingReviewCount }}</span>
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

        <div class="roster fx-stagger">
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

              <!-- 已召集：成员任务（到席灯 + 状态 + 详情链接；waiting_review 醒目提示放行）；
                   chip-lastword（B2）：该任务的「最近动态」=最后一条事件的 message 原文
                   （可能是机械上报文案，不承诺第一人称叙事；仅前 5 个已召集成员取，
                   见 lastWordTargets）。 -->
              <div v-if="tasksFor(a).length" class="task-chips">
                <div v-for="t in tasksFor(a)" :key="t.id" class="chip-group">
                  <div
                    :class="['task-chip', { review: t.status === 'waiting_review' }]"
                    @click="goTask(t)"
                  >
                    <span class="chip-lamp" :class="{ 'is-pulsing': isWorkState(t.status) }" :style="{ background: taskLampColor(t.status) }"></span>
                    <span class="chip-name">{{ t.name || t.id.slice(0, 12) }}</span>
                    <span class="chip-status" :style="{ color: taskLampColor(t.status) }">{{ statusLabel(t.status) }}</span>
                    <span v-if="t.status === 'waiting_review'" class="chip-review">待人工放行 →</span>
                    <span v-else-if="chipActionLabel(t.status)" class="chip-action">{{ chipActionLabel(t.status) }}</span>
                    <!-- B2 速览接入（additive）：chip 本体点击仍走 goTask 跳详情；速览用 @click.stop 独立打开。 -->
                    <button type="button" class="chip-peek-btn" @click.stop="openTaskPeek(t.id)">速览</button>
                  </div>
                  <div v-if="taskLastWord[t.id]" class="chip-lastword">{{ taskLastWord[t.id] }}</div>
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
            <span class="chip-lamp" :class="{ 'is-pulsing': isWorkState(t.status) }" :style="{ background: taskLampColor(t.status) }"></span>
            <span class="chip-name">{{ t.name || t.agent_id }}</span>
            <span class="chip-status" :style="{ color: taskLampColor(t.status) }">{{ statusLabel(t.status) }}</span>
            <span v-if="t.status === 'waiting_review'" class="chip-review">待人工放行 →</span>
            <span v-else-if="chipActionLabel(t.status)" class="chip-action">{{ chipActionLabel(t.status) }}</span>
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
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { getConversation, listConversationTasks, concludeConversation } from "../api/conversations";
import { listTaskEvents } from "../api/tasks";
import { categoryColor, categoryLabel, statusLabel, taskLampColor, TASK_WORK_STATES } from "../utils/format";
import { markSeen } from "../utils/lastSeen";
import { openTaskPeek } from "../stores/statusCenter";

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
// 待签发常驻 pill：waiting_review 任务数（文案刻意避开"尚未召集"/"待人工放行"既有词，不占用锚点断言位）。
const waitingReviewCount = computed(() => memberTasks.value.filter((t) => t.status === "waiting_review").length);

// 锚点卡：色点工作态脉动 + 单一直达动作词，口径统一取自 utils/format 的 TASK_WORK_STATES/taskLampColor。
function isWorkState(status) {
  return TASK_WORK_STATES.has(status);
}
function chipActionLabel(status) {
  if (TASK_WORK_STATES.has(status)) return "查看进度 →";
  if (status === "completed") return "查看产物 →";
  if (status === "failed") return "查看失败详情 →";
  return "";
}

// 轻量轮询（B2）：silent=true 时不切 loading 态、失败不覆盖已展示数据/错误横幅
// （瞬时抖动不该把一个好端端的页面闪成空态或错误态，下一 tick 自愈）；沿用
// TaskDetail.vue 同款「轮询整包作废」守卫——baseline 身份比对，轮询在途期间
// 若发生过手动刷新/结束协作等整包重载，本次轮询结果整包作废，绝不用 stale
// 快照倒灌覆盖更新的状态。opts 用 ?. 兼容 @click="load" 时 Vue 透传的原生
// 事件对象（MouseEvent 没有 .silent，安全落到默认 false）。
async function load(opts) {
  const silent = opts?.silent === true;
  if (!silent) loading.value = true;
  const baseline = silent ? memberTasks.value : null;
  try {
    const [conv, tasks] = await Promise.all([
      getConversation(sessionId),
      listConversationTasks(sessionId),
    ]);
    if (silent && memberTasks.value !== baseline) return;
    conversation.value = conv;
    memberTasks.value = tasks;
    loadError.value = "";
    refreshLastWords(); // fire-and-forget：≤5 个补充请求，不阻塞主数据 loading 态
  } catch (err) {
    if (silent && memberTasks.value !== baseline) return;
    if (!silent) loadError.value = err.detail || err.message || "加载协作会话失败";
  } finally {
    if (!silent) loading.value = false;
  }
}

// 成员任务「最近动态」（Codex 子智能体面板同款定位，B2）：taskId → 该任务最后
// 一条事件的 message 原文（截 60 字）——是"最新一条留痕"而非承诺第一人称叙事。
// 无事件/message 为空则不记 key（对应行不渲染——绝不编造展示内容）。
const taskLastWord = ref({});
// taskId → 请求序号（非响应式）：手动刷新可与在途轮询重叠，只让「最新一次发起」
// 的结果落盘，迟到的旧响应作废，避免动态被 stale 快照倒灌回退。
const lastWordSeq = {};

async function fetchLastWord(taskId) {
  const seq = (lastWordSeq[taskId] = (lastWordSeq[taskId] || 0) + 1);
  try {
    const events = await listTaskEvents(taskId, { offset: 0 });
    if (seq !== lastWordSeq[taskId]) return;
    const msg = events.length ? events[events.length - 1].message || "" : "";
    if (msg) {
      taskLastWord.value[taskId] = msg.length > 60 ? `${msg.slice(0, 60)}…` : msg;
    } else {
      delete taskLastWord.value[taskId];
    }
  } catch {
    // 拉取失败：诚实降级为不显示该行，不阻断其它成员或主数据（非关键展示）
  }
}

// 上限 5 个已召集成员（按 roster 顺序截断，一并控住请求数——常态 1 任务/成员，
// ≤5 个请求）。
function lastWordTargets() {
  const members = rosterAgents.value.filter((a) => tasksFor(a).length > 0).slice(0, 5);
  const out = [];
  for (const a of members) {
    for (const t of tasksFor(a)) out.push(t);
  }
  return out;
}

// 每 tick 无条件重取（不做「状态未变跳过」节流）：长任务在同一状态下事件持续
// 追加，按状态节流会让「最近动态」冻结在该状态的第一条——诚实优先于省请求；
// 代价可控（≤5 个请求/5s，task_events 有 task_id 索引，内网可承受）。
async function refreshLastWords() {
  await Promise.all(lastWordTargets().map((t) => fetchLastWord(t.id)));
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

// 轻量轮询（B2）：链式 setTimeout（TaskDetail 同款纪律）——下一个 tick 只在
// 上一次 load 完全落地后才排队，慢网/慢后端下绝不会堆积并发请求（setInterval
// 会）。document.hidden 时本 tick 跳过但仍续轮；手动「刷新」按钮保留不动
// （仍直调非 silent 的 load()）。
let pollTimer = null;
function schedulePoll() {
  clearPoll();
  pollTimer = setTimeout(async () => {
    try {
      if (!document.hidden) await load({ silent: true });
    } finally {
      schedulePoll();
    }
  }, 5000);
}
function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}
onMounted(() => {
  markSeen(sessionId); // 进入会话即视为「已看过」，驱动首页未读徽章
  load();
  schedulePoll();
});
onUnmounted(clearPoll);
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
  box-shadow: var(--shadow-hero);
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
.sess-goal-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--clay);
  margin-bottom: 4px;
}
.sess-goal {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 10px;
  color: var(--ink);
  line-height: 1.38;
  letter-spacing: 0.2px;
  max-width: 640px;
}
.sess-goal.muted {
  font-family: var(--sans, inherit);
  font-size: 15px;
  font-weight: 400;
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
.sess-progress .pill-amber {
  margin-top: 10px;
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
  color: var(--ink-mid);
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
  display: flex;
  align-items: stretch;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  background: var(--card-bg);
  box-shadow: var(--shadow-card);
  transition: box-shadow var(--ease-lift), transform var(--ease-lift);
}
.member:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.member-bar {
  flex: 0 0 4px;
  width: 4px;
  align-self: stretch;
}
.member-inner {
  flex: 1;
  padding: 14px 16px;
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
/* chip-group（B2）：chip + 其下第一人称一行汇报的纵向包裹，task-chips 仍按
   flex-wrap 逐组排布，task-chip 自身样式不变。 */
.chip-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 100%;
}
.chip-lastword {
  font-size: 11px;
  color: var(--ink-faint);
  padding-left: 4px;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  /* P4 微抬：hover 加一丝纸张离桌感，只用 transform/opacity，token 与全站动效系统对齐。 */
  transition: border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
}
.task-chip:hover {
  border-color: var(--clay-softer);
  transform: translateY(-1px);
}
.task-chip.review {
  border-color: var(--trust-pending);
  background: var(--review-chip-bg);
}
.chip-lamp {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.chip-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
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
  margin-left: auto;
}
.chip-action {
  font-size: 12px;
  font-weight: 700;
  color: var(--clay);
  margin-left: auto;
}
/* B2：chip 内速览微动作——不占用 chip-review/chip-action 的 margin-left:auto
   靠右位；两者都不存在时（如 completed/failed 且已有专属动作词）也保持贴右。 */
.chip-peek-btn {
  flex: none;
  margin-left: 4px;
  padding: 1px 6px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.chip-peek-btn:hover {
  border-color: var(--clay-softer);
  color: var(--clay);
}
@media (prefers-reduced-motion: reduce) {
  .chip-lamp.is-pulsing { animation: none; }
  .task-chip:hover { transform: none; }
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
