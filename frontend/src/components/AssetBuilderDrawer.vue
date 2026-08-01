<template>
  <el-drawer
    :model-value="modelValue"
    direction="rtl"
    size="560px"
    class="asset-builder-drawer"
    :aria-describedby="drawerDescriptionId"
    :close-on-click-modal="!generating"
    :close-on-press-escape="!generating"
    :before-close="beforeClose"
    @opened="focusActiveSurface"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header="{ titleId, titleClass }">
      <div class="asset-builder-head">
        <span class="asset-builder-kicker">WORK CASE → REUSABLE ASSET</span>
        <h2 :id="titleId" :class="titleClass">沉淀本次工作</h2>
        <p :id="drawerDescriptionId">把一项真实工作整理成 Task Pattern 与 Skill 待审草稿。</p>
      </div>
    </template>

    <div ref="builderBody" class="asset-builder-body">
      <ol class="asset-builder-steps" aria-label="资产草稿步骤">
        <li
          v-for="item in STEPS"
          :key="item.id"
          :class="{ 'is-current': step === item.id, 'is-past': step > item.id }"
          :aria-current="step === item.id ? 'step' : undefined"
        >
          <span class="asset-step-num num-token">{{ item.id }}</span>
          <span>{{ item.label }}</span>
        </li>
      </ol>

      <section v-if="step < 3" class="asset-builder-section asset-focus-flow" aria-labelledby="asset-focus-question-title">
        <div class="asset-focus-status">
          <span class="asset-section-index">
            {{ currentQuestion.step === 1 ? "01 · WORK CASE" : "02 · GENERALIZE" }}
          </span>
          <span class="asset-focus-count num-token">问题 {{ focusState.position }} / {{ focusState.total }}</span>
        </div>

        <div
          class="asset-focus-progress"
          role="progressbar"
          aria-label="资产草稿问题进度"
          aria-valuemin="1"
          :aria-valuemax="focusState.total"
          :aria-valuenow="focusState.position"
        >
          <span :style="{ width: `${focusProgress}%` }"></span>
        </div>

        <div v-if="currentQuestion.step === 1" class="asset-source-line" aria-label="当前 Work Case 来源">
          <el-icon aria-hidden="true"><Link /></el-icon>
          <span>当前会话</span>
          <strong class="num-token">{{ conversationId }}</strong>
          <span class="asset-source-state">生成时由平台解析并校验</span>
        </div>

        <div class="asset-focus-copy">
          <span>{{ currentQuestion.group }} · {{ currentQuestion.label }}</span>
          <h3 id="asset-focus-question-title" tabindex="-1">{{ currentQuestion.prompt }}</h3>
          <p id="asset-focus-question-helper">{{ currentQuestion.helper }}</p>
        </div>

        <el-form label-position="top" class="asset-builder-form asset-focus-form" :disabled="generating" @submit.prevent>
          <el-form-item :label="currentQuestion.label">
            <el-input
              :key="currentQuestion.id"
              :id="currentQuestion.fieldId"
              :model-value="form[currentQuestion.field]"
              :type="currentQuestion.multiline ? 'textarea' : 'text'"
              :autosize="currentQuestion.multiline ? { minRows: currentQuestion.minRows, maxRows: currentQuestion.maxRows } : undefined"
              :maxlength="currentQuestion.maxlength"
              :show-word-limit="Boolean(currentQuestion.maxlength)"
              :placeholder="currentQuestion.placeholder"
              :aria-label="currentQuestion.prompt"
              aria-describedby="asset-focus-question-helper"
              @update:model-value="setCurrentAnswer"
            />
          </el-form-item>
        </el-form>

        <div v-if="previewError" class="asset-builder-error" role="alert">
          <el-icon aria-hidden="true"><Warning /></el-icon>
          <span>{{ previewError }}</span>
        </div>

        <div class="asset-answer-summary">
          <button
            type="button"
            class="asset-summary-toggle"
            :aria-expanded="summaryOpen"
            aria-controls="asset-answered-list"
            @click="summaryOpen = !summaryOpen"
          >
            <span>已整理 {{ focusState.answeredCount }} / {{ focusState.total }} 项</span>
            <span>{{ summaryOpen ? "收起摘要" : "查看摘要" }}</span>
          </button>
          <div id="asset-answered-list" v-show="summaryOpen">
            <ul v-if="answeredQuestions.length" class="asset-answered-list">
              <li v-for="question in answeredQuestions" :key="question.id">
                <button
                  type="button"
                  :class="{ 'is-current': question.id === currentQuestion.id }"
                  @click="goToQuestion(question.id)"
                >
                  <span>{{ question.label }}</span>
                  <strong>{{ answerSummary(question) }}</strong>
                </button>
              </li>
            </ul>
            <p v-else class="asset-summary-empty">
              还没有已整理的回答。可以先跳到下一问，稍后再补。
            </p>
          </div>
        </div>
      </section>

      <section v-else class="asset-builder-section asset-review" aria-labelledby="asset-review-title">
        <div class="asset-section-head asset-review-head">
          <span class="asset-section-index">03 · GOVERNED DRAFT</span>
          <h3 id="asset-review-title" tabindex="-1">待审草稿包</h3>
          <p>确定性投影已经生成。这里没有执行、注册、晋级或批准动作。</p>
        </div>

        <template v-if="preview">
          <div class="asset-review-status" :class="{ 'needs-revision': !reviewReady }">
            <span class="asset-review-state">
              <el-icon aria-hidden="true"><Warning /></el-icon>
              {{ reviewReady ? "结构校验完成 · 等待人工审核" : `需补全 · ${preview.validation.blocking_count} 项阻断` }}
            </span>
            <span class="num-token">{{ shortDigest }}</span>
          </div>

          <div class="asset-honesty-floor">
            <el-icon aria-hidden="true"><Lock /></el-icon>
            <p>
              <strong>这是待审草稿，不是已登记资产。</strong>
              未调用 LLM，未写数据库，未执行工作，也未注册或晋级。下载不等于注册。
            </p>
          </div>

          <article class="asset-draft-card">
            <header>
              <span class="asset-draft-type">TASK PATTERN · DRAFT</span>
              <span class="asset-draft-id num-token">{{ preview.task_pattern.suggested_id }}</span>
            </header>
            <h4>{{ preview.task_pattern.title || "标题待补全" }}</h4>
            <dl class="asset-draft-facts">
              <div><dt>触发</dt><dd>{{ preview.task_pattern.trigger || "待补全" }}</dd></div>
              <div><dt>结果</dt><dd>{{ preview.task_pattern.desired_outcome || "待补全" }}</dd></div>
              <div><dt>输入</dt><dd>{{ joinOrPending(preview.task_pattern.inputs) }}</dd></div>
              <div><dt>输出</dt><dd>{{ joinOrPending(preview.task_pattern.outputs) }}</dd></div>
            </dl>
          </article>

          <article class="asset-draft-card">
            <header>
              <span class="asset-draft-type">SKILL · DRAFT</span>
              <span class="asset-draft-id num-token">{{ preview.skill.suggested_id }}</span>
            </header>
            <h4>{{ preview.skill.name || "名称待补全" }}</h4>
            <p class="asset-draft-description">{{ preview.skill.description || "描述待补全" }}</p>
            <div class="asset-draft-list">
              <span>可复用步骤</span>
              <ol v-if="preview.skill.instructions?.length">
                <li v-for="(item, index) in preview.skill.instructions" :key="`${item}-${index}`">{{ item }}</li>
              </ol>
              <p v-else>待补全</p>
            </div>
            <div class="asset-draft-list">
              <span>人工判断点</span>
              <ul v-if="preview.skill.human_boundaries?.length">
                <li v-for="(item, index) in preview.skill.human_boundaries" :key="`${item}-${index}`">{{ item }}</li>
              </ul>
              <p v-else>待补全</p>
            </div>
          </article>

          <article class="asset-validation-card">
            <header>
              <span>确定性校验</span>
              <span class="num-token">{{ preview.validation.blocking_count }} 阻断 · {{ preview.validation.warning_count }} 提醒</span>
            </header>
            <ul v-if="preview.validation.issues.length" class="asset-issue-list">
              <li
                v-for="issue in preview.validation.issues"
                :key="`${issue.code}-${issue.path}`"
                :class="`is-${issue.severity}`"
              >
                <strong>{{ issue.severity === "blocking" ? "需补全" : "待核" }}</strong>
                <span>{{ issue.message }}</span>
                <code>{{ issue.path }}</code>
                <button
                  v-if="issueTarget(issue.path)"
                  type="button"
                  class="asset-issue-action"
                  @click="goToIssue(issue.path)"
                >
                  返回补全
                </button>
              </li>
            </ul>
            <p v-else class="asset-validation-empty">没有结构阻断项；仍须按下列要求人工审核。</p>
          </article>

          <article class="asset-review-gate">
            <span class="asset-draft-type">HUMAN REVIEW GATE</span>
            <h4>{{ reviewReady ? "可以提交给工程师审核" : "补全阻断项后才能进入人工审核" }}</h4>
            <ul>
              <li v-for="item in preview.review.requirements" :key="item">{{ item }}</li>
            </ul>
            <p>审核决定尚未记录（{{ preview.review.decision_state }}）。本页不提供批准按钮。</p>
          </article>
        </template>

        <div v-else class="asset-review-empty">
          <el-icon aria-hidden="true"><Warning /></el-icon>
          <p>尚未生成确定性预览。返回上一步补充方法后再生成。</p>
        </div>
      </section>
    </div>

    <template #footer>
      <div class="asset-builder-footer">
        <p>关闭后本会话内保留草稿 · 只生成与下载待审 JSON · 不执行 · 不注册 · 不晋级</p>
        <div class="asset-builder-actions">
          <button v-if="step < 3 && focusState.previousId" type="button" class="asset-btn is-secondary" :disabled="generating" @click="goToQuestion(focusState.previousId)">
            <el-icon aria-hidden="true"><ArrowLeft /></el-icon>上一问
          </button>
          <button v-else-if="step === 3" type="button" class="asset-btn is-secondary" :disabled="generating" @click="goToQuestion(lastQuestion.id)">
            <el-icon aria-hidden="true"><ArrowLeft /></el-icon>返回整理
          </button>
          <button v-else type="button" class="asset-btn is-secondary" :disabled="generating" @click="closeDrawer">取消</button>

          <button v-if="step < 3 && focusState.nextId" type="button" class="asset-btn is-primary" :disabled="generating" @click="goToQuestion(focusState.nextId)">
            下一问<el-icon aria-hidden="true"><ArrowRight /></el-icon>
          </button>
          <button v-else-if="step < 3" type="button" class="asset-btn is-primary" :disabled="generating" @click="generatePreview">
            <el-icon v-if="generating" class="is-loading" aria-hidden="true"><Loading /></el-icon>
            {{ generating ? "正在确定性校验…" : "生成待审草稿" }}
          </button>
          <button v-else type="button" class="asset-btn is-primary" :disabled="reviewReady !== true" @click="downloadPreview">
            <el-icon aria-hidden="true"><Download /></el-icon>下载待审 JSON
          </button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, reactive, ref, useId, watch } from "vue";
