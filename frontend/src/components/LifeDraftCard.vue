<template>
  <!--
    持久化模型草稿卡片（life_guide_agent 教学 demo 专用）。
    只读展示服务端 record 绑定的 9 字段 Generalization；预览按钮只提交
    record id + expected content digest，不把 payload 重新交给客户端声明来源。
    返回修改会开启下一轮，并产生新的不可变 record。
    本卡片不提供签发/批准——人审唯一签发（铁律 1）。
  -->
  <div class="life-draft-card" data-testid="life-draft-card">
    <div class="life-draft-card__head">
      <span class="life-draft-card__kind">模型草稿 · Generalization</span>
      <span :class="['life-draft-card__stage', `is-${stage}`]">{{ stageLabel }}</span>
    </div>

    <div class="life-draft-card__record" data-testid="life-draft-record-binding">
      <div>
        <span>草稿记录 ID</span>
        <code>{{ recordId }}</code>
      </div>
      <div>
        <span>记录内容摘要</span>
        <code>{{ recordContentDigest }}</code>
      </div>
      <p>状态：model_draft · waiting_review（等待人工复核）</p>
    </div>

    <dl class="life-draft-card__fields">
      <div
        v-for="entry in entries"
        :key="entry.id"
        :class="['life-draft-card__field', `is-${entry.kind}`, { 'is-boundary': isBoundaryField(entry.id) }]"
      >
        <dt>
          {{ entry.label }}<span class="life-draft-card__hint">{{ entry.hint }}</span>
        </dt>
        <dd v-if="entry.kind === 'text'">{{ entry.value }}</dd>
        <dd v-else>
          <ul>
            <li v-for="(item, i) in entry.value" :key="`${entry.id}-${i}`">{{ item }}</li>
          </ul>
        </dd>
      </div>
    </dl>

    <!-- 投影结果：digest 钢印 + 校验 + 审核门 + 副作用声明 -->
    <div v-if="summary" class="life-draft-card__seal" data-testid="life-draft-seal">
      <div class="life-draft-card__digest">
        <span class="life-draft-card__digest-label">Asset Draft Bundle 摘要</span>
        <code class="life-draft-card__digest-value">{{ summary.digest }}</code>
      </div>
      <div class="life-draft-card__facts">
        <div class="life-draft-card__fact">
          <span class="life-draft-card__fact-label">结构校验</span>
          <span :class="summary.blockingCount === 0 ? 'is-ok' : 'is-bad'">
            {{ summary.blockingCount === 0
              ? "通过 · 等待人工审核"
              : `${summary.blockingCount} 项阻断` }}
          </span>
        </div>
        <div class="life-draft-card__fact">
          <span class="life-draft-card__fact-label">审核门</span>
          <span>{{ summary.reviewState === "awaiting_human_review" ? "等你审核" : summary.reviewState }}</span>
        </div>
        <div class="life-draft-card__fact">
          <span class="life-draft-card__fact-label">生成方式</span>
          <span :class="summary.deterministic ? 'is-ok' : 'is-bad'">
            {{ summary.deterministic ? "确定性投影 · 没用 LLM" : "生成声明异常" }}
          </span>
        </div>
      </div>
      <div class="life-draft-card__effects">
        <span
          v-for="row in summary.effectRows"
          :key="row.key"
          :class="['life-draft-card__effect', row.value === false ? 'is-ok' : 'is-bad']"
        >
          {{ row.label }}：{{ row.value === false ? "False" : "未知" }}
        </span>
      </div>
      <p class="life-draft-card__oath">
        这只是候选投影，不是签发。签发权在你手里——本卡片不提供批准按钮。
        想改哪里，直接在对话框里说，下一轮是新草稿、新钢印。
      </p>
    </div>

    <div v-if="stage === 'error'" class="life-draft-card__error" role="alert">
      预览失败：{{ errorText }}。持久草稿仍保留在这条会话消息中；可重试，或返回对话补充后形成新记录。
    </div>

    <div class="life-draft-card__actions">
      <button
        v-if="stage !== 'previewed'"
        type="button"
        class="life-draft-card__accept"
        :disabled="stage === 'loading'"
        data-testid="life-draft-accept"
        @click="previewRecord"
      >
        {{ stage === "loading" ? "正在生成预览..." : "生成待审资产预览" }}
      </button>
      <button
        type="button"
        class="life-draft-card__revise"
        data-testid="life-draft-revise"
        @click="$emit('revise')"
      >
        返回修改
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { previewGeneralizationDraftRecord } from "../api/assetDrafts.js";
import {
  isLifeDraftShape,
  lifeDraftFieldEntries,
  summarizeLifeDraftPreview,
} from "../utils/lifeDraft.js";

const props = defineProps({
  record: { type: Object, required: true },
  conversationId: { type: String, required: true },
});
defineEmits(["revise"]);

// stage: pending → loading → previewed | error
const stage = ref("pending");
const preview = ref(null);
const errorText = ref("");

