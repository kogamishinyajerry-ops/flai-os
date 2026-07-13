<template>
  <!-- 首载骨架（批A A3）：暖白 shimmer;只在「从未 loaded」时由宿主 v-if 挂载,
       轮询期间绝不回骨架（防闪烁）;失败态走宿主既有 error/EmptyState,骨架不吞错误。 -->
  <div class="skel" :style="{ height, width }" aria-hidden="true"></div>
</template>
<script setup>
defineProps({ height: { type: String, default: "16px" }, width: { type: String, default: "100%" } });
</script>
<style scoped>
.skel {
  border-radius: 6px;
  background: linear-gradient(90deg, rgba(var(--ink-rgb), 0.06) 25%, rgba(var(--ink-rgb), 0.12) 37%, rgba(var(--ink-rgb), 0.06) 63%);
  background-size: 400% 100%;
  animation: skel-shimmer 1.4s ease infinite;
}
@keyframes skel-shimmer { 0% { background-position: 100% 0; } 100% { background-position: 0 0; } }
@media (prefers-reduced-motion: reduce) { .skel { animation: none; background: rgba(var(--ink-rgb), 0.08); } }
</style>
