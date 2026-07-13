<template>
  <!-- 今日工作台（批B §一）：开工即看——待签发置顶、进行中一眼可见，
       版块 3/4/5（今日交付/Agent 动态/团队总量）占位待批B后续任务接入。
       全部数据来自 liveFeed 'tasks' channel（与 StatusCenter/StatusDock 同一份真值，
       全站只此一条该 channel 轮询）。 -->
  <div class="today">
    <div class="today-head">
      <span class="today-title">今日</span>
    </div>

    <div v-if="feedError" class="today-error">{{ feedError }}</div>

    <!-- 首载骨架：只在「从未 loaded 且无错误」时撑轮廓，轮询期间/带旧值刷新绝不回骨架。 -->
    <div v-if="!feedLoaded && !feedError" class="today-skel">
      <SkeletonBlock v-for="(w, i) in ['70%', '92%', '84%', '76%', '88%', '64%']" :key="i" height="52px" :width="w" />
    </div>

    <template v-else>
      <!-- 版块 1：待你签发（amber 置顶，行动召唤最高优先） -->
      <section class="today-section">
        <div class="today-section-head waiting">✍ 待你签发 · {{ waitingTasks.length }}</div>
        <div v-if="waitingTasks.length" class="today-list">
          <div
            v-for="t in waitingTasks"
            :key="t.id"
            class="today-card"
            role="button"
            tabindex="0"
            @click="openTask(t.id)"
            @keydown.enter.prevent="openTask(t.id)"
            @keydown.space.prevent="openTask(t.id)"
          >
            <!-- lamp 走 taskLampColor SSOT（B-T3 审 P3）；耗时文案「运行」而非
                 「等待」——taskElapsedMs 起点是 started_at，是任务总耗时不是
                 进入待签发队列的排队时长（诚实地板：文案不得暗示不存在的语义）。 -->
            <span class="today-lamp" :style="{ background: taskLampColor(t.status) }"></span>
            <span class="today-card-main">
              <span class="today-card-name">{{ t.name || t.id.slice(0, 12) }}</span>
              <span class="today-card-sub">
                {{ t.agent_id }}<template v-if="elapsedText(t)"> · 运行 {{ elapsedText(t) }}</template>
              </span>
            </span>
          </div>
        </div>
        <EmptyState v-else variant="action" description="没有等你签发的任务" />
      </section>

      <!-- 版块 2：进行中 -->
      <section class="today-section">
        <div class="today-section-head working">进行中 · {{ workingTasks.length }}</div>
        <div v-if="workingTasks.length" class="today-list">
          <div
            v-for="t in workingTasks"
            :key="t.id"
            class="today-card"
            role="button"
            tabindex="0"
            @click="openTask(t.id)"
            @keydown.enter.prevent="openTask(t.id)"
            @keydown.space.prevent="openTask(t.id)"
          >
            <span class="today-lamp" :class="{ 'is-pulsing': isWork(t.status) }" :style="{ background: taskLampColor(t.status) }"></span>
            <span class="today-card-main">
              <span class="today-card-name">{{ t.name || t.id.slice(0, 12) }}</span>
              <span class="today-card-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }}</span>
            </span>
          </div>
        </div>
        <EmptyState v-else variant="data" description="当前没有进行中的任务" />
      </section>

      <!-- 版块 3：今日交付（终态叙事卡）。animate 恒 false 占位——Task 6 才接
           sealAnimateIds（本会话亲历迁移才播盖章仪式），此处直开静态渲染零回归。 -->
      <section class="today-section">
        <div class="today-section-head">今日交付 · {{ deliveryTasks.length }}</div>
        <div v-if="deliveryTasks.length" class="today-list">
          <DeliveryCard v-for="t in deliveryTasks" :key="t.id" :task="t" :animate="false" />
        </div>
        <EmptyState v-else variant="data" description="今天还没有交付的任务" />
      </section>

      <!-- 版块 4：Agent 动态（4a 本周最近晋升 ≤5 条 + 4b 今日最活跃 Agent top3）。
           4a 用「本周」框定（与版块5「本周晋升」同一 since 口径），故对
           listGlobalPromotions 的结果做本地 weekStartIso 过滤而非直接取前 5——
           否则「本周暂无晋升」空态文案可能在有更早晋升时误判有数据。 -->
      <section class="today-section">
        <div class="today-section-head">Agent 动态</div>
        <div v-if="promotionsError" class="today-error">{{ promotionsError }}</div>
        <template v-else>
          <div v-if="recentPromotions.length" class="today-list">
            <div v-for="p in recentPromotions" :key="p.id" class="today-promo-row">
              <span class="today-promo-main">
                {{ p.agent_id }} 晋升 {{ maturityLabel(p.from_maturity) }} → {{ maturityLabel(p.to_maturity) }}
              </span>
              <span class="today-promo-sub">{{ formatTime(p.created_at) }} · 签发人 {{ p.confirmed_by }}</span>
            </div>
          </div>
          <EmptyState v-else variant="data" description="本周暂无晋升" />
        </template>

        <div class="today-subhead">今日最活跃 Agent</div>
        <div v-if="topActiveAgents.length" class="today-active-row">
          <span v-for="a in topActiveAgents" :key="a.agent_id" class="today-active-chip">
            {{ a.agent_id }} · {{ a.count }}
          </span>
        </div>
        <EmptyState v-else variant="data" description="窗口内暂无任务" />
        <div class="today-subhead-note">近 100 条任务窗口口径</div>
      </section>

      <!-- 版块 5：团队总量条——四格横条，全中性 ink 色（信任色锁：绿/teal 只留给
           REAL 结果/人签动作本身，不预支到统计数字）。 -->
      <section class="today-section">
        <div class="today-section-head">团队总量</div>
        <div v-if="statsError" class="today-error">{{ statsError }}</div>
        <div v-else-if="stats" class="today-stats-bar">
          <div class="today-stat-tile">
            <span class="today-stat-num">{{ stats.tasks_completed }}</span>
            <span class="today-stat-label">本周完成</span>
          </div>
          <div class="today-stat-tile">
            <span class="today-stat-num">{{ stats.reviews_approved }}</span>
            <span class="today-stat-label">本周人签放行</span>
          </div>
          <div class="today-stat-tile">
            <span class="today-stat-num">{{ stats.curated_cases_total }}</span>
            <span class="today-stat-label">累计固化 case（按仓内固化文件计）</span>
          </div>
          <div class="today-stat-tile">
            <span class="today-stat-num">{{ stats.promotions }}</span>
            <span class="today-stat-label">本周晋升</span>
          </div>
        </div>
        <SkeletonBlock v-else height="52px" width="100%" />
      </section>
    </template>

    <div class="today-foot-note">基于最近 100 条任务窗口</div>
  </div>
