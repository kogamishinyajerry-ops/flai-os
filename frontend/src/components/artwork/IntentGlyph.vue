<template>
  <svg
    class="intent-glyph"
    viewBox="0 0 48 48"
    fill="none"
    :width="props.size"
    :height="props.size"
    aria-hidden="true"
    focusable="false"
    xmlns="http://www.w3.org/2000/svg"
  >
    <g class="glyph-ink" stroke-linecap="round" stroke-linejoin="round">
      <!-- 性能包线图纸：坐标轴承托一条有机包线，clay 点标出当前工况。 -->
      <g v-if="props.name === 'disk'">
        <path class="ink-echo" d="M8.8 7.6Q23.5 6.5 39.7 8.3L40.7 40.1Q24.3 41.2 7.5 39.7Z" />
        <path d="M7.2 6.3Q23.7 5.4 40.2 7.2L41 39Q24 40.1 6.7 38.7Z" />
        <path d="M13.2 33.9Q13.5 23.4 13.1 12.2M12.9 34.1Q26.2 33.5 38.5 34.2" />
        <path class="ink-detail" d="M11.2 16.8l2-.1M19.5 32.1l.1 2.2M26.1 32l.1 2.1M32.8 32.2v2" />
        <path class="ink-echo" d="M15.9 32.1C18.5 24 21 16.1 27.1 14.4 33 14.8 36.4 22.3 38.3 30.5" />
        <path class="ink-strong" d="M15.2 31.4C17.7 23.6 20.3 15.3 26.8 13.5 32.8 13.9 36.2 21.5 38 29.8" />
        <circle class="clay-mark" cx="29.2" cy="15.3" r="2.15" />
      </g>

      <!-- 故障树：顶事件方块向下分叉，两枚末端圆代表基础事件。 -->
      <g v-else-if="props.name === 'fta'">
        <path class="ink-echo" d="M15.2 7.8Q23.8 7.1 33.1 8l-.2 8.4q-8.8.8-17.6 0Z" />
        <path d="M14.2 6.6Q23.8 5.9 33.8 6.8l-.3 8.5q-9.4.8-19.1 0Z" />
        <path d="M24 15.8c.2 3 .1 5.2-.1 8M23.9 23.8C19.1 24 14.2 27 11.6 31.2M23.9 23.8c5.2.1 10.3 2.9 12.7 7.2" />
        <path class="ink-detail" d="M17.1 9.8q6.9-.6 13.7 0M23.9 20.1l.2 3.2" />
        <path d="M16.8 36.2c.1 3.7-2.4 6.1-6.1 5.7-3.5-.3-5.6-3.2-5-6.5.6-3.1 3.2-5.1 6.3-4.8 3 .2 4.7 2.5 4.8 5.6ZM42.3 36c.2 3.5-2.2 5.8-5.7 5.9-3.3.1-5.7-2.5-5.5-5.8.1-3.2 2.5-5.5 5.7-5.5 3.1 0 5.3 2.2 5.5 5.4Z" />
        <circle class="clay-mark" cx="23.9" cy="23.8" r="2" />
      </g>

      <!-- 知识检索：翻开的书页上叠一枚放大镜，clay 点是被找到的线索。 -->
      <g v-else-if="props.name === 'knowledge'">
        <path class="ink-echo" d="M6.5 13.9q8.8-2.2 17 2.7 8-4.8 17.6-2.2l-.6 21.3q-8.7-2.4-16.8 2.3-8.1-4.5-16.9-2.1Z" />
        <path d="M5.6 12.5q9-2.2 17.9 2.9 8.3-5.1 18.7-2.6l-.7 21.5q-9.3-2.6-17.8 2.5-8.5-4.8-17.5-2.4Z" />
        <path d="M23.5 15.4q.4 10.7.2 21.4M9.5 17.4q5.4-1.1 10.3 1.3M9.7 21.2q4.8-.8 9.4 1.2" />
        <path class="ink-detail" d="M9.8 30.9q4.6-.5 8.7 1.5M28 17.9q4.9-1.6 9.9-.5" />
        <path class="lens-paper" d="M39 27.8c.2 4.4-2.8 7.5-7.2 7.5-4.2 0-7.2-3.1-7-7.3.2-4 3.2-6.8 7.2-6.8 3.9.1 6.8 2.8 7 6.6Z" />
        <path class="ink-strong" d="M37.1 33.4q3.1 3.2 5.5 6.5" />
        <circle class="clay-mark" cx="31.8" cy="27.9" r="1.9" />
      </g>

      <!-- 协作网络：三个节点以略带手感的连线围成稳定三角。 -->
      <g v-else-if="props.name === 'collab'">
        <path class="ink-echo" d="M23.9 8.8Q17.1 20 10.4 34.7M25.1 8.7q6.3 13.4 13 26M11.4 36q12.8 1.6 25.7-.1" />
        <path d="M23.4 7.4Q16.6 19.2 9.2 34.3M25 7.5q6.7 13.2 14 26.6M10.2 35.3q13.8 1.5 27.8-.1" />
        <path d="M30 8c0 3.3-2.5 5.7-5.9 5.6-3.4 0-5.7-2.5-5.5-5.9.1-3.3 2.7-5.6 5.9-5.4C27.7 2.4 30 4.8 30 8ZM15.3 37c.1 3.4-2.3 5.9-5.8 5.9-3.4 0-5.8-2.5-5.7-5.9.1-3.3 2.5-5.7 5.8-5.7 3.2 0 5.6 2.4 5.7 5.7ZM44.2 37c.1 3.4-2.3 5.8-5.7 5.8-3.4 0-5.8-2.4-5.7-5.8.1-3.3 2.5-5.7 5.8-5.7 3.2.1 5.5 2.4 5.6 5.7Z" />
        <path class="ink-detail" d="M21.2 7.8q3.2-1.5 6 .2M6.5 37.3q2.9-1.4 5.8 0M35.6 36.8q3-1.3 5.8.1" />
        <circle class="clay-mark" cx="24.3" cy="7.9" r="2.1" />
      </g>

      <!-- 控制逻辑：两个错位状态块由迁移弧连接，clay 点落在箭头处。 -->
      <g v-else-if="props.name === 'logic'">
        <path class="ink-echo" d="M9.3 7.5q7.2-.5 14.1.2 1.6.2 1.5 1.8l-.3 8.8q-.1 1.9-2 1.9L9.1 19.8q-1.8 0-1.7-1.9l.2-8.7q.1-1.5 1.7-1.7ZM28.2 30.5q7.2-.5 14 .2 1.6.2 1.5 1.8l-.3 8.7q0 1.8-1.9 1.8L28 42.6q-1.6 0-1.6-1.8l.2-8.6q.1-1.5 1.6-1.7Z" />
        <path d="M8.3 6.3q7.2-.5 14.1.2 1.6.2 1.5 1.8l-.3 8.8q-.1 1.9-2 1.9L8.1 18.6q-1.8 0-1.7-1.9L6.6 8q.1-1.5 1.7-1.7ZM27.2 29.3q7.2-.5 14 .2 1.6.2 1.5 1.8l-.3 8.7q0 1.8-1.9 1.8L27 41.4q-1.6 0-1.6-1.8l.2-8.6q.1-1.5 1.6-1.7Z" />
        <path class="ink-echo" d="M20.5 20.3c-.7 5.7 1 11 5.8 14" />
        <path d="M19.6 19.3c-.9 6.4.9 12.5 5.9 15.3M21.8 32.9q1.8.8 3.7 1.7l-2.3 3" />
        <path class="ink-detail" d="M10.1 10.3q4.9-.5 9.8.1M10 14.2q3.4-.3 6.9.1M29.1 33.4q4.7-.4 9.4.1M29 37.3q3.6-.3 7.3.1" />
        <circle class="clay-mark" cx="25.5" cy="34.6" r="1.9" />
      </g>
    </g>
  </svg>
</template>

<script setup>
const props = defineProps({
  name: {
    type: String,
    required: true,
    validator: (value) => ['disk', 'fta', 'knowledge', 'collab', 'logic'].includes(value),
  },
  size: {
    type: Number,
    default: 28,
  },
})

</script>

<style scoped>
.intent-glyph {
  display: inline-block;
  flex: none;
  overflow: visible;
  color: inherit;
  vertical-align: -0.18em;
  pointer-events: none;
}

.glyph-ink {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.65;
}

.ink-echo {
  stroke-width: 0.75;
  opacity: 0.24;
}

.ink-detail {
  stroke-width: 0.85;
  opacity: 0.58;
}

.ink-strong {
  stroke-width: 1.95;
}

.lens-paper {
  fill: none;
  stroke: currentColor;
}

.clay-mark {
  fill: var(--clay);
  stroke: currentColor;
  stroke-width: 0.75;
}
</style>
