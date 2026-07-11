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

      <div v-if="listError" class="cl-error">{{ listError }}</div>

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
            <span class="cl-name">{{ t.name || t.id.slice(0, 12) }}</span>
            <span class="cl-sub">{{ t.agent_id }} · 需要你签发</span>
          </span>
        </div>
      </template>

      <!-- 全部任务（最近窗口）：状态徽章随 5s 轮询原地切换 -->
      <div class="cl-group-label">最近任务 · {{ otherTasks.length }}</div>
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
          <span class="cl-name">{{ t.name || t.id.slice(0, 12) }}</span>
          <span class="cl-sub">{{ t.agent_id }} · {{ statusLabel(t.status) }}</span>
        </span>
      </div>
      <div v-if="!loadingList && !tasks.length" class="cl-zero">还没有任务——从对话召集，或点上方「+ 新任务」。</div>

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
// 左栏列表：5s 链式轮询（上轮落地才排下轮，hidden 跳过仍续轮，disposed 防
// 越过卸载）——与 StatusDock/工作台同一纪律；徽章颜色走 taskLampColor 信任
// 色锁 SSOT。选中=路由（/tasks/:taskId），深链/刷新/回退天然可用。
import { ref, computed, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listTasks } from "../api/tasks";
import { statusLabel, taskLampColor, TASK_WORK_STATES } from "../utils/format";
import TaskDetail from "./TaskDetail.vue";
import EmptyState from "../components/EmptyState.vue";

const route = useRoute();
const router = useRouter();

const selectedId = computed(() => (typeof route.params.taskId === "string" ? route.params.taskId : ""));

const tasks = ref([]);
const listError = ref("");
const loadingList = ref(true);

const waitingTasks = computed(() => tasks.value.filter((t) => t.status === "waiting_review"));
const otherTasks = computed(() => tasks.value.filter((t) => t.status !== "waiting_review"));

function isWork(status) {
  return TASK_WORK_STATES.has(status);
}

function select(t) {
  if (t.id !== selectedId.value) router.push(`/tasks/${t.id}`);
}

async function refreshList() {
  try {
    tasks.value = await listTasks({ limit: 100 });
    listError.value = "";
  } catch (err) {
    // 首载失败如实报错；轮询失败保留上次清单下 tick 自愈
    if (!tasks.value.length) listError.value = err.detail || err.message || "加载失败";
  } finally {
    loadingList.value = false;
  }
}

let pollTimer = null;
let disposed = false;
function schedulePoll() {
  clearPoll();
  pollTimer = setTimeout(async () => {
    try {
      if (!document.hidden) await refreshList();
    } finally {
      if (!disposed) schedulePoll();
    }
  }, 5000);
}
function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}
onMounted(async () => {
  await refreshList();
  if (!disposed) schedulePoll();
});
onUnmounted(() => {
  disposed = true;
  clearPoll();
});
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
}
.cl-lamp.is-pulsing {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out infinite;
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
  }
}
</style>
