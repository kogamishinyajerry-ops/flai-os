<template>
  <div
    v-if="notice"
    class="connection-truth"
    :class="[`is-${notice.kind}`, { 'is-compact': compact }]"
    :role="notice.kind === 'cold' ? 'alert' : 'status'"
    aria-live="polite"
  >
    <div class="connection-copy">
      <strong>{{ notice.title }}</strong>
      <span>{{ notice.detail }}</span>
      <span v-if="lastSuccessText" class="connection-meta">最后成功同步于 {{ lastSuccessText }}</span>
      <span v-if="notice.error" class="connection-meta">原因：{{ notice.error }}</span>
    </div>
    <button v-if="retryable" type="button" class="connection-retry" @click="$emit('retry')">
      重新同步
    </button>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { describeLiveConnection } from "../stores/liveSnapshotCore";

const props = defineProps({
  loaded: { type: Boolean, default: false },
  connection: { type: String, default: "idle" },
  lastSuccessAt: { type: Number, default: null },
  stale: { type: Boolean, default: true },
  resyncing: { type: Boolean, default: false },
  error: { type: String, default: "" },
  compact: { type: Boolean, default: false },
  retryable: { type: Boolean, default: true },
});

defineEmits(["retry"]);

const notice = computed(() => describeLiveConnection({
  loaded: props.loaded,
  connection: props.connection,
  lastSuccessAt: props.lastSuccessAt,
  stale: props.stale,
  resyncing: props.resyncing,
  error: props.error,
}));

const lastSuccessText = computed(() => {
  if (!notice.value?.lastSuccessAt) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(notice.value.lastSuccessAt));
});
</script>

<style scoped>
.connection-truth {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid rgba(var(--trust-pending-rgb), 0.45);
  border-left: 3px solid var(--trust-pending);
  border-radius: var(--radius-md, 10px);
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--ink);
}
.connection-copy {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px var(--space-2);
  font-size: 12.5px;
  line-height: 1.5;
}
.connection-copy strong {
  font-size: 13px;
  font-weight: 700;
}
.connection-copy > span:not(.connection-meta) {
  color: var(--ink-soft);
}
.connection-meta {
  color: var(--ink-faint);
  font-size: 11.5px;
  overflow-wrap: anywhere;
}
.connection-retry {
  flex: 0 0 auto;
  min-height: 32px;
  padding: 5px 10px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm, 8px);
  background: var(--paper-surface);
  color: var(--ink);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.connection-retry:hover {
  background: var(--hover-tint);
}
.is-compact {
  margin-bottom: var(--space-2);
  padding: var(--space-2) var(--space-3);
}
@media (max-width: 520px) {
  .connection-truth {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (prefers-reduced-motion: reduce) {
  .connection-truth,
  .connection-retry {
    transition: none;
  }
}
</style>