</template>

<script setup>
// 数据源：liveFeed 'tasks' channel（批A 单源轮询，5s 自链，与 StatusCenter/
// StatusDock/TaskConsole 同一份真值）。本页整页挂载期间持有一次 acquire，
// 卸载即 release（channel 无其它订阅者时自停）。
import { computed, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { acquireChannel, onTransition } from "../stores/liveFeed";
import { getStatsOverview, listGlobalPromotions } from "../api/stats";
import { statusLabel, taskLampColor, taskElapsedMs, formatDuration, formatTime, TASK_WORK_STATES, MATURITY } from "../utils/format";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import DeliveryCard from "../components/DeliveryCard.vue";

const router = useRouter();

const tasksChannel = acquireChannel("tasks");
const { tasks: feedTasks, loaded: feedLoaded, error: feedError } = tasksChannel.state;

const maturityLabel = (m) => MATURITY[m]?.label ?? m;

const waitingTasks = computed(() => feedTasks.value.filter((t) => t.status === "waiting_review"));
const workingTasks = computed(() =>
  feedTasks.value.filter((t) => ["created", "queued", "running", "validating"].includes(t.status))
);

// 版块 3：今日交付——终态（completed/failed/cancelled）且 finished_at 落在本地
// 今日（本地日切：今天 0 点起，非 UTC）。本地日切用 Date 对象比较，不字符串截断。
const TERMINAL_STATES = new Set(["completed", "failed", "cancelled"]);
const deliveryTasks = computed(() => {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  return feedTasks.value.filter(
    (t) => TERMINAL_STATES.has(t.status) && t.finished_at && new Date(t.finished_at) >= todayStart
  );
});

// 版块 4/5（B-T5）：「本周」=本地周一零点转 UTC ISO 作 since（周日 getDay()=0 归上周一）。
// 算一次即可——页面挂载期间「本周」边界不变，不必做成响应式。
const weekStartIso = (() => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.toISOString();
})();

const stats = ref(null);
const statsError = ref("");
const promotions = ref([]);
const promotionsError = ref("");

