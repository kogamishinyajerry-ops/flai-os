<template>
  <div class="guide-page">
    <div class="page-header">
      <h2>智能导引</h2>
      <p class="page-sub">
        说说你要做什么，导引会帮你找到合适的 Agent 并预填一份任务草案——
        <strong>草案由你确认后亲手提交，导引不会替你创建任务。</strong>
      </p>
    </div>

    <el-alert
      v-if="pageError"
      type="error"
      :title="pageError"
      show-icon
      :closable="false"
      class="page-alert"
    />

    <div v-if="!started" class="starter">
      <el-input v-model="createdBy" placeholder="你的名字（对话需具名）" class="name-input" />
      <p class="starter-hint">先留个名字，然后在下方描述你的需求开始对话。</p>
    </div>

    <div ref="streamEl" class="chat-stream">
      <div v-for="(m, idx) in messages" :key="idx" :class="['bubble-row', m.role]">
        <div class="bubble">
          <div class="bubble-role">{{ m.role === "user" ? "你" : "导引" }}</div>
          <div class="bubble-text">{{ m.content }}</div>

          <div v-if="m.recommendation" class="reco-card">
            <div class="reco-bar" :style="{ background: categoryColor(m.recommendation.category) }"></div>
            <div class="reco-inner">
              <div class="reco-head">
                <span class="reco-title">推荐：{{ m.recommendation.agent_name }}</span>
                <span
                  class="reco-pill"
                  :style="{ color: categoryColor(m.recommendation.category), background: categoryColor(m.recommendation.category) + '18' }"
                >{{ categoryLabel(m.recommendation.category) }}</span>
                <el-tag size="small" type="info" effect="plain">{{ m.recommendation.maturity }} / {{ m.recommendation.status }}</el-tag>
              </div>
              <p v-if="m.recommendation.rationale" class="reco-rationale">{{ m.recommendation.rationale }}</p>

              <div class="reco-block">
                <div class="reco-block-label">预填草案（{{ prefilledCount(m.recommendation) }} 个字段，未必完整）</div>
                <pre class="reco-json">{{ prettyInputs(m.recommendation.prefilled_inputs) }}</pre>
              </div>

              <el-alert
                v-if="m.recommendation.stripped_fields && m.recommendation.stripped_fields.length"
                type="warning"
                :closable="false"
                show-icon
                class="reco-stripped"
                :title="`已剔除不合法字段：${m.recommendation.stripped_fields.join('、')}（未匹配该 Agent 的输入契约）`"
              />

              <div class="reco-actions">
                <el-button type="primary" @click="confirmAndGoCreate(m.recommendation)">
                  确认草案，去创建任务
                </el-button>
                <span class="reco-note">你将进入创建任务页补全并<strong>亲手提交</strong>——签发权在你。</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="sending" class="bubble-row assistant">
        <div class="bubble thinking">导引思考中…</div>
      </div>
    </div>

    <div class="composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        :disabled="sending"
        placeholder="描述你的工程需求，或回答导引的追问…（Enter 发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">发送</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, concludeConversation } from "../api/conversations";
import { categoryColor, categoryLabel } from "../utils/format";

const router = useRouter();

const GUIDE_AGENT_ID = "guide_agent";

const createdBy = ref("");
const started = ref(false);
const conversationId = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const pageError = ref("");
const streamEl = ref(null);

function prettyInputs(inputs) {
  return JSON.stringify(inputs || {}, null, 2);
}
function prefilledCount(reco) {
  return Object.keys(reco.prefilled_inputs || {}).length;
}

async function scrollToBottom() {
  await nextTick();
  if (streamEl.value) streamEl.value.scrollTop = streamEl.value.scrollHeight;
}

async function send() {
  const content = draft.value.trim();
  if (!content) return;
  if (!createdBy.value.trim()) {
    ElMessage.error("请先在上方填写你的名字");
    return;
  }
  pageError.value = "";

  // 乐观追加用户气泡
  messages.value.push({ role: "user", content });
  draft.value = "";
  await scrollToBottom();

  sending.value = true;
  try {
    if (!conversationId.value) {
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID, createdBy: createdBy.value.trim() });
      conversationId.value = conv.id;
      started.value = true;
    }
    const res = await postMessage(conversationId.value, content);
    messages.value.push({
      role: "assistant",
      content: res.message.content,
      recommendation: res.message.recommendation || null,
    });
    await scrollToBottom();
  } catch (err) {
    // 本轮失败：后端契约是「失败零落库」（幂等重试，ADR-0013），本地同样回滚
    // 乐观气泡并把原文还原到输入框——不在界面上留一条服务端不存在的幽灵消息，
    // 重试也不会堆出重复 user 气泡（Codex R1-P2）。不伪造 assistant 回复。
    const last = messages.value[messages.value.length - 1];
    if (last && last.role === "user" && last.content === content) {
      messages.value.pop();
    }
    draft.value = content;
    pageError.value = err.detail || err.message;
  } finally {
    sending.value = false;
  }
}

function confirmAndGoCreate(reco) {
  // 人确认接缝：把预填草案交给创建任务页，由人补全后亲手提交（导引绝不代签）。
  // 走 sessionStorage 而非 URL，避免工程数据进查询串。
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({ agent_id: reco.agent_id, inputs: reco.prefilled_inputs || {} })
  );
  // 确认即归档会话（active→concluded，ADR-0013）。fire-and-forget：归档失败
  // 不阻断人去创建任务——会话留 active 只是可观测性小瑕疵，不是流程阻塞点。
  if (conversationId.value) {
    concludeConversation(conversationId.value).catch(() => {});
  }
  router.push({ path: "/tasks/new", query: { agent_id: reco.agent_id, from: "guide" } });
}
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0 0 4px;
}
.page-sub {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
  line-height: 1.6;
}
.page-alert {
  margin-bottom: 12px;
}
.starter {
  margin-bottom: 12px;
}
.name-input {
  max-width: 260px;
}
.starter-hint {
  margin: 6px 0 0;
  color: var(--ink-soft);
  font-size: 12px;
}
.chat-stream {
  min-height: 320px;
  max-height: 56vh;
  overflow-y: auto;
  padding: 8px 4px 4px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.bubble-row {
  display: flex;
}
.bubble-row.user {
  justify-content: flex-end;
}
.bubble-row.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 78%;
  border-radius: 12px;
  padding: 10px 14px;
  border: 1px solid var(--hairline);
  background: var(--card-bg);
}
.bubble-row.user .bubble {
  background: var(--clay-soft);
  border-color: #e9d3c7;
}
.bubble-role {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  margin-bottom: 4px;
}
.bubble-text {
  white-space: pre-wrap;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.6;
}
.thinking {
  color: var(--ink-soft);
  font-size: 13px;
  font-style: italic;
}
.reco-card {
  margin-top: 12px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.reco-bar {
  height: 4px;
  width: 100%;
}
.reco-inner {
  padding: 12px 14px;
}
.reco-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.reco-title {
  font-weight: 700;
  color: var(--ink);
  font-size: 14px;
}
.reco-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
}
.reco-rationale {
  margin: 0 0 10px;
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
}
.reco-block-label {
  font-size: 12px;
  color: var(--ink-soft);
  margin-bottom: 4px;
}
.reco-json {
  margin: 0;
  padding: 10px 12px;
  background: #faf7f2;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 12.5px;
  color: #4a443d;
  overflow-x: auto;
  white-space: pre;
}
.reco-stripped {
  margin-top: 10px;
}
.reco-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.reco-note {
  color: var(--ink-soft);
  font-size: 12px;
}
.composer {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.composer .el-textarea {
  flex: 1;
}
</style>
