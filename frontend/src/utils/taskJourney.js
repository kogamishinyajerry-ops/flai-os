import { deriveSignoff, statusLabel, TASK_WORK_STATES } from "./format.js";

const TOOL_EVENT_TYPES = new Set(["tool_started", "tool_finished", "tool_failed"]);

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function hasEvent(events, type) {
  return safeArray(events).some((event) => event?.event_type === type);
}

function inputStep(task, events) {
  if (hasEvent(events, "validation_failed")) {
    return { tone: "fail", detail: "输入校验失败" };
  }
  const filesValid = Array.isArray(task.input_file_ids);
  const inputsValid = task.inputs !== null
    && typeof task.inputs === "object"
    && !Array.isArray(task.inputs);
  if (!filesValid || !inputsValid) {
    return { tone: "pending", detail: "输入字段待核" };
  }
  const fileCount = task.input_file_ids.length;
  const inputs = task.inputs;
  const paramCount = Object.keys(inputs).length;
  const parts = [];
  if (fileCount > 0) parts.push(`${fileCount} 个输入文件`);
  if (paramCount > 0) parts.push(`${paramCount} 项参数`);
  return {
    tone: "neutral",
    detail: parts.length ? parts.join(" · ") : "无文件或参数记录",
  };
}

function executionStep(task, events) {
  const status = task.status;
  const list = safeArray(events);
  const validationFailed = list.some((event) => event?.event_type === "validation_failed");
  const reviewRejected = list.some((event) => event?.event_type === "review_rejected");
  const executionFailed = list.some((event) =>
    event?.event_type === "tool_failed"
    || (event?.event_type === "model_call" && event?.level === "error")
    || event?.event_type === "task_failed"
  );
  if (status === "failed" && (validationFailed || reviewRejected)) {
    return {
      tone: "neutral",
      detail: validationFailed ? "未进入有效执行" : "执行已结束",
    };
  }
  if (status === "failed" && executionFailed) return { tone: "fail", detail: "执行失败" };
  if (status === "failed") return { tone: "pending", detail: "失败原因待核" };
  if (TASK_WORK_STATES.has(status)) return { tone: "work", detail: statusLabel(status) };
  if (status === "waiting_review" || status === "completed") {
    return { tone: "neutral", detail: "执行已落定" };
  }
  if (status === "cancelled") return { tone: "neutral", detail: "执行已取消" };
  if (status === "queued") return { tone: "neutral", detail: "等待执行" };
  if (status === "created") return { tone: "neutral", detail: "等待入队" };
  return { tone: "pending", detail: status ? `状态待核：${statusLabel(status)}` : "状态未知" };
}

function callsStep(events, modelCalls, modelCallsError, modelCallsLoaded) {
  const list = safeArray(events);
  const toolEvents = list.filter((event) => TOOL_EVENT_TYPES.has(event?.event_type));
  const toolStarted = toolEvents.filter((event) => event.event_type === "tool_started");
  const toolTerminal = toolEvents.filter((event) =>
    event.event_type === "tool_finished" || event.event_type === "tool_failed"
  );
  const countedToolEvents = toolStarted.length > 0 ? toolStarted : toolTerminal;
  const toolCount = countedToolEvents.length;
  const mockCount = countedToolEvents.filter((event) => event?.payload?.mock === true).length;
  const toolFailureCount = toolEvents.filter((event) => event.event_type === "tool_failed").length;
  const modelEvents = list.filter((event) => event?.event_type === "model_call");
  const modelEventFailureCount = modelEvents.filter((event) => event?.level === "error").length;
  const modelCallsFormatInvalid = modelCallsLoaded === true && !Array.isArray(modelCalls);
  const calls = Array.isArray(modelCalls) ? modelCalls : [];
  const modelRowFailureCount = calls.filter((call) => call?.status === "failed").length;
  const modelFailureCount = Math.max(modelEventFailureCount, modelRowFailureCount);
  const failureCount = toolFailureCount + modelFailureCount;
  const modelCount = Math.max(modelEvents.length, calls.length);
  const detailsMismatch = modelCallsLoaded === true
    && modelEvents.length > 0
    && modelEvents.length !== calls.length;
  const parts = [];
  if (toolCount > 0) parts.push(`工具 ${toolCount} 次`);
  if (modelCount > 0) parts.push(`模型 ${modelCount} 次`);
  if (mockCount > 0) parts.push(`含 ${mockCount} 次 mock`);
  if (failureCount > 0) parts.push(`含 ${failureCount} 次失败`);
  if (modelCallsError) parts.push("模型明细不可用");
  else if (modelCallsFormatInvalid) parts.push("模型明细格式待核");
  else if (modelCallsLoaded !== true) parts.push(modelCount > 0 ? "模型明细待核" : "调用明细待核");
  else if (detailsMismatch) parts.push("模型明细未对上");
  if (toolCount > 0 && mockCount === 0) parts.push("工具真实性见核验");

  return {
    tone: failureCount > 0
      ? "fail"
      : modelCallsError
        || modelCallsFormatInvalid
        || modelCallsLoaded !== true
        || detailsMismatch
        || mockCount > 0
        || toolCount > 0
        ? "pending"
        : "neutral",
    detail: parts.length
      ? parts.join(" · ")
      : "无工具或模型调用记录",
  };
}

