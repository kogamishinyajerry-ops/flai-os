<template>
  <!-- 思考墨滴（动效系统 A2）：仅在请求真实在途时由调用方渲染（诚实地板——
       动画=真的在等模型回复）。装饰元素：aria-hidden + 不可交互。 -->
  <span class="think-ink" aria-hidden="true">
    <svg class="ink-mark" viewBox="0 0 40 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- 两圈略不对称的线，像墨水沿纸纤维先后洇开。 -->
      <path
        class="ink-ripple ink-ripple--far"
        d="M10.5 13.3C12.8 10.4 27.1 10.2 29.8 13.1 27.6 16.1 13.2 16.3 10.5 13.3Z"
      />
      <path
        class="ink-ripple ink-ripple--near"
        d="M14.2 13.3C15.7 11.3 24.9 11.1 26.4 13.1 24.8 15.1 15.9 15.3 14.2 13.3Z"
      />

      <path
        class="ink-puddle"
        d="M16.9 13.1C18.2 11.8 22.8 11.6 24.7 12.9 24 14.4 18.1 14.5 16.9 13.1Z"
      />

      <!-- 落纸瞬间飞出的两粒细墨星，让小尺寸仍有液体质感。 -->
      <circle class="ink-speck ink-speck--left" cx="17.5" cy="12.3" r="0.75" />
      <path class="ink-speck ink-speck--right" d="M24.8 11.8c.7-.35 1.25.15.92.78-.34.62-1.3.1-.92-.78Z" />

      <g class="falling-drop">
        <path
          class="drop-body"
          d="M20.2 1.2C19.1 2.9 18.2 4 18.2 5.4c0 1.65 1.05 2.75 2.6 2.75 1.5 0 2.55-1.07 2.55-2.6 0-1.4-1.02-2.65-2.15-4.35-.24-.36-.76-.35-1 .01Z"
        />
        <path class="drop-sheen" d="M19.6 4.1c-.45.75-.48 1.45-.08 1.92" />
      </g>
    </svg>
  </span>
</template>

<script setup>
// 无 props：出现即表示「在等」，语义由调用方的 v-if 保证。
</script>

<style scoped>
.think-ink {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 18px;
  max-height: 18px;
  line-height: 0;
  vertical-align: -4px;
  flex: none;
  pointer-events: none;
}

.ink-mark {
  display: block;
  width: 40px;
  height: 18px;
  overflow: hidden;
}

.falling-drop {
  transform-box: view-box;
  transform-origin: 20.8px 7px;
  animation: ink-drop-fall 2.7s var(--ease-out-soft) infinite;
}

.drop-body {
  fill: var(--ink-soft);
}

.drop-sheen {
  fill: none;
  stroke: var(--hairline);
  stroke-width: 0.65;
  stroke-linecap: round;
}

.ink-puddle {
  fill: var(--ink-soft);
  transform-box: view-box;
  transform-origin: 20.8px 13px;
  animation: ink-puddle-settle 2.7s var(--ease-out-soft) infinite;
}

.ink-ripple {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  transform-box: view-box;
  transform-origin: 20.3px 13.3px;
}

.ink-ripple--near {
  stroke: var(--ink-faint);
  stroke-width: 0.75;
  animation: ink-ripple-near 2.7s var(--ease-out-soft) infinite;
}

.ink-ripple--far {
  stroke: var(--hairline);
  stroke-width: 0.9;
  animation: ink-ripple-far 2.7s var(--ease-out-soft) infinite;
}

.ink-speck {
  fill: var(--ink-faint);
  transform-box: view-box;
}

.ink-speck--left {
  transform-origin: 17.5px 12.3px;
  animation: ink-speck-left 2.7s ease-out infinite;
}

.ink-speck--right {
  transform-origin: 25.2px 12.2px;
  animation: ink-speck-right 2.7s ease-out infinite;
}

@keyframes ink-drop-fall {
  0%, 9% { opacity: 0; transform: translateY(-4px) scale(0.68); }
  16% { opacity: 0.76; }
  42% { opacity: 0.9; transform: translateY(3.2px) scale(0.92); }
  49% { opacity: 0.72; transform: translateY(4.7px) scale(1.12, 0.56); }
  55%, 100% { opacity: 0; transform: translateY(5px) scale(1.24, 0.42); }
}

@keyframes ink-puddle-settle {
  0%, 43% { opacity: 0; transform: scale(0.24); }
  50% { opacity: 0.68; transform: scale(0.48, 0.28); }
  63% { opacity: 0.66; transform: scale(1, 0.68); }
  83% { opacity: 0.38; transform: scale(0.82, 0.58); }
  100% { opacity: 0; transform: scale(0.52, 0.46); }
}

@keyframes ink-ripple-near {
  0%, 46% { opacity: 0; transform: scale(0.25); }
  53% { opacity: 0.56; transform: scale(0.38); }
  77% { opacity: 0.2; transform: scale(1.04); }
  91%, 100% { opacity: 0; transform: scale(1.24); }
}

@keyframes ink-ripple-far {
  0%, 57% { opacity: 0; transform: scale(0.28); }
  64% { opacity: 0.42; transform: scale(0.42); }
  88% { opacity: 0.12; transform: scale(1.03); }
  100% { opacity: 0; transform: scale(1.16); }
}

@keyframes ink-speck-left {
  0%, 45% { opacity: 0; transform: translate(0, 0) scale(0.4); }
  51% { opacity: 0.65; }
  70% { opacity: 0; transform: translate(-3px, -2px) scale(0.62); }
  100% { opacity: 0; }
}

@keyframes ink-speck-right {
  0%, 46% { opacity: 0; transform: translate(0, 0) scale(0.4); }
  52% { opacity: 0.58; }
  72% { opacity: 0; transform: translate(3px, -1.7px) scale(0.58); }
  100% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .falling-drop,
  .ink-puddle,
  .ink-ripple,
  .ink-speck {
    animation: none;
  }

  .falling-drop {
    opacity: 0.72;
    transform: translateY(3px) scale(0.78);
  }

  .ink-puddle {
    opacity: 0.42;
    transform: scale(0.85, 0.6);
  }

  .ink-ripple--near {
    opacity: 0.34;
    transform: scale(0.76);
  }

  .ink-ripple--far {
    opacity: 0.14;
    transform: scale(0.94);
  }

  .ink-speck--left {
    opacity: 0.24;
    transform: translate(-1px, -0.5px) scale(0.65);
  }

  .ink-speck--right {
    opacity: 0.2;
    transform: translate(1px, -0.5px) scale(0.62);
  }
}
</style>
