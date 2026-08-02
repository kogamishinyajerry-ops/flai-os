const INVALID_VIEW = Object.freeze({
  available: false,
  summary: null,
  capabilities: [],
  assets: [],
});

const MAX_CAPABILITIES = 200;
const MAX_ASSETS = 100;
const ASSET_STATE_BY_CANDIDATE_STATE = Object.freeze({
  awaiting_human_review: "candidate_revision",
  accepted: "approved_revision",
  rejected: "rejected_revision",
});
const CANDIDATE_PRESENTATIONS = Object.freeze({
  awaiting_human_review: Object.freeze({
    label: "Candidate 待人审核",
    shortLabel: "待审核",
    className: "is-pending",
  }),
  accepted: Object.freeze({
    label: "Candidate 已由人接受",
    shortLabel: "人已接受",
    className: "is-signed",
  }),
  rejected: Object.freeze({
    label: "Candidate 已驳回",
    shortLabel: "已驳回",
    className: "is-failed",
  }),
});
const PACKAGE_PRESENTATIONS = Object.freeze({
  pending_review: Object.freeze({ label: "待独立人审", className: "is-pending" }),
  approved: Object.freeze({ label: "包级人审通过", className: "is-signed" }),
  rejected: Object.freeze({ label: "已驳回", className: "is-failed" }),
  not_formed: Object.freeze({ label: "尚未形成", className: "is-unformed" }),
});

