<template>
  <!-- 仿真监控浮窗（实验性，默认关）：UI-PARADIGM「状态来找人」在仿真域的延伸。
       监控内容不是平台自有数据，而是 sim-live-hub（本机多域仿真监控台）的嵌入视图——
       浮窗只做外壳与收起态 pill，监控 UI 的 SSOT 留在 hub 侧（零逻辑复制）。
       启用：访问任意页带 ?simhub=http://127.0.0.1:8791（持久化 localStorage），
       ?simhub=off 关闭。未配置时整个组件零渲染——e2e 与生产构建不受任何影响。 -->
  <div v-if="enabled" class="sim-float">
    <div v-show="expanded" class="sim-card">
      <div class="sim-head">
        <span class="sim-title">仿真实时监控</span>
        <a class="sim-full" :href="hubOrigin + '/'" target="_blank" rel="noopener">完整面板 ↗</a>
        <button class="sim-btn" title="收起为角标" @click="expanded = false">收起</button>
      </div>
      <!-- iframe 常驻装载、收起仅隐藏不卸载：收起态 pill 的活状态全靠页内
           1s 轮询 + postMessage 持续流入；卸载即失明（pill 会说谎"最新"）。 -->
      <iframe class="sim-frame" :src="frameSrc" title="仿真实时监控（sim-live-hub 嵌入视图）"></iframe>
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
import { computed, onMounted, onUnmounted, ref } from "vue";

const STORAGE_KEY = "flai.simMonitorHub";

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
const frameSrc = enabled
  ? `${hubOrigin}/embed.html?host_origin=${encodeURIComponent(window.location.origin)}`
  : "";

const expanded = ref(false);
const last = ref(null); // 最近一条 sim-live-status 负载
const lastTs = ref(0);
const nowTick = ref(Date.now());

function onMessage(e) {
  if (e.origin !== hubOrigin) return;
  const d = e.data;
  if (!d || d.type !== "sim-live-status") return;
  last.value = d;
  lastTs.value = Date.now();
}

// 诚实地板：消息断流（hub 服务/iframe 死亡）≠ 一切安好——pill 显式转「未连接」，
// 绝不让最后一帧旧状态冒充活着。阈值 6s ≈ 6 个 1s 心跳全丢。
const connLost = computed(
  () => nowTick.value - lastTs.value > 6000 || (last.value && last.value.status === "unreachable"),
);

// pill 配色遵守信任色锁：运行=clay（工作/进行槽）、停滞/失败=真失败红、
// 完成/空闲/未连接=中性灰——completed 不给绿的既有纪律同样适用于仿真域。
const pill = computed(() => {
  const d = last.value;
  if (!d || connLost.value) {
    return { cls: "mut", text: d ? "仿真监控 · 未连接" : "仿真监控 · 连接中…" };
  }
  const short = (d.label || d.module || "").split("·")[0].trim();
  if (d.alarm === true) {
    return { cls: "fail", text: `⚠ ${short} ${d.status === "failed" ? "失败" : "停滞"}` };
  }
  if (d.status === "running") {
    return { cls: "work", text: `${short} · ${d.stageLabel || "进行中"}` };
  }
  if (d.status === "finished") return { cls: "mut", text: `${short} · 最近完成` };
  return { cls: "mut", text: "仿真监控 · 空闲" };
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
  height: 430px;
  border: 1px solid var(--hairline);
  border-radius: 12px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-card-hover);
  overflow: hidden;
}
.sim-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--hairline);
}
.sim-title { font-size: 12.5px; font-weight: 700; color: var(--ink-soft); flex: 1; }
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
</style>
