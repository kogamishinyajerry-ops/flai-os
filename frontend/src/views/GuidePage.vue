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
          <div v-if="m.attachments && m.attachments.length" class="bubble-files">
            <el-tag v-for="a in m.attachments" :key="a.id" size="small" type="info" effect="plain">
              📎 {{ a.filename }}
            </el-tag>
          </div>

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
      <div v-if="pendingFiles.length" class="composer-files">
        <el-tag
          v-for="f in pendingFiles"
          :key="f.uid"
          size="small"
          closable
          :type="f.status === 'error' ? 'danger' : 'info'"
          :title="f.status === 'error' ? f.error : ''"
          @close="removePendingFile(f)"
        >
          📎 {{ f.name }}{{ f.status === "error" ? "（上传失败）" : "" }}
        </el-tag>
      </div>
      <div class="composer-row">
        <el-upload :auto-upload="false" :show-file-list="false" multiple :on-change="handleFileSelect" :disabled="sending">
          <el-button :disabled="sending" title="添加附件（≤5 个/条；文本类直读、xlsx 预览，详见导引说明）">📎</el-button>
        </el-upload>
        <el-input
          v-model="draft"
          type="textarea"
          :rows="2"
          :disabled="sending"
          placeholder="描述你的工程需求，或回答导引的追问…（Enter 发送，Shift+Enter 换行；可用 📎 带附件）"
          @keydown.enter.exact.prevent="send"
        />
        <el-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { createConversation, postMessage, concludeConversation } from "../api/conversations";
import { uploadFile as apiUploadFile } from "../api/files";
import { categoryColor, categoryLabel } from "../utils/format";

const router = useRouter();

const GUIDE_AGENT_ID = "guide_agent";
const MAX_FILES_PER_MESSAGE = 5; // 与后端 PostMessageRequest / 运行时同值

const createdBy = ref("");
const started = ref(false);
const conversationId = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const pageError = ref("");
const streamEl = ref(null);
// 待发送附件（M7）：选中只入列（raw 留本地），发送时才上传——同 TaskCreate 的
// P2-A 反孤儿纪律；已上传项记 fileId，失败重试不重复上传。
const pendingFiles = ref([]);
let fileSeq = 0;

function handleFileSelect(uploadFile) {
  if (pendingFiles.value.length >= MAX_FILES_PER_MESSAGE) {
    ElMessage.error(`单条消息最多 ${MAX_FILES_PER_MESSAGE} 个附件`);
    return;
  }
  pendingFiles.value.push(
    reactive({
      uid: uploadFile.uid ?? `gf_${++fileSeq}`,
      name: uploadFile.name,
      raw: uploadFile.raw,
      status: "pending", // pending | done | error
      fileId: null,
      error: "",
    })
  );
}

function removePendingFile(item) {
  pendingFiles.value = pendingFiles.value.filter((f) => f.uid !== item.uid);
}

async function uploadPendingFiles() {
  // 顺序上传未完成项（含上一轮失败项）；任一失败即抛出，本轮消息不发送。
  for (const item of pendingFiles.value) {
    if (item.status === "done") continue;
    item.status = "uploading";
    item.error = "";
    try {
      const res = await apiUploadFile(item.raw);
      item.status = "done";
      item.fileId = res.id;
    } catch (err) {
      item.status = "error";
      item.error = err.detail || err.message;
      throw new Error(`附件「${item.name}」上传失败：${item.error}`);
    }
  }
  return pendingFiles.value.map((f) => f.fileId);
}

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

  // 乐观追加用户气泡（附件 chips 一并显示；失败整体回滚）
  const optimisticAttachments = pendingFiles.value.map((f) => ({ id: f.uid, filename: f.name }));
  messages.value.push({
    role: "user",
    content,
    attachments: optimisticAttachments.length ? optimisticAttachments : undefined,
  });
  draft.value = "";
  await scrollToBottom();

  sending.value = true;
  try {
    // 先传附件（已 done 的跳过，失败即中止——本轮消息不发送）
    const fileIds = await uploadPendingFiles();
    if (!conversationId.value) {
      const conv = await createConversation({ agentId: GUIDE_AGENT_ID, createdBy: createdBy.value.trim() });
      conversationId.value = conv.id;
      started.value = true;
    }
    const res = await postMessage(conversationId.value, content, fileIds);
    // 成功：附件已随消息落库，清空待发区；气泡 chips 换用真实文件 id
    const sent = messages.value[messages.value.length - 1];
    if (sent && sent.role === "user" && optimisticAttachments.length) {
      sent.attachments = pendingFiles.value.map((f) => ({ id: f.fileId, filename: f.name }));
    }
    pendingFiles.value = [];
    messages.value.push({
      role: "assistant",
      content: res.message.content,
      recommendation: res.message.recommendation || null,
    });
    await scrollToBottom();
  } catch (err) {
    // 本轮失败：后端契约是「失败零落库」（幂等重试，ADR-0013），本地同样回滚
    // 乐观气泡并把原文还原到输入框——不在界面上留一条服务端不存在的幽灵消息，
    // 重试也不会堆出重复 user 气泡（Codex R1-P2）。附件 chips 留在待发区
    // （已上传项带 fileId，重试不重复上传）。不伪造 assistant 回复。
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
  // M7：会话里传过的附件（真实 fileId 的）随草案带走——创建页以「已上传」
  // 状态入列，人可移除；是否随任务提交仍由人决定。
  // 发送成功的气泡按构造只含真实 fileId（失败气泡已回滚、成功时 chips 已换真 id）
  const carried = [];
  const seen = new Set();
  for (const m of messages.value) {
    if (m.role !== "user" || !m.attachments) continue;
    for (const a of m.attachments) {
      if (a.id && !seen.has(a.id)) {
        seen.add(a.id);
        carried.push({ id: a.id, name: a.filename });
      }
    }
  }
  sessionStorage.setItem(
    "flai_prefill",
    JSON.stringify({ agent_id: reco.agent_id, inputs: reco.prefilled_inputs || {}, files: carried })
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
}
.composer-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.composer-row .el-textarea {
  flex: 1;
}
.composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.bubble-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
</style>