import {
  ArrowLeft,
  ArrowRight,
  Download,
  Link,
  Loading,
  Lock,
  Warning,
} from "@element-plus/icons-vue";
import { previewConversationAssetDraft } from "../api/assetDrafts.js";
import {
  ASSET_DRAFT_FOCUS_QUESTIONS,
  assetDraftFocusState,
  assetDraftQuestionForIssue,
  buildAssetDraftPreviewRequest,
  normalizeAssetDraftPreview,
  seedAssetDraftGeneralization,
  serializeAssetDraftDownload,
} from "../utils/assetDrafts.js";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversationId: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  initialStep: { type: Number, default: 1 },
  initialGeneralization: { type: Object, default: null },
  initialPreview: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const STEPS = [
  { id: 1, label: "本次工作" },
  { id: 2, label: "复用方法" },
  { id: 3, label: "待审草稿" },
];
const LIST_FIELDS = [
  "inputs",
  "outputs",
  "steps",
  "evidence_requirements",
  "human_decision_points",
  "limitations",
];
const form = reactive({
  title: "",
  trigger: "",
  desired_outcome: "",
  inputs: "",
  outputs: "",
  steps: "",
  evidence_requirements: "",
  human_decision_points: "",
  limitations: "",
});
const step = ref(1);
const activeQuestionId = ref(ASSET_DRAFT_FOCUS_QUESTIONS[0].id);
const summaryOpen = ref(false);
const generating = ref(false);
const previewError = ref("");
const preview = ref(null);
const builderBody = ref(null);
const loadedConversationId = ref(null);
const drawerDescriptionId = `asset-builder-description-${useId()}`;

