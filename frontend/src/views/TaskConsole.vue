<template>
  <!-- 任务台（范式 2b，Codex 任务页三栏哲学）：左=任务列表（状态徽章原地随
       轮询切换）；右=选中任务的叙事流+输出/来源面板（TaskDetail 完整复用——
       它自身已是「主列+来源栏」双栏，嵌入后合成三栏）。/tasks 未选中=空态。 -->
  <div class="console">
    <aside class="console-list" :class="{ 'is-collapsed': selectedId }">
      <div class="cl-head">
        <span class="cl-title">任务台</span>
        <el-button size="small" text type="primary" @click="$router.push('/tasks/new')">+ 新任务</el-button>
      </div>

      <div v-if="feedError" class="cl-error">{{ feedError }}</div>

      <!-- 首载骨架（A3）：只在「从未 loaded 且无错误」时撑轮廓，轮询期间/带旧值
           刷新绝不回骨架；失败态走上面 cl-error，骨架不吞错误。 -->
      <div v-if="!feedLoaded && !feedError" class="cl-skel-list">
        <SkeletonBlock v-for="(w, i) in ['92%', '76%', '88%', '68%', '84%', '72%']" :key="i" height="40px" :width="w" />
      </div>

      <template v-else>
        <!-- 待你签发：amber 组置顶（行动召唤最高优先） -->
        <template v-if="waitingTasks.length">
          <div class="cl-group-label waiting">✍ 待你签发 · {{ waitingTasks.length }}</div>
          <div
            v-for="t in waitingTasks"
            :key="t.id"
            class="cl-item"
            :class="{ 'is-active': t.id === selectedId }"
            role="button"
            tabindex="0"
            @click="select(t)"
            @keydown.enter.prevent="select(t)"
            @keydown.space.prevent="select(t)"
          >
            <span class="cl-lamp" :style="{ background: 'var(--trust-pending)' }"></span>
            <span class="cl-main">
              <!-- 人话称呼（批次四 Q1）：taskDisplayName 三级诚实降级 SSOT；
                   meta 时钟=同名行消歧锚（3-lens 可用性镜头 P2）。 -->
              <span class="cl-name">{{ taskDisplayName(t, agentNames.map) }}</span>
              <span class="cl-sub">{{ t.agent_id }} · 需要你签发 · {{ consoleClock(t.created_at) }}</span>
            </span>
          </div>
        </template>

        <!-- 全部任务（最近窗口）：状态徽章随 5s 轮询原地切换。
             零值不显示（批次四 Q2）：N=0 时不渲染「· 0」。 -->
        <div class="cl-group-label">最近任务<template v-if="otherTasks.length"> · {{ otherTasks.length }}</template></div>
        <div
          v-for="t in otherTasks"
          :key="t.id"
          class="cl-item"
          :class="{ 'is-active': t.id === selectedId }"
          role="button"
          tabindex="0"
          @click="select(t)"
          @keydown.enter.prevent="select(t)"
          @keydown.space.prevent="select(t)"
        >
          <span class="cl-lamp" :class="{ 'is-pulsing': isWork(t.status) }" :style="{ background: taskLampColor(t.status) }"></span>
          <span class="cl-main">
            <span class="cl-name" :class="{ 'is-unread': unseen(t) }">{{ taskDisplayName(t, agentNames.map) }}</span>
            <span class="cl-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }} · {{ consoleClock(t.finished_at || t.created_at) }}</span>
          </span>
          <span v-if="unseen(t)" class="cl-unseen-dot" title="完成后你还没看过"></span>
        </div>
        <div v-if="feedLoaded && !feedTasks.length" class="cl-zero">还没有任务——从对话召集，或点上方「+ 新任务」。</div>
      </template>

      <div class="cl-foot-note">清单来自最近任务窗口（100 条）真实轮询——窗口外不虚报。</div>
    </aside>

    <section class="console-main">
      <!-- 选中任务：TaskDetail 完整复用（叙事流+签发+输出/来源栏全承袭，
           m2 验收契约原样保留）；:key 保证切换任务时干净重建。 -->
      <TaskDetail v-if="selectedId" :key="selectedId" />

      <!-- 未选中空态 -->
      <div v-else class="console-empty">
        <EmptyState variant="action" description="从左栏选择一个任务，或从对话召集一个新任务" />
      </div>
    </section>
  </div>
</template>

