<template>
  <!-- 全局状态坞（UI-PARADIGM.md 祈使句②「状态来找人」）：常驻每页右上，
       计数全部来自真实轮询（诚实地板——绝不估算）。点击任意处打开状态中心。 -->
  <div class="status-dock" role="button" tabindex="0" :aria-label="dockLabel" @click="openInbox" @keydown.enter="openInbox" @keydown.space.prevent="openInbox">
    <span v-if="syncIssue" class="dock-pill dock-pill-sync">
      {{ feedResyncing ? "正在重同步" : "同步中断" }}
    </span>
    <span v-if="waitingCount > 0" class="dock-pill dock-pill-waiting" :class="{ 'dock-pulse-echo': pulseEcho }">
      ✍ 待你签发 <span class="num-token">{{ waitingCount }}</span>
    </span>
    <span v-if="workingCount > 0" class="dock-pill dock-pill-working">
      <span class="work-pulse-dot"></span>
      运行中 <span class="num-token">{{ workingCount }}</span>
    </span>
    <span class="dock-core" :class="{ 'has-sync-issue': syncIssue }" :title="dockLabel">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
    </span>
    <!-- 仿真监控发现入口（转正批）：仅在浮窗已配置（同 localStorage 开关，默认关
         零渲染）时出现，让同事不用记 ?simhub= 咒语就能进监控。@click.stop 不触发
         状态中心；中性色——发现入口不是工作/告警信号，不占信任色锁。 -->
    <a v-if="simHubUrl" class="dock-monitor" :href="simHubUrl" target="_blank"
       rel="noopener" title="仿真实时监控" @click.stop @keydown.enter.stop @keydown.space.stop>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/></svg>
      <span class="dock-monitor-tx">监控</span>
    </a>
  </div>
</template>

