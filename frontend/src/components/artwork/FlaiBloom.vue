<template>
  <span
    class="flai-bloom"
    :class="{ 'is-generating': state === 'generating' }"
    :style="{ '--flai-bloom-size': `${size}px` }"
    aria-hidden="true"
  >
    <img :src="flaiBloomUrl" alt="" draggable="false" />
  </span>
</template>

<script setup>
import flaiBloomUrl from "../../assets/flai-bloom.png";

defineProps({
  state: {
    type: String,
    default: "idle",
    validator: (value) => value === "idle" || value === "generating",
  },
  size: {
    type: Number,
    default: 24,
  },
});
</script>

<style scoped>
.flai-bloom {
  display: inline-flex;
  flex: 0 0 auto;
  width: var(--flai-bloom-size);
  height: var(--flai-bloom-size);
  line-height: 0;
}

.flai-bloom img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
}

/* 生成态只做整枚图标围绕自身中心的匀速旋转；没有墨滴、晕染、散点或形变。 */
.flai-bloom.is-generating img {
  transform-origin: 50% 50%;
  animation: flai-bloom-spin 3.6s linear infinite;
  will-change: transform;
}

@keyframes flai-bloom-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .flai-bloom.is-generating img {
    animation: none;
    transform: none;
    will-change: auto;
  }
}
</style>
