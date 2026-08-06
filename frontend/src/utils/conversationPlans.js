const SCHEMA_ANNOTATIONS = new Set([
  "$schema",
  "$id",
  "title",
  "description",
  "default",
  "examples",
  "readOnly",
  "writeOnly",
  "deprecated",
  "display_hints",
]);
const SCHEMA_VALIDATORS = new Set([
  "type",
  "enum",
  "const",
  "properties",
  "required",
  "additionalProperties",
  "items",
  "minItems",
  "maxItems",
  "uniqueItems",
  "minLength",
  "maxLength",
  "pattern",
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "exclusiveMaximum",
  "multipleOf",
]);
const JSON_TYPES = new Set(["object", "array", "string", "number", "integer", "boolean", "null"]);

function plainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function jsonEqual(left, right) {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => jsonEqual(item, right[index]));
  }
  if (plainObject(left) && plainObject(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && jsonEqual(left[key], right[key]))
    );
  }
  return false;
}

function timestampMs(value) {
  if (typeof value !== "string" || value.trim() === "") return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

// 切片 3（#31 方案 B）：ADR-0033 三终点单消息判定——Guide 明确拒绝 / canonical
// 制度标准问答交付。附件路由（currentWorkSegmentFiles）与 UI 段分隔（workSegments）
// 共用同一谓词，绝不各自再造第二份口径。
function terminalKindOf(message) {
  if (
    !message ||
    message.role !== "assistant" ||
    message.transient === true ||
    message.persistenceUnknown === true ||
    !plainObject(message.recommendation)
  ) return null;
  const recommendation = message.recommendation;
  if (recommendation.decision === "refuse") return "refuse";
  const findings = Array.isArray(recommendation.findings) ? recommendation.findings : null;
  const refusals = Array.isArray(recommendation.refusals) ? recommendation.refusals : null;
  const isQaDelivery = (
    !Object.hasOwn(recommendation, "decision") &&
    ((findings && findings.length > 0) || (refusals && refusals.length > 0))
  );
  return isQaDelivery ? "qa" : null;
}

// 一次会话可以连续承载多项工作。任务创建时点是上一工作段已经由工程师明确
// “开工”的权威边界：只有边界之后、服务端已保存的用户附件才属于下一份方案。
// 没有任何任务边界时保留整段 canonical 历史，支持用户先发材料、再逐轮补充。
// 边界存在但消息缺 createdAt 时保守排除，绝不让未知时序的旧附件污染新任务。
export function currentWorkSegmentFiles(messages, tasks, localBoundaryMs = 0) {
  const taskBoundaries = Array.isArray(tasks)
    ? tasks.map((task) => timestampMs(task?.created_at)).filter((value) => value !== null)
    : [];
  const localBoundary = Number.isFinite(localBoundaryMs) && localBoundaryMs > 0
    ? localBoundaryMs
    : 0;
  const boundaryMs = Math.max(localBoundary, ...taskBoundaries, 0);
  // 不是每一段工程工作都会创建任务。垂类问答交付与 Guide 明确拒绝同样是
  // canonical 的工作段终点；它们之后的新请求不能继续继承上一段附件。普通
  // 澄清没有 recommendation，仍属于同一工作段，必须保留先发材料。
  let terminalMessageIndex = -1;
  const messageList = Array.isArray(messages) ? messages : [];
  for (let index = 0; index < messageList.length; index += 1) {
    if (terminalKindOf(messageList[index])) terminalMessageIndex = index;
  }
  const carried = [];
  const seen = new Set();

  for (let index = terminalMessageIndex + 1; index < messageList.length; index += 1) {
    const message = messageList[index];
    if (
      message?.role !== "user" ||
      !Array.isArray(message.attachments) ||
      message.transient === true ||
      message.persistenceUnknown === true
    ) continue;
    if (boundaryMs > 0) {
      const messageMs = timestampMs(message.createdAt);
      if (messageMs === null || messageMs <= boundaryMs) continue;
    }
    for (const attachment of message.attachments) {
      const id = typeof attachment?.id === "string" ? attachment.id.trim() : "";
      if (!id || seen.has(id)) continue;
      seen.add(id);
      carried.push({
        id,
        name: typeof attachment.filename === "string" ? attachment.filename : "",
      });
    }
  }
  return carried;
}

// 切片 3（#31 方案 B）：UI 工作段分隔描述符。与附件路由同源三终点（terminalKindOf），
// 任务创建戳投影规则同 currentWorkSegmentFiles（createdAt 严格大于边界戳才开新段；
// 缺时序消息对该边界保守跳过，绝不凭未知时序切段）。
// 返回 [{ start, end, ordinal }]（end 含，升序，覆盖 [0, messages.length-1]）。
// first=ordinal 0、current=末段、middle=其余——折叠/分隔的可见面决策由调用方做。
export function workSegments(messages, tasks, localBoundaryMs = 0) {
  const list = Array.isArray(messages) ? messages : [];
  if (list.length === 0) return [];
  const starts = new Set();
  for (let index = 0; index < list.length; index += 1) {
    if (terminalKindOf(list[index]) && index + 1 < list.length) starts.add(index + 1);
  }
  const stamps = (Array.isArray(tasks) ? tasks : [])
    .map((task) => timestampMs(task?.created_at)).filter((value) => value !== null);
  const local = Number.isFinite(localBoundaryMs) && localBoundaryMs > 0 ? localBoundaryMs : 0;
  if (local > 0) stamps.push(local);
  for (const stamp of stamps) {
    for (let index = 0; index < list.length; index += 1) {
      const messageMs = timestampMs(list[index]?.createdAt);
      if (messageMs !== null && messageMs > stamp) {
        if (index > 0) starts.add(index);
        break;
      }
    }
  }
  const ordered = [...starts].filter((s) => s > 0).sort((a, b) => a - b);
  const segments = [];
  let cursor = 0;
  let ordinal = 0;
  for (const start of ordered) {
    segments.push({ start: cursor, end: start - 1, ordinal });
    ordinal += 1;
    cursor = start;
  }
  segments.push({ start: cursor, end: list.length - 1, ordinal });
  return segments;
}

function matchesDeclaredType(type, value) {
  if (type === "object") return plainObject(value);
  if (type === "array") return Array.isArray(value);
  if (type === "string") return typeof value === "string";
  if (type === "number") return typeof value === "number" && Number.isFinite(value);
  if (type === "integer") return typeof value === "number" && Number.isInteger(value);
  if (type === "boolean") return typeof value === "boolean";
  if (type === "null") return value === null;
  return false;
}

// 浏览器端只实现仓库当前 input_schema 使用的确定性子集；遇到任何未知关键字
// 直接返回 false，而不是假装支持。Guide workflow 与任务 Runtime 仍会用 Python
// jsonschema 做完整复核，这一层负责防止历史方案/schema 漂移时错误开放开工按钮。
function schemaValueValid(schema, value) {
  if (!plainObject(schema)) return false;
  if (Object.keys(schema).some((key) => !SCHEMA_ANNOTATIONS.has(key) && !SCHEMA_VALIDATORS.has(key))) {
    return false;
  }
  if (typeof schema.type !== "string" || !JSON_TYPES.has(schema.type)) return false;
  if (!matchesDeclaredType(schema.type, value)) return false;
  if (Array.isArray(schema.enum) && !schema.enum.some((item) => jsonEqual(item, value))) return false;
  if (Object.hasOwn(schema, "enum") && !Array.isArray(schema.enum)) return false;
  if (Object.hasOwn(schema, "const") && !jsonEqual(schema.const, value)) return false;

  if (schema.type === "object") {
    const properties = schema.properties;
    if (!plainObject(properties)) return false;
    if (Object.values(properties).some((child) => !plainObject(child))) return false;
    const required = schema.required === undefined ? [] : schema.required;
    if (!Array.isArray(required) || required.some((key) => typeof key !== "string")) return false;
    if (required.some((key) => !Object.hasOwn(value, key))) return false;
    for (const [key, childValue] of Object.entries(value)) {
      if (Object.hasOwn(properties, key)) {
        if (!schemaValueValid(properties[key], childValue)) return false;
      } else if (schema.additionalProperties === false) {
        return false;
      } else if (plainObject(schema.additionalProperties)) {
        if (!schemaValueValid(schema.additionalProperties, childValue)) return false;
      } else if (schema.additionalProperties !== undefined && schema.additionalProperties !== true) {
        return false;
      }
    }
  }

  if (schema.type === "array") {
    if (schema.minItems !== undefined && (!Number.isInteger(schema.minItems) || schema.minItems < 0 || value.length < schema.minItems)) return false;
    if (schema.maxItems !== undefined && (!Number.isInteger(schema.maxItems) || schema.maxItems < 0 || value.length > schema.maxItems)) return false;
    if (schema.uniqueItems !== undefined && typeof schema.uniqueItems !== "boolean") return false;
    if (schema.uniqueItems === true) {
      for (let i = 0; i < value.length; i += 1) {
        if (value.slice(i + 1).some((item) => jsonEqual(item, value[i]))) return false;
      }
    }
    if (schema.items !== undefined) {
      if (!plainObject(schema.items) || value.some((item) => !schemaValueValid(schema.items, item))) return false;
    }
  }

  if (schema.type === "string") {
    const codePointLength = [...value].length;
    if (schema.minLength !== undefined && (!Number.isInteger(schema.minLength) || schema.minLength < 0 || codePointLength < schema.minLength)) return false;
    if (schema.maxLength !== undefined && (!Number.isInteger(schema.maxLength) || schema.maxLength < 0 || codePointLength > schema.maxLength)) return false;
    if (schema.pattern !== undefined) {
      if (typeof schema.pattern !== "string") return false;
      try {
        if (!new RegExp(schema.pattern, "u").test(value)) return false;
      } catch {
        return false;
      }
    }
  }

  if (schema.type === "number" || schema.type === "integer") {
    if (schema.minimum !== undefined && (!Number.isFinite(schema.minimum) || value < schema.minimum)) return false;
    if (schema.maximum !== undefined && (!Number.isFinite(schema.maximum) || value > schema.maximum)) return false;
    if (schema.exclusiveMinimum !== undefined && (!Number.isFinite(schema.exclusiveMinimum) || value <= schema.exclusiveMinimum)) return false;
    if (schema.exclusiveMaximum !== undefined && (!Number.isFinite(schema.exclusiveMaximum) || value >= schema.exclusiveMaximum)) return false;
    if (schema.multipleOf !== undefined) {
      if (typeof schema.multipleOf !== "number" || !Number.isFinite(schema.multipleOf) || schema.multipleOf <= 0) return false;
      const quotient = value / schema.multipleOf;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) return false;
    }
  }
  return true;
}

