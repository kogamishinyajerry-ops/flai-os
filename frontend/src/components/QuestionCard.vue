<template>
  <section
    class="question-card"
    :class="`is-${status}`"
    :aria-busy="busy ? 'true' : 'false'"
    :aria-labelledby="headingId"
  >
    <div class="question-meta">
      <span class="question-kicker">需要补充</span>
      <span ref="statusEl" class="question-status" tabindex="-1" aria-live="polite">
        {{ statusText }}
      </span>
    </div>

    <h3 :id="headingId" class="question-prompt">{{ question.prompt }}</h3>
    <p v-if="question.description" class="question-description">{{ question.description }}</p>

    <form v-if="status === 'pending'" class="question-form" @submit.prevent="submitAnswer">
      <fieldset :disabled="busy || stale" class="question-fieldset">
        <legend class="sr-only">{{ question.prompt }}</legend>

        <template v-if="question.kind === 'single_choice'">
          <label v-for="option in question.options" :key="option.id" class="question-option">
            <input
              v-model="modeValue"
              type="radio"
              :name="`question-${question.id}`"
              :value="`option:${option.id}`"
            />
            <span class="option-copy">
              <span class="option-label">{{ option.label }}</span>
              <span v-if="option.description" class="option-description">{{ option.description }}</span>
            </span>
          </label>

          <label class="question-option custom-option">
            <input
              v-model="modeValue"
              type="radio"
              :name="`question-${question.id}`"
              value="text"
            />
            <span class="option-copy">
              <span class="option-label">自定义回答</span>
              <span class="option-description">选项都不准确时，写下你的实际情况。</span>
            </span>
          </label>
        </template>

        <label
          v-if="question.kind === 'free_text' || modeValue === 'text'"
          class="text-label"
          :for="`question-text-${question.id}`"
        >
          {{ question.kind === "free_text" ? "你的回答" : "自定义回答内容" }}
        </label>
        <textarea
          v-if="question.kind === 'free_text' || modeValue === 'text'"
          :id="`question-text-${question.id}`"
          v-model="textValue"
          class="question-textarea"
          rows="3"
          maxlength="4000"
          placeholder="请写下准确、可继续推进的信息"
          @keydown.meta.enter.prevent="submitAnswer"
          @keydown.ctrl.enter.prevent="submitAnswer"
        ></textarea>
      </fieldset>

      <div v-if="stale" class="question-stale" aria-live="polite">
        <span>当前状态可能已变化，重新核对后才能提交。</span>
        <button type="button" class="question-refresh" :disabled="busy" @click="emit('refresh')">
          {{ busy ? "核对中…" : "重新核对" }}
        </button>
      </div>
      <p
        v-if="visibleError"
        class="question-error"
        :class="{ 'is-request-failure': visibleRequestFailure }"
        role="alert"
      >{{ visibleError }}</p>
      <div class="question-actions">
        <span class="question-note">这是普通澄清，只会继续本次对话。</span>
        <button type="submit" class="question-submit cta-clay" :disabled="busy || stale">
          {{ busy ? "提交中…" : "提交回答" }}
        </button>
      </div>
    </form>

    <div v-else class="question-resolution" aria-live="polite">
      <template v-if="status === 'answered'">
        <span class="resolution-label">已回答</span>
        <span class="resolution-value">{{ answerLabel || "回答内容无法识别" }}</span>
      </template>
      <template v-else-if="status === 'expired'">
        <span class="resolution-label">已过期</span>
        <span class="resolution-value">回答未提交，请在下方继续说明需要的信息。</span>
      </template>
      <template v-else-if="status === 'superseded'">
        <span class="resolution-label">已被后续对话替代</span>
      </template>
      <template v-else>
        <span class="resolution-label question-unknown">状态无法核对，已停止交互。</span>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import {
  createSecureSubmissionId,
  effectiveQuestionStatus,
  questionAnswerLabel,
  validateQuestionSubmission,
} from "../utils/questionCardCore.js";

const props = defineProps({
  question: { type: Object, required: true },
  busy: { type: Boolean },
  error: { type: String },
  requestFailed: { type: Boolean },
  stale: { type: Boolean },
});
const emit = defineEmits(["submit", "refresh"]);

const nowMs = ref(Date.now());
const modeValue = ref(props.question.kind === "free_text" ? "text" : "");
const textValue = ref("");
const localError = ref("");
const submissionId = ref("");
const submittedHere = ref(false);
const statusEl = ref(null);
let expiryTimer = null;

const status = computed(() => effectiveQuestionStatus(props.question, nowMs.value));
const headingId = computed(() => `question-heading-${props.question.id}`);
const answerLabel = computed(() => questionAnswerLabel(props.question));
const visibleError = computed(() => localError.value || props.error || "");
const visibleRequestFailure = computed(() =>
  !localError.value && Boolean(props.error) && props.requestFailed === true
);
const statusText = computed(() => ({
  pending: "待你回答",
  answered: "回答已记录",
  expired: "问题已过期",
  superseded: "历史问题",
  unknown: "状态未核对",
})[status.value] || "状态未核对");

function resetDraft() {
  modeValue.value = props.question.kind === "free_text" ? "text" : "";
  textValue.value = "";
  localError.value = "";
  submissionId.value = "";
  submittedHere.value = false;
}

function scheduleExpiry() {
  if (expiryTimer) clearTimeout(expiryTimer);
  expiryTimer = null;
  const expires = Date.parse(props.question.expires_at);
  if (props.question.status !== "pending" || !Number.isFinite(expires)) return;
  const delay = Math.max(0, Math.min(expires - Date.now() + 20, 2_147_000_000));
  expiryTimer = setTimeout(() => {
    nowMs.value = Date.now();
    if (nowMs.value < expires) scheduleExpiry();
  }, delay);
}

