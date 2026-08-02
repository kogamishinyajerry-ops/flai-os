<template>
  <aside
    v-if="phase !== 'idle'"
    class="asset-candidate-callout"
    :class="`is-${visualState}`"
    aria-live="polite"
  >
    <span class="candidate-mark" aria-hidden="true"></span>
    <div class="candidate-callout-copy">
      <span class="candidate-kicker">可复用资产</span>
      <strong>{{ headline }}</strong>
      <span class="candidate-summary">{{ summary }}</span>
    </div>
    <button
      v-if="phase === 'reconcile_required'"
      type="button"
      class="candidate-open"
      @click="$emit('retry')"
    >核对真实状态</button>
    <button
      v-else-if="candidate"
      ref="reviewTrigger"
      type="button"
      class="candidate-open"
      @click="reviewOpen = true"
    >{{ openLabel }}</button>
    <button
      v-else-if="phase === 'unavailable'"
      type="button"
      class="candidate-open"
      @click="$emit('retry')"
    >重新核对</button>
  </aside>

  <el-drawer
    v-if="candidate"
    v-model="reviewOpen"
    class="asset-candidate-review"
    direction="rtl"
    :size="drawerSize"
    :close-on-click-modal="phase !== 'deciding'"
    :close-on-press-escape="phase !== 'deciding'"
    :show-close="phase !== 'deciding'"
    :aria-busy="phase === 'deciding'"
    destroy-on-close
    @closed="restoreFocus"
  >
    <template #header>
      <div class="candidate-review-heading">
        <span class="candidate-kicker">任务完成后自动形成</span>
        <h2>可复用方法候选</h2>
        <p>你只需判断这套方法值不值得留下；系统内部如何路由，不需要你填写或选择。</p>
      </div>
    </template>

    <div class="candidate-review-body" :aria-busy="phase === 'deciding'">
      <section class="candidate-primary">
        <span class="candidate-state" :class="`is-${candidate.state}`">
          {{ stateLabel }}
        </span>
        <h3>{{ candidate.bundle.task_pattern.title }}</h3>
        <p>{{ candidate.bundle.task_pattern.desired_outcome }}</p>
      </section>

      <section class="candidate-section">
        <h3>什么时候复用</h3>
        <p>{{ candidate.bundle.task_pattern.trigger }}</p>
      </section>

      <section class="candidate-section">
        <h3>系统归纳的方法</h3>
        <ol>
          <li v-for="step in candidate.bundle.skill.instructions" :key="step">{{ step }}</li>
        </ol>
      </section>

      <section class="candidate-section candidate-boundary">
        <h3>人必须保留的判断</h3>
        <ul>
          <li v-for="boundary in candidate.bundle.skill.human_boundaries" :key="boundary">
            {{ boundary }}
          </li>
        </ul>
      </section>

      <section class="candidate-section">
        <h3>这次形成了什么</h3>
        <div class="candidate-map">
          <div class="candidate-map-row is-formed">
            <span>Task Pattern</span>
            <strong>{{ revisionLabel(candidate.asset_map.task_pattern.state) }}</strong>
          </div>
          <div class="candidate-map-row is-formed">
            <span>Skill</span>
            <strong>{{ revisionLabel(candidate.asset_map.skill.state) }}</strong>
          </div>
          <div class="candidate-map-row">
            <span>Workflow</span>
            <strong>尚未形成</strong>
            <small>{{ candidate.asset_map.workflow.gate }}</small>
          </div>
          <div class="candidate-map-row">
            <span>Agent</span>
            <strong>尚未形成</strong>
            <small>{{ candidate.asset_map.agent.gate }}</small>
          </div>
        </div>
      </section>

      <section v-if="candidate.skill_package" class="candidate-section candidate-package">
        <span class="candidate-state" :class="`is-package-${candidate.skill_package.state}`">
          {{ packageStateLabel }}
        </span>
        <h3>{{ candidate.skill_package.name }} · {{ candidate.skill_package.version }}</h3>
        <p v-if="candidate.skill_package.state === 'pending_review'">
          已从接受的候选确定性生成隔离包待复核；当前不可执行、未登记，也不会自动发布。
        </p>
        <p v-else-if="candidate.skill_package.state === 'approved'">
          这份精确版本已通过包级人工复核；相似新任务将自动复用，开工与结果签发仍由工程师确认。
        </p>
        <p v-else>
          这份隔离包本次不进入自动复用；Candidate 与复核记录仍完整保留。
        </p>
        <small>
          独立任务证据 {{ candidate.skill_package.formation_evidence.independent_work_case_count }}
          / {{ candidate.skill_package.formation_evidence.required_independent_work_cases }}；
          达到数量门也不会自动形成 Workflow 或 Agent Candidate。
        </small>
        <div class="candidate-package-review-content">
          <button
            type="button"
            class="candidate-package-content-toggle"
            :aria-expanded="packageContentOpen"
            :disabled="phase === 'deciding' || packageReviewPhase === 'loading'"
            @click="togglePackageContent"
          >{{ packageContentActionLabel }}</button>
          <p
            v-if="packageReviewPhase === 'loading'"
            class="candidate-package-content-status"
            role="status"
          >正在冷核验隔离包真实字节…</p>
          <p
            v-else-if="packageReviewPhase === 'error'"
            class="candidate-package-content-status is-error"
            role="alert"
          >{{ packageReviewError || "真实包内容暂时无法核验；批准复用已锁定。" }}</p>
          <div
            v-if="packageContentOpen && packageReviewPhase === 'ready' && packageReviewContent"
            class="candidate-package-files"
          >
            <article
              v-for="file in packageReviewContent.files"
              :key="file.path"
              class="candidate-package-file"
            >
              <h4>{{ file.path }}</h4>
              <pre>{{ file.text }}</pre>
            </article>
          </div>
        </div>
      </section>

      <section class="candidate-evidence">
        <button
          type="button"
          class="candidate-evidence-toggle"
          :aria-expanded="evidenceOpen"
          :disabled="phase === 'deciding'"
          @click="toggleEvidence"
        >{{ evidenceOpen ? "收起来源与摘要证据" : "查看来源与摘要证据" }}</button>
        <dl v-if="evidenceOpen">
          <div><dt>来源任务</dt><dd>{{ candidate.source.task_id }}</dd></div>
          <div><dt>执行单元</dt><dd>{{ candidate.source.agent_id }}@{{ candidate.source.agent_version }}</dd></div>
          <div><dt>候选摘要</dt><dd>{{ shortDigest(candidate.candidate_digest) }}</dd></div>
          <div><dt>草稿摘要</dt><dd>{{ shortDigest(candidate.bundle_digest) }}</dd></div>
          <div v-if="candidate.skill_package"><dt>隔离包摘要</dt><dd>{{ shortDigest(candidate.skill_package.package_digest) }}</dd></div>
          <div v-if="candidate.skill_package"><dt>包内文件</dt><dd>{{ candidate.skill_package.files.length }} 份</dd></div>
          <div><dt>产物引用</dt><dd>{{ candidate.lineage.output_files.length }} 份</dd></div>
          <div><dt>签发证据</dt><dd>{{ signoffLabel }}</dd></div>
        </dl>
      </section>

      <p class="candidate-honesty" :class="{ 'is-signed': candidate.state === 'accepted' }">
        <template v-if="candidate.state === 'accepted'">
          已接受为资产候选，尚未登记、发布或形成 Agent。Candidate 接受不等于隔离包批准。
        </template>
        <template v-else-if="candidate.state === 'rejected'">
          本次候选已明确不保留；原任务与审核记录仍完整存在。
        </template>
        <template v-else>
          接受只会保留这份精确候选；不会执行工作、写 Agent 包、注册、发布或晋级。
        </template>
      </p>
    </div>

    <template #footer>
      <div class="candidate-review-actions">
        <template
          v-if="candidate.state === 'awaiting_human_review' && (phase === 'ready' || phase === 'deciding')"
        >
          <button
            type="button"
            class="candidate-action is-accept"
            :disabled="phase !== 'ready'"
            @click="$emit('decide', 'accept')"
          >接受这个候选</button>
          <button
            type="button"
            class="candidate-action is-reject"
            :disabled="phase !== 'ready'"
            @click="$emit('decide', 'reject')"
          >本次不保留</button>
        </template>
        <template
          v-if="candidate.state === 'accepted' && candidate.skill_package?.state === 'pending_review' && (phase === 'ready' || phase === 'deciding')"
        >
          <button
            type="button"
            class="candidate-action is-accept"
            :disabled="phase !== 'ready' || packageReviewPhase !== 'ready' || !packageReviewContent"
            @click="$emit('decide-package', 'approve')"
          >{{ phase === "deciding" ? "正在记录决定…" : "批准复用" }}</button>
          <button
            type="button"
            class="candidate-action is-reject"
            :disabled="phase !== 'ready'"
            @click="$emit('decide-package', 'reject')"
          >本次不批准</button>
        </template>
        <button
          v-if="phase === 'reconcile_required'"
          type="button"
          class="candidate-action"
          @click="$emit('retry')"
        >核对真实状态</button>
        <button
          type="button"
          class="candidate-action"
          :disabled="phase === 'deciding'"
          @click="downloadCandidate"
        >
          {{ candidate.state === "awaiting_human_review" ? "下载待审包" : "下载候选记录" }}
        </button>
        <button
          type="button"
          class="candidate-action"
          :disabled="phase === 'deciding'"
          @click="reviewOpen = false"
        >
          回到对话
        </button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, ref } from "vue";