<script setup>
// 计数派生自 taskFeed 共享轮询源（范式 2c：与任务台左栏同一条链同一份数据）；
// 「最近窗口 100 条」诚实口径、失败保留上次计数下 tick 自愈、从未成功不显示
// pill（无数据不装有数据）全部由 store 层承袭。
import { computed, h, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { TASK_WORK_STATES, taskDisplayName } from "../utils/format";
import { useAgentNames } from "../stores/agentNames";
import { openInbox } from "../stores/statusCenter";
import {
  feedTasks,
  feedLoaded,
  feedConnection,
  feedStale,
  feedResyncing,
  acquireTaskFeed,
  releaseTaskFeed,
} from "../stores/taskFeed";
import { onTransition } from "../stores/liveFeed";
import { setTitleBadge } from "../utils/titleBadge";

const router = useRouter();

// Agent 人话名册（批次四 Q1）：签发提醒 toast 的任务称呼与行级面同一 SSOT。
const agentNames = useAgentNames();

const workingCount = computed(() => feedTasks.value.filter((t) => TASK_WORK_STATES.has(t.status)).length);
const waitingCount = computed(() => feedTasks.value.filter((t) => t.status === "waiting_review").length);
const syncIssue = computed(() =>
  feedConnection.value === "disconnected" && (feedLoaded.value || feedStale.value)
);
const dockLabel = computed(() => syncIssue.value
  ? `打开状态中心；${feedResyncing.value ? "正在重新核对完整快照" : "任务同步已中断"}`
  : "打开状态中心"
);

// N5 标签页召回：内网 http 无 Notification API，切走标签页后「待你签发」
// 只能靠 title 徽章召回。计数与坞内 pill 同源（真实轮询），坞卸载即清零
// ——绝不让残留徽章冒充仍有待签。
watch(waitingCount, (v) => setTitleBadge(v), { immediate: true });
onUnmounted(() => setTitleBadge(0));

// 待签发即时回声（批A T10）：tasks channel 每次翻转经 liveFeed 总线广播,这里
// 只订阅落地→waiting_review 的迁移。冷启动首拉的 from=null 噪声已在 channel
// 层水合抑制掉（liveFeed.js buildTasksChannel 的 hydrating 判据，Task 12 修复
// 3）——这里收到的 from=null 只可能是水合完成后、轮询窗口间新出现即直达
// waiting_review 的真事件（快任务两 tick 间创建即到审，同样要提醒），故不再
// 要求 ev.from != null。
const ECHO_DEDUPE_MS = 30000; // 同 id 30s 内不重复弹 toast（角标脉冲不受此限）
const echoedAt = new Map();
const pulseEcho = ref(false);
let pulseTimer = null;
let offTransition = null;

function sweepEchoedAt(now) {
  // 懒惰清理：随写入机会顺带扫一遍过期项,不开定时器。
  for (const [id, ts] of echoedAt) {
    if (now - ts >= ECHO_DEDUPE_MS) echoedAt.delete(id);
  }
}

function playPulseEcho() {
  if (pulseTimer) clearTimeout(pulseTimer);
  pulseEcho.value = false;
  // 先摘类目再下一帧重加,使连续两次翻转（class 未变化时浏览器不会重播 CSS 动画）
  // 也能各自重播「播一轮」。
  requestAnimationFrame(() => {
    pulseEcho.value = true;
    pulseTimer = setTimeout(() => {
      pulseEcho.value = false;
      pulseTimer = null;
    }, 3600); // flai-work-pulse 1.8s × 2 播完即停,不常驻闪烁
  });
}

function handleTransition(ev) {
  if (ev.to !== "waiting_review") return;
  const now = Date.now();
  sweepEchoedAt(now);
  playPulseEcho(); // 角标脉冲不受 dedupe/hidden 限制——「积到角标」
  if (document.hidden) return; // 后台标签页不弹 toast，脉冲已代为记录
  const last = echoedAt.get(ev.id);
  if (last && now - last < ECHO_DEDUPE_MS) return;
  echoedAt.set(ev.id, now);
  // 人话称呼（批次四 Q1）：缺名回退 Agent 显示名；连名册都缺位时退 id 切片
  // （旧行为是全量裸 id，比切片更不可读）。
  const name = ev.task ? taskDisplayName(ev.task, agentNames.map) : ev.id.slice(0, 12);
  ElMessage({
    type: "warning",
    message: h(
      "span",
      { style: "cursor:pointer", onClick: () => router.push(`/tasks/${ev.id}`) },
      `「${name}」待你签发`
    ),
  });
}

// 仿真监控发现入口：读浮窗同款配置（未配置=null=零渲染，e2e 不受扰）；
// scheme 白名单与浮窗/深链同判据，防 localStorage 被 ?simhub= 投毒的危险 scheme。
// 响应式 ref 而非一次性 IIFE（Codex 治理审 P2）：浮窗经 ?simhub= 确认后写
// localStorage 的时机晚于本坞挂载，若只读一次则入口滞留到刷新才出现。
const simHubUrl = ref(null);
function readSimHubUrl() {
  try {
    const configured = window.localStorage.getItem("flai.simMonitorHub");
    if (!configured) {
      simHubUrl.value = null;
      return;
    }
    const u = new URL(configured);
    simHubUrl.value = (u.protocol === "http:" || u.protocol === "https:") ? u.origin + "/" : null;
  } catch (e) {
    simHubUrl.value = null;
  }
}

onMounted(() => {
  acquireTaskFeed();
  offTransition = onTransition(handleTransition);
  readSimHubUrl();
  // 浮窗（SimMonitorFloat）确认新源后派发 flai:simhub-changed（同标签页内变更，
  // storage 事件不会自触发故需自定义事件）；storage 事件覆盖跨标签页改配置。
  window.addEventListener("flai:simhub-changed", readSimHubUrl);
  window.addEventListener("storage", readSimHubUrl);
});
onUnmounted(() => {
  releaseTaskFeed();
  if (offTransition) offTransition();
  if (pulseTimer) clearTimeout(pulseTimer);
  window.removeEventListener("flai:simhub-changed", readSimHubUrl);
  window.removeEventListener("storage", readSimHubUrl);
});
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
/* 待签发即时回声：复用全局 flai-work-pulse，限定 2 轮（3.6s）播完自停——
   常驻角标绝不常驻闪烁，只在真翻转发生的这一刻多看一眼。 */
.dock-pill-waiting.dock-pulse-echo {
  animation: flai-work-pulse var(--pulse-duration) ease-in-out 2;
}
/* clay=工作中（唯一工作强调色）；脉动点复用全局 .work-pulse-dot */
.dock-pill-working {
  color: var(--clay);
  border: 1px solid rgba(var(--clay-rgb), 0.3);
  background: var(--surface-raised);
}
.dock-pill-sync {
  color: var(--trust-pending);
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  background: var(--surface-raised);
}
.dock-core.has-sync-issue {
  color: var(--trust-pending);
  border-color: var(--trust-pending);
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
/* 监控发现入口：中性色（非工作/告警信号，不占信任色锁）；hover 才轻抬 */
.dock-monitor {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  box-shadow: var(--shadow-card);
  transition: color var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft);
}
.dock-monitor:hover { color: var(--ink); border-color: var(--ink-faint); transform: translateY(-1px); }
@media (max-width: 860px) {
  /* 窄屏与汉堡钮同高不同侧；pill 收起只留核心钮，避免挤占标题区 */
  .status-dock { top: 12px; right: 12px; }
  .dock-pill { display: none; }
  .dock-monitor .dock-monitor-tx { display: none; }  /* 窄屏只留图标 */
}
@media (prefers-reduced-motion: reduce) {
  .dock-pill,
  .dock-core,
  .dock-monitor {
    transition: none;
  }
  .status-dock:hover .dock-pill,
  .status-dock:hover .dock-core,
  .dock-monitor:hover {
    transform: none;
  }
  .dock-pill-waiting.dock-pulse-echo {
    animation: none;
  }
}
</style>
