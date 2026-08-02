import { request, unwrapDetail } from "./client.js";

// created_by 服务端从登录会话派生（ADR-0019 D5），前端不再发送任何身份文本。
export const createTask = ({ agentId, name, inputs, inputFileIds, conversationId, retryOf }) =>
  request("/api/tasks", {
    method: "POST",
    json: {
      agent_id: agentId,
      name: name || null,
      inputs: inputs || {},
      input_file_ids: inputFileIds || [],
      // M8：由导引协作会话产出的任务带上会话 id，归到协作工作台的同一次会话下。
      conversation_id: conversationId || null,
      // N4a/迁移#12：「复制为新任务」的血缘注记（纯元数据，指向不存在→后端 404）。
      retry_of: retryOf || null,
    },
  });

// 批七 §3-B6：编队一键开工走原子 batch——全有全无（任一项非法整批 422 零写入，
// detail.batch_errors 逐项透出），after=同批更早下标 → 服务端映射真 depends_on；
// retryOf 是失败回流时由系统附加的审计血缘，不暴露给工程师填写。
export const createBatchOperationId = (cryptoApi = globalThis.crypto) => {
  const randomUUID = cryptoApi?.randomUUID;
  if (typeof randomUUID === "function") {
    return `guide_batch_${randomUUID.call(cryptoApi)}`;
  }
  const getRandomValues = cryptoApi?.getRandomValues;
  if (typeof getRandomValues !== "function") {
    throw new Error("当前浏览器无法生成安全的创建操作标识——本次未发起任务");
  }
  // randomUUID 在部分内网 HTTP（非 secure context）不可用，但 Web Crypto 的
  // getRandomValues 仍可提供 128 bit CSPRNG。保留 UUID v4 形状以满足现有有界
  // 字符契约；绝不退回 Math.random 或时间戳。
  const bytes = new Uint8Array(16);
  getRandomValues.call(cryptoApi, bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  const uuid = [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10, 16).join(""),
  ].join("-");
  return `guide_batch_${uuid}`;
};

// network/timeout/5xx，以及 2xx 后响应 JSON 损坏，都可能发生在服务端 COMMIT
// 之后。只有明确的 4xx 才能沿 batch 全有全无契约断言零写入；其余必须进入
// 「创建状态待核」并用同一 operation_id 重放核对，绝不换 key 自动再建。
export const batchCreatePersistenceUnknown = (error) => {
  if (error?.persistenceUnknown === true) return true;
  const status = error?.status;
  if (typeof status !== "number") return true;
  if (status === 409) return batchCreateErrorCode(error) === "batch_operation_conflict";
  return status === 0 || status >= 500;
};

export const batchCreateErrorCode = (error) => {
  const detail = unwrapDetail(error?.detail);
  return detail && typeof detail === "object" && typeof detail.code === "string"
    ? detail.code
    : null;
};

function invalidBatchCreateResponse(reason) {
  const error = new Error(`批量创建响应无法权威核对：${reason}`);
  error.code = "batch_response_invalid";
  error.persistenceUnknown = true;
  return error;
}

function sameStringList(actual, expected) {
  return actual.length === expected.length && actual.every(
    (value, index) => value === expected[index],
  );
}

function sameSkillPackageRef(actual, expected) {
  if (!actual || !expected || typeof actual !== "object" || typeof expected !== "object") {
    return false;
  }
  const keys = [
    "schema_version",
    "package_id",
    "package_version",
    "package_digest",
    "candidate_digest",
    "skill_digest",
    "skill_name",
    "matched_agent_id",
    "review_state",
    "match_policy_version",
    "match_basis_digest",
  ];
  const expectedKeys = [...keys].sort();
  const actualKeys = Object.keys(actual).sort();
  const requestedKeys = Object.keys(expected).sort();
  return actualKeys.length === expectedKeys.length
    && requestedKeys.length === expectedKeys.length
    && actualKeys.every((key, index) => key === expectedKeys[index])
    && requestedKeys.every((key, index) => key === expectedKeys[index])
    && keys.every((key) => actual[key] === expected[key]);
}

