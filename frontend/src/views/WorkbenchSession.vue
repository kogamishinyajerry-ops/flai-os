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
        <el-button text @click="pokeConversation(sessionId)">刷新</el-button>
      </div>
    </div>

    <!-- 三态降级：加载中 / 出错 / 就绪。批A Task 6：loading 现由 channel 的
         loaded 派生（首次拉取失败时 loaded 恒为 false，见 liveFeed.js
         refresh()）——补 !loadError 条件，否则失败态会被挡在「加载中」分支
         里出不来，错误横幅永远不可见。 -->
    <!-- 首载骨架（A3）：只在「从未 loaded 且无 conversation 且无错误」时撑
         hero+roster 轮廓，轮询期间/带旧值刷新绝不回骨架；失败态走下面
         el-alert，骨架不吞错误。 -->
    <div v-if="loading && !conversation && !loadError" class="wb-skel">
      <SkeletonBlock height="28px" width="220px" />
      <SkeletonBlock height="60px" width="90%" />
      <SkeletonBlock height="72px" width="100%" />
      <SkeletonBlock height="72px" width="100%" />
      <SkeletonBlock height="72px" width="100%" />
    </div>

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
          <div class="prog-sub"><span class="num-token">{{ completedCount }}</span> 个任务已完成 · 共 <span class="num-token">{{ memberTasks.length }}</span> 个任务</div>
          <span v-if="waitingReviewCount > 0" class="pill-amber">待你签发 <span class="num-token">{{ waitingReviewCount }}</span></span>
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
                <span v-if="tasksFor(a).length" class="member-state summoned">已召集 · <span class="num-token">{{ tasksFor(a).length }}</span> 个任务</span>
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
                    <span class="chip-name">{{ taskDisplayName(t, agentNames.map) }}</span>
                    <!-- chip 时钟（3-lens 可用性镜头 P2）：同 Agent 分组内多个缺名
                         任务主名必然相同，时钟是 chip 级唯一消歧锚。 -->
                    <span class="chip-time">{{ sessClock(t.created_at) }}</span>
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
            <span class="chip-name">{{ taskDisplayName(t, agentNames.map) }}</span>
            <span class="chip-time">{{ sessClock(t.created_at) }}</span>
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
// 批A Task 6：会话数据并轨 liveFeed 'conversation:<id>' channel（frontend/src/
// stores/liveFeed.js）。本页 route.path 含 :sessionId，App.vue 的 router-view
// :key 令 sessionId 变化时整页重挂载（同 TaskDetail 惯例），故这里可以在 setup
// 顶层直接 acquireChannel 并解构 state，无需像 GuidePage 那样按目标 watch
// acquire/release（GuidePage 组件实例跨会话复用）。旧的自建 5s 轮询链
// （schedulePoll/load(silent)/baseline 守卫）整体删除，防 stale 语义由
// channel 的 epoch guard 统一承接。
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { concludeConversation } from "../api/conversations";
import { categoryColor, categoryLabel, statusLabel, taskLampColor, taskDisplayName, formatClockCompact, TASK_WORK_STATES } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import { useTodayKey } from "../composables/useTodayKey";
import { markSeen } from "../utils/lastSeen";
import { openTaskPeek } from "../stores/statusCenter";
import { acquireChannel, pokeConversation } from "../stores/liveFeed";
import SkeletonBlock from "../components/SkeletonBlock.vue";

const route = useRoute();
const router = useRouter();
const sessionId = route.params.sessionId;

// Agent 人话名册（批次四 Q1）：任务 chip 缺名时回退注册表显示名（roster 内外
// 两处 chip 同一 SSOT，不再各自 fallback 裸 id / 裸 agent_id）。
const agentNames = useAgentNames();

// chip 级紧凑时钟（消歧锚）：useTodayKey 响应式日界 SSOT。
const todayKey = useTodayKey();
const sessClock = (iso) => formatClockCompact(iso, todayKey.value);

const convHandle = acquireChannel(`conversation:${sessionId}`);
const { conversation, memberTasks, loaded: convLoaded, error: loadError } = convHandle.state;
const loading = computed(() => !convLoaded.value);

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

// 成员任务「最近动态」（Codex 子智能体面板同款定位，B2；批A Task 6 改增量
// 订阅）：taskId → 该任务最后一条事件的 message 原文（截 60 字）——是"最新
// 一条留痕"而非承诺第一人称叙事。无事件/message 为空则不记 key（对应行不
// 渲染——绝不编造展示内容）。
const taskLastWord = ref({});

// 上限 5 个已召集成员的任务（按 roster 顺序截断，控住常驻订阅数——常态
// 1 任务/成员，≤5 条 task channel），超出部分不订阅、不显示动态行（静态
// 占位=零渲染，不伪造陈旧数据）。
function lastWordTargets() {
  const members = rosterAgents.value.filter((a) => tasksFor(a).length > 0).slice(0, 5);
  const out = [];
  for (const a of members) {
    for (const t of tasksFor(a)) out.push(t);
  }
  return out.slice(0, 5);
}
// 只在目标 taskId 集合真变化时重新订阅（join 用字符串比较,避免每次轮询
// tick 因数组引用变化而空转 diff）。
const lastWordTargetKey = computed(() => lastWordTargets().map((t) => t.id).join(","));

