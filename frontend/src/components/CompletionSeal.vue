<template>
  <!-- 终态盖章（Codex CLI「─ Worked for Xs ─」哲学）：任务落定后的一行官宣，
       全宽横线+等宽小字=TUI 血统的「工作结束」仪式感。信任色锁：completed
       永远中性（不给绿），failed 红只染状态词本身（时长保持中性），cancelled
       淡墨。时长凑不出（缺时间戳/解析失败）=只盖状态不编时长——诚实地板。 -->
  <div v-if="statusWord" class="completion-seal">
    <span class="seal-line"></span>
    <span class="seal-text">
      <span :class="{ 'seal-word-failed': isFailed }">{{ statusWord }}</span><template v-if="tail"> · {{ tail }}</template>
    </span>
    <span class="seal-line"></span>
  </div>
</template>

<script setup>
// 时长口径 SSOT=utils/format 的 taskElapsedMs+formatDuration（与 WorkLog 同源
// 同取整）——绝不自建第二套 formatter，避免同屏「1h 0m」vs「59 分 59 秒」互相打脸。
import { computed } from "vue";
import { formatDuration, taskElapsedMs } from "../utils/format";

const props = defineProps({ task: Object });

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
</style>
