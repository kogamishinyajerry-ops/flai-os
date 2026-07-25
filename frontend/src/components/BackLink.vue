<template>
  <!-- 统一返回入口（打磨批 UX）：深链页（/portal /feedback /me /tasks/new 等）
       此前是死胡同——从侧栏/⌘K 进入后页头无退路。本组件收口「← 返回」：
       有浏览器历史则后退（保留滚动/筛选现场），直开无历史则回退到 fallback
       指定的一级 Surface。纯导航增强，不改任何数据/状态逻辑。 -->
  <button class="back-link" type="button" @click="goBack">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M19 12H5" /><path d="m12 19-7-7 7-7" />
    </svg>
    {{ label }}
  </button>
</template>

<script setup>
import { useRouter } from "vue-router";

const props = defineProps({
  label: { type: String, default: "返回" },
  // 直开无历史时的兜底目的地（默认回任务台——总览「来找你」的一级 Surface）。
  fallback: { type: String, default: "/tasks" },
});

const router = useRouter();
function goBack() {
  // history.state.back 是 Vue Router 写入的上一条记录指针：非空=应用内有
  // 来路可退（保留原页现场）；空=直开/新标签，回退到兜底 Surface 不致卡死。
  if (window.history.state && window.history.state.back) {
    router.back();
  } else {
    router.push(props.fallback);
  }
}
</script>

<style scoped>
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0 0 6px -6px; /* 顶格对齐标题左缘（自身 padding 6px 的视觉补偿），上与标题留呼吸 */
  padding: 4px 10px 4px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: none;
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--ink-soft);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft),
    color var(--motion-fast) var(--ease-out-soft),
    transform var(--motion-fast) var(--ease-out-soft);
}
.back-link:hover {
  background: var(--hover-tint);
  color: var(--ink);
}
.back-link:active {
  transform: translateX(-2px); /* 按压微向左挪，呼应「后退」方向感 */
}
.back-link svg {
  flex: none;
}
@media (prefers-reduced-motion: reduce) {
  .back-link { transition: none; }
  .back-link:active { transform: none; }
}
</style>
