<template>
  <!-- 仿真监控浮窗（实验性，默认关）：UI-PARADIGM「状态来找人」在仿真域的延伸。
       v2 双页签：仿真监控（sim-live-hub /embed.html）｜Agent 工作台
       （/embed-workbench.html：思考冒泡+正在看的页面+操作流+中间结果）。
       浮窗只做外壳与收起态 pill，监控 UI 的 SSOT 留在 hub 侧（零逻辑复制）。
       启用：访问任意页带 ?simhub=http://127.0.0.1:8791（经用户显式确认后持久化
       localStorage），?simhub=off 关闭。未配置时整个组件零渲染——e2e 与生产构建
       不受任何影响。 -->
  <div v-if="enabled" class="sim-float">
    <div v-show="expanded" class="sim-card">
      <div class="sim-head">
        <button
          v-for="t in TABS"
          :key="t.key"
          class="sim-tab"
          :class="{ active: activeTab === t.key, alarmed: t.key !== activeTab && surfaceAlarm(t.key), stale: staleSeen(t.key) }"
          :title="staleSeen(t.key) ? t.label + '：消息断流（最后状态非实时）' : ''"
          @click="activeTab = t.key"
        >{{ t.label }}<span v-if="t.key !== activeTab && surfaceAlarm(t.key)" class="sim-tab-dot"></span></button>
        <span v-if="connLost" class="sim-conn-lost">双路断流</span>
        <span style="flex: 1"></span>
        <a class="sim-full" :href="fullLink" target="_blank" rel="noopener" :title="'监控源 ' + hubOrigin">完整面板 ↗</a>
        <button class="sim-btn" title="收起为角标" @click="expanded = false">收起</button>
      </div>
      <!-- 双 iframe 常驻装载（切页签仅切可见性，收起也不卸载）：pill 的活状态
           与跨页签报警穿透全靠两路 postMessage 持续流入；卸载即失明。
           sandbox：监控页只需脚本+自身 fetch（hub 跨源，allow-same-origin 不触
           及宿主），顶层导航/弹窗/表单/下载一律不给——配置被投毒时限制能力面。 -->
      <iframe v-show="activeTab === 'sim'" ref="simEl" class="sim-frame"
              sandbox="allow-scripts allow-same-origin" :src="frameSrc('embed.html')"
              title="仿真实时监控（sim-live-hub 嵌入视图）"></iframe>
      <iframe v-show="activeTab === 'workbench'" ref="wbEl" class="sim-frame"
              sandbox="allow-scripts allow-same-origin" :src="frameSrc('embed-workbench.html')"
              title="Agent 虚拟工作台（sim-live-hub 嵌入视图）"></iframe>
    </div>
    <button v-show="!expanded" class="sim-pill" :class="pill.cls"
            :title="'监控源 ' + hubOrigin" @click="expanded = true">
      <span class="sim-dot" :class="pill.cls"></span>{{ pill.text }}
    </button>
  </div>
</template>

<script setup>
// 消息边界（外部输入纪律，Codex 补审 R1 硬化）：iframe 内容来自用户显式确认的
// hub 地址，但 postMessage 仍按未受信输入对待——四道闸：
// ① event.origin 必须逐字等于 hub origin；② event.source 必须是自己两个 iframe
// 的窗口（surface 由来源窗口决定，负载自报不作数）；③ 类型必须 "sim-live-status"；
// ④ status 必须落在已知枚举（fail-closed，未知状态不刷新心跳不入槽）。
// 负载只读取展示，绝不执行/写入。
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessageBox } from "element-plus";
import { resolvedTheme } from "../stores/theme";

const STORAGE_KEY = "flai.simMonitorHub";
const TABS = [
  { key: "sim", label: "仿真" },
  { key: "workbench", label: "工作台" },
];

// 只认 http(s) origin：localStorage 值可能被 ?simhub= 链接投毒，scheme 白名单
// 防 javascript:/data:/file:（它们的 origin 序列化为 "null"，若放行则任何
// opaque-origin 文档的消息都能冒充 hub）。
function parseHubOrigin(raw) {
  if (!raw) return null;
  try {
    const u = new URL(raw);
    return (u.protocol === "http:" || u.protocol === "https:") ? u.origin : null;
  } catch (e) {
    return null;
  }
}

const hubOrigin = ref(null);
const enabled = computed(() => hubOrigin.value !== null);
const q = new URLSearchParams(window.location.search).get("simhub");
try {
  if (q === "off") window.localStorage.removeItem(STORAGE_KEY);
  hubOrigin.value = parseHubOrigin(window.localStorage.getItem(STORAGE_KEY));
} catch (e) {
  hubOrigin.value = null; // storage 不可用：按未配置处理，不半开
}

