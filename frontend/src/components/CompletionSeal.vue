<template>
  <!-- 终态盖章（Codex CLI「─ Worked for Xs ─」哲学）：任务落定后的一行官宣，
       全宽横线+等宽小字=TUI 血统的「工作结束」仪式感。信任色锁：completed
       永远中性（不给绿），failed 红只染状态词本身（时长保持中性），cancelled
       淡墨。时长凑不出（缺时间戳/解析失败）=只盖状态不编时长——诚实地板。
       animate（批A Task 9）：仪式只属于亲历者——本次会话内观察到活跃→终态
       迁移才由父级传 true 播放合拢+浮现；历史页面直开 animate 恒 false，
       走原静态渲染，零回归。 -->
  <div v-if="statusWord" ref="rootEl" class="completion-seal" :class="{ 'seal-animate': animate }">
    <span class="seal-line seal-line-left"></span>
    <span class="seal-text" :class="{ 'fx-ink-in': animate }" :style="animate ? { animationDelay: '0.3s' } : null">
      <span :class="{ 'seal-word-failed': isFailed }">{{ statusWord }}</span><template v-if="tail"> · {{ tail }}</template>
    </span>
    <span class="seal-line seal-line-right"></span>
  </div>
</template>

<script setup>
// 时长口径 SSOT=utils/format 的 taskElapsedMs+formatDuration（与 WorkLog 同源
// 同取整）——绝不自建第二套 formatter，避免同屏「1h 0m」vs「59 分 59 秒」互相打脸。
import { ref, computed, watch, onMounted } from "vue";
import { formatDuration, taskElapsedMs } from "../utils/format";
import { burstNeutral } from "../effects/burst";

const props = defineProps({ task: Object, animate: { type: Boolean, default: false } });

const rootEl = ref(null);
const isFailed = computed(() => props.task?.status === "failed");

const duration = computed(() => {
  const t = props.task;
  if (!t?.finished_at) return null; // 盖章只认已落定区间，绝不用「现在」兜底
  const ms = taskElapsedMs(t);
  if (ms == null) return null;
  const text = formatDuration(ms);
  return text === "—" ? null : text;
});

const statusWord = computed(() => {
  const status = props.task?.status;
  if (status === "completed") return "已完成";
  if (status === "failed") return "执行失败";
  if (status === "cancelled") return "已取消";
  return null; // 非终态不盖章——盖章是落定的仪式，不预支
});

const tail = computed(() => {
  const status = props.task?.status;
  if (!duration.value) return null;
  if (status === "completed") return `工作 ${duration.value}`;
  if (status === "failed") return `进行了 ${duration.value}`;
  return null; // cancelled 不报时长：中断时刻的耗时没有工作量语义
});

// 中性尘埃迸发（动效系统 v1 E2 burstNeutral）：仅 completed 且父级判定「亲历
// 迁移」时播放一次；failed/cancelled 零迸发零彩色（信任色锁——盖章本身已把
// 情绪限定在状态词，动效不得越权加戏）。组合条件 watch（Task 12 修复 7）：
// animate 与 task.status 常在同一 tick 内一起到账（channel 落地整包替换
// task），若只 watch animate 单源，animate 已 true 但 status 尚未翻到
// completed 的窗口会被单发 watch 漏判、之后 status 单独变化不会被本 watch
// 感知——双源 watch + bursted 标记显式保证「整个组件生命周期只咬一次」，
// 语义比原先的「watch 非 immediate 天然只咬一下」更明确、不依赖隐式假设。
// flush: post 确保 DOM（rootEl）先落定再取动效目标元素。
let bursted = false;
function maybeBurst(a, s) {
  if (a === true && s === "completed" && !bursted) {
    bursted = true;
    burstNeutral(rootEl.value); // el 缺失/降级 burstNeutral 自兜 no-op
  }
}
watch(
  [() => props.animate, () => props.task?.status],
  ([a, s]) => maybeBurst(a, s),
  { flush: "post" },
);
// 挂载即已满足的场景（Codex R2-P3 verbatim）：tasks channel 在本组件挂载前
// 就发出亲历迁移（TaskDetail 首拉未落地时父级已置 animate=true），组件带着
// animate=true + completed 初次挂载，非 immediate watch 永不触发——onMounted
// 补判一次，此时 rootEl 已可用；bursted 标记保证与 watch 路径互斥只咬一次。
onMounted(() => maybeBurst(props.animate, props.task?.status));
</script>

<style scoped>
.completion-seal {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}
.seal-line {
  flex: 1 1 auto;
  height: 1px;
  background: var(--hairline);
}
.seal-text {
  flex: none;
  font-family: var(--mono, "SF Mono", ui-monospace, monospace);
  font-size: 11.5px;
  color: var(--ink-faint);
  letter-spacing: 0.3px;
}
/* 真失败红只染状态词（信任色锁）；时长与横线保持中性不放大情绪 */
.seal-word-failed {
  color: var(--trust-fail);
}

/* 盖章仪式（批A Task 9）：两根横线各自从外端向中间合拢（transform-origin
   相向），状态词延迟约 .3s 等横线拉出后再用全局 fx-ink-in 浮现。仅 animate
   时生效，静态渲染（历史直开）零动画、零回归。 */
.seal-animate .seal-line-left {
  transform-origin: right;
  animation: seal-line-in var(--motion-slow) var(--ease-out-soft) both;
}
.seal-animate .seal-line-right {
  transform-origin: left;
  animation: seal-line-in var(--motion-slow) var(--ease-out-soft) both;
}
@keyframes seal-line-in {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}
/* App.vue 全局 reduced-motion 块只覆盖 .fx-ink-in（状态词浮现已被那边接管）；
   本组件新引入的横线合拢动画是局部产物，需自带降级，不能指望全局块覆盖到。 */
@media (prefers-reduced-motion: reduce) {
  .seal-animate .seal-line-left,
  .seal-animate .seal-line-right {
    animation: none;
  }
}
</style>
