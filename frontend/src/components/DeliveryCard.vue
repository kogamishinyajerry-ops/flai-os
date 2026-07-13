<template>
  <div
    v-if="task"
    class="delivery-card"
    role="button"
    tabindex="0"
    @click="openTask"
    @keydown.enter.prevent="openTask"
    @keydown.space.prevent="openTask"
  >
    <CompletionSeal :task="task" :animate="animate" />

    <div class="delivery-meta">
      <span class="delivery-name">{{ task.name || task.id.slice(0, 12) }}</span>
      <span class="delivery-sub">
        {{ task.agent_id }}<template v-if="task.agent_version"> · {{ task.agent_version }}</template>
        <template v-if="task.created_by"> · {{ task.created_by }}</template>
        <template v-if="elapsedText"> · 用时 {{ elapsedText }}</template>
      </span>
    </div>

    <!-- 产物条：无产物不渲染该条——诚实地板不编「0 产物」。fileId 去重 + 一次性
         取 meta（onMounted，终态数据静态绝不轮询），前 3 件文件名 chip，超出显「+N」。
         chip 是原生 <a download>，click.stop 阻断整卡点击（否则先触发下载又跳转）。 -->
    <div v-if="artifacts.length" class="delivery-artifacts">
      <a
        v-for="a in artifacts"
        :key="a.fileId"
        :href="downloadUrl(a.fileId)"
        download
        class="delivery-chip"
        :title="a.filename"
        @click.stop
      >{{ a.filename }}</a>
      <span v-if="extraCount > 0" class="delivery-chip delivery-chip-more">+{{ extraCount }}</span>
    </div>

    <div class="delivery-tail">
      <span class="delivery-tail-item">{{ modelCallText }}</span>
      <template v-if="batchSummary">
        <span class="delivery-tail-item">成功 {{ batchSummary.ok }}</span>
        <span class="delivery-tail-item" :class="{ 'delivery-tail-fail': batchSummary.failed > 0 }">
          失败 {{ batchSummary.failed }}
        </span>
      </template>
    </div>
  </div>
</template>

<script setup>
// 交付叙事卡（批B Task 4）：CompletionSeal 头行 → 名称/执行方/用时 →
// 产物条（前 3 件+N）→ 尾行（模型调用消耗 + 批量 ok/failed）。全部数据在
// onMounted 一次性拉取——本卡只服务终态任务（今日交付版块已过滤），数据落定
// 不会再变，绝不轮询（与 CompletionSeal 的「盖章即定」同一诚实哲学）。
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import CompletionSeal from "./CompletionSeal.vue";
import { downloadUrl, fetchOutputFile } from "../api/files";
import { listModelCalls, listTaskEvents } from "../api/tasks";
import { taskElapsedMs, formatDuration } from "../utils/format";

const props = defineProps({ task: Object, animate: { type: Boolean, default: false } });

const router = useRouter();

function openTask() {
  router.push(`/tasks/${props.task.id}`);
}

const elapsedText = computed(() => {
  const ms = taskElapsedMs(props.task);
  if (ms == null) return "";
  const text = formatDuration(ms);
  return text === "—" ? "" : text;
});

// ── 产物条：fileId 去重取前 3 件一次性拉 meta（fetchOutputFile 同 StatusCenter
// syncPeekArtifacts 手法）；单件拉取失败不摧毁整条——退化显示 fileId 前 8 位。 ──
const artifacts = ref([]);
const extraCount = ref(0);

async function loadArtifacts(ids) {
  const uniqueIds = [...new Set(ids || [])];
  const targets = uniqueIds.slice(0, 3);
  extraCount.value = Math.max(0, uniqueIds.length - targets.length);
  if (!targets.length) {
    artifacts.value = [];
    return;
  }
  const out = [];
  for (const fid of targets) {
    try {
      out.push(await fetchOutputFile(fid));
    } catch (err) {
      out.push({ fileId: fid, filename: fid.slice(0, 8) });
    }
  }
  artifacts.value = out;
}

// ── 尾行·模型调用：null（fetch 失败）→「模型调用：未知」；[]→「无模型调用」；
// 有→「N 次调用·token 合计 X」，token 凑不出（无任何一条能折算出总数）显「未知」。
// token 折算口径与 TaskDetail modelCallTokenTotal 同源（total_tokens 优先，
// 否则 prompt+completion；两者皆无算未知，绝不记 0）。 ──
const modelCalls = ref(null); // null=未知（fetch 失败）区别于 []（真的零调用）

function tokenTotal(call) {
  const usage = call.token_usage;
  if (!usage || typeof usage !== "object") return null;
  if (typeof usage.total_tokens === "number") return usage.total_tokens;
  const { prompt_tokens: p, completion_tokens: c } = usage;
  if (typeof p === "number" && typeof c === "number") return p + c;
  return null;
}

const modelCallText = computed(() => {
  const calls = modelCalls.value;
  if (calls === null) return "模型调用：未知";
  if (calls.length === 0) return "无模型调用";
  let tokenSum = 0;
  let tokenKnown = 0;
  for (const c of calls) {
    const t = tokenTotal(c);
    if (t != null) {
      tokenSum += t;
      tokenKnown++;
    }
  }
  const tokenText = tokenKnown > 0 ? String(tokenSum) : "未知";
  return `${calls.length} 次调用 · token 合计 ${tokenText}`;
});

// ── 尾行·批量 ok/failed：同 TaskDetail.batchSummary 口径——最后一条
// agent_log 且 payload.workflow_event_type==='summary_generated' 且带
// ok_count/failed_count 的事件；无该事件（非批量 Agent）不显示。 ──
const batchSummary = ref(null);

function deriveBatchSummary(events) {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (
      e.event_type === "agent_log" &&
      e.payload?.workflow_event_type === "summary_generated" &&
      e.payload.ok_count != null &&
      e.payload.failed_count != null
    ) {
      return { ok: e.payload.ok_count, failed: e.payload.failed_count };
    }
  }
  return null;
}

onMounted(() => {
  const t = props.task;
  if (!t) return;
  loadArtifacts(t.output_file_ids);
  listModelCalls(t.id)
    .then((calls) => { modelCalls.value = calls; })
    .catch(() => { modelCalls.value = null; });
  listTaskEvents(t.id, { offset: 0 })
    .then((events) => { batchSummary.value = deriveBatchSummary(events); })
    .catch(() => { batchSummary.value = null; });
});
</script>

<style scoped>
.delivery-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--card-bg);
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: border-color var(--motion-fast) var(--ease-out-soft), transform var(--motion-fast) var(--ease-out-soft), box-shadow var(--motion-fast) var(--ease-out-soft);
}
.delivery-card:hover {
  border-color: var(--clay-softer);
  transform: translateY(-1px);
  box-shadow: var(--shadow-card-hover);
}
.delivery-meta {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.delivery-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.delivery-sub {
  font-size: 11.5px;
  color: var(--ink-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.delivery-artifacts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.delivery-chip {
  display: inline-block;
  max-width: 160px;
  padding: 3px 8px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  font-size: 11px;
  color: var(--clay);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.delivery-chip-more {
  color: var(--ink-faint);
  cursor: default;
}
.delivery-tail {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  color: var(--ink-faint);
}
.delivery-tail-fail {
  color: var(--trust-fail);
}
</style>
