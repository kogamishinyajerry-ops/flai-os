<template>
  <div class="task-create">
    <h2>创建任务</h2>

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
            v-for="agent in agents"
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
            <el-tag v-if="item.status === 'uploading'" type="info" size="small">上传中…</el-tag>
            <el-tag v-else-if="item.status === 'done'" type="success" size="small">已上传</el-tag>
            <el-tag v-else type="danger" size="small">失败：{{ item.error }}</el-tag>
            <el-button size="small" text @click="removeUploadItem(item)">移除</el-button>
          </div>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交任务</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { listAgents, getAgent } from "../api/agents";
import { createTask } from "../api/tasks";
import { uploadFile as apiUploadFile } from "../api/files";
import { statusLabel, statusTagType } from "../utils/format";

const route = useRoute();
const router = useRouter();

const agents = ref([]);
const selectedAgent = ref(null);
const agentLoadError = ref("");
const inputsJsonError = ref("");
const submitting = ref(false);
const uploadItems = ref([]);

const form = reactive({
  agentId: typeof route.query.agent_id === "string" ? route.query.agent_id : "",
  name: "",
  createdBy: "",
  inputsText: "{}",
});

async function loadAgents() {
  try {
    agents.value = await listAgents();
    if (form.agentId) {
      await handleAgentChange(form.agentId);
    }
  } catch (err) {
    ElMessage.error(err.detail || err.message);
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

let uploadSeq = 0;
function handleFileSelect(uploadFile) {
  const item = reactive({
    uid: uploadFile.uid ?? `up_${++uploadSeq}`,
    name: uploadFile.name,
    status: "uploading",
    fileId: null,
    error: "",
  });
  uploadItems.value.push(item);
  apiUploadFile(uploadFile.raw)
    .then((res) => {
      item.status = "done";
      item.fileId = res.id;
    })
    .catch((err) => {
      item.status = "error";
      item.error = err.detail || err.message;
    });
}

function removeUploadItem(item) {
  uploadItems.value = uploadItems.value.filter((i) => i.uid !== item.uid);
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

  if (uploadItems.value.some((i) => i.status === "uploading")) {
    ElMessage.warning("文件仍在上传中，请等待完成后再提交");
    return;
  }

  submitting.value = true;
  try {
    const task = await createTask({
      agentId: form.agentId,
      name: form.name.trim() || null,
      inputs,
      inputFileIds: uploadItems.value.filter((i) => i.status === "done").map((i) => i.fileId),
      createdBy: form.createdBy.trim(),
    });
    ElMessage.success("任务已创建");
    router.push(`/tasks/${task.id}`);
  } catch (err) {
    ElMessage.error(err.detail || err.message);
  } finally {
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
  background: #f5f7fa;
}
.agent-preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.agent-preview-summary {
  margin: 0 0 6px;
  color: #606266;
  font-size: 13px;
}
.agent-preview-limits {
  font-size: 12px;
  color: #909399;
}
.limits-label {
  font-weight: 600;
}
.field-error {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 4px;
}
.field-hint {
  color: #909399;
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
