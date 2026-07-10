<template>
  <div class="task-create">
    <h2>创建任务</h2>

    <el-alert
      v-if="agentsListError"
      type="error"
      :title="`Agent 列表加载失败：${agentsListError}`"
      show-icon
      :closable="false"
      class="inline-alert"
    />

    <el-form label-width="100px" class="create-form">
      <el-form-item label="Agent" required>
        <el-select
          v-model="form.agentId"
          placeholder="请选择 Agent"
          filterable
          style="width: 100%"
          @change="handleAgentChange"
        >
          <el-option
            v-for="agent in selectableAgents"
            :key="agent.id"
            :label="`${agent.name}（${agent.id}）`"
            :value="agent.id"
            :disabled="agent.status === 'disabled'"
          />
        </el-select>
      </el-form-item>

      <el-alert
        v-if="agentLoadError"
        type="error"
        :title="agentLoadError"
        show-icon
        :closable="false"
        class="inline-alert"
      />

      <el-card v-if="selectedAgent" class="agent-preview" shadow="never">
        <div class="agent-preview-header">
          <strong>{{ selectedAgent.name }}</strong>
          <el-tag :type="statusTagType(selectedAgent.status)" size="small">
            {{ statusLabel(selectedAgent.status) }}
          </el-tag>
        </div>
        <p class="agent-preview-summary">{{ selectedAgent.summary }}</p>
        <div v-if="selectedAgent.limitations && selectedAgent.limitations.length" class="agent-preview-limits">
          <span class="limits-label">不适用范围：</span>{{ selectedAgent.limitations.join("；") }}
        </div>
      </el-card>

      <el-form-item label="任务名称">
        <el-input v-model="form.name" placeholder="可选，便于在历史中辨认" />
      </el-form-item>

      <el-form-item label="创建人" required>
        <el-input v-model="form.createdBy" placeholder="你的名字" />
      </el-form-item>

      <el-form-item label="输入参数">
        <div class="inputs-field">
          <el-alert
            v-if="prefilledFromGuide"
            type="success"
            :closable="false"
            show-icon
            class="prefill-note"
            title="已从智能导引带入预填草案，请核对并补全后再提交——签发权在你。"
          />
          <el-input
            v-model="form.inputsText"
            type="textarea"
            :rows="6"
            placeholder='请按该 Agent 的输入契约手填 JSON，例如：{"name": "张三"}'
          />
          <div v-if="inputsJsonError" class="field-error">{{ inputsJsonError }}</div>
          <div class="field-hint">
            按所选 Agent 的输入说明（见其 README / input_schema）填写 JSON 参数；结构化表单待后续版本。
          </div>
        </div>
      </el-form-item>

      <el-form-item label="附件">
        <el-upload :auto-upload="false" :show-file-list="false" multiple :on-change="handleFileSelect">
          <el-button>选择文件上传</el-button>
        </el-upload>
        <div v-if="uploadItems.length" class="upload-list">
          <div v-for="item in uploadItems" :key="item.uid" class="upload-item">
            <span class="upload-name">{{ item.name }}</span>
            <el-tag v-if="item.status === 'pending'" size="small">待上传</el-tag>
            <el-tag v-else-if="item.status === 'uploading'" type="info" size="small">上传中…</el-tag>
            <el-tag v-else-if="item.status === 'done'" type="success" size="small">已上传</el-tag>
            <el-tag v-else type="danger" size="small">失败：{{ item.error }}</el-tag>
            <el-button size="small" text :disabled="submitting" @click="removeUploadItem(item)">移除</el-button>
          </div>
        </div>
        <div class="field-hint">文件在提交任务时才上传；提交前移除不产生任何服务端残留。</div>
      </el-form-item>

      <el-alert
        v-if="submitError"
        type="error"
        :title="submitError"
        show-icon
        :closable="false"
        class="inline-alert"
      />

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ uploadingFiles ? "上传附件中…" : "提交任务" }}
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { listAgents, getAgent } from "../api/agents";
import { createTask } from "../api/tasks";
import { concludeConversation } from "../api/conversations";
import { uploadFile as apiUploadFile } from "../api/files";
import { statusLabel, statusTagType } from "../utils/format";

const route = useRoute();
const router = useRouter();

const agents = ref([]);
// interactive 型（导引）不作为一次性任务运行——从创建任务选择器剔除，避免用户
// 选中后只撞后端 409 死路（Codex P2 / ADR-0012）。
const selectableAgents = computed(() => agents.value.filter((a) => a.mode !== "interactive"));
const selectedAgent = ref(null);
const agentLoadError = ref("");
const agentsListError = ref("");
const inputsJsonError = ref("");
const submitting = ref(false);
const uploadingFiles = ref(false);
const submitError = ref("");
const uploadItems = ref([]);
const prefilledFromGuide = ref(false);
// M8：由导引协作会话带入的会话 id——提交任务时回填，使任务归到协作工作台的
// 同一次会话下。门户直建（无 from=guide）时保持 null。
const prefillConversationId = ref(null);
// 单 Agent 导引流程：任务创建成功后再归档本会话（异源 Codex R2-#3：会话 concluded 后
// API 真只读拒新任务，故归档必须后于创建，不能像旧流程那样先归档再跳创建页）。
const prefillConcludeAfter = ref(false);

const form = reactive({
  agentId: typeof route.query.agent_id === "string" ? route.query.agent_id : "",
  name: "",
  createdBy: "",
  inputsText: "{}",
});