// ?simhub= 带来的新地址必须经用户显式确认才持久化——恶意链接不能静默把浮窗
// 指向攻击者站点（Codex 补审 P1 钓鱼面）；已存储值=用户此前确认过，直接生效。
async function maybeAdoptParam() {
  if (!q || q === "off") return;
  const target = parseHubOrigin(q);
  if (target === null || target === hubOrigin.value) return;
  try {
    await ElMessageBox.confirm(
      `把仿真监控源指向 ${target}？浮窗将装载并信任该地址的监控页面（来自当前链接的 ?simhub= 参数）。`,
      "启用仿真监控",
      { confirmButtonText: "启用", cancelButtonText: "取消", type: "warning" },
    );
  } catch (e) {
    return; // 用户拒绝：不持久化、不启用
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, target);
  } catch (e) { /* storage 不可用：本次会话内仍生效 */ }
  // 换源必须清空旧源的全部状态（R2 复审 P2）：A 的运行/报警残影不得挂在 B
  // 名下；连接宽限期同步重起。
  last.value = { sim: null, workbench: null };
  lastTs.value = { sim: 0, workbench: 0 };
  alarmMemo.value = { sim: null, workbench: null };
  connectSince.value = Date.now();
  hubOrigin.value = target;
  // 通知全局状态坞（StatusDock）重取监控入口——它挂载时读过一次 localStorage，
  // 本次确认属挂载后变更，无此事件坞入口会滞留到刷新才出现（Codex 治理审 P2）。
  window.dispatchEvent(new CustomEvent("flai:simhub-changed"));
}

// 主题透传（转正门槛清单项）：暗色时经 ?theme=dark 让 hub 嵌入视图随平台
// 换肤；resolvedTheme 是响应式依赖——切主题时模板重取 src，iframe 重载
// （嵌入页无长驻状态，1s 轮询重建，代价可接受）。
function frameSrc(page) {
  if (!enabled.value) return "";
  const theme = resolvedTheme.value === "dark" ? "&theme=dark" : "";
  return `${hubOrigin.value}/${page}?host_origin=${encodeURIComponent(window.location.origin)}${theme}`;
}

const expanded = ref(false);
const activeTab = ref("sim");
const simEl = ref(null);
const wbEl = ref(null);
const fullLink = computed(() =>
  activeTab.value === "workbench" ? `${hubOrigin.value}/workbench.html` : `${hubOrigin.value}/`);

// 按 surface 分槽存最近消息；两路 1s 心跳独立断流判定。
const last = ref({ sim: null, workbench: null });
const lastTs = ref({ sim: 0, workbench: 0 });
const nowTick = ref(Date.now());
const connectSince = ref(Date.now());   // 本源的连接宽限期起点（换源时重起）
// 报警记忆（R2 复审 P2）：报警路后续可能只发得出 unreachable（无 alarm 字段），
// 负载替换不能吞掉「曾报警」这件事；恢复正常状态时才清。
const alarmMemo = ref({ sim: null, workbench: null });

const VALID_STATUS = new Set(["running", "finished", "failed", "stalled",
  "unreachable", "idle", "tooling", "generating"]);

function onMessage(e) {
  if (!enabled.value || e.origin !== hubOrigin.value) return;
  let surface = null;
  if (simEl.value && e.source === simEl.value.contentWindow) surface = "sim";
  else if (wbEl.value && e.source === wbEl.value.contentWindow) surface = "workbench";
  if (surface === null) return;  // 同 origin 的其他窗口/嵌套 frame 也不认
  const d = e.data;
  if (!d || d.type !== "sim-live-status") return;
  if (typeof d.status !== "string" || !VALID_STATUS.has(d.status)) return;
  // surface 以来源窗口判定为准，覆写负载自报（R2 复审 P2：静默态分支会读
  // act.surface，不规范化则 sim 帧可自称 workbench 展示）
  last.value = { ...last.value, [surface]: { ...d, surface } };
  lastTs.value = { ...lastTs.value, [surface]: Date.now() };
  if (d.alarm === true) {
    alarmMemo.value = { ...alarmMemo.value,
      [surface]: surface === "sim" ? (simWho(d) || "仿真") : "Agent 工作台" };
  } else if (d.status !== "unreachable") {
    alarmMemo.value = { ...alarmMemo.value, [surface]: null };
  }
}

function fresh(surface) {
  return nowTick.value - lastTs.value[surface] <= 6000
    && last.value[surface] && last.value[surface].status !== "unreachable";
}
function surfaceAlarm(surface) {
  return fresh(surface) === true && (last.value[surface].alarm === true);
}
// 单路断流必须可见（另一路的心跳不能掩盖它）：曾收到过消息但已断流，或
// 该路从未发来第一拍且已过宽限期（页面缺失/被拦/启动即挂，R2 复审 P2）。
function staleSeen(surface) {
  if (last.value[surface] !== null) return fresh(surface) !== true;
  return nowTick.value - connectSince.value > 15000;
}

