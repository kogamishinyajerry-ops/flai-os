<template>
  <!-- 仿真监控浮窗（实验性，默认关）：UI-PARADIGM「状态来找人」在仿真域的延伸。
       v2 双页签：仿真监控（sim-live-hub /embed.html）｜Agent 工作台
       （/embed-workbench.html：思考冒泡+正在看的页面+操作流+中间结果）。
       浮窗只做外壳与收起态 pill，监控 UI 的 SSOT 留在 hub 侧（零逻辑复制）。
       启用：访问任意页带 ?simhub=http://127.0.0.1:8791（持久化 localStorage），
       ?simhub=off 关闭。未配置时整个组件零渲染——e2e 与生产构建不受任何影响。 -->
  <div v-if="enabled" class="sim-float">
    <div v-show="expanded" class="sim-card">
      <div class="sim-head">
        <button
          v-for="t in TABS"
          :key="t.key"
          class="sim-tab"
          :class="{ active: activeTab === t.key, alarmed: t.key !== activeTab && surfaceAlarm(t.key) }"
          @click="activeTab = t.key"
        >{{ t.label }}<span v-if="t.key !== activeTab && surfaceAlarm(t.key)" class="sim-tab-dot"></span></button>
        <span style="flex: 1"></span>
        <a class="sim-full" :href="fullLink" target="_blank" rel="noopener">完整面板 ↗</a>
        <button class="sim-btn" title="收起为角标" @click="expanded = false">收起</button>
      </div>
      <!-- 双 iframe 常驻装载（切页签仅切可见性，收起也不卸载）：pill 的活状态
           与跨页签报警穿透全靠两路 postMessage 持续流入；卸载即失明。 -->
      <iframe v-show="activeTab === 'sim'" class="sim-frame" :src="frameSrc('embed.html')"
              title="仿真实时监控（sim-live-hub 嵌入视图）"></iframe>
      <iframe v-show="activeTab === 'workbench'" class="sim-frame" :src="frameSrc('embed-workbench.html')"
              title="Agent 虚拟工作台（sim-live-hub 嵌入视图）"></iframe>
    </div>
    <button v-show="!expanded" class="sim-pill" :class="pill.cls" @click="expanded = true">
      <span class="sim-dot" :class="pill.cls"></span>{{ pill.text }}
    </button>
  </div>
</template>

<script setup>
// 消息边界（外部输入纪律）：iframe 内容来自用户显式配置的 hub 地址，但 postMessage
// 仍按未受信输入对待——event.origin 必须逐字等于 hub origin，类型必须是
// "sim-live-status"，其余一律丢弃；负载只读取展示，绝不执行/写入。
// v2：负载 surface 字段（"sim"|"workbench"）分流双页签，缺省按 "sim" 兼容。
import { computed, onMounted, onUnmounted, ref } from "vue";
import { resolvedTheme } from "../stores/theme";

const STORAGE_KEY = "flai.simMonitorHub";
const TABS = [
  { key: "sim", label: "仿真" },
  { key: "workbench", label: "工作台" },
];

let hubOrigin = null;
try {
  const q = new URLSearchParams(window.location.search).get("simhub");
  if (q === "off") window.localStorage.removeItem(STORAGE_KEY);
  else if (q) window.localStorage.setItem(STORAGE_KEY, q);
  const configured = window.localStorage.getItem(STORAGE_KEY);
  hubOrigin = configured ? new URL(configured).origin : null;
} catch (e) {
  hubOrigin = null; // 非法 URL / storage 不可用：按未配置处理，不半开
}

const enabled = hubOrigin !== null;
// 主题透传（转正门槛清单项）：暗色时经 ?theme=dark 让 hub 嵌入视图随平台
// 换肤；resolvedTheme 是响应式依赖——切主题时模板重取 src，iframe 重载
// （嵌入页无长驻状态，1s 轮询重建，代价可接受）。
function frameSrc(page) {
  if (!enabled) return "";
  const theme = resolvedTheme.value === "dark" ? "&theme=dark" : "";
  return `${hubOrigin}/${page}?host_origin=${encodeURIComponent(window.location.origin)}${theme}`;
}

const expanded = ref(false);
const activeTab = ref("sim");
const fullLink = computed(() =>
  activeTab.value === "workbench" ? `${hubOrigin}/workbench.html` : `${hubOrigin}/`);

// 按 surface 分槽存最近消息；两路 1s 心跳独立断流判定。
const last = ref({ sim: null, workbench: null });
const lastTs = ref({ sim: 0, workbench: 0 });
const nowTick = ref(Date.now());

function onMessage(e) {
  if (e.origin !== hubOrigin) return;
  const d = e.data;
  if (!d || d.type !== "sim-live-status") return;
  const surface = d.surface === "workbench" ? "workbench" : "sim";
  last.value = { ...last.value, [surface]: d };
  lastTs.value = { ...lastTs.value, [surface]: Date.now() };
}

function fresh(surface) {
  return nowTick.value - lastTs.value[surface] <= 6000
    && last.value[surface] && last.value[surface].status !== "unreachable";
}
function surfaceAlarm(surface) {
  return fresh(surface) === true && (last.value[surface].alarm === true);
}