<script setup>
// 左栏列表订阅 taskFeed 共享轮询源（范式 2c：与 StatusDock 同一条 5s 链同一
// 份数据，页面不再各拉各的）；徽章颜色走 taskLampColor 信任色锁 SSOT。
// 选中=路由（/tasks/:taskId），深链/刷新/回退天然可用。
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { statusLabel, taskLampColor, taskDisplayName, formatClockCompact, TASK_WORK_STATES } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import { useTodayKey } from "../composables/useTodayKey";
import { ensureTaskBaseline, markTaskSeen, taskHasUnseen } from "../utils/lastSeen";
import { feedTasks, feedLoaded, feedError, acquireTaskFeed, releaseTaskFeed } from "../stores/taskFeed";
import TaskDetail from "./TaskDetail.vue";
import EmptyState from "../components/EmptyState.vue";
import SkeletonBlock from "../components/SkeletonBlock.vue";

const route = useRoute();
const router = useRouter();

// Agent 人话名册（批次四 Q1）：左栏行主文本缺名时回退注册表显示名。
const agentNames = useAgentNames();

// 行级紧凑时钟（同名行消歧锚，与状态中心行同律）：useTodayKey 响应式日界。
const todayKey = useTodayKey();
const consoleClock = (iso) => formatClockCompact(iso, todayKey.value);

const selectedId = computed(() => (typeof route.params.taskId === "string" ? route.params.taskId : ""));

const waitingTasks = computed(() => feedTasks.value.filter((t) => t.status === "waiting_review"));
const otherTasks = computed(() => feedTasks.value.filter((t) => t.status !== "waiting_review"));

function isWork(status) {
  return TASK_WORK_STATES.has(status);
}

// 完成未读点（localStorage 非响应式）：seenVersion 在点选时自增，让当行点
// 立即熄灭，不用等下一轮 feed 更新重渲。
const seenVersion = ref(0);
function unseen(t) {
  seenVersion.value; // 建立响应依赖
  return taskHasUnseen(t);
}

function select(t) {
  markTaskSeen(t.id);
  seenVersion.value += 1;
  if (t.id !== selectedId.value) router.push(`/tasks/${t.id}`);
}

onMounted(() => {
  ensureTaskBaseline(); // 首次进任务台锚定未读基线（幂等）
  acquireTaskFeed();
});
onUnmounted(releaseTaskFeed);
</script>

<style scoped>
.console {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.console-list {
  flex: none;
  width: 264px;
  position: sticky;
  top: 20px;
  max-height: calc(100vh - 72px);
  overflow-y: auto;
  padding: 4px 4px 12px 0;
}
.console-main {
  flex: 1 1 auto;
  min-width: 0;
}
.cl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.cl-title {
  font-family: var(--serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
}
.cl-error {
  color: var(--trust-fail);
  font-size: 12px;
  margin-bottom: 10px;
}
.cl-skel-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 10px;
}
.cl-group-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--ink-faint);
  margin: 14px 0 6px;
}
.cl-group-label.waiting {
  color: var(--trust-pending);
}
.cl-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: 9px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft);
}
.cl-item:hover {
  background: var(--paper-rail);
}
.cl-item.is-active {
  background: var(--paper-rail);
  border-color: var(--hairline);
}
.cl-lamp {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  /* 徽章切换微动效（2c）：轮询把状态原地翻面时颜色渐变过渡，不硬跳 */
  transition: background var(--motion-med) var(--ease-out-soft);
}
.cl-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
}
/* 完成未读（2c）：注意力信号≠信任信号，不占信任色锁五槽（clay 许可范围
 * 仅工作/进行/选中）——用形状（空心环）+字重（名字加粗）双通道承载，零新色。 */
.cl-unseen-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  border: 1.5px solid var(--ink);
  background: transparent;
}
.cl-name.is-unread {
  font-weight: 700;
  color: var(--ink);
}
.cl-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.cl-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cl-sub {
  font-size: 11px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cl-zero {
  font-size: 12px;
  color: var(--ink-faint);
  padding: 10px 2px;
  line-height: 1.6;
}
.cl-foot-note {
  font-size: 10.5px;
  color: var(--ink-faint);
  border-top: 1px dashed var(--hairline);
  margin-top: 14px;
  padding-top: 8px;
}
.console-empty {
  padding-top: 10vh;
}
@media (prefers-reduced-motion: reduce) {
  .cl-lamp.is-pulsing {
    animation: none;
  }
  .cl-lamp,
  .cl-item {
    transition: none;
  }
}
@media (max-width: 900px) {
  /* 窄屏：选中任务时列表让位给叙事流（返回走浏览器后退/左栏入口） */
  .console-list.is-collapsed {
    display: none;
  }
  .console {
    gap: 0;
    flex-direction: column;
    align-items: stretch; /* 列纵向时 flex-start 会让 .console-main 收成 fit-content → 撑不满/仍可能溢出 */
  }
}
</style>