// taskId → { handle, stop }：每个非终态/终态成员任务统一走 acquireChannel
// ('task:'+id)——与页面其它位置（TaskDetail/StatusCenter）共用同一条 channel
// 池,同 taskId 同屏零重复轮询。终态任务的 channel 由 liveFeedCore.nextInterval
// 自动停轮（返回 null），常驻 acquire 对它们是零持续成本，取实现最简单的
// 「常驻订阅」分支（brief 允许二选一），不再额外区分"一次性拉取即 release"。
const lastWordHandles = new Map();

function applyLastWordEvents(taskId, events) {
  const msg = events && events.length ? events[events.length - 1].message || "" : "";
  if (msg) {
    taskLastWord.value = { ...taskLastWord.value, [taskId]: msg.length > 60 ? `${msg.slice(0, 60)}…` : msg };
  } else if (taskLastWord.value[taskId] !== undefined) {
    const next = { ...taskLastWord.value };
    delete next[taskId];
    taskLastWord.value = next;
  }
}

function syncLastWordSubs() {
  const targets = lastWordTargets();
  const targetIds = new Set(targets.map((t) => t.id));
  for (const [taskId, entry] of lastWordHandles) {
    if (targetIds.has(taskId)) continue;
    entry.stop();
    entry.handle.release();
    lastWordHandles.delete(taskId);
    if (taskLastWord.value[taskId] !== undefined) {
      const next = { ...taskLastWord.value };
      delete next[taskId];
      taskLastWord.value = next;
    }
  }
  for (const t of targets) {
    if (lastWordHandles.has(t.id)) continue;
    const handle = acquireChannel(`task:${t.id}`);
    const stop = watch(handle.state.events, (evs) => applyLastWordEvents(t.id, evs), { immediate: true });
    lastWordHandles.set(t.id, { handle, stop });
  }
}
watch(lastWordTargetKey, syncLastWordSubs, { immediate: true });

function releaseLastWordSubs() {
  for (const [, entry] of lastWordHandles) {
    entry.stop();
    entry.handle.release();
  }
  lastWordHandles.clear();
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
    pokeConversation(sessionId); // 带外补拉：不等下一 tick，归档结果立即回显
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

onMounted(() => {
  markSeen(sessionId); // 进入会话即视为「已看过」，驱动首页未读徽章
});
onUnmounted(() => {
  convHandle.release(); // refCount 归零则停链（其它订阅者仍持有时继续养着，都正确）
  releaseLastWordSubs();
});
</script>

<style scoped>
.wb-back {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.wb-skel {
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  /* Task 9 R0 ④owner裁决：这是会话版块类型标签（同 TaskConsole .cl-title 一
     个语义层级），不是页标题——真正的内容标题是下方 22px serif 的 .sess-goal。
     裸 20px 魔数消到既有字号阶：--fs-h3=16px「版块标题」正是这一层级，绝不
     新增 --fs-h2。可见缩小 20px→16px，见 task-9-report.md 显著标注。 */
  font-size: var(--fs-h3);
}
.sess-goal-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  /* clay 预算（批次五 C3）：eyebrow 降灰，本屏 clay 焦点=进度大数字。 */
  color: var(--ink-faint);
  margin-bottom: 4px;
}
.sess-goal {
  font-family: var(--serif);
  /* 展示标题阶归位（W5）：22px 游离值并入 --fs-display，与方案卡目标句同阶 */
  font-size: var(--fs-display);
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
  font-variant-numeric: tabular-nums; /* N11：计数跳动不横移 */
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
/* clay 预算（批次五 C3）：蓝图分工徽章逐行重复，降灰——工作台的 clay 只留
   给 chip 工作灯与进度大数字（单一焦点）。 */
.bp-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  background: var(--hover-tint);
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
  transition: box-shadow var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
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
  /* clay 预算（批次五 C3）：「已召集」是信息态非强调——工作态由 chip 灯承担。 */
  color: var(--ink-mid);
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
  /* 人话称呼后名字可达注册表全名长度（批次四 Q1）：chip 内单行截断防撑爆。 */
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* chip 时钟（消歧锚）：安静弱字，不与状态词抢权重。 */
.chip-time {
  font-size: 11px;
  color: var(--ink-faint);
  flex: none;
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
  /* clay 预算（批次五 C3）：逐 chip 动作字常驻降灰，hover 回 clay。 */
  color: var(--ink-soft);
  margin-left: auto;
}
.task-chip:hover .chip-action {
  color: var(--clay);
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
@media (max-width: 640px) {
  .sess-hero { flex-direction: column; align-items: flex-start; gap: 10px; }
}
</style>
