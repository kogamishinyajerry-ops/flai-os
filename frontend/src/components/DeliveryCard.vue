<template>
  <!-- data-task-id（批次四 Q1）：主文本改人话称呼后，e2e 定位改走本属性——
       缺名任务不再有裸 id 字面可当定位串（batch_b_today 消费）。 -->
  <div
    v-if="task"
    class="delivery-card"
    role="button"
    tabindex="0"
    :data-task-id="task.id"
    @click="openTask"
    @keydown.enter.prevent="openTask"
    @keydown.space.prevent="openTask"
  >
    <CompletionSeal :task="task" :animate="animate" />

    <div class="delivery-meta">
      <span class="delivery-name">{{ taskDisplayName(task, agentNames.map) }}</span>
      <span class="delivery-sub">
        {{ task.agent_id }}<template v-if="task.agent_version"> · {{ task.agent_version }}</template>
        <template v-if="task.created_by"> · {{ task.created_by }}</template>
        <template v-if="elapsedText"> · 用时 {{ elapsedText }}</template>
      </span>
    </div>

    <!-- 产物条：无产物不渲染该条——诚实地板不编「0 产物」。一次性拉全部产物元数据
         投影（listOutputFiles，onMounted，终态数据静态绝不轮询），前 3 件文件名
         chip，超出显「+N」。internal 分级=原生 <a download> 真下载意图；非 internal
         （含拉取失败退化的 unknown）=不可点 span，绝不触发下载审计——chip 只做
         展示，点击才是下载意图。click/keydown.stop 阻断整卡点击（不 prevent 默认
         行为，Enter 仍能触发锚点原生下载）。 -->
    <div v-if="artifacts.length" class="delivery-artifacts">
      <template v-for="a in artifacts" :key="a.id">
        <a
          v-if="a.data_classification === 'internal'"
          :href="downloadUrl(a.id)"
          download
          class="delivery-chip"
          :title="a.filename"
          @click.stop
          @keydown.enter.stop
          @keydown.space.stop
        >{{ a.filename }}</a>
        <span
          v-else
          class="delivery-chip delivery-chip-restricted"
          title="受限产物，详情页签发流程查看"
        >{{ a.filename }}</span>
      </template>
      <span v-if="extraCount > 0" class="delivery-chip delivery-chip-more">+{{ extraCount }}</span>
    </div>

    <!-- 批七 §3-13 依据区（字段缺省渲染无，全存量 agent 向后兼容）：findings
         摘要 chip + 拒答 amber 行——数据走 taskEvidence 模块缓存（与 GuidePage/
         WorkbenchSession 同源，同任务零重复拉取）。 -->
    <div v-if="evidenceSummary" class="delivery-evidence" :class="{ 'has-unverified': evidenceSummary.invalid || evidenceSummary.unverified > 0 }">
      <template v-if="evidenceSummary.invalid">依据结构待核</template>
      <template v-else>依据 {{ evidenceSummary.total }} 条（{{ evidenceSummary.verified }} 已核验 · {{ evidenceSummary.unverified }} 未核）<template v-if="evidenceSummary.level"> · 置信度 {{ evidenceSummary.level }}（模型自评）</template></template>
    </div>
    <div v-if="refusalCount > 0" class="delivery-refusals">
      已如实说明：{{ refusalCount }} 项超出能力范围
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
import { downloadUrl } from "../api/files";
import { getDeliverySummary, listOutputFiles } from "../api/tasks";
import { taskElapsedMs, formatDuration, formatTokens, taskDisplayName } from "../utils/format";
import { orderArtifactsForReview } from "../utils/artifactReview";
import { useAgentNames } from "../stores/agentNames";
import { ensureTaskEvidence, taskEvidenceOf, taskEvidenceSummary } from "../stores/taskEvidence";

const props = defineProps({ task: Object, animate: { type: Boolean, default: false } });

// Agent 人话名册（批次四 Q1）：缺名交付卡回退 Agent 显示名。
const agentNames = useAgentNames();

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

// ── 产物条：一次请求拉全部产物元数据投影（/tasks/{id}/output_files，只读
// id/filename/size_bytes/data_classification，绝不含内容/路径——不再逐个调
// fetchOutputFile 拖全量 blob）。前 3 件 chip，超出显「+N」。整请求失败（非
// 单件失败）时 fail-closed 退化：用 id 前 8 位占位、分级标 unknown——unknown
// 一律按非 internal 处理（chip 不可点），绝不在拉取失败时误当 internal 放行下载。 ──
const artifacts = ref([]);
const extraCount = ref(0);