const focusState = computed(() =>
  assetDraftFocusState(activeQuestionId.value, form),
);
const currentQuestion = computed(() => focusState.value.question);
const lastQuestion = ASSET_DRAFT_FOCUS_QUESTIONS.at(-1);
const focusProgress = computed(() =>
  Math.round((focusState.value.position / focusState.value.total) * 100),
);
const answeredQuestions = computed(() => {
  const answered = new Set(focusState.value.answeredIds);
  return ASSET_DRAFT_FOCUS_QUESTIONS.filter((question) => answered.has(question.id));
});

const reviewReady = computed(
  () =>
    preview.value?.validation?.state === "ready_for_human_review" &&
    preview.value?.review?.ready === true,
);
const shortDigest = computed(() => {
  const digest = preview.value?.draft_digest || "";
  return digest.length > 25 ? `${digest.slice(0, 22)}…` : digest;
});

function toFormValue(value) {
  const request = buildAssetDraftPreviewRequest(value);
  const next = request.generalization;
  return {
    ...next,
    ...Object.fromEntries(LIST_FIELDS.map((field) => [field, next[field].join("\n")])),
  };
}

function assignForm(value) {
  const next = toFormValue(value);
  for (const key of Object.keys(form)) form[key] = next[key];
}

function resetFromSource() {
  const seeded = props.initialGeneralization || seedAssetDraftGeneralization(props.messages);
  assignForm(seeded);
  step.value = [1, 2, 3].includes(props.initialStep) ? props.initialStep : 1;
  previewError.value = "";
  preview.value = props.initialPreview
    ? normalizeAssetDraftPreview(props.initialPreview)
    : null;
  if (step.value === 3 && !preview.value) step.value = 2;
  if (step.value < 3) {
    activeQuestionId.value =
      ASSET_DRAFT_FOCUS_QUESTIONS.find((question) => question.step === step.value)?.id ||
      ASSET_DRAFT_FOCUS_QUESTIONS[0].id;
  }
  summaryOpen.value = false;
  loadedConversationId.value = props.conversationId;
}