function artifactStep(task, artifactCount) {
  const hasExplicitCount = Number.isInteger(artifactCount) && artifactCount >= 0;
  if (!hasExplicitCount && !Array.isArray(task.output_file_ids)) {
    return { tone: "pending", detail: "产物字段待核" };
  }
  const count = hasExplicitCount ? artifactCount : task.output_file_ids.length;
  return {
    tone: "neutral",
    detail: count > 0 ? `${count} 件文件产物` : "未声明文件产物",
  };
}

function reviewStep(task, events) {
  const list = safeArray(events);
  const signoff = deriveSignoff(list);
  if (signoff?.redacted) return { tone: "neutral", detail: "签发记录受限" };
  if (signoff?.unknown) return { tone: "neutral", detail: "签发记录不完整" };
  if (signoff) {
    return signoff.approved
      ? { tone: "signed", detail: `${signoff.reviewer} 已批准放行` }
      : { tone: "fail", detail: `${signoff.reviewer} 已驳回` };
  }
  if (task.status === "waiting_review") return { tone: "pending", detail: "等待人工签发" };
  if (hasEvent(list, "review_requested")) {
    return { tone: "pending", detail: "签发决策记录缺失" };
  }
  return { tone: "neutral", detail: "未进入人工签发" };
}

function deliveryStep(task, events) {
  const list = safeArray(events);
  const signoff = deriveSignoff(list);
  if (task.status === "failed" && signoff && signoff.approved === false) {
    return { tone: "fail", detail: "已驳回 · 未放行" };
  }
  if (task.status === "failed") return { tone: "fail", detail: "交付失败" };
  if (task.status === "waiting_review") return { tone: "pending", detail: "待人工放行" };
  if (task.status === "completed" && hasEvent(list, "review_requested") && !signoff) {
    return { tone: "pending", detail: "完成状态待核" };
  }
  if (task.status === "completed") return { tone: "neutral", detail: "任务已落定" };
  if (task.status === "cancelled") return { tone: "neutral", detail: "任务已取消" };
  if (TASK_WORK_STATES.has(task.status) || task.status === "queued" || task.status === "created") {
    return { tone: "neutral", detail: "尚未交付" };
  }
  return { tone: "pending", detail: "交付状态待核" };
}

/**
 * 把任务真值压成一个纯展示执行链。
 *
 * 色槽只允许 neutral/work/pending/signed/fail：
 * completed 与“调用成功”都不解锁绿色；signed 只来自具名 review_approved。
 */
export function buildTaskJourney({
  task,
  events = [],
  modelCalls = [],
  modelCallsError = "",
  modelCallsLoaded = false,
  artifactCount,
} = {}) {
  if (!task || typeof task !== "object") return [];

  return [
    { id: "input", label: "输入", ...inputStep(task, events) },
    { id: "execution", label: "Agent 执行", ...executionStep(task, events) },
    {
      id: "calls",
      label: "工具 / 模型",
      ...callsStep(events, modelCalls, modelCallsError, modelCallsLoaded),
    },
    { id: "artifacts", label: "产物", ...artifactStep(task, artifactCount) },
    { id: "review", label: "人工签发", ...reviewStep(task, events) },
    { id: "delivery", label: "交付", ...deliveryStep(task, events) },
  ];
}
