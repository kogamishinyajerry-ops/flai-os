<template>
  <!-- 统一错误态（打磨批）：收口全站散落的裸 el-alert type="error"。保留 .el-alert
       class（batch_d 视觉验收断言其可见），在其外套一层语义容器，补两点：
         1. 可选重试按钮——数据加载类错误给「再试一次」出口，不只冷冰冰一行红字；
         2. 错误正文与动作分行，层级更清。
       诚实地板：message 原样透传（err.detail||err.message，绝不改写/美化）；无
       retry 时不渲染按钮，与原先纯 alert 等价。 -->
  <!-- el-alert 自带 role=alert；外层保持纯布局，避免嵌套两个 live region 重复播报。 -->
  <div class="error-state">
    <el-alert type="error" :title="message" show-icon :closable="false" />
    <el-button
      v-if="retry"
      class="error-retry"
      size="small"
      :loading="retrying"
      @click="onRetry"
    >重试</el-button>
  </div>
</template>

<script setup>
import { ref } from "vue";

const props = defineProps({
  message: { type: String, required: true },
  // 传入 async 重试函数即启用重试按钮；按钮自带 loading，失败由调用方各自提示。
  retry: { type: Function, default: null },
});

const retrying = ref(false);
async function onRetry() {
  if (!props.retry || retrying.value) return;
  retrying.value = true;
  try {
    await props.retry();
  } finally {
    retrying.value = false;
  }
}
</script>

<style scoped>
.error-state {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.error-state :deep(.el-alert) {
  flex: 1 1 auto;
  min-width: 0;
}
.error-retry {
  flex: none;
}
</style>