watch(
  () => props.modelValue,
  (opened) => {
    if (!opened) return;
    if (loadedConversationId.value === props.conversationId) return;
    resetFromSource();
  },
  { immediate: true },
);

function setCurrentAnswer(value) {
  form[currentQuestion.value.field] = value;
}

function answerSummary(question) {
  const value = form[question.field];
  const text = (Array.isArray(value) ? value.join("、") : String(value || ""))
    .replace(/\s+/g, " ")
    .trim();
  return text.length > 72 ? `${text.slice(0, 69)}…` : text;
}

async function focusActiveSurface() {
  await nextTick();
  const targetId = step.value === 3
    ? "asset-review-title"
    : currentQuestion.value.fieldId;
  const target = builderBody.value?.querySelector(`[id="${targetId}"]`);
  target?.focus({ preventScroll: true });
}

async function goToQuestion(questionId) {
  let next;
  try {
    next = assetDraftFocusState(questionId, form);
  } catch {
    return;
  }
  activeQuestionId.value = next.questionId;
  step.value = next.step;
  summaryOpen.value = false;
  await nextTick();
  const scrollContainer = builderBody.value?.closest(".el-drawer__body");
  if (scrollContainer) scrollContainer.scrollTop = 0;
  await focusActiveSurface();
}

async function showReview() {
  step.value = 3;
  summaryOpen.value = false;
  await nextTick();
  const scrollContainer = builderBody.value?.closest(".el-drawer__body");
  if (scrollContainer) scrollContainer.scrollTop = 0;
  await focusActiveSurface();
}

function issueTarget(path) {
  return assetDraftQuestionForIssue(path);
}

async function goToIssue(path) {
  const questionId = issueTarget(path);
  if (!questionId) return;
  await goToQuestion(questionId);
}

function closeDrawer() {
  if (generating.value) return;
  emit("update:modelValue", false);
}

function beforeClose(done) {
  if (generating.value) return;
  done();
}