export function prefillSatisfiesSchema(schema, prefilled) {
  if (!plainObject(schema) || schema.type !== "object" || !plainObject(prefilled)) {
    return false;
  }
  // “必填”与空值语义完全交给当前 JSON Schema（required/minLength/minItems 等）
  // 决定，不用 String(value) 猜测；否则合法的 0/false/空集合会被错判。
  return schemaValueValid(schema, prefilled) === true;
}

export function matchingAgentFiles(contract, files) {
  const allowed = contract?.allowedExtensions;
  if (!Array.isArray(files) || files.length === 0) return [];
  if (!Array.isArray(allowed) || allowed.length === 0) return [];
  const normalized = allowed.map((item) => String(item).trim().toLowerCase());
  if (normalized.some((item) => !item.startsWith(".") || item.length < 2)) return [];
  return files.filter((file) => {
    const name = typeof file?.name === "string" ? file.name.trim().toLowerCase() : "";
    return name !== "" && normalized.some((extension) => name.endsWith(extension));
  });
}

// 把当前工作段的 canonical 附件映射到方案成员。返回 ready=false 代表归属或
// 契约不唯一，Guide 只能回到同一个 composer 继续追问，不能让工程师手工选
// 执行单元/文件，也不能静默丢附件。
//
// 新方案由 backend workflow 给出权威绑定：每个成员 attachments + 根级
// ignored_attachments。字段任一出现就要求整份 shape 完整，并逐 id/filename 与
// 当前工作段对账；重复、越界、漏记、none 收件、file_upload 非唯一/后缀不符都
// fail-closed。只有这些字段全部缺失的历史方案才沿用下面的保守推断：
//
// - file_upload：全方案只能有一个此类消费者，且只能有一份契约匹配文件；
// - params：没有 file_upload 消费者时，唯一 params 成员接收当前段全部附件；
// - none：从不接收附件；纯 none 方案遇到附件必须阻断；
// - 没有附件：params/none 方案正常开放，file_upload 仍因缺文件阻断。
export function planAttachmentRouting(planOrAgents, contractsByAgent, files) {
  const empty = { ready: false, inputFileIdsByAgent: {} };
  const plan = plainObject(planOrAgents) ? planOrAgents : null;
  const agents = plan ? plan.agents : planOrAgents;
  if (!Array.isArray(agents) || agents.length === 0 || !plainObject(contractsByAgent)) {
    return empty;
  }

  const members = [];
  const memberIds = new Set();
  for (const agent of agents) {
    const agentId = typeof agent?.agent_id === "string" ? agent.agent_id.trim() : "";
    const contract = contractsByAgent[agentId];
    if (!agentId || memberIds.has(agentId) || contract?.loaded !== true) return empty;
    if (!["params", "file_upload", "none"].includes(contract.inputMode)) return empty;
    memberIds.add(agentId);
    members.push({ agentId, contract });
  }

  const canonicalFiles = [];
  const fileIds = new Set();
  for (const file of Array.isArray(files) ? files : []) {
    const id = typeof file?.id === "string" ? file.id.trim() : "";
    const name = typeof file?.name === "string" ? file.name.trim() : "";
    if (!id || !name) return empty;
    if (fileIds.has(id)) continue;
    fileIds.add(id);
    canonicalFiles.push({ ...file, id, name });
  }

  // 一旦新字段任一出现就进入权威模式，绝不因 shape 残缺退回历史猜测。
  const canonicalFieldsPresent = Boolean(
    plan && (
      Object.hasOwn(plan, "ignored_attachments") ||
      agents.some((agent) => plainObject(agent) && Object.hasOwn(agent, "attachments"))
    )
  );
  if (canonicalFieldsPresent) {
    if (!Array.isArray(plan.ignored_attachments)) return empty;
    if (members.some(({ agentId }) => !Array.isArray(
      agents.find((agent) => agent?.agent_id?.trim?.() === agentId)?.attachments,
    ))) return empty;

    const currentById = new Map(canonicalFiles.map((file) => [file.id, file]));
    const accountedIds = new Set();
    const inputFileIdsByAgent = {};
    const attachmentsByAgent = {};

    const resolveBinding = (binding) => {
      if (!plainObject(binding)) return null;
      const keys = Object.keys(binding);
      if (
        keys.length !== 2 ||
        !Object.hasOwn(binding, "file_id") ||
        !Object.hasOwn(binding, "filename")
      ) return null;
      const id = typeof binding.file_id === "string" ? binding.file_id.trim() : "";
      const filename = typeof binding.filename === "string" ? binding.filename.trim() : "";
      const current = currentById.get(id);
      if (!id || !filename || !current || current.name !== filename || accountedIds.has(id)) {
        return null;
      }
      accountedIds.add(id);
      return { id, name: filename };
    };

    for (const { agentId, contract } of members) {
      const agent = agents.find((item) => item?.agent_id?.trim?.() === agentId);
      const resolved = [];
      for (const binding of agent.attachments) {
        const file = resolveBinding(binding);
        if (!file) return empty;
        resolved.push(file);
      }
      if (contract.inputMode === "none" && resolved.length !== 0) return empty;
      if (
        contract.inputMode === "file_upload" &&
        (resolved.length !== 1 || matchingAgentFiles(contract, resolved).length !== 1)
      ) return empty;
      attachmentsByAgent[agentId] = resolved;
      if (resolved.length > 0) inputFileIdsByAgent[agentId] = resolved.map((file) => file.id);
    }

    const ignoredAttachments = [];
    for (const binding of plan.ignored_attachments) {
      const file = resolveBinding(binding);
      if (!file) return empty;
      ignoredAttachments.push(file);
    }
    // 每份当前材料必须恰好进入一个执行单元或被明确记为忽略；两边之外没有第三态。
    if (accountedIds.size !== canonicalFiles.length) return empty;
    return {
      ready: true,
      inputFileIdsByAgent,
      attachmentsByAgent,
      ignoredAttachments,
      canonical: true,
    };
  }

  const fileUploadMembers = members.filter(({ contract }) => contract.inputMode === "file_upload");
  if (fileUploadMembers.length > 0) {
    if (fileUploadMembers.length !== 1) return empty;
    const [{ agentId, contract }] = fileUploadMembers;
    const matching = matchingAgentFiles(contract, canonicalFiles);
    // 唯一匹配之外若还有任何当前段附件，它们的消费者仍未确定；不能只转发
    // 匹配项并把其余材料静默丢掉。
    if (matching.length !== 1 || canonicalFiles.length !== 1) return empty;
    return {
      ready: true,
      inputFileIdsByAgent: { [agentId]: [matching[0].id] },
    };
  }

  if (canonicalFiles.length === 0) {
    return { ready: true, inputFileIdsByAgent: {} };
  }
  const paramsMembers = members.filter(({ contract }) => contract.inputMode === "params");
  if (paramsMembers.length !== 1) return empty;
  return {
    ready: true,
    inputFileIdsByAgent: {
      [paramsMembers[0].agentId]: canonicalFiles.map((file) => file.id),
    },
  };
}