async function loadArtifacts(taskId, ids) {
  const uniqueIds = [...new Set(ids || [])];
  if (!uniqueIds.length) {
    artifacts.value = [];
    extraCount.value = 0;
    return;
  }
  try {
    const files = await listOutputFiles(taskId);
    artifacts.value = orderArtifactsForReview(files).slice(0, 3);
    extraCount.value = Math.max(0, files.length - artifacts.value.length);
  } catch (err) {
    const targets = uniqueIds.slice(0, 3);
    extraCount.value = Math.max(0, uniqueIds.length - targets.length);
    artifacts.value = targets.map((fid) => ({ id: fid, filename: fid.slice(0, 8), data_classification: "unknown" }));
  }
}

// ── 尾行·模型调用 + 批量 ok/failed：单次服务端有界聚合（治理审 R1 P1 修复）
// ——GET /tasks/{id}/delivery_summary 取代此前 listModelCalls+listTaskEvents
// 两个无界请求（每卡 2-3 个只读请求 × 今日交付上界 12 张=无界扇出的另一半）。
// summary=null（fetch 失败）→「模型调用：未知」，与旧 modelCalls=null 语义相同。
// summary.token_known 折算口径与端点 docstring/DeliveryCard 旧版同源（服务端
// _model_call_token_total 同款：total_tokens 优先，否则 prompt+completion
// 均为数字才计，两者皆无算未知）；batch_ok/batch_failed 为 null=非批量 Agent
// 正常态或超出端点 50 条事件有界扫描（诚实降级：不显示批量行，不猜）。 ──
const summary = ref(null);

const modelCallText = computed(() => {
  const s = summary.value;
  if (!s) return "模型调用：未知";
  if (s.mc_total === 0) return "无模型调用";
  if (s.token_known === 0) return `${s.mc_total} 次调用 · token 用量：未知`;
  const suffix = s.token_known < s.mc_total ? "（部分未报，下界）" : "";
  // token 千位压缩（F1）：次数精确、消耗量压缩——disclosure-grammar §三两轴。
  return `${s.mc_total} 次调用 · tokens 合计 ${formatTokens(s.token_sum)}${suffix}`;
});

const batchSummary = computed(() => {
  const s = summary.value;
  if (!s || s.batch_ok == null || s.batch_failed == null) return null;
  return { ok: s.batch_ok, failed: s.batch_failed };
});

// 批七依据区：模块级缓存拉取（终态数据静态，同任务全站只拉一次）。
const evidenceSummary = computed(() => (props.task ? taskEvidenceSummary(props.task.id) : null));
const refusalCount = computed(() => {
  if (!props.task) return 0;
  const ev = taskEvidenceOf(props.task.id);
  return ev ? ev.refusals.length : 0;
});

onMounted(() => {
  const t = props.task;
  if (!t) return;
  loadArtifacts(t.id, t.output_file_ids);
  ensureTaskEvidence(t);
  getDeliverySummary(t.id)
    .then((s) => { summary.value = s; })
    .catch(() => { summary.value = null; });
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
/* 五槽修正（批次 D）：下载 chip 是次级动作而非「工作/进行/选中」，常驻 clay
   占槽违规——降 ink-soft+下划线（链接语义由下划线承担），hover 回 clay；
   与批次五 C3 对 TaskDetail 产物/来源链接的既裁决同款。 */
.delivery-chip {
  display: inline-block;
  max-width: 160px;
  padding: 3px 8px;
  border: 1px solid var(--hairline);
  border-radius: 6px;
  font-size: 11px;
  color: var(--ink-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
a.delivery-chip:hover {
  color: var(--clay);
}
/* 非链接 chip（+N / 受限占位）不得带下划线——下划线=可下载承诺，不造假 affordance。 */
.delivery-chip-more {
  color: var(--ink-faint);
  cursor: default;
  text-decoration: none;
}
.delivery-chip-restricted {
  color: var(--ink-faint);
  cursor: default;
  border-style: dashed;
  text-decoration: none;
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
/* 批七依据区：含未核 amber（信任色锁：amber=未核唯一语义，任何情况不染绿）；
   拒答 amber 非红——诚实拒答是履约不是失败。 */
.delivery-evidence {
  font-size: 11.5px;
  color: var(--ink-soft);
  margin: 2px 0;
  font-variant-numeric: tabular-nums;
}
.delivery-evidence.has-unverified { color: var(--trust-pending); }
.delivery-refusals {
  font-size: 11.5px;
  color: var(--trust-pending);
  margin: 2px 0;
}
</style>