const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const hasExactKeys = (value, keys) =>
  isRecord(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const isText = (value) => typeof value === "string" && value.length > 0;
const isOptionalText = (value) => value === null || isText(value);
const isCount = (value) => Number.isInteger(value) && value >= 0;
const isDigest = (value) => typeof value === "string" && /^sha256:[0-9a-f]{64}$/.test(value);

function validFacet(value) {
  return hasExactKeys(value, ["id", "total_count"]) && isText(value.id) && isCount(value.total_count);
}

function validCapability(value) {
  return (
    hasExactKeys(value, [
      "agent_id",
      "name",
      "summary",
      "category",
      "domain",
      "specialty",
      "launch_kind",
      "status",
      "maturity",
      "requires_human_review",
      "tool_count",
      "knowledge_scope_count",
      "unresolved_reference_count",
      "mock_tool_count",
    ]) &&
    isText(value.agent_id) &&
    isOptionalText(value.name) &&
    isOptionalText(value.summary) &&
    isOptionalText(value.category) &&
    isOptionalText(value.domain) &&
    isOptionalText(value.specialty) &&
    isText(value.launch_kind) &&
    isOptionalText(value.status) &&
    isOptionalText(value.maturity) &&
    (value.requires_human_review === null || typeof value.requires_human_review === "boolean") &&
    isCount(value.tool_count) &&
    isCount(value.knowledge_scope_count) &&
    isCount(value.unresolved_reference_count) &&
    isCount(value.mock_tool_count)
  );
}

function validAssetLevel(value) {
  return (
    hasExactKeys(value, ["state", "digest", "gate"]) &&
    value.state === "not_formed" &&
    value.digest === null &&
    isText(value.gate)
  );
}

function validTaskPattern(value) {
  return (
    hasExactKeys(value, ["title", "state", "digest"]) &&
    isText(value.title) &&
    ["candidate_revision", "approved_revision", "rejected_revision"].includes(value.state) &&
    isDigest(value.digest)
  );
}

function validSkill(value) {
  return (
    hasExactKeys(value, ["name", "description", "state", "digest"]) &&
    isText(value.name) &&
    isText(value.description) &&
    ["candidate_revision", "approved_revision", "rejected_revision"].includes(value.state) &&
    isDigest(value.digest)
  );
}

function validPackage(value) {
  return (
    hasExactKeys(value, [
      "id",
      "name",
      "version",
      "package_digest",
      "state",
      "reuse_eligible",
    ]) &&
    isText(value.id) &&
    isText(value.name) &&
    isText(value.version) &&
    isDigest(value.package_digest) &&
    ["pending_review", "approved", "rejected"].includes(value.state) &&
    typeof value.reuse_eligible === "boolean" &&
    value.reuse_eligible === (value.state === "approved")
  );
}

function validAsset(value) {
  if (
    !hasExactKeys(value, [
      "candidate_id",
      "candidate_digest",
      "revision",
      "state",
      "source",
      "task_pattern",
      "skill",
      "skill_package",
      "workflow",
      "agent",
      "updated_at",
    ]) ||
    !isText(value.candidate_id) ||
    !isDigest(value.candidate_digest) ||
    !Number.isInteger(value.revision) ||
    value.revision < 1 ||
    !["awaiting_human_review", "accepted", "rejected"].includes(value.state) ||
    !hasExactKeys(value.source, ["task_id", "conversation_id", "agent_id", "finished_at"]) ||
    !isText(value.source.task_id) ||
    !isText(value.source.conversation_id) ||
    !isText(value.source.agent_id) ||
    !isText(value.source.finished_at) ||
    !validTaskPattern(value.task_pattern) ||
    !validSkill(value.skill) ||
    !validAssetLevel(value.workflow) ||
    !validAssetLevel(value.agent) ||
    !isText(value.updated_at)
  ) {
    return false;
  }
  const expectedAssetState = ASSET_STATE_BY_CANDIDATE_STATE[value.state];
  if (
    value.task_pattern.state !== expectedAssetState ||
    value.skill.state !== expectedAssetState
  ) {
    return false;
  }
  if (value.state === "accepted") return validPackage(value.skill_package);
  return value.skill_package === null;
}

function validSummary(summary) {
  return (
    hasExactKeys(summary, [
      "capability_count",
      "asset_candidate_count",
      "accepted_candidate_count",
      "skill_package_count",
      "approved_skill_package_count",
      "unresolved_reference_count",
    ]) &&
    isCount(summary.capability_count) &&
    isCount(summary.asset_candidate_count) &&
    isCount(summary.accepted_candidate_count) &&
    isCount(summary.skill_package_count) &&
    isCount(summary.approved_skill_package_count) &&
    isCount(summary.unresolved_reference_count) &&
    summary.capability_count <= MAX_CAPABILITIES &&
    summary.asset_candidate_count <= MAX_ASSETS &&
    summary.accepted_candidate_count <= MAX_ASSETS &&
    summary.skill_package_count <= MAX_ASSETS &&
    summary.approved_skill_package_count <= MAX_ASSETS
  );
}

function validEnvelope(snapshot) {
  if (
    !hasExactKeys(snapshot, [
      "schema_version",
      "source",
      "summary",
      "functionality",
      "assets",
      "effects",
    ]) ||
    snapshot.schema_version !== "feature_asset_map.v1" ||
    !hasExactKeys(snapshot.source, ["kind", "owner_username", "owner_scoped", "read_only"]) ||
    snapshot.source.kind !== "owner_scoped_cold_projection" ||
    !isText(snapshot.source.owner_username) ||
    snapshot.source.owner_scoped !== true ||
    snapshot.source.read_only !== true ||
    !validSummary(snapshot.summary) ||
    !hasExactKeys(snapshot.functionality, ["work_types", "domains", "capabilities"]) ||
    !Array.isArray(snapshot.functionality.work_types) ||
    snapshot.functionality.work_types.length > MAX_CAPABILITIES ||
    !snapshot.functionality.work_types.every(validFacet) ||
    !Array.isArray(snapshot.functionality.domains) ||
    snapshot.functionality.domains.length > MAX_CAPABILITIES ||
    !snapshot.functionality.domains.every(validFacet) ||
    !Array.isArray(snapshot.functionality.capabilities) ||
    snapshot.functionality.capabilities.length > MAX_CAPABILITIES ||
    !snapshot.functionality.capabilities.every(validCapability) ||
    !Array.isArray(snapshot.assets) ||
    snapshot.assets.length > MAX_ASSETS ||
    !snapshot.assets.every(validAsset) ||
    !hasExactKeys(snapshot.effects, [
      "writes_database",
      "executes_work",
      "registers_asset",
      "promotes_asset",
    ]) ||
    snapshot.effects.writes_database !== false ||
    snapshot.effects.executes_work !== false ||
    snapshot.effects.registers_asset !== false ||
    snapshot.effects.promotes_asset !== false
  ) {
    return false;
  }
  const packages = snapshot.assets
    .map((asset) => asset.skill_package)
    .filter((value) => value !== null);
  return (
    snapshot.summary.capability_count === snapshot.functionality.capabilities.length &&
    snapshot.summary.asset_candidate_count === snapshot.assets.length &&
    snapshot.summary.accepted_candidate_count ===
      snapshot.assets.filter((asset) => asset.state === "accepted").length &&
    snapshot.summary.skill_package_count === packages.length &&
    snapshot.summary.approved_skill_package_count ===
      packages.filter((pkg) => pkg.state === "approved").length &&
    snapshot.summary.unresolved_reference_count ===
      snapshot.functionality.capabilities.reduce(
        (total, capability) => total + capability.unresolved_reference_count,
        0,
      )
  );
}

export function candidatePresentation(state) {
  return CANDIDATE_PRESENTATIONS[state] || CANDIDATE_PRESENTATIONS.awaiting_human_review;
}

export function packagePresentation(state) {
  return PACKAGE_PRESENTATIONS[state] || PACKAGE_PRESENTATIONS.not_formed;
}

export function buildFeatureAssetMapView(snapshot) {
  if (!validEnvelope(snapshot)) return INVALID_VIEW;
  return {
    available: true,
    ownerUsername: snapshot.source.owner_username,
    summary: {
      capabilityCount: snapshot.summary.capability_count,
      assetCandidateCount: snapshot.summary.asset_candidate_count,
      acceptedCandidateCount: snapshot.summary.accepted_candidate_count,
      skillPackageCount: snapshot.summary.skill_package_count,
      approvedSkillPackageCount: snapshot.summary.approved_skill_package_count,
      unresolvedReferenceCount: snapshot.summary.unresolved_reference_count,
    },
    workTypes: snapshot.functionality.work_types.map((item) => ({ ...item })),
    domains: snapshot.functionality.domains.map((item) => ({ ...item })),
    capabilities: snapshot.functionality.capabilities.map((capability) => ({
      id: capability.agent_id,
      name: capability.name || capability.agent_id,
      summary: capability.summary,
      category: capability.category,
      domain: capability.domain,
      launchKind: capability.launch_kind,
      status: capability.status,
      maturity: capability.maturity,
      requiresHumanReview: capability.requires_human_review,
      unresolvedReferenceCount: capability.unresolved_reference_count,
      mockToolCount: capability.mock_tool_count,
    })),
    assets: snapshot.assets.map((asset) => ({
      id: asset.candidate_id,
      state: asset.state,
      taskPatternTitle: asset.task_pattern.title,
      skillName: asset.skill.name,
      skillDescription: asset.skill.description,
      packageName: asset.skill_package?.name || null,
      packageVersion: asset.skill_package?.version || null,
      packageState: asset.skill_package?.state || null,
      reuseEligible: asset.skill_package?.reuse_eligible === true,
      workflowState: asset.workflow.state,
      agentState: asset.agent.state,
      sourceAgentId: asset.source.agent_id,
      updatedAt: asset.updated_at,
    })),
  };
}
