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
          <!-- 批七 §1.5：hero 进度句换 squad.js 分组计数句（O7 收束假绿禁令同源）。 -->
          <div v-if="heroSquadLine" class="prog-sub">{{ heroSquadLine }}</div>
          <div v-else class="prog-sub">尚无成员任务</div>
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
          <!-- 批七 §1.5：依赖拓扑一句话（depends_on 拓扑序，不画 DAG 图/泳道）。 -->
          <p v-if="relayOrderLine" class="bp-line"><span class="bp-tag">接力顺序</span>{{ relayOrderLine }}</p>
        </div>

        <!-- 批七 §1.5 三组 roster：①正在进行=展开卡占面积 ②等待接力=单行收纳
             （空心灯+灰字）③已完成=折叠单行（过去式+用时+依据缩略+未读环）；
             未召集成员保留既有卡与召集动作（第四段，蓝图召集语义不变）。 -->
        <div v-if="groupedMembers.active.length" class="rg-head">
          <span class="rg-title">正在进行 · <span class="num-token">{{ groupedMembers.active.length }}</span></span>
          <span v-if="anyActiveWork" class="work-pulse-dot"></span>
        </div>
        <div v-if="groupedMembers.active.length" class="roster fx-stagger">
          <div v-for="a in groupedMembers.active" :key="a.agent_id" class="member">
            <div class="member-bar" :style="{ background: categoryColor(a.category) }"></div>
            <div class="member-inner">
              <div class="member-head">
                <span class="member-name">{{ a.agent_name }}</span>
                <span class="member-pill" :style="{ '--member-cat': categoryColor(a.category), background: categoryColor(a.category) + '18' }">
                  {{ categoryLabel(a.category) }}
                </span>
                <span class="member-state summoned">已召集 · <span class="num-token">{{ tasksFor(a).length }}</span> 个任务</span>
              </div>
              <p v-if="a.role" class="member-role"><strong>分工：</strong>{{ a.role }}</p>

              <!-- 成员任务（到席灯 + 状态 + 详情链接；waiting_review 醒目提示放行）；
                   chip-lastword（B2）：该任务的「最近动态」=最后一条事件的 message 原文
                   （可能是机械上报文案，不承诺第一人称叙事；仅前 5 个已召集成员取，
                   见 lastWordTargets）。批七：等待接力条目状态词换人话、灯空心不脉动。 -->
              <div class="task-chips">
                <div v-for="t in tasksFor(a)" :key="t.id" class="chip-group">
                  <div
                    :class="['task-chip', { review: t.status === 'waiting_review' }]"
                    role="button"
                    tabindex="0"
                    @click="goTask(t)"
                    @keydown.enter.self.prevent="goTask(t)"
                    @keydown.space.self.prevent="goTask(t)"
                  >
                    <span class="chip-lamp" :class="{ 'is-pulsing': isWorkState(t.status), 'is-hollow': chipStatusWord(t) === '等待接力' }" :style="{ background: chipStatusWord(t) === '等待接力' ? 'transparent' : taskLampColor(t.status) }"></span>
                    <span class="chip-name">{{ taskDisplayName(t, agentNames.map) }}</span>
                    <!-- chip 时钟（3-lens 可用性镜头 P2）：同 Agent 分组内多个缺名
                         任务主名必然相同，时钟是 chip 级唯一消歧锚。 -->
                    <span class="chip-time">{{ sessClock(t.created_at) }}</span>
                    <span class="chip-status" :style="{ color: chipStatusColor(t) }">{{ chipStatusWord(t) }}</span>
                    <span v-if="t.status === 'waiting_review'" class="chip-review">待人工放行 →</span>
                    <span v-else-if="chipActionLabel(t.status)" class="chip-action">{{ chipActionLabel(t.status) }}</span>
                    <!-- B2 速览接入（additive）：chip 本体点击仍走 goTask 跳详情；速览用 @click.stop 独立打开。
                         chip 键盘三件套用 .self：嵌套速览钮上的 Enter/Space 冒泡不得双触发 goTask。 -->
                    <button type="button" class="chip-peek-btn" @click.stop="openTaskPeek(t.id)">速览</button>
                  </div>
                  <div v-if="taskLastWord[t.id]" class="chip-lastword">{{ taskLastWord[t.id] }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="groupedMembers.waiting.length" class="rg-head">
          <span class="rg-title">等待接力 · <span class="num-token">{{ groupedMembers.waiting.length }}</span></span>
        </div>
        <div
          v-for="a in groupedMembers.waiting"
          :key="'w-' + a.agent_id"
          class="rg-line"
        >
          <span class="rg-lamp-hollow"></span>
          <span class="rg-name">{{ a.agent_name }}</span>
          <span class="rg-gray">{{ waitingLineFor(a) }}</span>
          <span class="rg-spacer"></span>
          <button type="button" class="chip-peek-btn" @click.stop="openTaskPeek(focusTaskFor(a).id)">速览</button>
        </div>

        <div v-if="groupedMembers.done.length" class="rg-head">
          <span class="rg-title">已完成 · <span class="num-token">{{ groupedMembers.done.length }}</span></span>
        </div>
        <div
          v-for="a in groupedMembers.done"
          :key="'d-' + a.agent_id"
          class="rg-line rg-done"
          role="button"
          tabindex="0"
          @click="goTask(latestTaskFor(a))"
          @keydown.enter.prevent="goTask(latestTaskFor(a))"
        >
          <span v-if="doneUnseen(a)" class="rg-unread-ring"></span>
          <span class="rg-name" :class="{ 'is-unread': doneUnseen(a) }">{{ a.agent_name }}</span>
          <span class="rg-gray"><template v-for="(seg, si) in doneLineFor(a)" :key="si"><span v-if="seg.fail" class="rg-fail-word">{{ seg.text }}</span><template v-else>{{ seg.text }}</template></template></span>
          <span
            v-if="doneEvidenceText(a)"
            class="rg-evi"
            :class="{ 'has-unverified': doneEvidenceText(a).unverified > 0 }"
          >{{ doneEvidenceText(a).text }}</span>
        </div>

        <div v-if="groupedMembers.unsummoned.length" class="roster fx-stagger">
          <div v-for="a in groupedMembers.unsummoned" :key="a.agent_id" class="member">
            <div class="member-bar" :style="{ background: categoryColor(a.category) }"></div>
            <div class="member-inner">
              <div class="member-head">
                <span class="member-name">{{ a.agent_name }}</span>
                <span class="member-pill" :style="{ '--member-cat': categoryColor(a.category), background: categoryColor(a.category) + '18' }">
                  {{ categoryLabel(a.category) }}
                </span>
                <span class="member-state pending">尚未召集</span>
              </div>
              <p v-if="a.role" class="member-role"><strong>分工：</strong>{{ a.role }}</p>
              <!-- 未进入执行的席位只显示状态，不在成员卡上暴露创建表单或手工
                   Agent 启动。缺失信息统一回原对话，以文字/附件自然补充。 -->
              <div v-if="conversation.status === 'active'" class="member-action">
                <span class="member-hint">等待系统从主对话获得足够信息后自动编排。</span>
              </div>
              <div v-else class="member-action">
                <span class="member-hint">会话已归档，未召集——如需继续，请从智能导引开启新协作。</span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="conversation.status === 'active' && groupedMembers.unsummoned.length"
          class="clarify-return"
        >
          <span>还有协作环节需要更多上下文。请直接描述情况或上传附件，系统会重新编排。</span>
          <el-button type="primary" plain @click="returnToConversation">回到对话补充信息</el-button>
        </div>
      </template>

      <div v-else-if="!plan" class="sess-block">
        <p class="muted">本次会话没有形成结构化协作方案（可能仍在澄清需求，或以纯对话收尾）。</p>
      </div>

      <!-- 方案之外的会话内任务（防漏：归到本会话但不在蓝图 roster 里的任务） -->
      <div v-if="otherTasks.length" class="sess-block">
        <div class="block-label">其它归属本会话的任务</div>
        <div class="task-chips">
          <div v-for="t in otherTasks" :key="t.id" :class="['task-chip', { review: t.status === 'waiting_review' }]" role="button" tabindex="0" @click="goTask(t)" @keydown.enter.self.prevent="goTask(t)" @keydown.space.self.prevent="goTask(t)">
            <span class="chip-lamp" :class="{ 'is-pulsing': isWorkState(t.status), 'is-hollow': chipStatusWord(t) === '等待接力' }" :style="{ background: chipStatusWord(t) === '等待接力' ? 'transparent' : taskLampColor(t.status) }"></span>
            <span class="chip-name">{{ taskDisplayName(t, agentNames.map) }}</span>
            <span class="chip-time">{{ sessClock(t.created_at) }}</span>
            <span class="chip-status" :style="{ color: chipStatusColor(t) }">{{ chipStatusWord(t) }}</span>
            <span v-if="t.status === 'waiting_review'" class="chip-review">待人工放行 →</span>
            <span v-else-if="chipActionLabel(t.status)" class="chip-action">{{ chipActionLabel(t.status) }}</span>
          </div>
        </div>
      </div>

      <p class="sess-foot">
        系统负责自动路由与编排；你负责确认开工、关键工程决策与最终签发。
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
import { categoryColor, categoryLabel, statusLabel, taskLampColor, taskDisplayName, formatClockCompact, TASK_WORK_STATES, taskElapsedMs } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import { useTodayKey } from "../composables/useTodayKey";
import { markSeen, ensureTaskBaseline, taskHasUnseen } from "../utils/lastSeen";
import { memberPhase, squadCounts, squadLineText, relayOrderText } from "../utils/squad";
import { ensureTaskEvidence, taskEvidenceSummary, taskEvidenceWithheld } from "../stores/taskEvidence";
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

// ── 批七 §1.5 三组 roster + hero 分组计数句 ─────────────────────────────────
function latestTaskFor(a) {
  const list = tasksFor(a);
  return list.length ? list[0] : null; // channel 快照 created_at DESC，[0]=最新
}

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

// 成员行的代表任务：优先**最新的未收官任务**（等待组的速览/旁白必须指向真正
// 悬着的那件事），全终态才回退最新任务。
function focusTaskFor(a) {
  const list = tasksFor(a);
  return list.find((t) => !TERMINAL_STATUSES.has(t.status)) || (list.length ? list[0] : null);
}

// 成员按**全部任务**的相分组（Codex R0 P1：会话允许同一 Agent 多任务，只看
// 最新一条会让「新任务已完成、旧依赖任务还悬着」的成员被折进已完成，把在办
// 工作藏起来）：①正在进行=任一任务未收官且非纯等待（含排队/待签发——人还有
// 事要跟）②等待接力=未收官的全是 waiting_upstream 派生态 ③已完成=**全部**
// 任务真终态（含失败/取消如实过去式）④未召集（既有卡与召集动作原样保留）。
const groupedMembers = computed(() => {
  const active = [];
  const waiting = [];
  const done = [];
  const unsummoned = [];
  for (const a of rosterAgents.value) {
    const list = tasksFor(a);
    if (!list.length) {
      unsummoned.push(a);
      continue;
    }
    const open = list.filter((t) => !TERMINAL_STATUSES.has(t.status));
    if (open.length === 0) done.push(a);
    else if (open.every((t) => memberPhase(t) === "waiting_upstream")) waiting.push(a);
    else active.push(a);
  }
  return { active, waiting, done, unsummoned };
});
const anyActiveWork = computed(() =>
  groupedMembers.value.active.some((a) => tasksFor(a).some((t) => TASK_WORK_STATES.has(t.status)))
);

// hero 分组计数句（squad.js 同一口径；O7 收束假绿禁令由 squadLineText 承接）。
const heroSquadLine = computed(() => {
  if (memberTasks.value.length === 0) return "";
  return squadLineText(squadCounts(memberTasks.value), memberTasks.value, Date.now());
});

// 蓝图依赖拓扑一句话（不画图）：任一任务声明 depends_on 才渲。名字优先注册表
// 人话名，回退任务显示名。
const relayOrderLine = computed(() =>
  relayOrderText(memberTasks.value, (t) => agentNames.map[t.agent_id] || taskDisplayName(t, agentNames.map))
);

function durTextOf(t) {
  const ms = taskElapsedMs(t, Date.now());
  if (ms === null) return "";
  const sec = Math.max(0, Math.round(ms / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, "0")}s`;
}

// 等待接力单行灰字：上游名解析；上游真失败 → 中性暂停句（非红）。
// 代表任务=focusTaskFor（悬着的那条，而非可能已收官的最新条）。
function waitingLineFor(a) {
  const t = focusTaskFor(a);
  if (!t) return "";
  const byId = new Map(memberTasks.value.map((x) => [x.id, x]));
  const ups = (t.depends_on || []).map((d) => byId.get(d)).filter(Boolean);
  if (ups.some((u) => u.status === "failed" || u.status === "cancelled")) {
    return "前序失败，接力已暂停 · 详情→";
  }
  const names = ups.map((u) => agentNames.map[u.agent_id] || u.agent_id.slice(0, 12));
  return `等待〈${names.length ? names.join("、") : "上游成员"}〉的产物 · 就绪后自动接力`;
}

// 已完成折叠单行：过去式+用时（时态即状态；失败玫红词只给真失败）。
// W16 分段返回：真失败只染「失败」状态词 token（模板 .rg-fail-word），
// 其余段与完成/取消一样保持中性，绝不整行染色。
function doneLineFor(a) {
  const t = latestTaskFor(a);
  if (!t) return [];
  const extra = tasksFor(a).length - 1;
  const suffix = extra > 0 ? ` · +${extra} 更早任务` : "";
  if (t.status === "completed") {
    const d = durTextOf(t);
    return [{ text: (d ? `已完成 · 用时 ${d}` : "已完成") + suffix }];
  }
  if (t.status === "failed") return [{ text: "失败", fail: true }, { text: ` · 查看失败详情 →${suffix}` }];
  return [{ text: `已取消${suffix}` }];
}

function doneUnseen(a) {
  const t = latestTaskFor(a);
  return t !== null && taskHasUnseen(t) === true; // 完成未读 → 空心环（TaskConsole 同语法）
}

function doneEvidenceText(a) {
  const t = latestTaskFor(a);
  if (!t) return null;
  // 批八 withheld（O6）：密级受限产物零下载零计数——遮蔽文案绝不编 N。可读
  // internal 依据与受限件共存时两者都不隐瞒（Codex R2 P2：此前遮蔽即短路，
  // 收纳行吞掉了用户有权查看的可读计数，与 Guide/TaskDetail 口径不一致）。
  const withheld = taskEvidenceWithheld(t.id) === true;
  const s = taskEvidenceSummary(t.id);
  if (withheld && !s) return { text: "依据〔按密级隐藏〕", unverified: 0 };
  if (!s) return null;
  if (s.invalid) {
    return {
      text: withheld ? "依据结构待核·另有密级隐藏项" : "依据结构待核",
      unverified: 1,
    };
  }
  const base = `依据 ${s.total} 条${s.unverified > 0 ? `（${s.unverified} 未核）` : ""}`;
  return { text: withheld ? `${base}·另有密级隐藏项` : base, unverified: s.unverified };
}

// task-chips 状态词映射（§1.5）：等待接力条目——该态 chip-lamp 不脉动（created
// 本就非工作态）且状态词换人话。
function chipStatusWord(t) {
  return memberPhase(t) === "waiting_upstream" ? "等待接力" : statusLabel(t.status);
}

function chipStatusColor(t) {
  return memberPhase(t) === "waiting_upstream" ? "var(--ink-soft)" : taskLampColor(t.status);
}

// 依据摘要拉取：终审面（completed/waiting_review）任务到位即拉（模块级缓存，
// 与 GuidePage 共用同一份）。
watch(
  memberTasks,
  (tasks) => {
    for (const t of tasks || []) ensureTaskEvidence(t);
  },
  { immediate: true }
);

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
    ElMessage.info("协作已归档");
    pokeConversation(sessionId); // 带外补拉：不等下一 tick，归档结果立即回显
  } catch (err) {
    ElMessage.error(err.detail || err.message || "结束协作失败");
  }
}

function returnToConversation() {
  router.push({ path: "/", query: { c: sessionId } });
}

onMounted(() => {
  markSeen(sessionId); // 进入会话即视为「已看过」，驱动首页未读徽章
  ensureTaskBaseline(); // 批七 §1.5：已完成行未读空心环的基线（TaskConsole 同语法）
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
/* dock 带避让（Codex R0 修复期暴露的既有遮挡 + R1 复审 P2 收口）：StatusDock
   fixed 右上（top:16/z:150），「结束协作/刷新」正被 pill 压住（m8 ⑥ 实测点击
   被拦+截图铁证）。横向预留兜不住合法极端（待签+运行中+监控+core 全家桶
   ~360px），改竖向让位与 pill 数量彻底解耦：dock 带底 ≈ top16+pill高~32≈48px，
   main padding-top 28px + 本 28px → 头栏行顶 56px > 48px，任意 pill 组合不遮。 */
@media (min-width: 861px) {
  .wb-back { margin-top: 28px; }
}
/* 窄屏清零（Codex R2 审 P3，verbatim）：≤860px 时 App 主区已有 60px 顶距
   且 dock pill 隐藏，无遮挡可让——无条件 28px 是纯多余下沉。 */
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
  /* 窄屏防横向溢出：长发起人名 + 16 位会话 id 允许换行（桌面内容放得下时
     flex-wrap 不改变排版，视觉不变）。 */
  flex-wrap: wrap;
  gap: 6px;
}
.sess-meta > span {
  /* 弹性子项可缩到内容以下；无断点的 hex id 片段允许任意处折行。 */
  min-width: 0;
  overflow-wrap: anywhere;
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
/* ── 批七 §1.5 三组 roster ─────────────────────────────────────────────── */
.rg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 14px 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-soft);
  letter-spacing: 0.02em;
}
.rg-line {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 12px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  margin-bottom: 6px;
  font-size: 12.5px;
  background: var(--card-bg);
}
.rg-line.rg-done { cursor: pointer; }
.rg-line.rg-done:hover { border-color: var(--hairline); }
/* 空心灯（等待接力）：1px ink 描边圆，绝无脉动 */
.rg-lamp-hollow {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--ink-soft);
}
/* 完成未读空心环（TaskConsole 未读语法复用） */
.rg-unread-ring {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid var(--ink);
  background: transparent;
}
.rg-name { font-weight: 600; color: var(--ink); white-space: nowrap; }
.rg-name.is-unread { font-weight: 700; }
.rg-gray { color: var(--ink-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* W16：真失败只染状态词 token（红仅真实失败），行内其余文字保持中性。 */
.rg-fail-word { color: var(--trust-fail); }
.rg-spacer { flex: 1 1 auto; }
.rg-evi {
  flex: none;
  font-size: 11.5px;
  color: var(--ink-soft);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  padding: 2px 7px;
  font-variant-numeric: tabular-nums;
}
.rg-evi.has-unverified {
  color: var(--trust-pending);
  border-color: color-mix(in srgb, var(--trust-pending) 45%, transparent);
}
/* chip 空心灯（等待接力条目）：不脉动由模板保证（created 非工作态） */
.chip-lamp.is-hollow { box-shadow: inset 0 0 0 1px var(--ink-soft); }
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
  /* 分类色经 --member-cat 传入（亮主题直吃分类色，与改前逐位一致）。 */
  color: var(--member-cat);
}
/* 暗主题仅提亮文字：四分类色直接吃在暗底上对比 2.7–3.1:1 不达 AA，
 * 向白混 45% 保持色相、对比拉过 4.5；分类轴身份语义与背景 tint 机制不动。 */
:root[data-theme="dark"] .member-pill {
  color: color-mix(in srgb, var(--member-cat) 45%, #fff);
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
.clarify-return {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin: 4px 0 16px;
  padding: 12px 14px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 12.5px;
  line-height: 1.6;
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
  .clarify-return { align-items: stretch; flex-direction: column; }
}
</style>