function activeOrchestrationBoundarySignal(value) {
  if (value === true) return true;
  if (typeof value === "number") return Number.isFinite(value) && value !== 0;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return false;
}

// dropped/capped 不是“部分成功”：它们证明最终方案没有完整纳入模型提议。
// 已知字段和未来同义信号都走 fail-closed，避免旧历史数据或前后端版本漂移时
// 重新露出 batch 开工入口。refuse/delegate 不创建任务，不在这里裁决。
export function planHasIncompleteOrchestration(plan) {
  if (!plan || plan.decision !== "orchestrate") return false;
  if (activeOrchestrationBoundarySignal(plan.dropped_agents)) return true;
  return Object.entries(plan).some(
    ([key, value]) =>
      /(?:capped|truncated)/i.test(key) &&
      activeOrchestrationBoundarySignal(value),
  );
}

export function agentExecutionReady(contract, inputs, files) {
  if (!contract || contract.loaded !== true) return false;
  if (!plainObject(inputs)) return false;
  const normalizedInputs = inputs;
  if (contract.inputMode === "params") {
    return prefillSatisfiesSchema(contract.schema, normalizedInputs) === true;
  }
  if (contract.inputMode === "file_upload") {
    // 当前三类 file_upload Agent 的 workflow 都只接受唯一一份匹配材料。
    // 多个同后缀历史附件时绝不全量转发或猜测；保持 fail-closed，等待后续
    // 由对话形成显式附件血缘。
    return (
      prefillSatisfiesSchema(contract.schema, normalizedInputs) === true &&
      matchingAgentFiles(contract, files).length === 1
    );
  }
  if (contract.inputMode === "none") {
    return Object.keys(normalizedInputs).length === 0;
  }
  return false;
}