watch(() => props.question.id, () => {
  resetDraft();
  nowMs.value = Date.now();
  scheduleExpiry();
});
watch(() => props.question.expires_at, scheduleExpiry);
watch(() => props.question.status, scheduleExpiry);
watch([modeValue, textValue], () => {
  if (props.busy) return;
  localError.value = "";
  submissionId.value = "";
});
watch(status, async (next, previous) => {
  if (next === "answered" && previous === "pending" && submittedHere.value) {
    await nextTick();
    statusEl.value?.focus();
  }
});

function draftShape() {
  if (modeValue.value.startsWith("option:")) {
    return { mode: "option", optionId: modeValue.value.slice(7), text: textValue.value };
  }
  return { mode: "text", optionId: "", text: textValue.value };
}

function submitAnswer() {
  if (props.busy) return;
  const submitNowMs = Date.now();
  nowMs.value = submitNowMs;
  const checked = validateQuestionSubmission(props.question, draftShape(), {
    stale: props.stale === true,
    nowMs: submitNowMs,
  });
  if (checked.ok !== true) {
    localError.value = checked.error;
    return;
  }
  try {
    if (!submissionId.value) submissionId.value = createSecureSubmissionId();
  } catch {
    localError.value = "浏览器无法生成稳定提交标识，请刷新后重试";
    return;
  }
  submittedHere.value = true;
  emit("submit", {
    questionId: props.question.id,
    questionRevision: props.question.revision,
    submissionId: submissionId.value,
    payload: checked.payload,
  });
}

scheduleExpiry();
onBeforeUnmount(() => {
  if (expiryTimer) clearTimeout(expiryTimer);
});
</script>

<style scoped>
.question-card {
  margin: var(--space-4) 0 var(--space-5);
  padding: var(--space-5);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-left: 3px solid var(--hairline);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  scroll-margin-bottom: 190px;
}
.question-card.is-pending { border-left-color: var(--clay); }
.question-card.is-expired,
.question-card.is-unknown { border-left-color: var(--trust-pending); }
.question-card.is-answered,
.question-card.is-superseded { border-left-color: var(--hairline); }
.question-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.question-kicker {
  color: var(--ink-soft);
  font-size: var(--fs-2xs);
  font-weight: 750;
  letter-spacing: 1px;
}
.question-card.is-pending .question-kicker,
.question-card.is-pending .question-status { color: var(--clay-deep); }
.question-card.is-expired .question-status,
.question-card.is-expired .resolution-label,
.question-card.is-unknown .question-status { color: var(--trust-pending); }
.question-status {
  color: var(--ink-faint);
  font-size: var(--fs-xs);
}
.question-status:focus-visible,
.question-option:has(input:focus-visible),
.question-textarea:focus-visible,
.question-submit:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
}
.question-prompt {
  margin: 0;
  color: var(--ink);
  font-family: var(--serif);
  font-size: var(--fs-h3);
  font-weight: 600;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.question-description {
  margin: var(--space-2) 0 0;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  line-height: 1.6;
}
.question-form { margin-top: var(--space-4); }
.question-fieldset {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.question-option {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  min-height: 44px;
  padding: 10px 12px;
  color: var(--ink);
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  cursor: pointer;
}
.question-option:has(input:checked) {
  border-color: var(--clay);
  background: color-mix(in srgb, var(--clay) 8%, var(--surface-raised));
}
.question-option input {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  margin: 2px 0 0;
  accent-color: var(--clay);
}
.option-copy { min-width: 0; }
.option-label {
  display: block;
  font-size: var(--fs-body);
  font-weight: 650;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.option-description {
  display: block;
  margin-top: 2px;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
  line-height: 1.5;
}
.text-label {
  color: var(--ink-mid);
  font-size: var(--fs-xs);
  font-weight: 650;
}
.question-textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 96px;
  resize: vertical;
  padding: var(--space-3);
  color: var(--ink);
  background: var(--paper-cream);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  font: inherit;
  line-height: 1.55;
}
.question-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-top: var(--space-3);
}
.question-note { color: var(--ink-faint); font-size: var(--fs-xs); line-height: 1.5; }
.question-submit {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 0;
  border-radius: var(--radius-md);
  cursor: pointer;
}
.question-submit:disabled { cursor: not-allowed; opacity: .58; }
.question-error,
.question-stale {
  margin: var(--space-3) 0 0;
  font-size: var(--fs-sm);
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.question-error { color: var(--trust-pending); }
.question-error.is-request-failure { color: var(--trust-fail); }
.question-stale {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--trust-pending);
}
.question-refresh {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 0 var(--space-4);
  color: var(--ink-mid);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  cursor: pointer;
}
.question-refresh:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
}
.question-refresh:disabled { cursor: not-allowed; opacity: .58; }
.question-resolution {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: var(--space-3);
  color: var(--ink-mid);
  background: var(--paper-rail);
  border-radius: var(--radius-md);
  font-size: var(--fs-body);
  line-height: 1.55;
}
.resolution-label { flex: 0 0 auto; color: var(--ink-soft); font-weight: 700; }
.resolution-value { min-width: 0; overflow-wrap: anywhere; }
.question-unknown { color: var(--trust-pending); }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
@media (max-width: 520px) {
  .question-card {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    padding: var(--space-4);
  }
  .question-meta,
  .question-actions,
  .question-stale,
  .question-resolution { align-items: stretch; flex-direction: column; }
  .question-submit,
  .question-refresh { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .question-card,
  .question-option,
  .question-textarea,
  .question-submit,
  .question-refresh {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto;
  }
}
</style>
