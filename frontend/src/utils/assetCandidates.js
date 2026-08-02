const DIGEST = /^sha256:[0-9a-f]{64}$/;
const CANDIDATE_ID = /^asset_candidate_[0-9a-f]{24}$/;
const RAW_DIGEST = /^[0-9a-f]{64}$/;
const STATES = new Set(["awaiting_human_review", "accepted", "rejected"]);
const INPUT_FILE_SOURCES = new Set([
  "work_segment_upload",
  "upstream_task_output",
]);


function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${label} 必须是对象`);
  }
  return value;
}


function text(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${label} 必须是非空文本`);
  }
  return value;
}


function digest(value, label) {
  if (typeof value !== "string" || !DIGEST.test(value)) {
    throw new TypeError(`${label} 不是规范摘要`);
  }
  return value;
}


function exactEffects(value, expected, label) {
  const effects = object(value, label);
  for (const [key, required] of Object.entries(expected)) {
    if (effects[key] !== required) {
      throw new TypeError(`${label}.${key} 与安全契约不一致`);
    }
  }
}


function canonicalValue(value) {
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") return value.normalize("NFC");
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") {
    const entries = Object.entries(value)
      .map(([key, item]) => [key.normalize("NFC"), canonicalValue(item)])
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
    if (new Set(entries.map(([key]) => key)).size !== entries.length) {
      throw new TypeError("规范对象含 Unicode 重名字段");
    }
    return Object.fromEntries(entries);
  }
  throw new TypeError("候选内容含不可规范化值");
}