export function latestActionablePlanIndex(
  messages,
  { activeRetryOf = null, retryPlanArmed = false } = {},
) {
  if (!Array.isArray(messages) || messages.length === 0) return -1;
  const latest = messages[messages.length - 1];
  if (latest?.role !== "assistant") return -1;
  if (latest.recommendation?.decision !== "orchestrate" || latest.fresh !== true) return -1;
  const messageRetryOf = normalizeRetryLineage(latest.retryOf);
  const routeRetryOf = normalizeRetryLineage(activeRetryOf);
  if (messageRetryOf !== null) {
    return messageRetryOf === routeRetryOf && retryPlanArmed === true
      ? messages.length - 1
      : -1;
  }
  // 处在失败恢复 query 时，只允许本轮明确带同一 retryOf 的 canonical 方案；
  // 普通历史方案不能借 query 复活成“重跑”按钮。
  return routeRetryOf === null ? messages.length - 1 : -1;
}

function normalizedLabel(value, fallback) {
  return String(value || fallback).trim().replace(/\s+/g, " ") || fallback;
}

export function automaticTaskName(plan, agent, index) {
  const goal = normalizedLabel(plan?.goal, "工程任务");
  if ((plan?.agents || []).length <= 1) return goal.slice(0, 200);
  const unit = normalizedLabel(
    agent?.role || agent?.agent_name,
    `成员 ${Number(index) + 1}`,
  );
  return `${goal} · ${unit}`.slice(0, 200);
}