// M6 人确认接缝：从智能导引带入的预填草案（sessionStorage 传递，不走 URL）。
// 只带入 inputs，仍由人补全 + 亲手点「提交任务」——导引不代签（ADR-0012）。
// M7：会话附件随草案带入——已是 File Service 真实文件，以「已上传」状态入
// 附件列表（status:done + fileId），提交时直接进 input_file_ids；人可移除。
if (route.query.from === "guide") {
  try {
    const raw = sessionStorage.getItem("flai_prefill");
    if (raw) {
      const draft = JSON.parse(raw);
      if (draft && draft.agent_id === form.agentId && draft.inputs) {
        form.inputsText = JSON.stringify(draft.inputs, null, 2);
        prefilledFromGuide.value = true;
        if (typeof draft.conversation_id === "string") {
          prefillConversationId.value = draft.conversation_id;
          // 单 Agent 草案带 conclude_after：提交成功后归档本会话（后于创建，见下）。
          prefillConcludeAfter.value = draft.conclude_after === true;
        }
        for (const f of Array.isArray(draft.files) ? draft.files : []) {
          if (f && f.id && f.name) {
            uploadItems.value.push(
              reactive({
                uid: `guide_${f.id}`,
                name: f.name,
                status: "done",
                raw: null,
                fileId: f.id,
                error: "",
              })
            );
          }
        }
      }
    }
  } catch {
    // 草案解析失败不阻断创建页——用户仍可手填
  } finally {
    sessionStorage.removeItem("flai_prefill");
  }
}

async function loadAgents() {
  try {
    agents.value = await listAgents();
    agentsListError.value = "";
    if (form.agentId) {
      await handleAgentChange(form.agentId);
    }
  } catch (err) {
    // 持久 alert 而非瞬时 toast：toast 消失后空下拉框与「确实没有 Agent」
    // 无法区分（反方审查 P2-2，与其余页面口径一致）。
    agentsListError.value = err.detail || err.message;
  }
}

async function handleAgentChange(agentId) {
  if (!agentId) {
    selectedAgent.value = null;
    return;
  }
  agentLoadError.value = "";
  try {
    selectedAgent.value = await getAgent(agentId);
  } catch (err) {
    selectedAgent.value = null;
    agentLoadError.value = err.detail || err.message;
  }
}

// P2-A：选中文件只入列（status:"pending"，raw File 留在本地），提交时才上传——
// 杜绝「选中即上传」在移除/弃页/创建失败时留下的孤儿 blob。
let uploadSeq = 0;
function handleFileSelect(uploadFile) {
  uploadItems.value.push(
    reactive({
      uid: uploadFile.uid ?? `up_${++uploadSeq}`,
      name: uploadFile.name,
      status: "pending",
      raw: uploadFile.raw,
      fileId: null,
      error: "",
    })
  );
}

function removeUploadItem(item) {
  uploadItems.value = uploadItems.value.filter((i) => i.uid !== item.uid);
}

async function uploadPendingFiles() {
  // 顺序上传全部未完成项（含上一轮失败重试项）；任一失败即中止并如实报错。
  for (const item of uploadItems.value) {
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
      return item;
    }
  }
  return null;
}

async function handleSubmit() {
  if (!form.agentId) {
    ElMessage.error("请选择 Agent");
    return;
  }
  if (!form.createdBy.trim()) {
    ElMessage.error("请填写创建人");
    return;
  }

  let inputs = {};
  try {
    inputs = form.inputsText.trim() ? JSON.parse(form.inputsText) : {};
  } catch (err) {
    inputsJsonError.value = `inputs 不是合法 JSON：${err.message}`;
    return;
  }
  inputsJsonError.value = "";
  submitError.value = "";

  submitting.value = true;
  try {
    if (uploadItems.value.some((i) => i.status !== "done")) {
      uploadingFiles.value = true;
      const failed = await uploadPendingFiles();
      uploadingFiles.value = false;
      if (failed) {
        // 持久错误提示（非瞬时 toast）：中止提交，已成的项保留 done 状态，
        // 用户可修正后重试（重试只补传未完成项）。
        submitError.value = `附件「${failed.name}」上传失败：${failed.error}，任务未创建`;
        return;
      }
    }

    const task = await createTask({
      agentId: form.agentId,
      name: form.name.trim() || null,
      inputs,
      inputFileIds: uploadItems.value.filter((i) => i.status === "done").map((i) => i.fileId),
      createdBy: form.createdBy.trim(),
      conversationId: prefillConversationId.value,
    });
    // 单 Agent 导引流程：任务已创建成功，此刻再归档本会话（fire-and-forget，归档失败
    // 不影响已建任务；多 Agent 由工作台「结束协作」显式归档）。必须后于 createTask——
    // 会话须在创建时仍 active（异源 Codex R2-#3：结束协作=真只读）。
    if (prefillConcludeAfter.value && prefillConversationId.value) {
      concludeConversation(prefillConversationId.value).catch(() => {});
    }
    ElMessage.success("任务已创建");
    router.push(`/tasks/${task.id}`);
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
    uploadingFiles.value = false;
    submitting.value = false;
  }
}

onMounted(loadAgents);
</script>

<style scoped>
.task-create {
  max-width: 640px;
}
.inline-alert {
  margin-bottom: 16px;
}
.agent-preview {
  margin-bottom: 16px;
  background: var(--paper-rail);
}
.agent-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.agent-preview-summary {
  margin: 0 0 6px;
  color: var(--ink-soft);
  font-size: 13px;
}
.agent-preview-limits {
  font-size: 12px;
  color: var(--ink-faint);
}
.limits-label {
  font-weight: 600;
}
.prefill-note {
  margin-bottom: 8px;
}
.field-error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
}
.field-hint {
  color: var(--ink-faint);
  font-size: 12px;
  margin-top: 4px;
}
.upload-list {
  margin-top: 8px;
}
.upload-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.upload-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
