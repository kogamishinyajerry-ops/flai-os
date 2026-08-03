function isRecord(value) {
  return value !== null && typeof value === "object" && Array.isArray(value) === false;
}

function hasOwnProperties(value, properties) {
  return isRecord(value) && properties.every((property) =>
    Object.prototype.hasOwnProperty.call(value, property));
}

function nullableString(value) {
  return value === null || typeof value === "string";
}

function enumOrNull(value, allowed) {
  return value === null || (typeof value === "string" && allowed.has(value));
}

function booleanOrNull(value) {
  return value === null || typeIsBoolean(value);
}

function typeIsBoolean(value) {
  return value === true || value === false;
}

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function literalBoolean(value) {
  return value === true ? true : value === false ? false : null;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function stringList(value) {
  if (Array.isArray(value) === false) return null;
  const items = value.filter((item) => typeof item === "string");
  return items.length === value.length ? items : null;
}

const WORK_TYPES = new Set([
  "tool_automation",
  "knowledge_qa",
  "structured_gen",
  "reasoning_assist",
]);
const DOMAINS = new Set([
  "policy_qa",
  "standards_qa",
  "fault_history",
  "sys_calc",
  "cfd_sim",
  "test_data",
  "design_opt",
  "generic",
]);
const STATUS_VALUES = new Set(["draft", "trial", "released", "disabled"]);
const MATURITY_VALUES = new Set(["L0", "L1", "L2", "L3"]);
const USEFULNESS_VALUES = new Set(["L1", "L2", "L3"]);
const INPUT_TYPES = new Set(["file_upload", "params", "none"]);
const VISIBILITY_VALUES = new Set(["admin_only", "department_trial", "all"]);
const ROLE_VALUES = new Set(["admin", "agent_developer", "business_user"]);
const CLEARANCE_VALUES = new Set(["public", "internal", "sensitive"]);
const CLEARANCE_SOURCES = new Set(["declared", "defaulted", "invalid_defaulted"]);
const EVIDENCE_KINDS = new Set([
  "regulation_clause",
  "standard_clause",
  "type_case",
  "fault_case",
  "knowledge_doc",
  "calculation",
]);
const TOOL_CLASSIFICATIONS = new Set(["internal", "sensitive"]);
const SCOPE_KINDS = new Set(["document", "engineering_experience", "run_memory"]);
const SCOPE_CONFIDENTIALITIES = new Set(["public_internal", "department", "restricted"]);
const LAUNCH_KINDS = new Set(["task", "conversation", "unknown"]);

function validEnumList(value, allowed) {
  return Array.isArray(value) && value.every((item) =>
    typeof item === "string" && allowed.has(item));
}

function validFacet(item) {
  return hasOwnProperties(item, [
    "id",
    "total_count",
    "task_count",
    "conversation_count",
    "unknown_launch_count",
  ]) &&
    text(item.id) !== null &&
    [
      item.total_count,
      item.task_count,
      item.conversation_count,
      item.unknown_launch_count,
    ].every((count) => nonNegativeInteger(count) !== null);
}

function validSchemaMetadata(value) {
  return hasOwnProperties(value, [
    "state",
    "reason",
    "filename",
    "property_count",
    "required_count",
  ]) &&
    ["available", "unavailable"].includes(value.state) &&
    nullableString(value.reason) &&
    nullableString(value.filename) &&
    nonNegativeInteger(value.property_count) !== null &&
    nonNegativeInteger(value.required_count) !== null;
}

function validToolReference(value) {
  return hasOwnProperties(value, [
    "id",
    "name",
    "version",
    "state",
    "mock",
    "output_classification",
  ]) &&
    text(value.id) !== null &&
    nullableString(value.name) &&
    nullableString(value.version) &&
    ["resolved", "unresolved"].includes(value.state) &&
    booleanOrNull(value.mock) &&
    enumOrNull(value.output_classification, TOOL_CLASSIFICATIONS);
}

function validScopeReference(value) {
  return hasOwnProperties(value, ["id", "name", "kind", "confidentiality", "state"]) &&
    text(value.id) !== null &&
    nullableString(value.name) &&
    enumOrNull(value.kind, SCOPE_KINDS) &&
    enumOrNull(value.confidentiality, SCOPE_CONFIDENTIALITIES) &&
    ["resolved", "unresolved"].includes(value.state);
}

function validAgentRecord(agent) {
  if (hasOwnProperties(agent, ["identity", "classification", "capability", "trust", "launch"]) === false) {
    return false;
  }
  const { identity, classification, capability, trust, launch } = agent;
  const input = isRecord(capability) ? capability.input : null;
  const output = isRecord(capability) ? capability.output : null;
  const clearance = isRecord(trust) ? trust.clearance : null;
  const evidence = isRecord(trust) ? trust.evidence : null;
  return hasOwnProperties(identity, ["agent_id", "name", "version", "summary"]) &&
    text(identity.agent_id) !== null &&
    nullableString(identity.name) &&
    nullableString(identity.version) &&
    nullableString(identity.summary) &&
    hasOwnProperties(classification, ["category", "domain", "specialty", "usefulness_level"]) &&
    enumOrNull(classification.category, WORK_TYPES) &&
    enumOrNull(classification.domain, DOMAINS) &&
    nullableString(classification.specialty) &&
    enumOrNull(classification.usefulness_level, USEFULNESS_VALUES) &&
    hasOwnProperties(capability, ["input", "output", "tools", "knowledge_scopes"]) &&
    hasOwnProperties(input, ["type", "schema"]) &&
    enumOrNull(input.type, INPUT_TYPES) &&
    validSchemaMetadata(input.schema) &&
    hasOwnProperties(output, ["formats", "schema"]) &&
    stringList(output.formats) !== null &&
    validSchemaMetadata(output.schema) &&
    Array.isArray(capability.tools) && capability.tools.every(validToolReference) &&
    Array.isArray(capability.knowledge_scopes) && capability.knowledge_scopes.every(validScopeReference) &&
    hasOwnProperties(trust, [
      "status",
      "maturity",
      "limitations",
      "visibility",
      "allowed_roles",
      "clearance",
      "requires_human_review",
      "evidence",
    ]) &&
    enumOrNull(trust.status, STATUS_VALUES) &&
    enumOrNull(trust.maturity, MATURITY_VALUES) &&
    stringList(trust.limitations) !== null &&
    enumOrNull(trust.visibility, VISIBILITY_VALUES) &&
    validEnumList(trust.allowed_roles, ROLE_VALUES) &&
    hasOwnProperties(clearance, ["effective", "source"]) &&
    CLEARANCE_VALUES.has(clearance.effective) &&
    CLEARANCE_SOURCES.has(clearance.source) &&
    booleanOrNull(trust.requires_human_review) &&
    hasOwnProperties(evidence, ["required", "kinds"]) &&
    booleanOrNull(evidence.required) &&
    validEnumList(evidence.kinds, EVIDENCE_KINDS) &&
    hasOwnProperties(launch, ["kind"]) && LAUNCH_KINDS.has(launch.kind);
}

function validSnapshotEnvelope(snapshot) {
  if (
    isRecord(snapshot) === false ||
    snapshot.schema_version !== "agent_shell.v1" ||
    hasOwnProperties(snapshot.source, ["kind", "read_only"]) === false ||
    snapshot.source.kind !== "registry_snapshot" ||
    snapshot.source.read_only !== true ||
    hasOwnProperties(snapshot.summary, [
      "agent_count",
      "work_type_count",
      "domain_count",
      "unresolved_reference_count",
      "defaulted_clearance_count",
      "mock_tool_reference_count",
    ]) === false ||
    [
      snapshot.summary.agent_count,
      snapshot.summary.work_type_count,
      snapshot.summary.domain_count,
      snapshot.summary.unresolved_reference_count,
      snapshot.summary.defaulted_clearance_count,
      snapshot.summary.mock_tool_reference_count,
    ].some((count) => nonNegativeInteger(count) === null) ||
    hasOwnProperties(snapshot.facets, ["work_types", "domains", "launch_kinds"]) === false ||
    Array.isArray(snapshot.facets.work_types) === false ||
    Array.isArray(snapshot.facets.domains) === false ||
    Array.isArray(snapshot.facets.launch_kinds) === false ||
    snapshot.facets.work_types.every(validFacet) === false ||
    snapshot.facets.domains.every(validFacet) === false ||
    snapshot.facets.launch_kinds.length !== 3 ||
    snapshot.facets.launch_kinds.every(validFacet) === false ||
    snapshot.facets.launch_kinds[0].id !== "task" ||
    snapshot.facets.launch_kinds[1].id !== "conversation" ||
    snapshot.facets.launch_kinds[2].id !== "unknown" ||
    Array.isArray(snapshot.agents) === false ||
    Array.isArray(snapshot.diagnostics) === false
  ) {
    return false;
  }
  return snapshot.diagnostics.every((item) =>
    hasOwnProperties(item, ["agent_id", "field", "state"]) &&
    text(item.agent_id) !== null &&
    text(item.field) !== null &&
    text(item.state) !== null);
}

function normalizeWorkTypes(value) {
  if (Array.isArray(value) === false) return null;
  const items = [];
  for (const item of value) {
    if (isRecord(item) === false) return null;
    const id = text(item.id);
    const count = nonNegativeInteger(item.task_count);
    if (id === null || count === null) return null;
    items.push({ id, count });
  }
  return items;
}

function referenceSummary(capability) {
  if (isRecord(capability) === false) {
    return {
      state: "unknown",
      unresolved: null,
      toolCount: null,
      scopeCount: null,
      mockToolCount: null,
      unknownMockToolCount: null,
    };
  }
  const tools = capability.tools;
  const scopes = capability.knowledge_scopes;
  if (Array.isArray(tools) === false || Array.isArray(scopes) === false) {
    return {
      state: "unknown",
      unresolved: null,
      toolCount: null,
      scopeCount: null,
      mockToolCount: null,
      unknownMockToolCount: null,
    };
  }
  const refs = [...tools, ...scopes];
  const unresolved = refs.filter(
    (item) => isRecord(item) === false || item.state !== "resolved",
  ).length;
  return {
    state: unresolved > 0 ? "unresolved" : "resolved",
    unresolved,
    toolCount: tools.length,
    scopeCount: scopes.length,
    mockToolCount: tools.filter((item) => item.mock === true).length,
    unknownMockToolCount: tools.filter(
      (item) => item.state === "resolved" && item.mock === null,
    ).length,
  };
}

function normalizeAgent(agent) {
  if (validAgentRecord(agent) === false) return null;
  const identity = isRecord(agent.identity) ? agent.identity : {};
  const classification = isRecord(agent.classification) ? agent.classification : {};
  const trust = isRecord(agent.trust) ? agent.trust : {};
  const evidence = isRecord(trust.evidence) ? trust.evidence : {};
  const clearance = isRecord(trust.clearance) ? trust.clearance : {};
  const launch = isRecord(agent.launch) ? agent.launch : {};
  const id = text(identity.agent_id);
  const name = text(identity.name);
  if (id === null || name === null) return null;

  const limitations = stringList(trust.limitations);
  const refs = referenceSummary(agent.capability);
  return {
    id,
    name,
    version: text(identity.version),
    summary: text(identity.summary),
    category: text(classification.category),
    domain: text(classification.domain),
    specialty: text(classification.specialty),
    usefulnessLevel: text(classification.usefulness_level),
    status: text(trust.status),
    maturity: text(trust.maturity),
    limitations,
    detail: limitations?.[0] ? `边界：${limitations[0]}` : "边界待核",
    clearance: text(clearance.effective),
    clearanceSource: text(clearance.source),
    reviewRequired: literalBoolean(trust.requires_human_review),
    evidenceRequired: literalBoolean(evidence.required),
    evidenceKinds: stringList(evidence.kinds),
    launchKind: text(launch.kind) || "unknown",
    referenceState: refs.state,
    unresolvedReferenceCount: refs.unresolved,
    toolCount: refs.toolCount,
    scopeCount: refs.scopeCount,
    mockToolCount: refs.mockToolCount,
    unknownMockToolCount: refs.unknownMockToolCount,
    raw: agent,
  };
}

function searchableText(agent) {
  return [
    agent.name,
    agent.summary,
    agent.specialty,
    agent.domain,
    ...(agent.limitations || []),
  ]
    .filter(Boolean)
    .join("\n")
    .toLocaleLowerCase("zh-CN");
}

export function buildAgentShellNavigator(snapshot, options = {}) {
  const valid = validSnapshotEnvelope(snapshot);
  if (valid !== true) {
    return {
      available: false,
      error: "Agent 本体投影不可用",
      totalCount: null,
      visibleCount: null,
      items: [],
      workTypes: [],
      selectionInvalid: false,
    };
  }

  const declaredWorkTypes = normalizeWorkTypes(snapshot.facets.work_types);
  const normalizedAgents = snapshot.agents.map(normalizeAgent);
  if (
    declaredWorkTypes === null ||
    normalizedAgents.some((agent) => agent === null)
  ) {
    return {
      available: false,
      error: "Agent 本体投影不可用",
      totalCount: null,
      visibleCount: null,
      items: [],
      workTypes: [],
      selectionInvalid: false,
    };
  }
  const declaredWorkTypeIds = new Set(declaredWorkTypes.map((item) => item.id));
  const allAgents = normalizedAgents;
  const selectableStatuses = new Set(["draft", "trial", "released"]);
  const taskAgents = allAgents.filter(
    (agent) =>
      agent.launchKind === "task" &&
      selectableStatuses.has(agent.status) &&
      declaredWorkTypeIds.has(agent.category),
  );
  const workTypes = declaredWorkTypes.map((item) => ({
    id: item.id,
    count: taskAgents.filter((agent) => agent.category === item.id).length,
  }));
  const workType = options.workType || "all";
  const selectionInvalid =
    workType !== "all" && workTypes.some((item) => item.id === workType) === false;
  const query = typeof options.query === "string"
    ? options.query.trim().toLocaleLowerCase("zh-CN")
    : "";

  const items = selectionInvalid
    ? []
    : taskAgents.filter((agent) => {
        if (workType !== "all" && agent.category !== workType) return false;
        return query === "" || searchableText(agent).includes(query);
      });

  return {
    available: true,
    error: "",
    totalCount: taskAgents.length,
    visibleCount: items.length,
    items,
    workTypes,
    selectionInvalid,
  };
}

export function stageAgentPrompt(agent) {
  const name = isRecord(agent) ? text(agent.name) : null;
  return name === null ? null : `我想用「${name}」做：`;
}

export function buildAgentShellOverview(snapshot) {
  const navigator = buildAgentShellNavigator(snapshot);
  if (navigator.available !== true || isRecord(snapshot.summary) === false) {
    return {
      available: false,
      items: [],
      domainCount: null,
      unresolvedReferenceCount: null,
      defaultedClearanceCount: null,
      mockToolReferenceCount: null,
      unknownMockToolReferenceCount: null,
    };
  }
  const workTypes = Array.isArray(snapshot.facets.work_types)
    ? snapshot.facets.work_types
    : [];
  const items = workTypes.flatMap((item) => {
    if (isRecord(item) === false || text(item.id) === null) return [];
    const total = nonNegativeInteger(item.total_count);
    const task = nonNegativeInteger(item.task_count);
    const conversation = nonNegativeInteger(item.conversation_count);
    const unknown = nonNegativeInteger(item.unknown_launch_count);
    if ([total, task, conversation, unknown].some((value) => value === null)) return [];
    return [{ id: item.id, total, task, conversation, unknown }];
  });
  const domainCount = nonNegativeInteger(snapshot.summary.domain_count);
  const unresolvedReferenceCount = nonNegativeInteger(
    snapshot.summary.unresolved_reference_count,
  );
  const defaultedClearanceCount = nonNegativeInteger(
    snapshot.summary.defaulted_clearance_count,
  );
  const mockToolReferenceCount = nonNegativeInteger(
    snapshot.summary.mock_tool_reference_count,
  );
  const unknownMockToolReferenceCount = snapshot.agents.reduce(
    (total, agent) => total + agent.capability.tools.filter(
      (tool) => tool.state === "resolved" && tool.mock === null,
    ).length,
    0,
  );
  if (
    domainCount === null ||
    unresolvedReferenceCount === null ||
    defaultedClearanceCount === null ||
    mockToolReferenceCount === null
  ) {
    return {
      available: false,
      items: [],
      domainCount: null,
      unresolvedReferenceCount: null,
      defaultedClearanceCount: null,
      mockToolReferenceCount: null,
      unknownMockToolReferenceCount: null,
    };
  }
  return {
    available: true,
    items,
    domainCount,
    unresolvedReferenceCount,
    defaultedClearanceCount,
    mockToolReferenceCount,
    unknownMockToolReferenceCount,
  };
}