const entries = computed(() => lifeDraftFieldEntries(props.record.payload));
const recordId = computed(() => props.record.id);
const recordContentDigest = computed(() => props.record.content_digest);
const summary = computed(() =>
  summarizeLifeDraftPreview(preview.value?.asset_draft),
);
const stageLabel = computed(() => {
  if (stage.value === "loading") return "正在投影";
  if (stage.value === "previewed") return "预览已生成 · 等待人工复核";
  if (stage.value === "error") return "投影失败";
  return "已保存 · 等待人工复核";
});

function isBoundaryField(id) {
  return id === "human_decision_points" || id === "limitations";
}

async function previewRecord() {
  // fail-closed：record payload 形状不合规绝不发起投影
  if (stage.value === "loading" || !isLifeDraftShape(props.record.payload)) return;
  stage.value = "loading";
  errorText.value = "";
  try {
    preview.value = await previewGeneralizationDraftRecord(
      props.conversationId,
      props.record,
    );
    stage.value = "previewed";
  } catch (err) {
    preview.value = null;
    errorText.value =
      (typeof err?.detail === "string" && err.detail) ||
      err?.message ||
      String(err);
    stage.value = "error";
  }
}
</script>

<style scoped>
.life-draft-card {
  align-self: stretch;
  margin: 2px 0 6px;
  padding: 16px 18px;
  background: var(--paper-cream);
  border: 1px solid var(--hairline);
  border-left: 3px solid var(--clay);
  border-radius: 10px;
}

.life-draft-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.life-draft-card__kind {
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
}

.life-draft-card__stage {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  color: var(--ink-soft);
  background: var(--surface-raised);
}

.life-draft-card__stage.is-previewed {
  color: var(--trust-signed);
  border-color: var(--trust-signed);
}

.life-draft-card__stage.is-error {
  color: var(--trust-fail);
  border-color: var(--trust-fail);
}

.life-draft-card__record {
  display: grid;
  gap: 7px;
  margin: 0 0 14px;
  padding: 10px 12px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--surface-raised);
  font-size: 11px;
  color: var(--ink-soft);
}

.life-draft-card__record > div {
  display: grid;
  grid-template-columns: minmax(92px, auto) 1fr;
  gap: 8px;
  align-items: baseline;
}

.life-draft-card__record code {
  min-width: 0;
  font-family: var(--mono, ui-monospace, monospace);
  color: var(--ink);
  overflow-wrap: anywhere;
}

.life-draft-card__record p {
  margin: 1px 0 0;
  color: var(--trust-pending, var(--ink-soft));
}

.life-draft-card__fields {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.life-draft-card__field dt {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  margin-bottom: 3px;
}

.life-draft-card__hint {
  margin-left: 6px;
  font-weight: 400;
  font-size: 11px;
  color: var(--ink-faint);
}

.life-draft-card__field dd {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink);
  white-space: pre-wrap;
  word-wrap: break-word;
}

.life-draft-card__field.is-list dd ul {
  margin: 0;
  padding-left: 18px;
}

.life-draft-card__field.is-boundary {
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--trust-signed) 7%, var(--surface-raised));
  border: 1px solid color-mix(in srgb, var(--trust-signed) 25%, var(--hairline));
}

.life-draft-card__field.is-boundary dt {
  color: var(--trust-signed);
}

.life-draft-card__seal {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed var(--hairline);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.life-draft-card__digest {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.life-draft-card__digest-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--trust-signed);
}

.life-draft-card__digest-value {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 11px;
  color: var(--ink-soft);
  word-break: break-all;
}

.life-draft-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
}

.life-draft-card__fact {
  font-size: 12px;
  color: var(--ink-soft);
}

.life-draft-card__fact-label {
  margin-right: 6px;
  color: var(--ink-faint);
}

.life-draft-card__effect {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
}

.life-draft-card__effect.is-ok {
  color: var(--trust-signed);
  border-color: color-mix(in srgb, var(--trust-signed) 40%, var(--hairline));
}

.life-draft-card__effect.is-bad {
  color: var(--trust-fail);
  border-color: var(--trust-fail);
}

.is-ok {
  color: var(--trust-signed);
}

.is-bad {
  color: var(--trust-fail);
}

.life-draft-card__effects {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.life-draft-card__oath {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--ink-soft);
}

.life-draft-card__error {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--trust-fail) 36%, var(--hairline));
  background: color-mix(in srgb, var(--trust-fail) 7%, var(--surface-raised));
  color: var(--trust-fail);
  font-size: 12px;
  line-height: 1.6;
}

.life-draft-card__actions {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}

.life-draft-card__accept {
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--clay);
  background: var(--clay);
  color: white;
  cursor: pointer;
}

.life-draft-card__accept:disabled {
  background: var(--hairline);
  border-color: var(--hairline);
  color: var(--ink-faint);
  cursor: not-allowed;
}

.life-draft-card__revise {
  font: inherit;
  font-size: 13px;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  cursor: pointer;
}

.life-draft-card__revise:hover {
  color: var(--ink);
  border-color: var(--clay-softer);
}

@media (max-width: 640px) {
  .life-draft-card__actions {
    flex-direction: column;
  }
}
</style>
