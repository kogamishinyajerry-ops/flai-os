const CATEGORY_LABELS = {
  tool_automation: "工具自动化",
  knowledge_qa: "知识问答",
  structured_gen: "结构化生成",
  reasoning_assist: "推理辅助",
};

function hasText(value) {
  return typeof value === "string" && value.trim() !== "";
}

function hasErrors(value) {
  return Array.isArray(value) && value.length > 0;
}

function policyDetail(agent) {
  if (!agent || typeof agent !== "object") {
    return { tone: "pending", detail: "选择 Agent 后核对策略边界" };
  }

  let clearance;
  if (agent.clearance === null || agent.clearance === undefined) {
    clearance = "密级未声明，按内部数据上限保守处理";
  } else if (agent.clearance === "public") {
    clearance = "密级上限：公开";
  } else if (agent.clearance === "internal") {
    clearance = "密级上限：内部";
  } else if (agent.clearance === "sensitive") {
    clearance = "密级上限：敏感";
  } else {
    clearance = "密级策略待核";
  }

  const evidence = agent.evidence_policy_required === true
    ? "产物要求附依据"
    : agent.evidence_policy_required === false
      ? "未强制要求附依据"
      : "依据策略待核";
  const limitations = Array.isArray(agent.limitations)
    ? `${agent.limitations.length} 项不适用边界`
    : "不适用边界待核";
  const tone = (
    !["public", "internal", "sensitive", null, undefined].includes(agent.clearance)
    || typeof agent.evidence_policy_required !== "boolean"
    || !Array.isArray(agent.limitations)
  ) ? "pending" : "neutral";

  return { tone, detail: `${clearance} · ${evidence} · ${limitations}` };
}

export function buildTaskCreateJourney({
  agentId = "",
  selectedAgent = null,
  agentsListError = "",
  agentLoadError = "",
  prefillOrigin = "",
  schemaRenderable = false,
  jsonMode = false,
  inputsErrors = [],
  inputsJsonError = "",
  uploadItems = [],
  submitting = false,
  uploadingFiles = false,
  submitError = "",
} = {}) {
  const uploads = Array.isArray(uploadItems) ? uploadItems : [];
  const uploadFailure = uploads.some((item) => item?.status === "error");
  const uploadWorking = uploads.some((item) => item?.status === "uploading");
  const doneCount = uploads.filter((item) => item?.status === "done").length;
  const selectedMatches = (
    selectedAgent
    && typeof selectedAgent === "object"
    && hasText(selectedAgent.id)
    && hasText(agentId)
    && selectedAgent.id === agentId
  );
  // Agent 下拉值与详情必须同一身份才能派生能力/策略；任何在途或错配详情均
  // fail-closed 为待核，绝不把旧 Agent 的边界挂到新选择上。
  const journeyAgent = selectedMatches ? selectedAgent : null;

  let agentStep;
  if (hasText(agentsListError) || hasText(agentLoadError)) {
    agentStep = { tone: "fail", detail: "Agent 信息加载失败" };
  } else if (journeyAgent) {
    agentStep = { tone: "neutral", detail: `已选择 ${journeyAgent.name || journeyAgent.id}` };
  } else if (hasText(agentId)) {
    agentStep = { tone: "pending", detail: "正在核对 Agent 信息" };
  } else {
    agentStep = { tone: "pending", detail: "请选择 Agent" };
  }

  let capabilityStep;
  if (!journeyAgent) {
    capabilityStep = { tone: "pending", detail: "能力说明待 Agent 选定" };
  } else {
    const category = CATEGORY_LABELS[journeyAgent.category] || "能力类型待核";
    const maturity = hasText(journeyAgent.maturity)
      ? `成熟度 ${journeyAgent.maturity}`
      : "成熟度待核";
    capabilityStep = {
      tone: CATEGORY_LABELS[journeyAgent.category] && hasText(journeyAgent.maturity)
        ? "neutral"
        : "pending",
      detail: `${category} · ${maturity} · 请核对适用范围`,
    };
  }

  let inputStep;
  if (
    hasErrors(inputsErrors)
    || hasText(inputsJsonError)
    || uploadFailure
    || hasText(submitError)
  ) {
    inputStep = { tone: "fail", detail: "输入或附件存在真实错误" };
  } else if (uploadingFiles || uploadWorking || submitting) {
    inputStep = {
      tone: "work",
      detail: uploadingFiles || uploadWorking ? "正在上传附件" : "正在锁定本次输入",
    };
  } else if (hasText(prefillOrigin)) {
    inputStep = { tone: "pending", detail: "预填草案待核，请你确认" };
  } else if (journeyAgent && jsonMode && schemaRenderable !== true) {
    inputStep = { tone: "pending", detail: "改用 JSON，结构仍待后端校验" };
  } else if (journeyAgent) {
    inputStep = {
      tone: "neutral",
      detail: doneCount > 0
        ? `已上传 ${doneCount} 件，尚未提交`
        : "填写参数并按需添加附件",
    };
  } else {
    inputStep = { tone: "pending", detail: "输入契约待 Agent 选定" };
  }

  const submitStep = hasText(submitError)
    ? { tone: "fail", detail: "任务未创建，请处理错误后重试" }
    : submitting
      ? { tone: "work", detail: uploadingFiles ? "上传后将按快照创建" : "正在创建任务" }
      : { tone: "pending", detail: "等待你亲手提交；提交不等于签发" };

  return [
    { id: "agent", label: "选择 Agent", ...agentStep },
    { id: "capability", label: "核对能力", ...capabilityStep },
    { id: "input", label: "准备输入", ...inputStep },
    { id: "policy", label: "确认边界", ...policyDetail(journeyAgent) },
    { id: "submit", label: "人工提交", ...submitStep },
  ];
}

function cloneJsonValue(value) {
  return JSON.parse(JSON.stringify(value));
}

/**
 * 在任何附件上传 await 之前冻结请求的语义字段。
 *
 * uploadItems 只冻结集合成员；成员对象继续承载本次上传写回的 fileId/status，
 * 因而 await 后无需回读可变页面状态。
 */
export function captureTaskSubmission({
  form,
  inputs,
  uploadItems,
  conversationId = null,
  retryOf = null,
  concludeAfter = false,
  returnToChat = false,
} = {}) {
  return {
    agentId: form?.agentId,
    name: hasText(form?.name) ? form.name.trim() : null,
    inputs: cloneJsonValue(inputs ?? {}),
    uploadItems: Array.isArray(uploadItems) ? [...uploadItems] : [],
    conversationId,
    retryOf,
    concludeAfter: concludeAfter === true,
    returnToChat: returnToChat === true,
  };
}
