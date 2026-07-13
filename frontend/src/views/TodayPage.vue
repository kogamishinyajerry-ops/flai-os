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

      <!-- 版块 4/5：占位（Agent 动态/团队总量），批B后续任务接入 -->
      <section class="today-section today-placeholder">
        <div class="today-section-head">Agent 动态</div>
        <div class="today-placeholder-note">占位——待接入最近晋升 + 今日最活跃 Agent</div>
      </section>
      <section class="today-section today-placeholder">
        <div class="today-section-head">团队总量</div>
        <div class="today-placeholder-note">占位——待接入团队总量条</div>
      </section>
    </template>

    <div class="today-foot-note">基于最近 100 条任务窗口</div>
  </div>
</template>

<script setup>
// 数据源：liveFeed 'tasks' channel（批A 单源轮询，5s 自链，与 StatusCenter/
// StatusDock/TaskConsole 同一份真值）。本页整页挂载期间持有一次 acquire，
// 卸载即 release（channel 无其它订阅者时自停）。
import { computed, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { acquireChannel } from "../stores/liveFeed";
import { statusLabel, taskLampColor, taskElapsedMs, formatDuration, TASK_WORK_STATES } from "../utils/format";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";
import DeliveryCard from "../components/DeliveryCard.vue";

const router = useRouter();

const tasksChannel = acquireChannel("tasks");
const { tasks: feedTasks, loaded: feedLoaded, error: feedError } = tasksChannel.state;

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
.today-placeholder .today-placeholder-note {
  font-size: 12px;
  color: var(--ink-faint);
  padding: 12px 14px;
  border: 1px dashed var(--hairline);
  border-radius: 10px;
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