// 2xx 只说明 HTTP 成功，不足以证明本次原子创建对应的整组任务。必须先核对
// operation_id、任务全集、顺序、血缘、版本与包摘要，调用方随后才能写本地成功
// 状态或消费 retry 上下文；任一缺失都属于 COMMIT 后状态不明。
export function validateBatchCreateResponse(
  response,
  {
    conversationId,
    items,
    pinnedVersions,
    pinnedPackageDigests,
    operationId,
  },
) {
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw invalidBatchCreateResponse("响应不是对象");
  }
  const expectedOperationId = operationId || null;
  if ((response.operation_id ?? null) !== expectedOperationId) {
    throw invalidBatchCreateResponse("operation_id 与请求不一致");
  }
  if (!Array.isArray(response.tasks)) {
    throw invalidBatchCreateResponse("tasks 不是数组");
  }
  if (response.tasks.length !== items.length) {
    throw invalidBatchCreateResponse(
      `响应任务数量 ${response.tasks.length} 与请求 ${items.length} 不一致`,
    );
  }

  const ids = [];
  const seenIds = new Set();
  for (const task of response.tasks) {
    if (!task || typeof task !== "object" || Array.isArray(task)) {
      throw invalidBatchCreateResponse("任务投影不是对象");
    }
    if (typeof task.id !== "string" || !task.id.trim() || seenIds.has(task.id)) {
      throw invalidBatchCreateResponse("任务 id 缺失或重复");
    }
    seenIds.add(task.id);
    ids.push(task.id);
  }

  const expectedConversationId = conversationId || null;
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    const task = response.tasks[index];
    if (task.agent_id !== item.agentId) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 Agent 或顺序不一致`);
    }
    if ((task.conversation_id ?? null) !== expectedConversationId) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 conversation_id 不一致`);
    }
    const expectedRetryOf = item.retryOf || null;
    if ((task.retry_of ?? null) !== expectedRetryOf) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 retry_of 不一致`);
    }
    if (task.depends_on != null && !Array.isArray(task.depends_on)) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 depends_on 不是数组`);
    }
    const after = item.after || [];
    if (!after.every((dependencyIndex) => (
      Number.isInteger(dependencyIndex) && dependencyIndex >= 0 && dependencyIndex < index
    ))) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项请求依赖下标非法`);
    }
    const expectedDependsOn = after.map((dependencyIndex) => ids[dependencyIndex]);
    const actualDependsOn = task.depends_on || [];
    if (!sameStringList(actualDependsOn, expectedDependsOn)) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 depends_on 不一致`);
    }
    if (
      pinnedVersions &&
      Object.hasOwn(pinnedVersions, item.agentId) &&
      task.agent_version !== pinnedVersions[item.agentId]
    ) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 Agent 版本不一致`);
    }
    if (pinnedPackageDigests && Object.hasOwn(pinnedPackageDigests, item.agentId)) {
      const actualDigest = task.metadata?.package_snapshot_digest;
      if (actualDigest !== pinnedPackageDigests[item.agentId]) {
        throw invalidBatchCreateResponse(`第 ${index + 1} 项 Agent 包摘要不一致`);
      }
    }
    const actualSkillPackageRef = task.metadata?.skill_package_ref;
    if (
      item.skillPackageRef
        ? !sameSkillPackageRef(actualSkillPackageRef, item.skillPackageRef)
        : actualSkillPackageRef != null
    ) {
      throw invalidBatchCreateResponse(`第 ${index + 1} 项 Skill Package 复用引用不一致`);
    }
  }
  return response;
}

export const createTasksBatch = async ({
  conversationId,
  items,
  pinnedVersions,
  pinnedPackageDigests,
  operationId,
}) => {
  const normalizedItems = (items || []).map((it) => ({
    agentId: it.agentId,
    name: it.name || null,
    inputs: it.inputs || {},
    inputFileIds: it.inputFileIds || [],
    retryOf: it.retryOf || null,
    after: it.after || [],
    ...(it.skillPackageRef ? { skillPackageRef: it.skillPackageRef } : {}),
  }));
  const response = await request("/api/tasks/batch", {
    method: "POST",
    json: {
      conversation_id: conversationId || null,
      pinned_versions: pinnedVersions || null,
      pinned_package_digests: pinnedPackageDigests || null,
      operation_id: operationId || null,
      items: normalizedItems.map((it) => ({
        agent_id: it.agentId,
        name: it.name,
        inputs: it.inputs,
        input_file_ids: it.inputFileIds,
        retry_of: it.retryOf || null,
        after: it.after,
        ...(it.skillPackageRef
          ? { skill_package_ref: it.skillPackageRef }
          : {}),
      })),
    },
  });
  return validateBatchCreateResponse(response, {
    conversationId,
    items: normalizedItems,
    pinnedVersions,
    pinnedPackageDigests,
    operationId,
  });
};

export const listTasks = ({ status, agentId, limit, offset } = {}) => {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (agentId) params.set("agent_id", agentId);
  if (limit != null) params.set("limit", String(limit));
  if (offset != null) params.set("offset", String(offset));
  const qs = params.toString();
  return request(`/api/tasks${qs ? `?${qs}` : ""}`);
};

export const getTask = (taskId) => request(`/api/tasks/${taskId}`);
// 分页拉取到取尽（ADR-0013 审计修复）：此前单页 5000 封顶，但 parser 契约上限
// max_rows=5000 时批量任务可产 ~2 万事件——尾部的 summary_generated/task_completed
// 恰在最需要它的场景被静默截断。页大小 2000 对齐后端默认；短尾页即终止。
// offset 起点（Codex R1-P2）：详情页 2s 轮询若每次从 0 全量重翻，事件越多轮询
// 越重；事件表 append-only 且按 id ASC 排序，偏移稳定——轮询方传入已持有的
// 条数，只拉自己没有的尾段。
export const listTaskEvents = async (taskId, { offset = 0 } = {}) => {
  const pageSize = 2000;
  const all = [];
  for (let cursor = offset; ; cursor += pageSize) {
    const page = await request(`/api/tasks/${taskId}/events?limit=${pageSize}&offset=${cursor}`);
    all.push(...page);
    if (page.length < pageSize) return all;
  }
};
export const cancelTask = (taskId) =>
  request(`/api/tasks/${taskId}/cancel`, { method: "POST" });

// 人工放行（P1-B）。签发者=登录会话身份，服务端派生（ADR-0019 D5），前端不发。
export const reviewTask = (taskId, { action, comment }) =>
  request(`/api/tasks/${taskId}/review`, {
    method: "POST",
    json: { action, comment: comment || null },
  });

// 工具调用明细（只读端点，工作态氛围展示用）。
export const listToolRuns = (taskId) => request(`/api/tasks/${taskId}/tool_runs`);

// 工具调用计数投影（批次二 Codex R0-P2）：核验段只要 total/mock_count 两个数，
// 有界聚合取代全量明细（批量任务的 input/output 轨迹不再整条搬运）。
export const getToolRunsSummary = (taskId) => request(`/api/tasks/${taskId}/tool_runs/summary`);

// 模型调用留痕（只读端点，消耗诚实披露用；字段=model_profile/model_name/status/
// token_usage，token_usage 上游未回报时为 null，绝不补 0）。
export const listModelCalls = (taskId) => request(`/api/tasks/${taskId}/model_calls`);

// 产物文件只读元数据投影（批B P1 修复，字段=id/filename/size_bytes/data_classification，
// 绝不含 path/内容）——DeliveryCard 产物条用它取代逐个 fetchOutputFile 全量拉 blob。
export const listOutputFiles = (taskId) => request(`/api/tasks/${taskId}/output_files`);

// 单卡交付摘要（批B 治理审 R1 P1 修复）：服务端有界聚合 model_calls 状态/token
// 与批量 ok/failed（口径见后端端点 docstring），DeliveryCard 用它取代
// listModelCalls+listTaskEvents 两个无界只读请求。
export const getDeliverySummary = (taskId) => request(`/api/tasks/${taskId}/delivery_summary`);
