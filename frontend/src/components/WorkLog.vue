<template>
  <div class="worklog">
    <div class="worklog-head" @click="toggleExpanded">
      <div class="worklog-head-left">
        <span v-if="isWorking" class="work-pulse-dot"></span>
        <span class="worklog-head-text">{{ headText }}</span>
      </div>
      <span class="worklog-arrow" :class="{ 'is-open': expanded }">▸</span>
    </div>

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
    </div>

    <!-- 原始事件 token 行：e2e 保命线（task_created/tool_started/tool_finished/
         task_completed/review_approved 等英文 token 逐字可见），折叠态也常显，绝不 v-if 隐藏。 -->
    <div v-if="rawLine" class="worklog-rawline">{{ rawLine }}</div>

    <div v-if="expanded" class="worklog-timeline">
      <EmptyState v-if="!events.length" variant="log" description="暂无事件" />
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
import { listToolRuns } from "../api/tasks";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
  events: { type: Array, default: () => [] },
  task: { type: Object, default: null },
});

// 仅有的两个本地状态：展开开关 + 懒加载的工具运行明细（用于 mock 徽标）。
const expanded = ref(false);
const toolRuns = ref([]);
let toolRunsRequested = false;

async function toggleExpanded() {
  expanded.value = !expanded.value;
  if (expanded.value && !toolRunsRequested) {
    toolRunsRequested = true;
    try {
      toolRuns.value = await listToolRuns(props.task.id);
    } catch {
      // 诚实降级：懒加载失败只是不显示 mock 徽标，绝不报错阻塞展开内容。
      // 复位请求标记：否则一次网络抖动后 mock 徽标永久丢失（把"未知"呈现成"非 mock"）。
      toolRunsRequested = false;
      toolRuns.value = [];
    }
  }
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
});

const elapsedMs = computed(() => taskElapsedMs(props.task, nowTick.value));

const headText = computed(() => {
  if (isWorking.value) {
    // started_at 缺失（如 validating 早期）时不硬凑"已 —"，退化为纯进行态文案。
    return elapsedMs.value === null ? "正在处理…" : `正在处理 · 已 ${formatDuration(elapsedMs.value)}`;
  }
  if (elapsedMs.value === null) {
    return "尚未开始";
  }
  return `已处理 ${formatDuration(elapsedMs.value)} · ${(props.events || []).length} 条事件`;
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

// tool_runs 数据源只认 tool_id → mock 是否为 true，绝不从 agent_log payload 猜。
const toolRunsByToolId = computed(() => {
  const map = new Map();
  for (const r of toolRuns.value || []) {
    const bucket = map.get(r.tool_id) || [];
    bucket.push(r);
    map.set(r.tool_id, bucket);
  }
  return map;
});
function toolHasMock(toolId) {
  const runs = toolRunsByToolId.value.get(toolId);
  return Array.isArray(runs) && runs.some((r) => r.mock === true);
}

const TOOL_EVENT_TYPES = new Set(["tool_started", "tool_finished", "tool_failed"]);

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

// 原始事件 token 行：按首次出现顺序去重，附计数；e2e 直接在 innerText 里找
// 这些英文 token，折叠态也必须可见（不得 v-if="expanded" 隐藏）。
const rawLine = computed(() => {
  const order = [];
  const counts = new Map();
  for (const e of props.events || []) {
    if (!counts.has(e.event_type)) order.push(e.event_type);
    counts.set(e.event_type, (counts.get(e.event_type) || 0) + 1);
  }
  return order.map((t) => `${t} ×${counts.get(t)}`).join(" · ");
});
</script>

<style scoped>
.worklog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  padding: 10px 14px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
}
.worklog-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.worklog-head-text {
  font-size: 13.5px;
  font-weight: 600;
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
.worklog-rawline {
  margin-top: 6px;
  font-family: var(--mono, monospace);
  font-size: 10.5px;
  color: var(--ink-faint);
  word-break: break-all;
  padding-left: 2px;
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
