<template>
  <!-- 全局状态坞（UI-PARADIGM.md 祈使句②「状态来找人」）：常驻每页右上，
       计数全部来自真实轮询（诚实地板——绝不估算）。点击任意处打开状态中心。 -->
  <div class="status-dock" role="button" tabindex="0" aria-label="打开状态中心" @click="openInbox" @keydown.enter="openInbox" @keydown.space.prevent="openInbox">
    <span v-if="waitingCount > 0" class="dock-pill dock-pill-waiting">
      ✍ 待你签发 {{ waitingCount }}
    </span>
    <span v-if="workingCount > 0" class="dock-pill dock-pill-working">
      <span class="work-pulse-dot"></span>
      运行中 {{ workingCount }}
    </span>
    <span class="dock-core" title="状态中心">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
    </span>
  </div>
</template>

<script setup>
// 计数派生自 taskFeed 共享轮询源（范式 2c：与任务台左栏同一条链同一份数据）；
// 「最近窗口 100 条」诚实口径、失败保留上次计数下 tick 自愈、从未成功不显示
// pill（无数据不装有数据）全部由 store 层承袭。
import { computed, onMounted, onUnmounted } from "vue";
import { TASK_WORK_STATES } from "../utils/format";
import { openInbox } from "../stores/statusCenter";
import { feedTasks, acquireTaskFeed, releaseTaskFeed } from "../stores/taskFeed";

const workingCount = computed(() => feedTasks.value.filter((t) => TASK_WORK_STATES.has(t.status)).length);
const waitingCount = computed(() => feedTasks.value.filter((t) => t.status === "waiting_review").length);

onMounted(acquireTaskFeed);
onUnmounted(releaseTaskFeed);
</script>

<style scoped>
.status-dock {
  position: fixed;
  top: 16px;
  right: 20px;
  z-index: 150; /* 低于 ⌘K 面板(200)，高于页面内容 */
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.dock-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  box-shadow: var(--shadow-card);
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.status-dock:hover .dock-pill {
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
/* amber=仅待人核（信任色锁）；行动召唤最强的一枚 */
.dock-pill-waiting {
  color: var(--trust-pending);
  border: 1px solid rgba(var(--trust-pending-rgb), 0.35);
  background: var(--surface-raised);
}
/* clay=工作中（唯一工作强调色）；脉动点复用全局 .work-pulse-dot */
.dock-pill-working {
  color: var(--clay);
  border: 1px solid rgba(var(--clay-rgb), 0.3);
  background: var(--surface-raised);
}
.dock-core {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  box-shadow: var(--shadow-card);
  transition: color var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
}
.status-dock:hover .dock-core {
  color: var(--clay);
  border-color: var(--clay-softer);
  transform: translateY(-1px);
}
@media (max-width: 860px) {
  /* 窄屏与汉堡钮同高不同侧；pill 收起只留核心钮，避免挤占标题区 */
  .status-dock { top: 12px; right: 12px; }
  .dock-pill { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .dock-pill,
  .dock-core {
    transition: none;
  }
  .status-dock:hover .dock-pill,
  .status-dock:hover .dock-core {
    transform: none;
  }
}
</style>