async function canonicalDigest(value) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle || typeof globalThis.TextEncoder !== "function") {
    throw new TypeError("当前环境无法核验资产候选摘要");
  }
  const payload = new TextEncoder().encode(JSON.stringify(canonicalValue(value)));
  const bytes = new Uint8Array(await subtle.digest("SHA-256", payload));
  return `sha256:${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}


function without(value, keys) {
  const copy = { ...object(value, "digest basis") };
  for (const key of keys) delete copy[key];
  return copy;
}


function fileReferences(value, { label, expectedKind, sourceTaskId }) {
  if (!Array.isArray(value) || value.length > 64) {
    throw new TypeError(`${label} 必须是有限文件引用列表`);
  }
  const seen = new Set();
  for (const item of value) {
    const reference = object(item, label);
    const fileId = text(reference.file_id, `${label}.file_id`);
    if (seen.has(fileId)) throw new TypeError(`${label} 含重复文件引用`);
    seen.add(fileId);
    if (typeof reference.sha256 !== "string" || !RAW_DIGEST.test(reference.sha256)) {
      throw new TypeError(`${label}.sha256 不是原始文件摘要`);
    }
    if (!Number.isInteger(reference.size_bytes) || reference.size_bytes < 0) {
      throw new TypeError(`${label}.size_bytes 不合法`);
    }
    if (reference.classification !== "internal") {
      throw new TypeError(`${label} 只接受 internal 文件`);
    }
    if (expectedKind === "output") {
      if (
        reference.kind !== "output"
        ||
        reference.source_kind !== "current_task_output"
        || reference.producer_task_id !== sourceTaskId
      ) {
        throw new TypeError(`${label} 没有绑定当前任务输出`);
      }
    } else if (!INPUT_FILE_SOURCES.has(reference.source_kind)) {
      throw new TypeError(`${label}.source_kind 不受支持`);
    } else if (
      (reference.source_kind === "work_segment_upload"
        && (reference.kind !== "input" || reference.producer_task_id !== null))
      || (reference.source_kind === "upstream_task_output"
        && (reference.kind !== "output"
          || typeof reference.producer_task_id !== "string"
          || reference.producer_task_id.trim() === ""))
    ) {
      throw new TypeError(`${label} 的生产任务血缘不完整`);
    }
  }
}


export function eligibleAssetCandidateTask(tasks) {
  if (!Array.isArray(tasks) || tasks.length !== 1) return null;
  const task = tasks[0];
  if (!task || typeof task !== "object" || Array.isArray(task)) return null;
  if (task.status !== "completed" || task.origin !== "user") return null;
  if (typeof task.id !== "string" || task.id.trim() === "") return null;
  return task;
}


export function assetCandidateRequestIsCurrent(expected, current) {
  if (
    !expected
    || typeof expected !== "object"
    || !current
    || typeof current !== "object"
  ) return false;
  return (
    Number.isInteger(expected.seq)
    && expected.seq === current.seq
    && typeof expected.taskId === "string"
    && expected.taskId !== ""
    && expected.taskId === current.taskId
    && typeof expected.conversationId === "string"
    && expected.conversationId !== ""
    && expected.conversationId === current.conversationId
  );
}


export function assetCandidateReconcileCreateReason(status, detail) {
  if (status === 404) return "missing";
  if (
    status === 409
    && detail
    && typeof detail === "object"
    && !Array.isArray(detail)
    && detail.code === "candidate_source_drift"
  ) return "source_drift";
  return null;
}


export function normalizeAssetCandidate(value, { expectedTaskId } = {}) {
  const candidate = object(value, "asset candidate");
  if (candidate.schema_version !== "asset_candidate.v1") {
    throw new TypeError("资产候选版本不受支持");
  }
  if (typeof candidate.id !== "string" || !CANDIDATE_ID.test(candidate.id)) {
    throw new TypeError("资产候选 ID 不合法");
  }
  digest(candidate.candidate_digest, "candidate_digest");
  digest(candidate.bundle_digest, "bundle_digest");
  digest(candidate.lineage_digest, "lineage_digest");
  if (!Number.isInteger(candidate.revision) || candidate.revision < 1) {
    throw new TypeError("资产候选修订号不合法");
  }
  if (candidate.supersedes_candidate_digest !== null) {
    digest(
      candidate.supersedes_candidate_digest,
      "supersedes_candidate_digest",
    );
  }
  if (
    (candidate.revision === 1 && candidate.supersedes_candidate_digest !== null)
    || (candidate.revision > 1 && candidate.supersedes_candidate_digest === null)
  ) {
    throw new TypeError("资产候选修订血缘不完整");
  }
  if (!STATES.has(candidate.state)) throw new TypeError("资产候选状态不受支持");

  const source = object(candidate.source, "source");
  const sourceTaskId = text(source.task_id, "source.task_id");
  if (expectedTaskId !== undefined && sourceTaskId !== expectedTaskId) {
    throw new TypeError("资产候选没有绑定预期任务");
  }
  if (source.task_status !== "completed") {
    throw new TypeError("资产候选来源任务不是 completed");
  }
  text(source.conversation_id, "source.conversation_id");
  text(source.agent_id, "source.agent_id");
  text(source.agent_version, "source.agent_version");
  const initiatedByUsername = text(
    source.initiated_by_username,
    "source.initiated_by_username",
  );
  if (typeof source.agent_package_digest !== "string" || !RAW_DIGEST.test(source.agent_package_digest)) {
    throw new TypeError("Agent Package 摘要不合法");
  }

  const bundle = object(candidate.bundle, "bundle");
  if (bundle.schema_version !== "asset_draft_bundle.v1") {
    throw new TypeError("候选草稿包版本不受支持");
  }
  if (digest(bundle.draft_digest, "bundle.draft_digest") !== candidate.bundle_digest) {
    throw new TypeError("候选与草稿摘要不一致");
  }
  const review = object(bundle.review, "bundle.review");
  if (review.decision_state !== "not_recorded") {
    throw new TypeError("Draft Bundle 不得承载候选决定");
  }
  exactEffects(bundle.effects, {
    writes_database: false,
    executes_work: false,
    registers_asset: false,
    promotes_asset: false,
  }, "bundle.effects");
  exactEffects(candidate.effects, {
    writes_candidate_store: true,
    executes_work: false,
    writes_package_files: false,
    registers_asset: false,
    promotes_asset: false,
  }, "effects");

  const taskPattern = object(bundle.task_pattern, "bundle.task_pattern");
  const skill = object(bundle.skill, "bundle.skill");
  const map = object(candidate.asset_map, "asset_map");
  const expectedRevisionState = candidate.state === "accepted"
    ? "approved_revision"
    : candidate.state === "rejected"
      ? "rejected_revision"
      : "candidate_revision";
  for (const [key, expectedDigest] of [
    ["task_pattern", taskPattern.content_digest],
    ["skill", skill.content_digest],
  ]) {
    const formed = object(map[key], `asset_map.${key}`);
    if (formed.state !== expectedRevisionState) {
      throw new TypeError(`${key} 资格状态与候选状态不一致`);
    }
    if (digest(formed.digest, `asset_map.${key}.digest`) !== digest(expectedDigest, `${key}.content_digest`)) {
      throw new TypeError(`${key} 摘要与草稿内容不一致`);
    }
  }
  for (const key of ["workflow", "agent"]) {
    const gated = object(map[key], `asset_map.${key}`);
    if (gated.state !== "not_formed" || gated.digest !== null) {
      throw new TypeError(`${key} 不得由单个任务候选伪造`);
    }
    text(gated.gate, `asset_map.${key}.gate`);
  }

  if (candidate.state === "awaiting_human_review") {
    if (candidate.decision !== null) {
      throw new TypeError("待审候选不得已有人工决定");
    }
  } else {
    const decision = object(candidate.decision, "decision");
    const expectedAction = candidate.state === "accepted" ? "accept" : "reject";
    if (
      decision.action !== expectedAction
      || decision.signer_source !== "authenticated_session"
      || decision.signer_session_bound !== true
    ) {
      throw new TypeError("候选终态没有有效的人签绑定");
    }
    text(decision.decided_by, "decision.decided_by");
    if (
      text(decision.decided_by_username, "decision.decided_by_username")
      !== initiatedByUsername
    ) {
      throw new TypeError("候选决定签发者与任务所有者不一致");
    }
    text(decision.created_at, "decision.created_at");
  }
  const lineage = object(candidate.lineage, "lineage");
  if (lineage.schema_version !== "asset_candidate_lineage.v1") {
    throw new TypeError("资产候选血缘版本不受支持");
  }
  fileReferences(lineage.input_files, {
    label: "lineage.input_files",
    expectedKind: "input",
    sourceTaskId,
  });
  fileReferences(lineage.output_files, {
    label: "lineage.output_files",
    expectedKind: "output",
    sourceTaskId,
  });
  const taskLineage = object(lineage.task, "lineage.task");
  if (
    taskLineage.task_id !== sourceTaskId
    || taskLineage.agent_id !== source.agent_id
    || taskLineage.agent_version !== source.agent_version
    || taskLineage.agent_package_digest !== source.agent_package_digest
    || taskLineage.initiated_by_username !== initiatedByUsername
    || taskLineage.terminal_status !== "completed"
    || taskLineage.finished_at !== source.finished_at
  ) {
    throw new TypeError("任务血缘与候选来源不一致");
  }
  digest(taskLineage.inputs_digest, "lineage.task.inputs_digest");
  digest(taskLineage.task_snapshot_digest, "lineage.task.task_snapshot_digest");
  const conversationLineage = object(lineage.conversation, "lineage.conversation");
  const workCase = object(bundle.work_case, "bundle.work_case");
  if (
    conversationLineage.conversation_id !== source.conversation_id
    || workCase.source_id !== source.conversation_id
    || conversationLineage.work_case_source_revision !== workCase.source_revision
  ) {
    throw new TypeError("会话血缘与 Work Case 不一致");
  }
  const executionSnapshot = object(
    lineage.execution_snapshot,
    "lineage.execution_snapshot",
  );
  text(executionSnapshot.event_id, "lineage.execution_snapshot.event_id");
  digest(
    executionSnapshot.event_digest,
    "lineage.execution_snapshot.event_digest",
  );
  digest(
    executionSnapshot.input_file_ids_digest,
    "lineage.execution_snapshot.input_file_ids_digest",
  );
  digest(
    executionSnapshot.input_files_digest,
    "lineage.execution_snapshot.input_files_digest",
  );
  if (
    digest(
      executionSnapshot.task_inputs_digest,
      "lineage.execution_snapshot.task_inputs_digest",
    ) !== taskLineage.inputs_digest
  ) {
    throw new TypeError("执行快照没有绑定任务输入摘要");
  }
  const executionEvidenceDigest = digest(
    executionSnapshot.execution_evidence_digest,
    "lineage.execution_snapshot.execution_evidence_digest",
  );
  text(
    executionSnapshot.package_snapshot_contract,
    "lineage.execution_snapshot.package_snapshot_contract",
  );
  if (
    executionSnapshot.package_snapshot_digest !== source.agent_package_digest
    || !RAW_DIGEST.test(executionSnapshot.package_snapshot_digest)
  ) {
    throw new TypeError("执行时 Package 摘要与候选来源不一致");
  }
  const signoff = object(lineage.signoff, "lineage.signoff");
  text(signoff.event_id, "lineage.signoff.event_id");
  digest(signoff.event_digest, "lineage.signoff.event_digest");
  if (
    digest(
      signoff.execution_evidence_digest,
      "lineage.signoff.execution_evidence_digest",
    ) !== executionEvidenceDigest
  ) {
    throw new TypeError("任务签发没有绑定执行时的同一输入证据");
  }
  if (
    signoff.kind === "human_review_approved"
    && signoff.required === true
  ) {
    text(signoff.signer_username, "lineage.signoff.signer_username");
  } else if (
    signoff.kind !== "deterministic_no_review"
    || signoff.required !== false
    || signoff.signer_username !== null
  ) {
    throw new TypeError("任务签发血缘不受支持");
  }
  const provenance = object(candidate.proposal_provenance, "proposal_provenance");
  const expectedSources = [
    "work_case_segment",
    "completed_task",
    "agent_package_snapshot",
    "artifact_digests",
    "signoff_evidence",
  ];
  if (
    provenance.schema_version !== "generalization_proposal_provenance.v1"
    || provenance.kind !== "deterministic_task_projection"
    || provenance.policy_version !== "asset_candidate_policy.v1"
    || provenance.llm_used !== false
    || !Array.isArray(provenance.sources)
    || provenance.sources.length !== expectedSources.length
    || provenance.sources.some((item, index) => item !== expectedSources[index])
  ) {
    throw new TypeError("Generalization Proposal 来源不受支持");
  }
  text(candidate.created_at, "created_at");
  text(candidate.updated_at, "updated_at");
  return candidate;
}


export async function verifyAssetCandidateIntegrity(value, options = {}) {
  const candidate = normalizeAssetCandidate(value, options);
  const taskPattern = candidate.bundle.task_pattern;
  const taskPatternDigest = await canonicalDigest(
    without(taskPattern, ["suggested_id", "content_digest"]),
  );
  if (
    taskPattern.content_digest !== taskPatternDigest
    || taskPattern.suggested_id
      !== `task_pattern_candidate_${taskPatternDigest.slice("sha256:".length, "sha256:".length + 12)}`
  ) {
    throw new TypeError("Task Pattern 草稿内容与地址摘要不一致");
  }

  const skill = candidate.bundle.skill;
  if (skill.operationalizes_task_pattern_digest !== taskPatternDigest) {
    throw new TypeError("Skill 草稿没有咬合 Task Pattern 摘要");
  }
  const skillDigest = await canonicalDigest(
    without(skill, ["suggested_id", "content_digest"]),
  );
  if (
    skill.content_digest !== skillDigest
    || skill.suggested_id
      !== `skill_candidate_${skillDigest.slice("sha256:".length, "sha256:".length + 12)}`
  ) {
    throw new TypeError("Skill 草稿内容与地址摘要不一致");
  }

  const bundleDigest = await canonicalDigest(
    without(candidate.bundle, ["draft_digest"]),
  );
  if (
    candidate.bundle.draft_digest !== bundleDigest
    || candidate.bundle_digest !== bundleDigest
  ) {
    throw new TypeError("资产草稿包内容与地址摘要不一致");
  }

  const lineageDigest = await canonicalDigest(candidate.lineage);
  if (candidate.lineage_digest !== lineageDigest) {
    throw new TypeError("资产候选血缘与地址摘要不一致");
  }
  const inputFileIdsDigest = await canonicalDigest(
    candidate.lineage.input_files.map((item) => item.file_id),
  );
  if (
    candidate.lineage.execution_snapshot.input_file_ids_digest
    !== inputFileIdsDigest
  ) {
    throw new TypeError("执行快照没有绑定候选输入文件清单");
  }
  const executionEvidenceDigest = await canonicalDigest({
    package_snapshot_digest:
      candidate.lineage.execution_snapshot.package_snapshot_digest,
    task_inputs_digest: candidate.lineage.task.inputs_digest,
    input_file_ids: candidate.lineage.input_files.map((item) => item.file_id),
    input_files_digest:
      candidate.lineage.execution_snapshot.input_files_digest,
  });
  if (
    candidate.lineage.execution_snapshot.execution_evidence_digest
      !== executionEvidenceDigest
    || candidate.lineage.signoff.execution_evidence_digest
      !== executionEvidenceDigest
  ) {
    throw new TypeError("执行、完成与签发没有绑定同一份输入证据");
  }

  const proposalProvenanceDigest = await canonicalDigest(
    candidate.proposal_provenance,
  );
  const candidateDigest = await canonicalDigest({
    schema_version: "asset_candidate.v1",
    revision: candidate.revision,
    supersedes_candidate_digest: candidate.supersedes_candidate_digest,
    bundle_digest: bundleDigest,
    lineage_digest: lineageDigest,
    proposal_provenance_digest: proposalProvenanceDigest,
    validation_policy_version: "asset_candidate_policy.v1",
  });
  if (
    candidate.candidate_digest !== candidateDigest
    || candidate.id
      !== `asset_candidate_${candidateDigest.slice("sha256:".length, "sha256:".length + 24)}`
  ) {
    throw new TypeError("资产候选内容与地址摘要不一致");
  }
  return candidate;
}


export function buildAssetCandidateDecisionRequest(candidateValue, action) {
  const candidate = normalizeAssetCandidate(candidateValue, {
    expectedTaskId: candidateValue?.source?.task_id,
  });
  if (candidate.state !== "awaiting_human_review") {
    throw new TypeError("只有待审候选可以作决定");
  }
  if (action !== "accept" && action !== "reject") {
    throw new TypeError("候选决定只接受 accept 或 reject");
  }
  return {
    schema_version: "asset_candidate_decision_request.v1",
    action,
    expected_candidate_digest: candidate.candidate_digest,
    expected_bundle_digest: candidate.bundle_digest,
  };
}