export function automaticTeamName(plan) {
  const goal = normalizedLabel(plan?.goal, "工程任务");
  return `${goal} · 专家团队`.slice(0, 100);
}

// 异步开工响应只能落回提交时的会话 + retry 语义。routeConversationId 允许为空
// （新会话 router.replace 尚在收尾），但一旦地址栏已指向另一会话就必须作废。
export function conversationSnapshotMatches(submitted, current) {
  const submittedConversationId = typeof submitted?.conversationId === "string"
    ? submitted.conversationId.trim()
    : "";
  const currentConversationId = typeof current?.conversationId === "string"
    ? current.conversationId.trim()
    : "";
  const routeConversationId = typeof current?.routeConversationId === "string"
    ? current.routeConversationId.trim()
    : "";
  if (!submittedConversationId || currentConversationId !== submittedConversationId) return false;
  if (routeConversationId && routeConversationId !== submittedConversationId) return false;

  const submittedRetryOf = normalizeRetryLineage(submitted?.retryOf);
  return (
    normalizeRetryLineage(current?.retryOf) === submittedRetryOf &&
    normalizeRetryLineage(current?.requestedRetryOf) === submittedRetryOf
  );
}

// 新会话第一次发送会把内部 conversationId 镜像到 URL。这个 replace 不是一次
// “切换会话”，必须由 watcher 精确消费一次；否则 retry_of 仍在时 watcher 会重读
// 刚创建的空会话，抹掉当前乐观用户轮次。token 带 epoch，调用方负责消费后清空。
export function internalConversationRouteBindingMatches(binding, rawConversationId, rawRetryOf) {
  if (!plainObject(binding) || !Number.isInteger(binding.epoch) || binding.epoch < 1) return false;
  const conversationId = typeof binding.conversationId === "string"
    ? binding.conversationId.trim()
    : "";
  const routeConversationId = typeof rawConversationId === "string"
    ? rawConversationId.trim()
    : "";
  if (!conversationId || routeConversationId !== conversationId) return false;

  const expectedRetryOf = normalizeRetryLineage(binding.retryOf);
  if (expectedRetryOf === null) {
    return rawRetryOf === undefined || rawRetryOf === null;
  }
  return normalizeRetryLineage(rawRetryOf) === expectedRetryOf;
}

export function normalizeRetryLineage(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!normalized || normalized.length > 64) return null;
  return normalized;
}

// URL 只是恢复意图，不是事实来源。只有服务端权威任务与 URL id 精确一致且当前
// 状态字面为 failed，壳才可以展示/携带 retry_of；queued/completed/未知都拒绝。
export function verifiedFailedRetryLineage(task, requestedId) {
  const normalized = normalizeRetryLineage(requestedId);
  if (!normalized || task?.id !== normalized || task?.status !== "failed") return null;
  return normalized;
}

// 一次失败恢复可以自动编排成并行根任务 + 依赖成员。旧任务是每个根任务的
// 直接恢复来源；下游成员已经由 depends_on 留下接力血缘，不重复冒充直接重跑。
export function retryLineageForPlanItem(retryOf, after) {
  const normalized = normalizeRetryLineage(retryOf);
  if (!normalized) return null;
  return Array.isArray(after) && after.length > 0 ? null : normalized;
}