const props = defineProps({
  candidate: { type: Object, default: null },
  phase: { type: String, default: "idle" },
  error: { type: String, default: "" },
  packageReviewContent: { type: Object, default: null },
  packageReviewPhase: { type: String, default: "idle" },
  packageReviewError: { type: String, default: "" },
});
const emit = defineEmits([
  "decide",
  "decide-package",
  "load-package-content",
  "retry",
]);

const reviewOpen = ref(false);
const evidenceOpen = ref(false);
const packageContentOpen = ref(false);
const reviewTrigger = ref(null);
const drawerSize = computed(() => (
  typeof window !== "undefined" && window.innerWidth <= 640
    ? "100%"
    : "min(560px, 92vw)"
));
const visualState = computed(() => (
  props.candidate?.skill_package?.state === "pending_review"
    ? "package_pending"
    : props.candidate?.skill_package?.state === "approved"
      ? "package_approved"
      : props.candidate?.skill_package?.state === "rejected"
        ? "package_rejected"
    : props.candidate?.state || props.phase
));
const openLabel = computed(() => {
  if (props.candidate?.state === "awaiting_human_review" && props.phase === "ready") {
    return "查看并决定";
  }
  if (props.candidate?.skill_package?.state === "pending_review") {
    return "复核隔离包";
  }
  return "查看记录";
});
const stateLabel = computed(() => ({
  awaiting_human_review: "等待你决定",
  accepted: "已由工程师接受",
  rejected: "已由工程师不保留",
}[props.candidate?.state] || "状态待核"));
const packageStateLabel = computed(() => ({
  pending_review: "隔离包待复核",
  approved: "工程师已批准复用",
  rejected: "本次未批准复用",
}[props.candidate?.skill_package?.state] || "包状态待核"));
const headline = computed(() => {
  if (props.phase === "loading") return "正在从任务证据整理一套可复用方法";
  if (props.phase === "deciding") return "正在记录你的人工决定";
  if (props.phase === "reconcile_required") return "刚才的人工决定状态还需核对";
  if (props.phase === "unavailable") return "这次任务暂时不能形成可信候选";
  if (props.candidate?.skill_package?.state === "pending_review") return "隔离包待复核";
  if (props.candidate?.skill_package?.state === "approved") return "这套方法可在相似新任务中自动复用";
  if (props.candidate?.skill_package?.state === "rejected") return "这份隔离包本次不进入自动复用";
  if (props.candidate?.state === "accepted") return "这套方法已保留为资产候选";
  if (props.candidate?.state === "rejected") return "这次方法已明确不保留";
  return "这次任务里，有一套方法值得你看一眼";
});
const summary = computed(() => {
  if (props.phase === "loading") return "只读取完成证据和不可变摘要，不需要你填写任何字段。";
  if (props.phase === "deciding") return "决定提交期间保持当前修订不变；关闭动作暂时锁定。";
  if (props.error) return props.error;
  if (props.candidate?.skill_package?.state === "pending_review") return "系统已自动生成版本化文件包；需由你复核精确版本，不需要填写字段。";
  if (props.candidate?.skill_package?.state === "approved") return "相似新任务将自动匹配，并在原方案中说明复用来源。";
  if (props.candidate?.skill_package?.state === "rejected") return "拒绝包级复用不会影响原任务或 Candidate 审计记录。";
  if (props.candidate?.state === "accepted") return "Candidate 已接受，正在等待隔离包状态核对。";
  if (props.candidate?.state === "rejected") return "拒绝是正常工程判断，不会被标记成任务失败。";
  return props.candidate?.bundle?.skill?.description || "系统已自动归纳 Task Pattern 与 Skill 草稿。";
});
const packageContentActionLabel = computed(() => {
  if (props.packageReviewPhase === "loading") return "正在核验真实包内容…";
  if (props.packageReviewPhase === "error") return "重新核验真实包内容";
  if (props.packageReviewPhase === "ready") {
    return packageContentOpen.value ? "收起真实包内容" : "查看真实包内容";
  }
  return "读取并审阅真实包内容";
});
const signoffLabel = computed(() => (
  props.candidate?.lineage?.signoff?.kind === "human_review_approved"
    ? "已绑定任务人工签发事件"
    : "确定性免审边界已核对"
));