// 诚实地板：双路全断流 → pill 显式「未连接」，绝不让最后一帧旧状态冒充活着。
const connLost = computed(() => !fresh("sim") && !fresh("workbench"));

const WORK_STATUS = new Set(["running", "tooling", "generating"]);
const WB_LABEL = { tooling: "工具执行中", generating: "生成中", idle: "空闲", stalled: "停滞" };

const simWho = (d) => String(d.label || "").split("·")[0].trim();
const otherStale = (surface) => staleSeen(surface === "sim" ? "workbench" : "sim");

// pill 配色遵守信任色锁：工作中=clay（工作/进行槽）、停滞/失败=真失败红、
// 完成/空闲/未连接=中性灰。报警穿透跨页签：任一 surface 报警 pill 即红。
const pill = computed(() => {
  if (connLost.value) {
    const everSeen = last.value.sim || last.value.workbench;
    if (everSeen) return { cls: "mut", text: "监控 · 未连接" };
    // 首连超时：从未收到任何消息也不能永远「连接中」装等待
    return nowTick.value - connectSince.value > 15000
      ? { cls: "mut", text: "监控 · 未连接（hub 无响应）" }
      : { cls: "mut", text: "监控 · 连接中…" };
  }
  // ① 报警优先（跨页签穿透）
  for (const s of ["sim", "workbench"]) {
    if (surfaceAlarm(s)) {
      const d = last.value[s];
      const who = s === "sim" ? simWho(d) : "Agent 工作台";
      return { cls: "fail", text: `⚠ ${who} ${d.status === "failed" ? "失败" : "停滞"}` };
    }
  }
  // ①b 曾报警的一路断流/失联——报警不能因心跳消失或 unreachable 替换而被掩盖
  for (const s of ["sim", "workbench"]) {
    if (staleSeen(s) && alarmMemo.value[s]) {
      return { cls: "fail", text: `⚠ ${alarmMemo.value[s]} 失联（曾报警）` };
    }
  }
  // ② 工作中（仿真优先展示，其次工作台）；另一路断流时如实标注
  const sim = fresh("sim") ? last.value.sim : null;
  if (sim && sim.status === "running") {
    return { cls: "work", text: `${simWho(sim)} · ${sim.stageLabel || "进行中"}${otherStale("sim") ? "｜另路断流" : ""}` };
  }
  const wb = fresh("workbench") ? last.value.workbench : null;
  if (wb && WORK_STATUS.has(wb.status)) {
    return { cls: "work", text: `工作台 · ${wb.stageLabel || WB_LABEL[wb.status] || wb.status}${otherStale("workbench") ? "｜另路断流" : ""}` };
  }
  // ③ 静默态：跟当前页签
  const act = fresh(activeTab.value) ? last.value[activeTab.value] : (sim || wb);
  const staleNote = (s) => (otherStale(s) ? "｜另路断流" : "");
  if (act && act.surface === "workbench") {
    return { cls: "mut", text: `工作台 · ${WB_LABEL[act.status] || act.status}${staleNote("workbench")}` };
  }
  if (act && act.status === "finished") {
    return { cls: "mut", text: `${simWho(act)} · 最近完成${staleNote("sim")}` };
  }
  // 兜底空闲态也要披露单路断流（R2 复审 P2：收起态页签不可见，这里不标就全隐身）
  const anyStale = staleSeen("sim") || staleSeen("workbench");
  return { cls: "mut", text: `监控 · 空闲${anyStale ? "｜另路断流" : ""}` };
});

let timer = null;
onMounted(() => {
  window.addEventListener("message", onMessage);
  // 页面隐藏时跳过 tick，避免后台空跑（nowTick 仅驱动相对时间显示，恢复后下一拍即刷新）
  timer = window.setInterval(() => { if (document.hidden) return; nowTick.value = Date.now(); }, 2000);
  maybeAdoptParam();
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
.sim-tab.stale { opacity: 0.55; }
.sim-tab-dot {
  position: absolute;
  top: 1px;
  right: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--trust-fail);
}
.sim-conn-lost { font-size: 11px; font-weight: 600; color: var(--trust-fail); white-space: nowrap; }
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
/* iframe 底色跟随宿主主题（批D修正：hub embed.html 早已随 frameSrc 的 ?theme=dark
 * 透传自带暗色纸阶#24201c，钉死亮色纸色反而在暗色下先闪浅底再切成 hub 自身暗底——
 * 换 token 使容器底色与即将加载的 hub 内容一致，才是真正消闪白/黑）*/
.sim-frame { flex: 1; border: none; width: 100%; background: var(--paper-rail); }
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
