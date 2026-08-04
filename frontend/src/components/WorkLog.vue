<template>
  <div class="worklog">
    <!-- 真 button（批次五 C6，native-first）：旧裸 div 不可键盘聚焦/激活、不向
         AT 暴露展开态——与仓内 artifact-toggle 真 button 范式对齐；Enter/Space
         原生免费，aria-expanded 携真实状态。类名与四边框逐值覆盖保留（craft
         有 border 断言面）。 -->
    <button type="button" class="worklog-head" :aria-expanded="expanded ? 'true' : 'false'" @click="toggleExpanded">
      <span class="worklog-head-left">
        <span v-if="isWorking" class="work-pulse-dot"></span>
        <span class="worklog-head-text">{{ headText }}</span>
      </span>
      <span class="worklog-arrow" :class="{ 'is-open': expanded }">▸</span>
    </button>

    <!-- 授权链口播：approved=teal / rejected=红，绝不用绿。措辞与谓词
         SSOT=utils/format deriveSignoff+signoffText（与 VerificationCard 真同源，
         3-lens paradigm P3 收口——此前「依据/已由」两处漂移）。redacted 态
         （3-lens trust P1）：签发事件在场但 payload 被分级门遮蔽→中性「不可用」，
         绝不呈现成「没签过」。 -->
    <div
      v-if="signoff && signoff.redacted"
      class="worklog-signoff"
      :style="{ color: 'var(--ink-faint)' }"
    >
      签发记录不可用（内容受限）
    </div>
    <!-- unknown（Codex R0-P2）：无遮蔽标记的缺字段=「不完整」，不编「受限」。 -->
    <div
      v-else-if="signoff && signoff.unknown"
      class="worklog-signoff"
      :style="{ color: 'var(--ink-faint)' }"
    >
      签发记录不完整
    </div>
    <div
      v-else-if="signoff"
      class="worklog-signoff"
      :style="{ color: signoff.approved ? 'var(--trust-signed)' : 'var(--trust-fail)' }"
      :title="signoff.comment || undefined"
    >
      {{ signoffText(signoff) }}
    </div>

    <!-- 过去式摘要：终态/审核事件优先，否则退化为最后一条事件消息。 -->
    <div v-if="summaryText" class="worklog-summary">{{ summaryText }}</div>

    <!-- 工具聚合行（W13 实机证伪修正）：Codex 真实语言=灰色纯文字聚合行，
         非徽章 chip——聚合逻辑不变，只降视觉噪音；mock 徽是诚实标注（amber
         信任语言）保留贴在对应工具旁。折叠态也常显。 -->
    <div v-if="chips.length" class="worklog-toolline">
      <span v-for="(c, i) in chips" :key="c.key" class="worklog-tool">
        <span v-if="i > 0" class="worklog-tool-sep" aria-hidden="true">·</span>
        <!-- 两级语义权重（W16 语法）：动词安静、仅对象名（工具 id）加重——
             DOM 拆 span 但 innerText 逐字不变（e2e 文本断言面零扰动）。 -->
        <template v-if="c.object">{{ c.label }} <span class="worklog-tool-object">{{ c.object }}</span></template>
        <template v-else>{{ c.label }}</template><template v-if="c.count > 1"> ×{{ c.count }}</template>
        <span v-if="c.mock" class="pill-amber">mock</span>
      </span>
      <!-- 真实性未核（Codex R0 P1 + R1-P1 + R2-P2 措辞不猜原因）：投影未就绪
           或逐工具对账缺行（记录未就绪/未执行/内容受限）时，工具行的 mock
           标注不可作数——未知如实亮 amber，绝不静默装「非 mock」。 -->
      <span
        v-if="toolAuthenticityUnknown"
        class="pill-amber worklog-authenticity-unverified"
        title="工具真实性尚无法逐项对账（记录未就绪、未执行或内容受限）：此行 mock 标注不可作数"
      >真实性未核</span>
    </div>

    <!-- 原始事件 token（批次四 Q5，「process 藏折叠里」）：英文 token 只活在
         展开态时间轴的逐条 .event-type-raw 里（m2 断言同批改走展开路径）——
         折叠态是给新人的扫读面，只留人话头行/工具聚合行/签发口播。 -->
    <div v-if="expanded" class="worklog-timeline">
      <!-- 纯数据空态=line 轻量态（W2）：事件流为空不庆祝不引导，一行安静文字；
           variant="log" 语义分类保留（line 态不选图）。文案逐字不动。 -->
      <EmptyState v-if="!events.length" variant="log" tier="line" description="暂无事件" />
      <el-timeline v-else>
        <!-- 墨迹入场只在真实工作态生效：工作中轮询追加的新事件晕开入场；已终态
             任务展开日志时不重播「新事件」视觉（诚实地板——信任镜头 P2）。 -->
        <el-timeline-item
          v-for="e in events"
          :key="e.event_id"
          :timestamp="formatTime(e.created_at)"
          :color="markerColor(e)"
          :class="{ 'fx-ink-in': isWorking }"
        >
          <!-- 失败态语义着色（W16「失败只染动词 token」）：仅译文状态词着玫红，
               raw token/消息正文不动——着色预算精确到 token 粒度。 -->
          <div class="event-type" :class="{ 'is-failure': isFailureEvent(e) }">
            {{ eventTypeLabel(e.event_type) }}
            <span class="event-type-raw">{{ e.event_type }}</span>
          </div>
          <div class="event-message">{{ e.message }}</div>
          <el-collapse v-if="e.payload && Object.keys(e.payload).length">
            <el-collapse-item title="详细数据">
              <pre class="payload-json">{{ JSON.stringify(e.payload, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup>
// 折叠工作日志（Codex「已处理 13m54s ›」模式）。纯展示组件：全部派生数据用
// computed 从 props 算，组件内绝不复制/缓存 events——父页有「轮询整包作废」
// 竞态守卫，本组件必须无状态跟随，否则会显示已被父页判定为 stale 的快照。
import { ref, computed, watch, onUnmounted } from "vue";
import { TASK_WORK_STATES, formatDuration, taskElapsedMs, formatTime, LEVEL_COLOR, eventTypeLabel, deriveSignoff, signoffText } from "../utils/format";
import { getToolRunsSummary } from "../api/tasks";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
  events: { type: Array, default: () => [] },
  task: { type: Object, default: null },
});

// 本地状态：展开开关 + 工具真实性投影（mock 徽标唯一数据源）。
// 批次四 Q5 把折叠态升格为主扫读面（Codex R0 P1 + R1-P1/P2 收口）：
// - 数据面走 /tool_runs/summary 的 by_tool 有界投影（tool_id+计数纯元数据），
//   绝不为折叠态预载整条执行轨迹（input/output/raw_path 随 run 数无界增长）；
// - 拉取由工具**终结**事件计数驱动（run 行只在工具结束/失败时落库，started
//   时拉必空）；状态机 idle|loading|loaded|failed + seq 守卫防慢响应回写；
// - loaded ≠ 已核：还要逐工具对账（见 toolAuthenticityUnknown）。
const expanded = ref(false);
const toolAuthByTool = ref(new Map());
const toolRunsState = ref("idle");
let toolRunsSeq = 0;

async function loadToolAuthenticity() {
  if (!props.task?.id) return;
  const seq = ++toolRunsSeq;
  toolRunsState.value = "loading";
  try {
    const summary = await getToolRunsSummary(props.task.id);
    if (seq !== toolRunsSeq) return;
    const map = new Map();
    for (const entry of Array.isArray(summary?.by_tool) ? summary.by_tool : []) {
      map.set(entry.tool_id, entry);
    }
    toolAuthByTool.value = map;
    toolRunsState.value = "loaded";
  } catch {
    if (seq !== toolRunsSeq) return;
    // 诚实降级：失败=真实性未知（toolline 亮「真实性未核」），绝不静默装
    // 「非 mock」，也不报错阻塞正文；展开动作可触发一次重试。
    toolAuthByTool.value = new Map();
    toolRunsState.value = "failed";
  }
}

function toggleExpanded() {
  expanded.value = !expanded.value;
  if (expanded.value && toolRunsState.value === "failed") loadToolAuthenticity();
}

const isWorking = computed(() => TASK_WORK_STATES.has(props.task?.status));

// 活跳计时（批次二 F2，Codex R7 运行态语法）：「已处理 Xm Xs」逐秒递增、纯
// 离散文本替换（零动画——文本替换非运动，reduced-motion 无涉）。此前 elapsed
// 只随轮询整包更新，8s 间隔内数字冻结，「正在工作」的披露失真。ticker 只在
// 工作态存活：终态/卸载即清，绝不给已落定任务走表（诚实地板——taskElapsedMs
// 对有 finished_at 的任务本就忽略 nowMs，双保险）。
const nowTick = ref(Date.now());
let tickTimer = null;
watch(isWorking, (working) => {
  if (working && tickTimer === null) {
    tickTimer = setInterval(() => { nowTick.value = Date.now(); }, 1000);
  } else if (!working && tickTimer !== null) {
    clearInterval(tickTimer);
    tickTimer = null;
  }
}, { immediate: true });
onUnmounted(() => {
  if (tickTimer !== null) clearInterval(tickTimer);
  // 作废在飞的真实性投影请求（Codex R1-P2）：卸载后到达的响应不再回写。
  toolRunsSeq++;
});

const elapsedMs = computed(() => taskElapsedMs(props.task, nowTick.value));

const headText = computed(() => {
  // 三段式节奏（批次三 G2，cd-workflow-card 思考指示器三段式的诚实适配）：
  // 状态词 · 时间 · 计量——计量轴用真实事件计数（轮询到账即增），不编 token。
  // 零值豁口（cd-bg-tasks-panel「空值不显示 0」）：N=0 该段整段不出现，
  // 工作态/完成态同一规——绝不显示「0 条事件」。
  const n = (props.events || []).length;
  const eventsPart = n > 0 ? ` · ${n} 条事件` : "";
  // 批 0 切片 1（HANDOFF-K3 #4 owner 裁）：时长段零值豁口——<1s 时「已 X」
  // 整段不出现（0 不是信息），工作态/完成态同一规；≥1s 段自然长出，活跳不变。
  const durZero = elapsedMs.value !== null && elapsedMs.value < 1000;
  if (isWorking.value) {
    // started_at 缺失（如 validating 早期）时不硬凑"已 —"，退化为纯进行态文案。
    if (elapsedMs.value === null) return "正在处理…";
    const durPart = durZero ? "" : ` · 已 ${formatDuration(elapsedMs.value)}`;
    return `正在处理${durPart}${eventsPart}`;
  }
  if (elapsedMs.value === null) {
    return "尚未开始";
  }
  const durPart = durZero ? "" : ` ${formatDuration(elapsedMs.value)}`;
  return `已处理${durPart}${eventsPart}`;
});

// 授权链口播：SSOT=utils/format deriveSignoff（null/redacted/完整 三态），
// 与 VerificationCard 同一份谓词——绝不各自再造第二份。
const signoff = computed(() => deriveSignoff(props.events));

// 过去式摘要：终态/审核类事件优先，否则退化为最后一条事件消息；都没有则不渲染。
const TERMINAL_SUMMARY_TYPES = ["task_completed", "task_failed", "review_approved", "review_rejected", "task_cancelled"];
const summaryText = computed(() => {
  const list = props.events || [];
  if (!list.length) return "";
  for (let i = list.length - 1; i >= 0; i--) {
    if (TERMINAL_SUMMARY_TYPES.includes(list[i].event_type)) {
      return list[i].message || "";
    }
  }
  return list[list.length - 1].message || "";
});

// 真实性数据源只认 by_tool 投影的 tool_id → mock_count，绝不从 agent_log payload 猜。
function toolHasMock(toolId) {
  const entry = toolAuthByTool.value.get(toolId);
  return entry ? entry.mock_count > 0 : false;
}

const TOOL_EVENT_TYPES = new Set(["tool_started", "tool_finished", "tool_failed"]);

// 工具**终结**事件计数涨了才（重）拉投影（Codex R1-P2 刷新策略）：run 行只在
// 工具结束/失败时落库，tool_started 时拉必空是白费；工作态每个工具跑完
// mock 徽即跟上（旧懒加载一次性 latch，连展开态都不会刷新）。事件驱动、
// 无轮询；计数不变（父页轮询整包替换同长数组）不触发。
const toolTerminalCount = computed(
  () => (props.events || []).filter(
    (e) => e.event_type === "tool_finished" || e.event_type === "tool_failed"
  ).length
);
watch(toolTerminalCount, (n) => {
  if (n > 0) loadToolAuthenticity();
}, { immediate: true });

// 折叠常显的诚实闸（mock 如实标注，Codex R0 P1 + R1-P1 收口）：
// ① 有工具 chip 而投影未就绪（未拉/加载中/失败）→ 未核；
// ② loaded 也要逐工具对账：run 行只在工具终结后落库，「有 tool 事件、无
//    对应 by_tool 行」（运行中/未执行/无法归因）= 该工具真实性未知——
//    成功空表绝不当「已核非 mock」。amber=仅未核槽（信任色锁）。
const toolAuthenticityUnknown = computed(() => {
  const toolChips = chips.value.filter((c) => c.key.startsWith("tool:"));
  if (!toolChips.length) return false;
  if (toolRunsState.value !== "loaded") return true;
  return toolChips.some((c) => !toolAuthByTool.value.has(c.object));
});

// 失败类事件判定：真失败语义（trust-fail 红）只认失败 token 与 error level——
// 玫红只染译文状态词一处，不外溢整行（W16 着色预算）。取消（task_cancelled）
// 是中性动作非真失败，**先于 level 兜底显式豁免**：毒丸隔离（runner.py
// _quarantine_poison_candidate）会写 task_cancelled+level=error，若只靠枚举排除
// 会被 OR 兜底重新卷进红槽（信任色锁：红=仅真失败/驳回，3-lens trust P1）。
const FAILURE_EVENT_TYPES = new Set(["task_failed", "tool_failed", "review_rejected"]);
function isFailureEvent(e) {
  if (e.event_type === "task_cancelled") return false;
  return FAILURE_EVENT_TYPES.has(e.event_type) || e.level === "error";
}
// 时间轴节点色与文字着色同一谓词（Codex R1 P1）：豁免路径（task_cancelled+
// level=error 毒丸隔离）节点降中性蓝，绝不残留红点——红=仅真失败/驳回。
function markerColor(e) {
  if (isFailureEvent(e)) return LEVEL_COLOR[e.level] || LEVEL_COLOR.error;
  if (e.level === "error") return LEVEL_COLOR.info;
  return LEVEL_COLOR[e.level] || LEVEL_COLOR.info;
}

// 聚合 chips：相邻 tool_* 事件归工具组（组内再按 tool_id 分别计数），相邻
// agent_log 归一组；其余事件类型各自成组（不与相邻同类合并）。
const chips = computed(() => {
  const out = [];
  let group = null; // { type: 'tool' | 'agent_log', events: [] }

  const flush = () => {
    if (!group) return;
    if (group.type === "tool") {
      const byTool = new Map();
      for (const e of group.events) {
        const id = e.payload?.tool_id || "未知工具";
        const entry = byTool.get(id) || { started: 0, total: 0 };
        entry.total += 1;
        if (e.event_type === "tool_started") entry.started += 1;
        byTool.set(id, entry);
      }
      for (const [id, { started, total }] of byTool) {
        out.push({
          key: `tool:${out.length}:${id}`,
          // label=动词（安静）/ object=对象名（加重）分踢——模板拼接后
          // innerText 仍为「调用工具 <id>」逐字不变。
          label: "调用工具",
          object: id,
          count: started || total,
          mock: toolHasMock(id),
        });
      }
    } else if (group.type === "agent_log") {
      out.push({ key: `agentlog:${out.length}`, label: "Agent 日志", count: group.events.length, mock: false });
    }
    group = null;
  };

  for (const e of props.events || []) {
    if (TOOL_EVENT_TYPES.has(e.event_type)) {
      if (group && group.type === "tool") {
        group.events.push(e);
      } else {
        flush();
        group = { type: "tool", events: [e] };
      }
    } else if (e.event_type === "agent_log") {
      if (group && group.type === "agent_log") {
        group.events.push(e);
      } else {
        flush();
        group = { type: "agent_log", events: [e] };
      }
    } else {
      flush();
      out.push({ key: `single:${out.length}:${e.event_id}`, label: eventTypeLabel(e.event_type), count: 1, mock: false });
    }
  }
  flush();
  return out;
});

</script>

<style scoped>
/* 贴地形态（批次三 G1，cd-collapsed-blocks「折叠思考块=纯一行灰字，无背景
   无图标」+ cx worklog 上下发丝线三明治）：去盒化——背景透明、无边框盒/圆角，
   只留上下发丝线；折叠态默认只占一行安静灰字，hover 回墨保可点性 affordance。 */
.worklog-head {
  /* button 化重置（批次五 C6）：UA 默认 outset 边框/字体/内边距全部显式归零，
     四边框逐值与旧 div 形态一致（craft ①有 border 四边断言：上下 1px 左右 0）。 */
  appearance: none;
  width: 100%;
  font: inherit;
  color: inherit;
  text-align: left;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  padding: 9px 2px;
  border: 0;
  border-top: 1px solid var(--hairline-soft);
  border-bottom: 1px solid var(--hairline-soft);
  border-radius: 0;
  background: transparent;
}
.worklog-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.worklog-head-text {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ink-soft);
  transition: color var(--motion-fast) var(--ease-out-soft);
}
.worklog-head:hover .worklog-head-text {
  color: var(--ink);
}
.worklog-arrow {
  display: inline-block;
  color: var(--ink-faint);
  font-size: 12px;
  transition: transform var(--motion-fast) var(--ease-out-soft);
  flex: none;
}
.worklog-arrow.is-open {
  transform: rotate(90deg);
}
.worklog-signoff {
  font-size: 12.5px;
  font-weight: 600;
  margin-top: 8px;
  padding-left: 2px;
}
.worklog-summary {
  font-size: 12.5px;
  color: var(--ink-soft);
  margin-top: 8px;
  padding-left: 2px;
}
.worklog-toolline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 6px;
  row-gap: 2px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--ink-soft);
}
.worklog-tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
/* 两级语义权重：动词（调用工具）承袭行内安静灰，对象名（工具 id）mono 加重——
 * 「动词灰/仅对象名黑加粗」的 W16 语法。 */
.worklog-tool-object {
  font-family: var(--mono);
  font-weight: 600;
  color: var(--ink);
}
.worklog-tool-sep {
  color: var(--ink-faint);
}
.worklog-timeline {
  margin-top: 14px;
}
.event-type-raw {
  font-family: var(--mono, monospace);
  font-size: 11px;
  color: var(--ink-faint);
  margin-left: 8px;
  font-weight: 400;
}
.event-type {
  font-weight: 600;
  font-size: 13px;
}
/* 失败只染动词：译文状态词玫红一处，raw token 与消息正文保持原色。 */
.event-type.is-failure {
  color: var(--trust-fail);
}
.event-type.is-failure .event-type-raw {
  color: var(--ink-faint);
}
.event-message {
  color: var(--ink-soft);
  font-size: 13px;
  margin: 2px 0 4px;
}
.payload-json {
  background: var(--paper-rail);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
}
</style>