// 诚实地板：双路全断流 → pill 显式「未连接」，绝不让最后一帧旧状态冒充活着。
const connLost = computed(() => !fresh("sim") && !fresh("workbench"));

const WORK_STATUS = new Set(["running", "tooling", "generating"]);
const WB_LABEL = { tooling: "工具执行中", generating: "生成中", idle: "空闲", stalled: "停滞" };

// pill 配色遵守信任色锁：工作中=clay（工作/进行槽）、停滞/失败=真失败红、
// 完成/空闲/未连接=中性灰。报警穿透跨页签：任一 surface 报警 pill 即红。
const pill = computed(() => {
  if (connLost.value) {
    const everSeen = last.value.sim || last.value.workbench;
    return { cls: "mut", text: everSeen ? "监控 · 未连接" : "监控 · 连接中…" };
  }
  // ① 报警优先（跨页签穿透）
  for (const s of ["sim", "workbench"]) {
    if (surfaceAlarm(s)) {
      const d = last.value[s];
      const who = s === "sim" ? (d.label || "").split("·")[0].trim() : "Agent 工作台";
      return { cls: "fail", text: `⚠ ${who} ${d.status === "failed" ? "失败" : "停滞"}` };
    }
  }
  // ② 工作中（仿真优先展示，其次工作台）
  const sim = fresh("sim") ? last.value.sim : null;
  if (sim && sim.status === "running") {
    return { cls: "work", text: `${(sim.label || "").split("·")[0].trim()} · ${sim.stageLabel || "进行中"}` };
  }
  const wb = fresh("workbench") ? last.value.workbench : null;
  if (wb && WORK_STATUS.has(wb.status)) {
    return { cls: "work", text: `工作台 · ${wb.stageLabel || WB_LABEL[wb.status] || wb.status}` };
  }
  // ③ 静默态：跟当前页签
  const act = fresh(activeTab.value) ? last.value[activeTab.value] : (sim || wb);
  if (act && act.surface === "workbench") {
    return { cls: "mut", text: `工作台 · ${WB_LABEL[act.status] || act.status}` };
  }
  if (act && act.status === "finished") {
    return { cls: "mut", text: `${(act.label || "").split("·")[0].trim()} · 最近完成` };
  }
  return { cls: "mut", text: "监控 · 空闲" };
});

let timer = null;
onMounted(() => {
  if (!enabled) return;
  window.addEventListener("message", onMessage);
  timer = window.setInterval(() => { nowTick.value = Date.now(); }, 2000);
});
onUnmounted(() => {
  window.removeEventListener("message", onMessage);
  if (timer !== null) window.clearInterval(timer);
});
</script>

<style scoped>
/* 挂 App.vue 根级（.app-main 之外）：.page-turn 带 transform 的容器会劫持
   position:fixed 的 containing block（动效系统判例），根级挂载天然免疫。 */
.sim-float {
  position: fixed;
  right: 20px;
  bottom: 24px;
  z-index: 140; /* 低于状态坞(150)与 ⌘K(200)：监控是背景信息，不抢签发/切换 */
}
.sim-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.sim-pill:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
.sim-pill.work { color: var(--clay); border-color: rgba(var(--clay-rgb), 0.3); }
.sim-pill.fail { color: var(--trust-fail); border-color: var(--trust-fail); }
.sim-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ink-faint, var(--ink-soft)); flex: none; }
.sim-dot.work { background: var(--clay); animation: sim-pulse 1.6s ease-in-out infinite; }
.sim-dot.fail { background: var(--trust-fail); }
@keyframes sim-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.sim-card {
  display: flex;
  flex-direction: column;
  width: 400px;
  height: 460px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-card-hover);
  overflow: hidden;
}
.sim-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--hairline);
}
.sim-tab {
  position: relative;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
}
.sim-tab.active { color: var(--clay); border-color: rgba(var(--clay-rgb), 0.35); }
.sim-tab.alarmed { color: var(--trust-fail); }
.sim-tab-dot {
  position: absolute;
  top: 1px;
  right: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--trust-fail);
}
.sim-full { font-size: 11.5px; font-weight: 600; color: var(--clay); text-decoration: none; }
.sim-btn {
  font-size: 11.5px;
  padding: 2px 10px;
  border-radius: 6px;
  border: 1px solid var(--hairline);
  background: transparent;
  color: var(--ink-soft);
  cursor: pointer;
}
.sim-btn:hover { color: var(--clay); border-color: var(--clay-softer); }
/* iframe 底色钉死为 hub 嵌入视图自身的暖纸色：暗色主题下装载瞬间不闪白/黑 */
.sim-frame { flex: 1; border: none; width: 100%; background: #f7f4ee; }
@media (prefers-reduced-motion: reduce) {
  .sim-pill { transition: none; }
  .sim-dot.work { animation: none; }
}
/* 窄屏（转正门槛清单项）：<900px 抬高避开 GuidePage 底部悬浮 composer，
   卡片宽度让出屏边距不溢出。 */
@media (max-width: 900px) {
  .sim-float { bottom: 96px; right: 12px; }
  .sim-card { width: min(400px, calc(100vw - 24px)); }
}
</style>