// 4a 空态文案「本周暂无晋升」要求本地按 weekStartIso 过滤（listGlobalPromotions
// 本身是全局最近 N 条，无 since 参数）——直接掐前 5 条在晋升稀疏时会把「本周
// 之前」的旧晋升误显示成「本周有」，或反过来把「本周确实有」误判成空。
// Date 对象比较而非字符串比较：weekStartIso 是 'Z' 后缀、created_at 是后端
// 归一化的 '+00:00' 后缀，同一时刻两种表示字典序不等价（stats.py 同款坑：
// ASCII '.'/'Z' 与 '+' 错序），必须转 Date 再比才是真时间序。
const weekStartMs = Date.parse(weekStartIso);
const recentPromotions = computed(() =>
  promotions.value.filter((p) => Date.parse(p.created_at) >= weekStartMs).slice(0, 5)
);

// 4b 今日最活跃 Agent：从已持有的 tasks channel（近 100 条窗口）派生，不再单独 acquire。
const topActiveAgents = computed(() => {
  const counts = new Map();
  for (const t of feedTasks.value) {
    if (!t.agent_id) continue;
    counts.set(t.agent_id, (counts.get(t.agent_id) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([agent_id, count]) => ({ agent_id, count }));
});

async function fetchStats() {
  try {
    stats.value = await getStatsOverview(weekStartIso);
    statsError.value = "";
  } catch (err) {
    // 诚实地板：失败显式报错，绝不显示 0 冒充无数据。
    statsError.value = err.detail || err.message || "统计不可用";
  }
}

async function fetchPromotions() {
  try {
    promotions.value = await listGlobalPromotions(20);
    promotionsError.value = "";
  } catch (err) {
    promotionsError.value = err.detail || err.message || "晋升列表不可用";
  }
}

fetchStats();
fetchPromotions();

// 补拉纪律（brief §拉取纪律）：任务转 completed 或离开 waiting_review 时才可能
// 产生新的治理事件（完成数/人签数），补拉一次 stats；30s 内去重防事件雨连环拉。
// 不进 liveFeed 轮询——只在真实转移事件上触发。
let lastStatsRefetchAt = 0;
const offTransition = onTransition((ev) => {
  if (ev.to === "completed" || ev.from === "waiting_review") {
    const now = Date.now();
    if (now - lastStatsRefetchAt < 30000) return;
    lastStatsRefetchAt = now;
    fetchStats();
  }
});

function isWork(status) {
  return TASK_WORK_STATES.has(status);
}

function elapsedText(t) {
  const ms = taskElapsedMs(t, Date.now());
  return ms === null ? "" : formatDuration(ms);
}

function openTask(id) {
  router.push(`/tasks/${id}`);
}

onUnmounted(() => {
  tasksChannel.release();
  offTransition();
});
</script>

<style scoped>
.today {
  max-width: 760px;
  margin: 0 auto;
}
.today-head {
  margin-bottom: 18px;
}
.today-title {
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
}
.today-error {
  color: var(--trust-fail);
  font-size: 12.5px;
  margin-bottom: 12px;
}
.today-skel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.today-section {
  margin-bottom: 26px;
}
.today-section-head {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--ink-faint);
  margin-bottom: 10px;
}
.today-section-head.waiting {
  color: var(--trust-pending);
}
.today-section-head.working {
  color: var(--clay);
}
.today-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.today-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.today-card:hover {
  border-color: var(--clay-softer);
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
.today-lamp {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  transition: background var(--motion-med) var(--ease-out-soft);
}
.today-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
.today-card-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.today-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-card-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.today-promo-row {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 8px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
}
.today-promo-main {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.today-promo-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
}
.today-subhead {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-faint);
  margin: 16px 0 8px;
}
.today-subhead-note {
  font-size: 10.5px;
  color: var(--ink-faint);
  margin-top: 6px;
}
.today-active-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.today-active-chip {
  font-size: 12px;
  color: var(--ink);
  padding: 5px 10px;
  border: 1px solid var(--hairline-soft);
  border-radius: 999px;
  background: var(--card-bg);
}
.today-stats-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.today-stat-tile {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
  box-shadow: var(--shadow-card);
}
.today-stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.today-stat-label {
  font-size: 10.5px;
  color: var(--ink-faint);
  line-height: 1.35;
}
.today-foot-note {
  font-size: 10.5px;
  color: var(--ink-faint);
  border-top: 1px dashed var(--hairline);
  margin-top: 8px;
  padding-top: 10px;
}
@media (prefers-reduced-motion: reduce) {
  .today-lamp.is-pulsing {
    animation: none;
  }
  .today-lamp,
  .today-card {
    transition: none;
  }
}
</style>