function revisionLabel(state) {
  return {
    candidate_revision: "候选修订",
    approved_revision: "已接受修订",
    rejected_revision: "不保留修订",
  }[state] || "状态待核";
}

function shortDigest(value) {
  if (typeof value !== "string" || value.length < 24) return "摘要待核";
  return `${value.slice(0, 15)}…${value.slice(-8)}`;
}

function downloadCandidate() {
  if (props.phase === "deciding") return;
  const body = JSON.stringify(props.candidate, null, 2);
  const url = URL.createObjectURL(new Blob([body], { type: "application/json;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${props.candidate.id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function toggleEvidence() {
  if (props.phase === "deciding") return;
  evidenceOpen.value = !evidenceOpen.value;
}

function togglePackageContent() {
  if (props.phase === "deciding" || props.packageReviewPhase === "loading") return;
  if (props.packageReviewPhase === "ready" && props.packageReviewContent) {
    packageContentOpen.value = !packageContentOpen.value;
    return;
  }
  packageContentOpen.value = true;
  emit("load-package-content");
}

function restoreFocus() {
  evidenceOpen.value = false;
  packageContentOpen.value = false;
  void nextTick(() => reviewTrigger.value?.focus({ preventScroll: true }));
}
</script>

<style scoped>
.asset-candidate-callout {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 2px 40px;
  padding: 12px 14px;
  border: 1px solid var(--hairline-soft);
  border-radius: 14px;
  background: var(--surface-raised);
  color: var(--ink);
}
.candidate-mark {
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--clay);
}
.asset-candidate-callout.is-awaiting_human_review .candidate-mark { background: var(--trust-pending); }
.asset-candidate-callout.is-package_pending .candidate-mark { background: var(--trust-pending); }
.asset-candidate-callout.is-package_approved .candidate-mark { background: var(--trust-signed); }
.asset-candidate-callout.is-accepted .candidate-mark { background: var(--trust-signed); }
.asset-candidate-callout.is-unavailable .candidate-mark,
.asset-candidate-callout.is-reconcile_required .candidate-mark { background: var(--trust-pending); }
.asset-candidate-callout.is-rejected .candidate-mark,
.asset-candidate-callout.is-package_rejected .candidate-mark {
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--ink-faint);
}
.candidate-callout-copy {
  display: grid;
  flex: 1 1 auto;
  min-width: 0;
  gap: 2px;
}
.candidate-kicker {
  color: var(--ink-faint);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.candidate-callout-copy strong { font-size: 14px; line-height: 1.4; }
.candidate-summary {
  overflow: hidden;
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.candidate-open,
.candidate-action {
  min-height: 40px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--paper-rail);
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}
.candidate-open { flex: 0 0 auto; padding: 0 13px; }
.candidate-open:hover,
.candidate-action:hover { border-color: var(--clay-softer); }
.candidate-review-heading h2 {
  margin: 4px 0 6px;
  color: var(--ink);
  font-family: var(--font-serif);
  font-size: 26px;
}
.candidate-review-heading p {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.6;
}
.candidate-review-body { display: grid; gap: 18px; }
.candidate-primary,
.candidate-section,
.candidate-evidence,
.candidate-honesty {
  margin: 0;
  padding: 16px;
  border: 1px solid var(--hairline-soft);
  border-radius: 14px;
  background: var(--surface-raised);
}
.candidate-primary h3,
.candidate-section h3 { margin: 8px 0 6px; color: var(--ink); font-size: 16px; }
.candidate-primary p,
.candidate-section p,
.candidate-section li { color: var(--ink-soft); font-size: 13px; line-height: 1.7; }
.candidate-section ol,
.candidate-section ul { margin: 8px 0 0; padding-left: 20px; }
.candidate-state {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--clay-soft);
  color: var(--clay);
  font-size: 11px;
  font-weight: 700;
}
.candidate-state.is-awaiting_human_review {
  color: var(--trust-pending);
  background: rgba(var(--trust-pending-rgb), 0.1);
}
.candidate-state.is-accepted { color: var(--trust-signed); background: rgba(var(--trust-signed-rgb), 0.1); }
.candidate-state.is-rejected { color: var(--ink-soft); background: var(--paper-rail); }
.candidate-state.is-package-pending_review { color: var(--trust-pending); background: rgba(var(--trust-pending-rgb), 0.1); }
.candidate-state.is-package-approved { color: var(--trust-signed); background: rgba(var(--trust-signed-rgb), 0.1); }
.candidate-state.is-package-rejected { color: var(--ink-soft); background: var(--paper-rail); }
.candidate-package small { display: block; margin-top: 8px; color: var(--ink-faint); line-height: 1.6; }
.candidate-package-review-content { display: grid; gap: 10px; margin-top: 14px; }
.candidate-package-content-toggle {
  justify-self: start;
  min-height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}
.candidate-package-content-toggle:disabled { color: var(--ink-faint); cursor: wait; }
.candidate-package-content-status { margin: 0; color: var(--ink-soft); font-size: 12px; }
.candidate-package-content-status.is-error {
  padding: 8px 10px;
  border-left: 2px solid var(--trust-pending);
  background: rgba(var(--trust-pending-rgb), 0.08);
  color: var(--trust-pending);
}
.candidate-package-files { display: grid; gap: 10px; }
.candidate-package-file { min-width: 0; }
.candidate-package-file h4 { margin: 0 0 5px; color: var(--ink-soft); font-size: 12px; }
.candidate-package-file pre {
  overflow: auto;
  max-height: 240px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--hairline-soft);
  border-radius: 10px;
  background: var(--paper-rail);
  color: var(--ink);
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.candidate-boundary { border-color: rgba(var(--trust-pending-rgb), 0.35); }
.candidate-map { display: grid; gap: 0; }
.candidate-map-row {
  display: grid;
  grid-template-columns: minmax(92px, 0.8fr) minmax(110px, 1fr);
  gap: 6px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--hairline-soft);
}
.candidate-map-row:first-child { border-top: 0; }
.candidate-map-row span { color: var(--ink-soft); font-size: 12px; }
.candidate-map-row strong { color: var(--ink); font-size: 13px; }
.candidate-map-row.is-formed strong { color: var(--clay); }
.candidate-map-row small { grid-column: 2; color: var(--ink-faint); line-height: 1.5; }
.candidate-evidence-toggle {
  min-height: 40px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}