async function generatePreview() {
  if (generating.value) return;
  generating.value = true;
  previewError.value = "";
  try {
    preview.value = await previewConversationAssetDraft(props.conversationId, form);
    await showReview();
  } catch (error) {
    previewError.value = error?.detail || error?.message || "资产草稿预览生成失败";
  } finally {
    generating.value = false;
  }
}

function joinOrPending(items) {
  return Array.isArray(items) && items.length ? items.join("、") : "待补全";
}

function downloadPreview() {
  if (!preview.value || reviewReady.value !== true) return;
  const data = serializeAssetDraftDownload(preview.value);
  const blob = new Blob([data], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const digest = (preview.value.draft_digest || "draft").replace(/^sha256:/, "").slice(0, 12);
  anchor.href = url;
  anchor.download = `flai-asset-draft-${digest}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
</script>

<style>
.asset-builder-drawer {
  --el-drawer-padding-primary: 0;
  --asset-primary-bg: var(--clay-deep);
  --asset-primary-ink: #ffffff;
  width: min(560px, 100vw) !important;
  background: var(--surface-raised);
  color: var(--ink);
}
.asset-builder-drawer .el-drawer__header {
  flex: none;
  margin: 0;
  padding: var(--space-5) var(--space-6) var(--space-4);
  border-bottom: 1px solid var(--hairline-soft);
}
.asset-builder-drawer .el-drawer__close-btn {
  width: 36px;
  height: 36px;
  margin: 0;
  border-radius: var(--radius-md);
  color: var(--ink-soft);
}
.asset-builder-drawer .el-drawer__body {
  min-height: 0;
  padding: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.asset-builder-drawer .el-drawer__footer {
  flex: none;
  padding: 0;
  border-top: 1px solid var(--hairline-soft);
  background: var(--surface-raised);
}
.asset-builder-head { min-width: 0; padding-right: var(--space-5); }
.asset-builder-kicker,
.asset-section-index,
.asset-draft-type {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: var(--fs-2xs);
  letter-spacing: 0.08em;
}
.asset-builder-head h2 {
  margin: var(--space-1) 0 0;
  font-family: var(--serif);
  font-size: var(--fs-h2);
  font-weight: 600;
}
.asset-builder-head p {
  margin: var(--space-1) 0 0;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  line-height: 1.45;
}
.asset-builder-body { min-height: 100%; }
.asset-builder-steps {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-1);
  margin: 0;
  padding: var(--space-3) var(--space-6);
  border-bottom: 1px solid var(--hairline-soft);
  background: color-mix(in srgb, var(--surface-raised) 94%, transparent);
  backdrop-filter: blur(10px);
  list-style: none;
}
.asset-builder-steps li {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--ink-soft);
  font-size: var(--fs-xs);
}
.asset-builder-steps li:not(:last-child)::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--hairline);
}
.asset-builder-steps li.is-current { color: var(--ink); font-weight: 650; }
.asset-builder-steps li.is-past { color: var(--ink-soft); }
.asset-step-num {
  flex: none;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border: 1px solid var(--hairline);
  border-radius: 50%;
  background: var(--paper-rail);
  font-size: var(--fs-2xs);
}
.asset-builder-steps li.is-current .asset-step-num {
  border-color: var(--focus-ring-clay);
  background: var(--select-tint-clay);
  color: var(--ink);
}
.asset-builder-section { padding: var(--space-6); }
.asset-focus-flow {
  min-height: min(640px, calc(100vh - 210px));
  display: flex;
  flex-direction: column;
}
.asset-focus-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.asset-focus-count { color: var(--ink-soft); font-size: var(--fs-2xs); }
.asset-focus-progress {
  width: 100%;
  height: 2px;
  margin-top: var(--space-3);
  overflow: hidden;
  border-radius: 999px;
  background: var(--hairline-soft);
}
.asset-focus-progress > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--clay);
  transition: width var(--motion-fast) var(--ease-out-soft);
}
.asset-source-line {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  margin-top: var(--space-4);
  color: var(--ink-soft);
  font-size: var(--fs-2xs);
}
.asset-source-line > strong {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
  font-size: var(--fs-2xs);
}
.asset-focus-copy { max-width: 480px; margin-top: clamp(36px, 7vh, 72px); }
.asset-focus-copy > span {
  color: var(--clay-deep);
  font-size: var(--fs-xs);
  font-weight: 700;
}
.asset-focus-copy h3 {
  margin: var(--space-2) 0 0;
  font-family: var(--serif);
  font-size: clamp(1.45rem, 3vw, 1.8rem);
  font-weight: 600;
  line-height: 1.28;
  text-wrap: balance;
}
.asset-focus-copy h3:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 4px;
  border-radius: 2px;
}
.asset-focus-copy p {
  max-width: 440px;
  margin: var(--space-3) 0 0;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.6;
}
.asset-focus-form { margin-top: var(--space-6); }
.asset-focus-form .el-form-item { margin-bottom: 0; }
.asset-focus-form .el-form-item__label { color: var(--ink-soft); font-size: var(--fs-xs); }
.asset-focus-form .el-input__wrapper,
.asset-focus-form .el-textarea__inner {
  font-size: var(--fs-body);
  line-height: 1.65;
}
.asset-answer-summary { margin-top: auto; padding-top: clamp(36px, 7vh, 72px); }
.asset-summary-toggle {
  width: 100%;
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0;
  border: 0;
  border-top: 1px solid var(--hairline-soft);
  background: transparent;
  color: var(--ink-soft);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
}
.asset-summary-toggle span:first-child { color: var(--ink); font-weight: 650; }
.asset-summary-toggle:hover span:last-child { color: var(--ink); }
.asset-summary-toggle:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}
.asset-answered-list {
  max-height: 230px;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: var(--space-2) 0 0;
  overflow-y: auto;
  list-style: none;
}
.asset-answered-list button {
  width: 100%;
  min-height: 44px;
  display: grid;
  grid-template-columns: minmax(90px, auto) minmax(0, 1fr);
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--ink-soft);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.asset-answered-list button:hover,
.asset-answered-list button.is-current { border-color: var(--hairline); background: var(--paper-rail); }
.asset-answered-list button:focus-visible { outline: 2px solid var(--focus-ring-clay); outline-offset: 2px; }
.asset-answered-list span { color: var(--ink); font-size: var(--fs-xs); font-weight: 650; }
.asset-answered-list strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-xs);
  font-weight: 450;
}
.asset-summary-empty { margin: var(--space-2) 0 0; color: var(--ink-soft); font-size: var(--fs-xs); }
.asset-section-head { margin-bottom: var(--space-5); }
.asset-section-head h3 {
  margin: var(--space-1) 0 0;
  font-family: var(--serif);
  font-size: var(--fs-h3);
  font-weight: 600;
}
.asset-section-head h3:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 4px;
  border-radius: 2px;
}
.asset-section-head p {
  margin: var(--space-2) 0 0;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.55;
}
.asset-source-state { flex: none; display: inline-flex; align-items: center; gap: var(--space-1); color: var(--ink-soft); font-size: var(--fs-2xs); }
.asset-source-state::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--trust-pending); }
.asset-builder-form .el-form-item { margin-bottom: var(--space-5); }
.asset-builder-form .el-form-item__label {
  padding: 0 0 var(--space-2);
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  font-weight: 650;
  line-height: 1.35;
}
.asset-builder-form .el-input__wrapper,
.asset-builder-form .el-textarea__inner {
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  box-shadow: 0 0 0 1px var(--hairline) inset;
}
.asset-builder-form .el-input__wrapper.is-focus,
.asset-builder-form .el-textarea__inner:focus {
  box-shadow: 0 0 0 1px var(--focus-ring-clay) inset, 0 0 0 3px rgba(var(--clay-rgb), 0.08);
}
.asset-builder-error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid color-mix(in srgb, var(--trust-fail) 30%, var(--hairline));
  border-radius: var(--radius-md);
  color: var(--trust-fail);
  font-size: var(--fs-sm);
  line-height: 1.45;
}
.asset-builder-error .el-icon { color: var(--trust-fail); }
.asset-review { display: flex; flex-direction: column; gap: var(--space-4); }
.asset-review-head { margin-bottom: 0; }
.asset-review-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid color-mix(in srgb, var(--trust-pending) 34%, var(--hairline));
  border-radius: var(--radius-md);
  color: var(--ink);
  background: color-mix(in srgb, var(--trust-pending) 7%, var(--surface-raised));
  font-size: var(--fs-xs);
}
.asset-review-state { display: inline-flex; align-items: center; gap: var(--space-2); font-weight: 650; }
.asset-review-state .el-icon { color: var(--trust-pending); }
.asset-review-status > .num-token { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink-soft); }
.asset-review-status.needs-revision {
  border-color: color-mix(in srgb, var(--trust-fail) 36%, var(--hairline));
  background: color-mix(in srgb, var(--trust-fail) 7%, var(--surface-raised));
  color: var(--trust-fail);
}
.asset-review-status.needs-revision .asset-review-state,
.asset-review-status.needs-revision .asset-review-state .el-icon { color: var(--trust-fail); }
.asset-honesty-floor {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--paper-rail);
  color: var(--ink-soft);
}
.asset-honesty-floor .el-icon { flex: none; margin-top: 2px; color: var(--trust-pending); }
.asset-honesty-floor p { margin: 0; font-size: var(--fs-xs); line-height: 1.55; }
.asset-honesty-floor strong { display: block; margin-bottom: var(--space-1); color: var(--ink); }
.asset-draft-card,
.asset-validation-card,
.asset-review-gate {
  padding: var(--space-4);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg);
  background: var(--surface-raised);
  box-shadow: var(--shadow-card);
  overflow-wrap: anywhere;
}
.asset-draft-card header,
.asset-validation-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.asset-draft-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink-soft);
  font-size: var(--fs-2xs);
}
.asset-draft-card h4,
.asset-review-gate h4 {
  margin: var(--space-3) 0;
  color: var(--ink);
  font-size: var(--fs-body);
  font-weight: 700;
}
.asset-draft-description { margin: calc(-1 * var(--space-2)) 0 var(--space-3); color: var(--ink-soft); font-size: var(--fs-sm); line-height: 1.5; }
.asset-draft-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); margin: 0; }
.asset-draft-facts div { min-width: 0; }
.asset-draft-facts dt,
.asset-draft-list > span { color: var(--ink-soft); font-size: var(--fs-2xs); font-weight: 650; }
.asset-draft-facts dd { margin: var(--space-1) 0 0; color: var(--ink-soft); font-size: var(--fs-xs); line-height: 1.45; }
.asset-draft-list { margin-top: var(--space-3); }
.asset-draft-list ol,
.asset-draft-list ul,
.asset-draft-list p,
.asset-review-gate ul {
  margin: var(--space-2) 0 0;
  padding-left: 1.25rem;
  color: var(--ink-soft);
  font-size: var(--fs-xs);
  line-height: 1.55;
}
.asset-validation-card header { color: var(--ink-soft); font-size: var(--fs-xs); font-weight: 650; }
.asset-validation-card header .num-token { color: var(--ink-soft); font-size: var(--fs-2xs); }
.asset-issue-list { display: flex; flex-direction: column; gap: var(--space-2); margin: var(--space-3) 0 0; padding: 0; list-style: none; }
.asset-issue-list li {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-2);
  padding: var(--space-2);
  border-left: 2px solid var(--trust-pending);
  background: color-mix(in srgb, var(--trust-pending) 6%, var(--surface-raised));
  color: var(--ink-soft);
  font-size: var(--fs-xs);
}
.asset-issue-list li.is-blocking { border-left-color: var(--trust-fail); }
.asset-issue-list li.is-blocking strong { color: var(--trust-fail); }
.asset-issue-list strong { color: var(--ink); }
.asset-issue-list code { grid-column: 2; color: var(--ink-soft); font-family: var(--mono); font-size: var(--fs-2xs); overflow-wrap: anywhere; }
.asset-issue-action {
  grid-column: 2;
  justify-self: start;
  min-height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  color: var(--ink);
  font: inherit;
  font-size: var(--fs-xs);
  font-weight: 650;
  cursor: pointer;
}
.asset-issue-action:hover { border-color: var(--focus-ring-clay); }
.asset-issue-action:focus-visible { outline: 2px solid var(--focus-ring-clay); outline-offset: 2px; }
.asset-validation-empty { margin: var(--space-3) 0 0; color: var(--ink-soft); font-size: var(--fs-xs); }
.asset-review-gate { border-color: color-mix(in srgb, var(--trust-pending) 30%, var(--hairline)); }
.asset-review-gate ul { padding-left: 1.1rem; }
.asset-review-gate > p { margin: var(--space-3) 0 0; color: var(--ink-soft); font-size: var(--fs-xs); line-height: 1.45; }
.asset-review-empty { min-height: 240px; display: grid; place-items: center; align-content: center; gap: var(--space-3); color: var(--ink-soft); text-align: center; }
.asset-review-empty p { max-width: 320px; margin: 0; font-size: var(--fs-sm); line-height: 1.5; }
.asset-builder-footer { padding: var(--space-3) var(--space-6) max(var(--space-4), env(safe-area-inset-bottom)); }
.asset-builder-footer > p { margin: 0 0 var(--space-2); color: var(--ink-soft); font-size: var(--fs-2xs); text-align: right; }
.asset-builder-actions { display: flex; justify-content: flex-end; gap: var(--space-2); }
.asset-btn {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: 0 var(--space-4);
  border-radius: var(--radius-md);
  font: inherit;
  font-size: var(--fs-sm);
  font-weight: 650;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out-soft), border-color var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.asset-btn.is-secondary { border: 1px solid var(--hairline); background: var(--surface-raised); color: var(--ink-soft); }
.asset-btn.is-secondary:hover:not(:disabled) { border-color: var(--ink-soft); color: var(--ink); }
.asset-btn.is-primary { border: 1px solid var(--asset-primary-bg); background: var(--asset-primary-bg); color: var(--asset-primary-ink); }
.asset-btn.is-primary:hover:not(:disabled) { box-shadow: 0 0 0 3px rgba(var(--clay-rgb), 0.12); }
.asset-btn:disabled { opacity: 0.45; cursor: not-allowed; }
:root[data-theme="dark"] .asset-builder-drawer { --asset-primary-ink: #2b2622; }
:root[data-theme="dark"] .asset-review-status.needs-revision,
:root[data-theme="dark"] .asset-review-status.needs-revision .asset-review-state,
:root[data-theme="dark"] .asset-builder-error,
:root[data-theme="dark"] .asset-issue-list li.is-blocking strong { color: var(--ink); }
@media (max-width: 639px) {
  .asset-builder-drawer { width: 100vw !important; }
  .asset-builder-drawer .el-drawer__header { padding: var(--space-4); }
  .asset-builder-drawer .el-drawer__close-btn { width: 44px; height: 44px; }
  .asset-builder-steps { padding: var(--space-3) var(--space-4); }
  .asset-builder-steps li { gap: var(--space-1); font-size: var(--fs-2xs); }
  .asset-builder-steps li:not(:last-child)::after { display: none; }
  .asset-builder-section { padding: var(--space-4); }
  .asset-focus-flow { min-height: calc(100vh - 210px); }
  .asset-focus-copy { margin-top: var(--space-6); }
  .asset-focus-copy h3 { font-size: 1.4rem; }
  .asset-source-line { align-items: flex-start; flex-wrap: wrap; }
  .asset-source-line > strong { flex-basis: calc(100% - 90px); }
  .asset-source-state { width: 100%; padding-left: calc(var(--space-2) + 1em); }
  .asset-focus-form { margin-top: var(--space-5); }
  .asset-answer-summary { padding-top: var(--space-6); }
  .asset-summary-toggle { min-height: 44px; }
  .asset-answered-list { max-height: 180px; }
  .asset-answered-list button { grid-template-columns: 88px minmax(0, 1fr); }
  .asset-draft-facts { grid-template-columns: 1fr; }
  .asset-builder-footer { padding: var(--space-3) var(--space-4) max(var(--space-4), env(safe-area-inset-bottom)); }
  .asset-builder-footer > p { text-align: left; }
  .asset-builder-actions { display: grid; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); }
  .asset-btn { min-height: 44px; padding-inline: var(--space-3); }
  .asset-issue-action { min-height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
  .el-drawer-fade-enter-active,
  .el-drawer-fade-leave-active,
  .asset-builder-drawer { transition: none !important; }
  .asset-btn { transition: none; }
  .asset-focus-progress > span { transition: none; }
  .asset-builder-drawer .is-loading { animation: none !important; }
}
</style>
