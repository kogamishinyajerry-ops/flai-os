<template>
  <!-- 清空的收件盘：漫画墨线与暖白纸面延续既有空态插画；盘中只留一枚
       归位的工程图章，叙事是「都签完了」。完全静止，清空即安宁。 -->
  <svg
    class="inbox-zero"
    viewBox="0 0 160 100"
    fill="none"
    aria-hidden="true"
    focusable="false"
    xmlns="http://www.w3.org/2000/svg"
  >
    <g stroke-linecap="round" stroke-linejoin="round">
      <!-- 极淡桌面投影把小场景落稳，不制造悬浮感。 -->
      <path class="desk-line" d="M17 88.5C47 87.3 112 87.5 143 89" />
      <path class="tray-shadow" d="M25 80.5C51 77.4 112 77.2 137 81.2 127 87.6 43 89 25 80.5Z" />

      <!-- 手绘错位复线：与既有 PNG / DraftingScene 的漫画墨线同源。 -->
      <path class="tray-echo" d="M22.5 49.5 41 27.5 121.5 28 140.5 49.5 137.5 79.5 99 80.5 93.5 87 66.5 86.5 61 80 23 78.8" />

      <!-- 收件盘外壳、内膛与四面折壁。大面积空膛是构图主角。 -->
      <path class="tray-shell" d="M19.5 47.5 39 25.5Q40 24.5 42 24.8L119.5 25.4Q121 25.4 122 26.6L140.5 47.8 137 78.7Q136.8 80.2 135.2 80.3L99 81 93 87H67L61 80 24 79.5Q22.5 79.5 22.3 78Z" />
      <path class="tray-floor" d="M28 49.8 44 33.3 116.8 33.8 132.2 50.3 127.2 66.8 98.3 67.2 92.2 74.5 68.7 74.3 62.5 67 33.2 66.5Z" />

      <path class="tray-wall" d="M39 25.5 42 24.8 119.5 25.4 116.8 33.8 44 33.3Z" />
      <path class="tray-wall" d="M19.5 47.5 39 25.5 44 33.3 28 49.8Z" />
      <path class="tray-wall" d="M119.5 25.4 140.5 47.8 132.2 50.3 116.8 33.8Z" />

      <!-- 前挡板开口把「已清空」讲清楚，也留出熟悉的收件盘剪影。 -->
      <path class="tray-front" d="M22.3 64.8 62.5 67 68.7 74.3 92.2 74.5 98.3 67.2 138.7 64.5 137 78.7Q136.8 80.2 135.2 80.3L99 81 93 87H67L61 80 24 79.5Q22.5 79.5 22.3 78Z" />
      <path class="tray-seam" d="M28.5 52.5 33.2 66.5M131.7 52.8 127.2 66.8M27 75.6 58.8 76.2M101 76.4 133.2 75.7" />
      <path class="tray-stitch" d="M37 29.2 41 30.3M122.8 30.1 126 33.4M30 70.8l4 .2M126.5 71l4-.3" />

      <!-- 唯一留下的物件：完成签发后端正搁回盘内的工程图章。 -->
      <g class="signoff-stamp" transform="rotate(-4 102 52)">
        <path class="stamp-echo" d="M87 59.5Q87.2 56.8 90 56.4L113.5 56.5Q116 56.8 116.5 59.3L117 63.2 87.5 64Z" />
        <path class="stamp-body" d="M88.5 56.6Q89 54.4 91.2 54.2H112.5Q114.8 54.3 115.3 56.6L116 61.7Q116.2 63 114.6 63.1L89.2 63.5Q87.8 63.5 88 62Z" />
        <path class="stamp-body" d="M96 54.2Q96.5 50.4 99.3 48.5L99.8 44.7Q96.4 43.5 96.8 40.5 97.4 36.1 102.2 35.6 107 35.2 108.2 39.3 109.1 42.4 105.8 44.3L106.7 48.2Q109.8 50 110.5 54.2Z" />
        <path class="stamp-detail" d="M99.8 44.7Q102.8 45.7 105.8 44.3M99.3 48.5Q103 49.7 106.7 48.2M91.2 58.1Q101.8 59 113 57.8" />
        <path class="stamp-check" d="m100 40.7 1.7 1.5 3.1-3.2" />
        <path class="stamp-clay" d="M108.5 60.1 114.6 59.5 115 62 108.8 62.4Z" />
      </g>

      <!-- 两笔很浅的清扫痕，强调盘底空净而非“尚未加载”。 -->
      <path class="settled-mark" d="M48 48.5q5.2-2.2 10.4.4M50.5 52q4.1-1.3 8.2.5" />
    </g>
  </svg>
</template>

<style scoped>
.inbox-zero {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  pointer-events: none;
}

.desk-line {
  stroke: var(--hairline);
  stroke-width: 0.8;
  opacity: 0.72;
}

.tray-shadow {
  fill: var(--hairline);
  opacity: 0.3;
}

.tray-echo {
  stroke: var(--hairline);
  stroke-width: 2.5;
  opacity: 0.86;
}

.tray-shell {
  fill: var(--hairline);
  fill-opacity: 0.14;
  stroke: var(--ink-soft);
  stroke-width: 1.25;
}

.tray-floor {
  fill: var(--hairline);
  fill-opacity: 0.08;
  stroke: var(--ink-faint);
  stroke-width: 0.85;
}

.tray-wall,
.tray-front {
  fill: var(--hairline);
  fill-opacity: 0.46;
  stroke: var(--ink-soft);
  stroke-width: 1.05;
}

.tray-front {
  fill-opacity: 0.55;
}

.tray-seam,
.tray-stitch,
.settled-mark {
  stroke: var(--ink-faint);
  stroke-width: 0.72;
  opacity: 0.78;
}

.tray-stitch {
  stroke-width: 0.62;
  opacity: 0.62;
}

.settled-mark {
  stroke-width: 0.68;
  opacity: 0.55;
}

.stamp-echo {
  stroke: var(--hairline);
  stroke-width: 2.2;
}

.stamp-body {
  fill: var(--hairline);
  fill-opacity: 0.62;
  stroke: var(--ink-soft);
  stroke-width: 1;
}

.stamp-detail,
.stamp-check {
  stroke: var(--ink-faint);
  stroke-width: 0.68;
}

.stamp-check {
  stroke-width: 0.8;
}

.stamp-clay {
  fill: #c15f3c;
}
</style>