.candidate-evidence-toggle:disabled { color: var(--ink-faint); cursor: wait; }
.candidate-evidence dl { display: grid; gap: 8px; margin: 14px 0 0; }
.candidate-evidence dl div { display: grid; grid-template-columns: 88px 1fr; gap: 8px; }
.candidate-evidence dt { color: var(--ink-faint); font-size: 12px; }
.candidate-evidence dd { overflow-wrap: anywhere; margin: 0; color: var(--ink-soft); font-size: 12px; }
.candidate-honesty { color: var(--trust-pending); font-size: 12px; line-height: 1.6; }
.candidate-honesty.is-signed { color: var(--trust-signed); }
.candidate-review-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.candidate-action { padding: 0 14px; }
.candidate-action.is-accept {
  border-color: var(--trust-signed);
  background: var(--trust-signed);
  color: white;
}
.candidate-action.is-reject { color: var(--ink-soft); }
.candidate-action:disabled { cursor: not-allowed; opacity: 0.55; }
@media (max-width: 640px) {
  .asset-candidate-callout { margin-left: 0; align-items: flex-start; flex-wrap: wrap; }
  .candidate-summary { white-space: normal; }
  .candidate-open { margin-left: 20px; min-height: 44px; }
  .candidate-review-actions { display: grid; grid-template-columns: 1fr; }
  .candidate-action { min-height: 44px; width: 100%; }
}
</style>
