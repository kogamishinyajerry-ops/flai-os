<template>
  <span
    class="flai-bloom"
    :class="{ 'is-slow': state === 'slow', 'is-fast': state === 'fast' }"
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
    // 动态涡轮三档（票 #65 定稿 Q2）：idle 静止 / slow 慢速 / fast 高速。
    // 单档 generating 已随三档扩展退役，调用点全部映射到新词汇。
    validator: (value) => value === "idle" || value === "slow" || value === "fast",
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

/* 动态涡轮三档（票 #65 定稿 Q1=甲/Q2/Q6）：形态零变化，只做整枚图标围绕自身
   中心的匀速旋转；没有墨滴、晕染、散点或形变。档位=CSS animation-duration 直切
   （无 WAAPI ramp，换档瞬间相位跳变已裁准）；慢速 8s/圈、高速 1.4s/圈，
   静止档无类无动画=零残动（诚实地板：信号消失必须回落到这一档）。 */
.flai-bloom.is-slow img {
  transform-origin: 50% 50%;
  animation: flai-bloom-spin 8s linear infinite;
  will-change: transform;
}

.flai-bloom.is-fast img {
  transform-origin: 50% 50%;
  animation: flai-bloom-spin 1.4s linear infinite;
  will-change: transform;
}

@keyframes flai-bloom-spin {
  to { transform: rotate(360deg); }
}

/* reduced-motion=静态（MOTION-SYSTEM 硬约束④）：照 PR #64 设计稿互审 F2 先例
   双通道硬停——animation 与 transform 均 !important 归零，任何档位不得漏网。 */
@media (prefers-reduced-motion: reduce) {
  .flai-bloom.is-slow img,
  .flai-bloom.is-fast img {
    animation: none !important;
    transform: none !important;
    will-change: auto;
  }
}
</style>
