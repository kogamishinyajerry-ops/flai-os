<template>
  <!-- mock=true 时如实披露「演示数据」；核验尚未得到可信答复时也必须显式
       amber，不能把「查不到」伪装成「没有 mock」。verified 且无 mock 才零渲染。 -->
  <span
    v-if="badgeText"
    class="mock-seal"
    role="note"
    aria-live="polite"
    :data-verification-state="verificationState"
    :title="tipText"
  >
    <svg class="mock-seal-icon" width="11" height="11" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 9v4" /><path d="M12 17h.01" />
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
    {{ badgeText }}
  </span>
</template>

<script setup>
// 数据源：listToolRuns（只读端点）——后端 tool_runs.mock 标记（registry 写入，
// repos 读出 bool）。只要本任务存在任一 mock=true 的工具调用，即判定产物含演示
// 数据成分。核验态同时作为两个签发面的 fail-closed 只读守卫。
import { ref, computed, watch, onUnmounted } from "vue";
import { listToolRuns } from "../api/tasks";

const props = defineProps({
  taskId: { type: String, required: true },
  status: { type: String, default: "" },
});

const mockToolNames = ref([]);
const verificationState = ref("loading");
let verificationEpoch = 0;

const hasMock = computed(() => mockToolNames.value.length > 0);
const badgeText = computed(() => {
  if (verificationState.value === "loading") return "数据来源核验中 · 暂不可签发";
  if (verificationState.value === "error") return "数据来源核验失败 · 暂不可签发";
  if (verificationState.value === "unknown") return "数据来源状态未知 · 暂不可签发";
  return hasMock.value ? "演示数据 · 未经核验" : "";
});
const tipText = computed(() => {
  if (verificationState.value === "loading") return "正在核验本任务工具调用的数据来源，核验完成前不可签发。";
  if (verificationState.value === "error") return "数据来源核验请求失败，当前无法确认是否含演示数据，暂不可签发。";
  if (verificationState.value === "unknown") return "数据来源接口返回了未知结构，当前无法确认是否含演示数据，暂不可签发。";
  if (hasMock.value) {
    return `本任务产物含演示/桩数据成分（mock 工具：${mockToolNames.value.join("、")}），未经真实核验，不可作为工程结论。`;
  }
  return "";
});

async function verifySource() {
  const epoch = ++verificationEpoch;
  mockToolNames.value = [];
  verificationState.value = "loading";
  if (!props.taskId) {
    verificationState.value = "unknown";
    return;
  }
  try {
    const rows = await listToolRuns(props.taskId);
    if (epoch !== verificationEpoch) return;
    if (!Array.isArray(rows)) {
      verificationState.value = "unknown";
      return;
    }
    const names = rows
      .filter((r) => r && r.mock === true)
      .map((r) => r.tool_id)
      .filter(Boolean);
    mockToolNames.value = [...new Set(names)];
    verificationState.value = "verified";
  } catch {
    if (epoch === verificationEpoch) verificationState.value = "error";
  }
}

// 同任务从运行态进入 waiting_review 时必须再查一次：工具调用可能晚于页面首载
// 才落库；taskId 切换同理。epoch 让前一任务/状态的迟到响应整包作废。
watch(() => [props.taskId, props.status], verifySource, { immediate: true });

function isSignoffBlocked() {
  return verificationState.value !== "verified";
}
defineExpose({ isSignoffBlocked });

onUnmounted(() => {
  verificationEpoch++;
});
</script>

<style scoped>
/* 琥珀「未核」徽章：与 .pill-amber 同族（--trust-pending），但语义更强（演示数据
   警示），加图标与虚线边框区分——虚线=「此结论尚不牢靠」的视觉隐喻。 */
.mock-seal {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: var(--fs-sm);
  font-weight: 600;
  letter-spacing: 0.2px;
  color: var(--trust-pending);
  border: 1px dashed rgba(var(--trust-pending-rgb), 0.55);
  background: rgba(var(--trust-pending-rgb), 0.1);
  white-space: nowrap;
  cursor: help;
}
.mock-seal-icon {
  flex: none;
  transform: translateY(0.5px); /* 光学对齐：警告三角视觉重心偏低，下移半像素 */
}
</style>
