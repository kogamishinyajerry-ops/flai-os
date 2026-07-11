<template>
  <div class="workbench-home">
    <div class="wb-hero">
      <!-- 动效 P1：hero ambient 粒子场（石墨尘，boost 绑真实 work-state 任务数）——
           纯装饰层，绝对定位铺满、置于文案之下，pointer-events:none + aria-hidden。 -->
      <canvas ref="heroCanvasEl" class="wb-hero-particles" aria-hidden="true"></canvas>
      <div class="wb-hero-text fx-stagger">
        <h2>协作工作台</h2>
        <p class="wb-sub">
          把一个繁琐任务交给<strong>智能导引</strong>——它帮你分析、拆解，找到合适的
          Agent 组成协作，或者说清为什么这套系统还不该接这个任务。确认后，被召集的
          Agent 会在这里协同工作，进度、分工与产物一目了然。
        </p>
        <div class="wb-cta">
          <el-button type="primary" @click="$router.push('/')">从导引开始一个协作</el-button>
          <el-button text @click="$router.push('/portal')">浏览已上线的 Agent →</el-button>
        </div>
      </div>
      <!-- 动效 A1：hero 右缘制图场景插画，窄视口隐藏，绝不遮挡文案。 -->
      <div class="wb-hero-art">
        <DraftingScene />
      </div>
    </div>

    <!-- 待我签发（P1-5）：waiting_review 任务前置，工程师一进来先看「要我处理的」。 -->
    <div v-if="reviewTasks.length" class="wb-section wb-review">
      <div class="wb-section-head">
        <h3>待你签发 <span class="wb-review-badge">{{ reviewTasks.length }}</span></h3>
      </div>
      <p class="wb-note">这些任务已产出草案，等你审阅后放行或拒绝——签发权在你。</p>
      <div class="wb-list">
        <div v-for="t in reviewTasks" :key="t.id" class="wb-row wb-row--review" @click="goDetail(t)">
          <span class="wb-lamp" :class="{ 'is-pulsing': isWorkState(t.status) }" :style="{ background: lampColor(t.status) }" :title="statusLabel(t.status)"></span>
          <span class="wb-name">{{ t.name || t.id.slice(0, 12) }}</span>
          <span class="wb-agent">{{ t.agent_id }}</span>
          <span class="wb-status" :style="{ color: lampColor(t.status) }">{{ statusLabel(t.status) }}</span>
          <span class="wb-by">{{ t.created_by }}</span>
          <span class="wb-time">{{ formatTime(t.created_at) }}</span>
          <span v-if="rowActionLabel(t.status)" class="row-action">{{ rowActionLabel(t.status) }}</span>
          <!-- B2 速览接入（additive）：不参与既有整行点击（goDetail），@click.stop 独立打开任务速览。 -->
          <el-button size="small" text class="wb-peek-btn" @click.stop="openTaskPeek(t.id)">速览</el-button>
        </div>
      </div>
    </div>

    <!-- 协作会话（M8 P4）：导引召集成方案的会话，进入即见分工架构+进度。 -->
    <div class="wb-section">
      <div class="wb-section-head">
        <h3>协作会话</h3>
      </div>
      <p class="wb-note">导引召集了合适 Agent 组成协作的会话——点开看分工架构、召集进度与产物。</p>
      <EmptyState
        v-if="!sessions.length"
        variant="action"
        description="还没有协作会话——从上方「从导引开始一个协作」发起"
        :image-size="76"
      />
      <div v-else class="sess-grid">
        <div v-for="c in sessions" :key="c.id" class="sess-card" @click="goSession(c)">
          <!-- 完成未读徽章（B2）：clay 圆点=刻意用法——语义是"有新进展待你去看"的行动
               召唤，而非真实性(REAL)/签署/失败/待审四个信任色槽，不违反信任色锁。 -->
          <span v-if="sessionHasUnseen(c)" class="sess-unread-dot" title="有新进展"></span>
          <div class="sess-card-bar"></div>
          <div class="sess-card-inner">
            <div class="sess-card-goal">{{ c.recommendation.goal || "协作会话" }}</div>
            <div class="sess-card-meta">
              <span class="sess-card-count">{{ (c.recommendation.agents || []).length }} 个 Agent</span>
              <el-tag :type="c.status === 'active' ? 'primary' : 'info'" effect="plain" size="small">
                {{ c.status === "active" ? "进行中" : "已归档" }}
              </el-tag>
            </div>
            <div class="sess-card-by">{{ c.created_by }} · {{ formatTime(c.created_at) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近任务台账（旧「任务历史」页降级折入此处）。 -->
    <div class="wb-section">
      <div class="wb-section-head">
        <h3>最近任务</h3>
        <div class="wb-filters">
          <el-select v-model="filters.status" placeholder="状态" clearable size="small" style="width: 140px" @change="load">
            <el-option v-for="(cfg, key) in TASK_STATUS" :key="key" :label="cfg.label" :value="key" />
          </el-select>
          <el-button size="small" text @click="load">刷新</el-button>
        </div>
      </div>
      <p class="wb-note">最近的单个任务台账；多 Agent 协作会话见上方「协作会话」。</p>

      <el-alert v-if="loadError" type="error" :title="loadError" show-icon :closable="false" class="wb-alert" />

      <div v-loading="loading" class="wb-list">
        <div v-for="t in tasks" :key="t.id" class="wb-row" @click="goDetail(t)">
          <span class="wb-lamp" :class="{ 'is-pulsing': isWorkState(t.status) }" :style="{ background: lampColor(t.status) }" :title="statusLabel(t.status)"></span>
          <span class="wb-name">{{ t.name || t.id.slice(0, 12) }}</span>
          <span class="wb-agent">{{ t.agent_id }}</span>
          <span class="wb-status" :style="{ color: lampColor(t.status) }">{{ statusLabel(t.status) }}</span>
          <span class="wb-by">{{ t.created_by }}</span>
          <span class="wb-time">{{ formatTime(t.created_at) }}</span>
          <span v-if="rowActionLabel(t.status)" class="row-action">{{ rowActionLabel(t.status) }}</span>
          <!-- B2 速览接入（additive）：不参与既有整行点击（goDetail），@click.stop 独立打开任务速览。 -->
          <el-button size="small" text class="wb-peek-btn" @click.stop="openTaskPeek(t.id)">速览</el-button>
        </div>
        <EmptyState v-if="!loading && tasks.length === 0" description="还没有任务——从导引开始一个协作吧" />
      </div>

      <div v-if="hasMore" class="wb-more">
        <el-button :loading="loadingMore" text @click="loadMore">加载更多</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { listTasks } from "../api/tasks";
import { listConversations } from "../api/conversations";
import EmptyState from "../components/EmptyState.vue";
import DraftingScene from "../components/artwork/DraftingScene.vue";
import { createParticleField } from "../effects/particleField";
import { statusLabel, formatTime, TASK_STATUS, taskLampColor, TASK_WORK_STATES } from "../utils/format";
import { hasUnseen } from "../utils/lastSeen";
import { openTaskPeek } from "../stores/statusCenter";

const router = useRouter();
const tasks = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const loadError = ref("");
const PAGE_SIZE = 100;
const hasMore = ref(false);
const filters = reactive({ status: "" });

// 动效 P1（MOTION-SYSTEM.md）：hero ambient 粒子场句柄 + boost 绑定真实信号
// （work-state 任务数/5 封顶，诚实地板——信号消失即回落到 0，不留残余强度）。
const heroCanvasEl = ref(null);
let heroField = null;
function updateHeroBoost() {
  if (!heroField) return;
  const workCount = tasks.value.filter((t) => TASK_WORK_STATES.has(t.status)).length;
  heroField.setBoost(Math.min(1, workCount / 5));
}

// 协作会话（M8 P4）：已形成召集方案（orchestrate）的导引会话——协作工作台的主对象。
const sessions = ref([]);
// silent=true（轮询 tick）：失败保留上次已知数据，不因瞬时抖动清空已渲染好的卡片；
// 首载/手动场景仍保留原「诚实留空」降级（无错误横幅承载会话区，留空即最诚实的呈现）。
async function loadSessions(silent = false) {
  try {
    const convs = await listConversations({ limit: 100 });
    sessions.value = convs.filter((c) => c.recommendation && c.recommendation.decision === "orchestrate");
  } catch {
    if (!silent) sessions.value = []; // 会话列表失败不阻断任务台账；诚实留空
  }
}
function goSession(c) {
  router.push(`/workbench/${c.id}`);
}

// 待我签发（P1-5）：waiting_review 任务前置，驱动日常回访——工程师一进来就看到「要我处理的」。
const reviewTasks = ref([]);
async function loadReviewTasks(silent = false) {
  try {
    reviewTasks.value = await listTasks({ status: "waiting_review", limit: 20 });
  } catch {
    if (!silent) reviewTasks.value = []; // 失败不阻断台账；诚实留空
  }
}

// 完成未读徽章（B2）：复用「最近任务」列表（tasks.value，随轮询保鲜，带 conversation_id）
// 按会话过滤，不为每张会话卡片单开请求（省内网带宽）。已知边界：只覆盖出现在这批
// 「最近任务」窗口内的成员任务——若某会话的任务因足够久远被更多新任务顶出窗口，未读
// 判定会诚实地不亮（宁可漏判，也不为徽章准确度而放大请求量）。
function sessionTasks(sessionId) {
  return tasks.value.filter((t) => t.conversation_id === sessionId);
}
function sessionHasUnseen(c) {
  return hasUnseen(c.id, sessionTasks(c.id));
}

// 到席灯配色守信任色锁：抽到 utils/format.js 的 taskLampColor 单处（协作会话共用），
// 关键纪律——completed **不给绿**（跑 mock，给绿即假 REAL）。
const lampColor = taskLampColor;

// 锚点卡同款：行内状态点工作态脉动 + 单一直达动作词（口径与 WorkbenchSession 一致，
// 取自 utils/format 的 TASK_WORK_STATES；waiting_review 行走「去签发」而非 chip 的「待人工放行」）。
function isWorkState(status) {
  return TASK_WORK_STATES.has(status);
}
function rowActionLabel(status) {
  if (TASK_WORK_STATES.has(status)) return "查看进度 →";
  if (status === "completed") return "查看产物 →";
  if (status === "failed") return "查看失败详情 →";
  if (status === "waiting_review") return "去签发 →";
  return "";
}

function _query(offset) {
  return { status: filters.status || undefined, limit: PAGE_SIZE, offset };
}

// 轻量轮询（B2）：opts?.silent 时不切 loading 态、失败不覆盖已展示数据/错误横幅
// （瞬时抖动不该把好端端的列表闪成空态，下一 tick 自愈）；沿用 TaskDetail.vue
// 同款「轮询整包作废」守卫——baseline 身份比对，轮询在途期间若发生过手动刷新/
// 「加载更多」等整包重载，本次轮询结果整包作废。opts?. 兼容 @click="load"/
// @change="load" 时 Vue 透传的原生事件对象或选中值（都没有 .silent，安全落到
// 默认 false）。
async function load(opts) {
  const silent = opts?.silent === true;
  if (!silent) loading.value = true;
  const baseline = silent ? tasks.value : null;
  try {
    const page = await listTasks(_query(0));
    if (silent && tasks.value !== baseline) return;
    tasks.value = page;
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
    updateHeroBoost(); // 每次任务数据刷新后同步——工作数为 0 时诚实回落到 0
  } catch (err) {
    if (silent && tasks.value !== baseline) return;
    if (!silent) loadError.value = err.detail || err.message;
  } finally {
    if (!silent) loading.value = false;
  }
}

async function loadMore() {
  loadingMore.value = true;
  try {
    const page = await listTasks(_query(tasks.value.length));
    tasks.value = tasks.value.concat(page);
    hasMore.value = page.length === PAGE_SIZE;
    loadError.value = "";
    updateHeroBoost();
  } catch (err) {
    loadError.value = err.detail || err.message;
  } finally {
    loadingMore.value = false;
  }
}

function goDetail(t) {
  router.push(`/tasks/${t.id}`);
}

// 轻量轮询（B2）：5s 一次同刷「最近任务/协作会话/待你签发」三处既有数据源。
// 链式 setTimeout（TaskDetail 同款纪律）——下一个 tick 只在上一轮三个请求全部
// 落地后才排队，慢网/慢后端下绝不会堆积并发请求（setInterval 会）；三个 load
// 各自内部兜错，Promise.all 不会 reject。document.hidden 时本 tick 跳过但仍
// 续轮；手动「刷新」按钮保留不动。
let pollTimer = null;
function schedulePoll() {
  clearPoll();
  pollTimer = setTimeout(async () => {
    try {
      if (!document.hidden) {
        await Promise.all([load({ silent: true }), loadSessions(true), loadReviewTasks(true)]);
      }
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
  // 动效 P1：先建粒子场句柄再触发数据加载——load() 完成后 updateHeroBoost()
  // 才有 heroField 可写；reduced-motion 下 createParticleField 返回零副作用桩。
  heroField = createParticleField(heroCanvasEl.value);
  load();
  loadSessions();
  loadReviewTasks();
  schedulePoll();
});
onUnmounted(() => {
  clearPoll();
  heroField?.destroy();
});
</script>

<style scoped>
.wb-hero {
  position: relative; /* 动效 P1：承载绝对定位粒子场 canvas + 右缘插画的定位上下文 */
  overflow: hidden; /* 粒子/插画绝不溢出 hero 卡片边界 */
  background: linear-gradient(135deg, var(--paper-cream), var(--paper-surface));
  border: 1px solid var(--hairline);
  border-radius: 14px;
  padding: 28px 30px;
  margin-bottom: 24px;
  box-shadow: var(--shadow-hero);
}
/* 动效 P1：ambient 粒子场——铺满 hero、置于文案之下，纯装饰不吃交互。 */
.wb-hero-particles {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.wb-hero-text {
  position: relative; /* 高于粒子场 */
  z-index: 1;
}
.wb-hero h2 {
  font-family: var(--serif);
  margin: 0 0 10px;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: 0.2px;
}
.wb-sub {
  margin: 0 0 18px;
  max-width: 720px;
  line-height: 1.7;
  color: var(--ink-soft);
}
.wb-cta {
  display: flex;
  gap: 12px;
  align-items: center;
}
/* 动效 A1：hero 右缘制图场景插画——窄视口隐藏，绝不遮挡文案（文案侧同步让出空间）。 */
.wb-hero-art {
  position: absolute;
  right: 26px;
  top: 50%;
  transform: translateY(-50%);
  width: 260px;
  z-index: 1;
  pointer-events: none;
  opacity: 0.9;
}
@media (max-width: 1099px) {
  .wb-hero-art {
    display: none;
  }
}
@media (min-width: 1100px) {
  .wb-hero-text {
    padding-right: 280px;
  }
}
.sess-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.sess-card {
  position: relative; /* B2：承载右上角未读圆点的定位上下文 */
  border: 1px solid var(--hairline);
  border-radius: 12px;
  overflow: hidden;
  background: var(--card-bg);
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: border-color var(--ease-lift), box-shadow var(--ease-lift), transform var(--ease-lift);
}
.sess-unread-dot {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--clay);
  box-shadow: 0 0 0 2px var(--card-bg);
  z-index: 1;
}
.sess-card:hover {
  border-color: var(--clay-softer);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-3px);
}
.sess-card-bar {
  height: 4px;
  background: var(--clay);
}
.sess-card-inner {
  padding: 14px 16px;
}
.sess-card-goal {
  font-weight: 700;
  color: var(--ink);
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sess-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sess-card-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
}
.sess-card-by {
  font-size: 12px;
  color: var(--ink-faint);
}
.wb-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.wb-section-head h3 {
  margin: 0;
}
.wb-filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.wb-note {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--ink-faint);
}
.wb-alert {
  margin-bottom: 12px;
}
/* 待我签发：amber（待人签）左描边 + 徽章，凸显「要我处理的」，但不抢主色。 */
.wb-review-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  margin-left: 6px;
  border-radius: 999px;
  background: var(--trust-pending);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  vertical-align: middle;
}
.wb-row--review {
  border-left: 3px solid var(--trust-pending);
}
.wb-row {
  display: grid;
  /* B2：末尾追加 76px 专列承载「速览」按钮，grid-column:8 显式定位——row-action
     的 v-if 存在与否不影响速览列位置（不依赖 DOM 序自动分配轨道）。 */
  grid-template-columns: 16px 1fr 160px 96px 96px 160px 112px 76px;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  margin-bottom: 8px;
  background: var(--card-bg);
  cursor: pointer;
  transition: border-color var(--ease-lift), box-shadow var(--ease-lift), transform var(--ease-lift);
}
.wb-row:hover {
  border-color: var(--clay-softer);
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.wb-lamp {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.wb-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  .wb-lamp.is-pulsing { animation: none; }
}
.row-action {
  font-size: 12px;
  font-weight: 700;
  color: var(--clay);
  text-align: right;
  white-space: nowrap;
}
/* B2：速览次级动作——固定占第 8 轨道、右对齐，与 row-action 是否渲染无关。 */
.wb-peek-btn {
  grid-column: 8;
  justify-self: end;
  padding: 0 6px !important;
  font-size: 12px;
  white-space: nowrap;
}
.wb-name {
  font-weight: 600;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-agent {
  color: var(--ink-soft);
  font-size: 13px;
}
.wb-status {
  font-size: 13px;
  font-weight: 600;
}
.wb-by,
.wb-time {
  color: var(--ink-faint);
  font-size: 12px;
}
.wb-more {
  display: flex;
  justify-content: center;
  margin-top: 8px;
}
@media (max-width: 720px) {
  .wb-row {
    grid-template-columns: 16px 1fr auto;
  }
  .wb-agent,
  .wb-by,
  .wb-time,
  .row-action,
  .wb-peek-btn {
    display: none;
  }
}
</style>
