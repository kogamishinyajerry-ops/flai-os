import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import {
  assetCandidateReconcileCreateReason,
  assetCandidateRequestIsCurrent,
  buildAssetCandidateDecisionRequest,
  buildSkillPackageDecisionRequest,
  eligibleAssetCandidateTask,
  normalizeAssetCandidate,
  normalizeSkillPackage,
  normalizeSkillPackageReviewContent,
  normalizeSkillReuseRef,
  verifySkillPackageDecisionResponse,
  verifyAssetCandidateIntegrity,
} from "../src/utils/assetCandidates.js";
import {
  decideSkillPackage,
  getSkillPackageReviewContent,
} from "../src/api/assetCandidates.js";
import { getUiAcceptanceCase } from "../src/ui-lab/uiAcceptanceCases.js";


const guideSource = readFileSync(
  new URL("../src/views/GuidePage.vue", import.meta.url),
  "utf8",
);
const calloutSource = readFileSync(
  new URL("../src/components/AssetCandidateCallout.vue", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(
  new URL("../src/api/assetCandidates.js", import.meta.url),
  "utf8",
);


const digest = (char) => `sha256:${char.repeat(64)}`;

const skillPackageReviewFiles = [
  { path: "SKILL.md", text: "---\nname: entry-review-method\ndescription: Review an entry.\n---\n\n# Method\n" },
  { path: "references/provenance.json", text: "{\"source\":\"accepted_candidate\"}\n" },
  { path: "references/skill-revision.json", text: "{\"schema_version\":\"skill_draft.v1\"}\n" },
  { path: "references/task-pattern-revision.json", text: "{\"schema_version\":\"task_pattern_draft.v1\"}\n" },
];

function reviewFileManifest() {
  return skillPackageReviewFiles.map((file) => ({
    path: file.path,
    size_bytes: Buffer.byteLength(file.text, "utf8"),
    sha256: createHash("sha256").update(file.text, "utf8").digest("hex"),
  }));
}

function skillPackage(state = "pending_review") {
  return {
    schema_version: "skill_package_revision.v1",
    id: `skill_package_${"2".repeat(24)}`,
    name: "entry-review-method",
    version: "0.1.0",
    package_digest: digest("2"),
    state,
    source: {
      candidate_id: `asset_candidate_${"a".repeat(24)}`,
      candidate_digest: digest("a"),
      bundle_digest: digest("b"),
      skill_digest: digest("1"),
      acceptance_event_digest: digest("8"),
      task_id: "task_done",
      agent_id: "hello_agent",
      initiated_by_username: "test_engineer",
    },
    storage_relpath: `entry-review-method/0.1.0/${"2".repeat(64)}`,
    files: reviewFileManifest(),
    review: state === "pending_review" ? null : {
      action: state === "approved" ? "approve" : "reject",
      reviewed_by: "测试工程师",
      reviewed_by_username: "test_engineer",
      signer_source: "authenticated_session",
      signer_session_bound: true,
      created_at: "2026-08-02T00:02:00Z",
    },
    isolation: {
      zone: "candidate_quarantine",
      registered: false,
      executable: false,
    },
    reuse_eligible: state === "approved",
    formation_evidence: {
      schema_version: "composition_eligibility.v1",
      independent_work_case_count: 0,
      required_independent_work_cases: 2,
      workflow_candidate: {
        state: "not_formed",
        eligible: false,
        reason: "requires_independent_composition_evidence",
      },
      agent_candidate: {
        state: "not_formed",
        eligible: false,
        reason: "requires_approved_workflow_revision",
      },
    },
    created_at: "2026-08-02T00:01:00Z",
    updated_at: "2026-08-02T00:01:00Z",
  };
}

function skillPackageReviewContent() {
  return {
    schema_version: "skill_package_review_content.v1",
    package_id: `skill_package_${"2".repeat(24)}`,
    package_digest: digest("2"),
    files: skillPackageReviewFiles.map((file) => ({ ...file })),
  };
}

function candidate(state = "awaiting_human_review") {
  const action = state === "accepted" ? "accept" : "reject";
  return {
    schema_version: "asset_candidate.v1",
    id: `asset_candidate_${"a".repeat(24)}`,
    candidate_digest: digest("a"),
    bundle_digest: digest("b"),
    lineage_digest: digest("c"),
    revision: 1,
    supersedes_candidate_digest: null,
    state,
    source: {
      task_id: "task_done",
      conversation_id: "conv_done",
      task_status: "completed",
      agent_id: "hello_agent",
      agent_version: "0.1.0",
      agent_package_digest: "d".repeat(64),
      initiated_by_username: "test_engineer",
      finished_at: "2026-08-02T00:00:00Z",
    },
    bundle: {
      schema_version: "asset_draft_bundle.v1",
      draft_digest: digest("b"),
      work_case: {
        source_id: "conv_done",
        source_revision: digest("e"),
      },
      task_pattern: {
        title: "入口复核方法",
        trigger: "收到待复核工程任务",
        desired_outcome: "形成可核对结果",
        inputs: ["工程输入"],
        outputs: ["复核结果"],
        steps: ["核对输入", "核验证据"],
        evidence_requirements: ["保留摘要"],
        human_decision_points: ["工程师判断"],
        limitations: ["仅有一个案例"],
        content_digest: digest("f"),
      },
      skill: {
        name: "入口复核 Skill",
        description: "按证据完成入口复核",
        instructions: ["核对输入", "核验证据"],
        verification: ["保留摘要"],
        human_boundaries: ["工程师判断"],
        content_digest: digest("1"),
      },
      review: { decision_state: "not_recorded" },
      effects: {
        writes_database: false,
        executes_work: false,
        registers_asset: false,
        promotes_asset: false,
      },
    },
    lineage: {
      schema_version: "asset_candidate_lineage.v1",
      task: {
        task_id: "task_done",
        agent_id: "hello_agent",
        agent_version: "0.1.0",
        agent_package_digest: "d".repeat(64),
        initiated_by_username: "test_engineer",
        terminal_status: "completed",
        finished_at: "2026-08-02T00:00:00Z",
        inputs_digest: digest("0"),
        task_snapshot_digest: digest("2"),
      },
      conversation: {
        conversation_id: "conv_done",
        work_case_source_revision: digest("e"),
      },
      input_files: [],
      output_files: [],
      execution_snapshot: {
        event_id: "event_validation_started",
        event_digest: digest("3"),
        package_snapshot_contract: "agent_package_snapshot.v1",
        package_snapshot_digest: "d".repeat(64),
        input_file_ids_digest: digest("4"),
        input_files_digest: digest("5"),
        task_inputs_digest: digest("0"),
        execution_evidence_digest: digest("7"),
      },
      signoff: {
        required: false,
        kind: "deterministic_no_review",
        event_id: "event_task_completed",
        event_digest: digest("6"),
        signer_username: null,
        execution_evidence_digest: digest("7"),
      },
    },
    proposal_provenance: {
      schema_version: "generalization_proposal_provenance.v1",
      kind: "deterministic_task_projection",
      policy_version: "asset_candidate_policy.v1",
      llm_used: false,
      sources: [
        "work_case_segment",
        "completed_task",
        "agent_package_snapshot",
        "artifact_digests",
        "signoff_evidence",
      ],
    },
    asset_map: {
      task_pattern: {
        state: state === "accepted" ? "approved_revision" : state === "rejected" ? "rejected_revision" : "candidate_revision",
        digest: digest("f"),
      },
      skill: {
        state: state === "accepted" ? "approved_revision" : state === "rejected" ? "rejected_revision" : "candidate_revision",
        digest: digest("1"),
      },
      workflow: {
        state: "not_formed",
        digest: null,
        gate: "需要已批准 Skill 的组合关系",
      },
      agent: {
        state: "not_formed",
        digest: null,
        gate: "需要 Package、Registry、Eval 与人工晋级门",
      },
    },
    decision: state === "awaiting_human_review" ? null : {
      action,
      decided_by: "测试工程师",
      decided_by_username: "test_engineer",
      signer_source: "authenticated_session",
      signer_session_bound: true,
      created_at: "2026-08-02T00:01:00Z",
    },
    skill_package: state === "accepted" ? skillPackage() : null,
    effects: {
      writes_candidate_store: true,
      executes_work: false,
      writes_package_files: false,
      registers_asset: false,
      promotes_asset: false,
    },
    created_at: "2026-08-02T00:00:30Z",
    updated_at: "2026-08-02T00:00:30Z",
  };
}


test("只有恰好一个权威 completed 用户任务才自动形成单候选", () => {
  const completed = { id: "task_done", status: "completed", origin: "user" };
  assert.deepEqual(eligibleAssetCandidateTask([completed]), completed);
  for (const status of ["created", "queued", "running", "waiting_review", "failed", "cancelled"] ) {
    assert.equal(
      eligibleAssetCandidateTask([{ ...completed, status }]),
      null,
      `${status} 不得出现候选成功态`,
    );
  }
  assert.equal(eligibleAssetCandidateTask([{ ...completed, origin: "eval" }]), null);
  assert.equal(eligibleAssetCandidateTask([completed, { ...completed, id: "task_2" }]), null);
  assert.equal(eligibleAssetCandidateTask([]), null);
});


test("候选投影同时咬合任务、两层摘要、零执行副作用与层级门", () => {
  const normalized = normalizeAssetCandidate(candidate(), { expectedTaskId: "task_done" });
  assert.equal(normalized.state, "awaiting_human_review");
  assert.equal(normalized.asset_map.workflow.state, "not_formed");
  assert.equal(normalized.asset_map.agent.state, "not_formed");

  const attacks = [
    (value) => { value.source.task_status = "waiting_review"; },
    (value) => { value.source.task_id = "task_other"; },
    (value) => { value.bundle.draft_digest = digest("9"); },
    (value) => { value.bundle.review.decision_state = "approved"; },
    (value) => { value.effects.registers_asset = true; },
    (value) => { value.asset_map.workflow.state = "approved_revision"; },
    (value) => { value.asset_map.agent.digest = digest("8"); },
    (value) => { value.lineage.execution_snapshot.package_snapshot_digest = "8".repeat(64); },
    (value) => { value.lineage.execution_snapshot.input_file_ids_digest = "bad"; },
    (value) => { value.lineage.execution_snapshot.task_inputs_digest = digest("9"); },
    (value) => { value.lineage.execution_snapshot.execution_evidence_digest = digest("9"); },
    (value) => { value.lineage.signoff.execution_evidence_digest = digest("9"); },
    (value) => { value.lineage.signoff.event_id = null; },
    (value) => { value.lineage.signoff.required = true; },
    (value) => { delete value.lineage.execution_snapshot; },
    (value) => { value.revision = 0; },
    (value) => { value.revision = 1.5; },
    (value) => { value.supersedes_candidate_digest = "not-a-digest"; },
    (value) => { value.revision = 2; },
    (value) => { value.supersedes_candidate_digest = digest("9"); },
  ];
  for (const mutate of attacks) {
    const invalid = structuredClone(candidate());
    mutate(invalid);
    assert.throws(
      () => normalizeAssetCandidate(invalid, { expectedTaskId: "task_done" }),
      TypeError,
    );
  }
});


test("候选完整性核验重算草稿、血缘、来源、候选地址与输入清单", async () => {
  const pending = getUiAcceptanceCase("asset-candidate-desktop").guide.assetCandidate;
  const accepted = getUiAcceptanceCase("asset-candidate-accepted-desktop").guide.assetCandidate;
  assert.equal(
    await verifyAssetCandidateIntegrity(pending, {
      expectedTaskId: "task-ui-asset-candidate",
    }),
    pending,
  );
  assert.equal(
    await verifyAssetCandidateIntegrity(accepted, {
      expectedTaskId: "task-ui-asset-candidate",
    }),
    accepted,
  );

  const attacks = [
    (value) => { value.id = `asset_candidate_${"f".repeat(24)}`; },
    (value) => { value.bundle.task_pattern.title = "被篡改的方法"; },
    (value) => { value.lineage.task.task_id = "task-other"; },
    (value) => { value.lineage.execution_snapshot.input_files_digest = digest("9"); },
    (value) => { value.lineage.execution_snapshot.execution_evidence_digest = digest("9"); },
    (value) => { value.lineage.signoff.execution_evidence_digest = digest("9"); },
    (value) => { value.proposal_provenance.llm_used = true; },
  ];
  for (const mutate of attacks) {
    const invalid = structuredClone(pending);
    mutate(invalid);
    await assert.rejects(
      () => verifyAssetCandidateIntegrity(invalid, {
        expectedTaskId: "task-ui-asset-candidate",
      }),
      TypeError,
    );
  }

  const invalidDecision = structuredClone(accepted);
  invalidDecision.decision.decided_by_username = "";
  await assert.rejects(
    () => verifyAssetCandidateIntegrity(invalidDecision, {
      expectedTaskId: "task-ui-asset-candidate",
    }),
    TypeError,
  );
  const crossOwnerDecision = structuredClone(accepted);
  crossOwnerDecision.decision.decided_by_username = "other_engineer";
  await assert.rejects(
    () => verifyAssetCandidateIntegrity(crossOwnerDecision, {
      expectedTaskId: "task-ui-asset-candidate",
    }),
    TypeError,
  );
});


test("文件血缘只接受当前工作片段上传、已解析上游输出或当前任务输出", () => {
  const directInput = candidate();
  directInput.lineage.input_files = [{
    file_id: "input_1",
    kind: "input",
    sha256: "7".repeat(64),
    size_bytes: 42,
    classification: "internal",
    source_kind: "work_segment_upload",
    producer_task_id: null,
  }];
  directInput.lineage.output_files = [{
    file_id: "output_1",
    kind: "output",
    sha256: "8".repeat(64),
    size_bytes: 84,
    classification: "internal",
    source_kind: "current_task_output",
    producer_task_id: "task_done",
  }];
  assert.equal(normalizeAssetCandidate(directInput), directInput);

  const upstream = structuredClone(directInput);
  upstream.lineage.input_files[0].kind = "output";
  upstream.lineage.input_files[0].source_kind = "upstream_task_output";
  upstream.lineage.input_files[0].producer_task_id = "task_upstream";
  assert.equal(normalizeAssetCandidate(upstream), upstream);

  for (const mutate of [
    (value) => { value.lineage.input_files[0].producer_task_id = "task_fake"; },
    (value) => { value.lineage.input_files[0].source_kind = "current_task_output"; },
    (value) => { value.lineage.output_files[0].producer_task_id = "task_other"; },
    (value) => { value.lineage.output_files[0].classification = "restricted"; },
  ]) {
    const invalid = structuredClone(directInput);
    mutate(invalid);
    assert.throws(() => normalizeAssetCandidate(invalid), TypeError);
  }
});


test("后续候选修订可精确引用上一版内容摘要", () => {
  const revision = candidate();
  revision.revision = 2;
  revision.supersedes_candidate_digest = digest("9");

  assert.equal(normalizeAssetCandidate(revision).revision, 2);
});


test("异步候选请求只允许回写原序号、原任务与原会话", () => {
  const captured = {
    seq: 7,
    taskId: "task_done",
    conversationId: "conv_done",
  };
  assert.equal(assetCandidateRequestIsCurrent(captured, { ...captured }), true);
  for (const current of [
    { ...captured, seq: 8 },
    { ...captured, taskId: "task_other" },
    { ...captured, conversationId: "conv_other" },
    null,
  ]) {
    assert.equal(assetCandidateRequestIsCurrent(captured, current), false);
  }
});


test("对账只为缺失候选或精确 source drift 自动形成新 Revision", () => {
  assert.equal(assetCandidateReconcileCreateReason(404, null), "missing");
  assert.equal(
    assetCandidateReconcileCreateReason(409, { code: "candidate_source_drift" }),
    "source_drift",
  );
  for (const [status, detail] of [
    [409, { code: "candidate_state_conflict" }],
    [409, "candidate_source_drift"],
    [409, null],
    [500, { code: "candidate_source_drift" }],
    [0, { code: "candidate_source_drift" }],
  ]) {
    assert.equal(assetCandidateReconcileCreateReason(status, detail), null);
  }
});


test("人工决定请求只有动作与两层预期摘要，不接受客户端权威字段", () => {
  assert.deepEqual(
    buildAssetCandidateDecisionRequest(candidate(), "accept"),
    {
      schema_version: "asset_candidate_decision_request.v1",
      action: "accept",
      expected_candidate_digest: digest("a"),
      expected_bundle_digest: digest("b"),
    },
  );
  assert.throws(() => buildAssetCandidateDecisionRequest(candidate(), "approve"), TypeError);
});


test("Candidate 必须携带与接受修订咬合的隔离 Skill Package 投影", () => {
  assert.equal(normalizeAssetCandidate(candidate()).skill_package, null);
  assert.equal(normalizeAssetCandidate(candidate("rejected")).skill_package, null);
  assert.equal(
    normalizeAssetCandidate(candidate("accepted")).skill_package.state,
    "pending_review",
  );

  for (const mutate of [
    (value) => { delete value.skill_package; },
    (value) => { value.skill_package = null; },
    (value) => { value.skill_package.source.candidate_digest = digest("9"); },
    (value) => { value.skill_package.source.skill_digest = digest("9"); },
    (value) => { value.skill_package.isolation.registered = true; },
    (value) => { value.skill_package.isolation.executable = true; },
    (value) => { value.skill_package.formation_evidence.workflow_candidate.eligible = true; },
  ]) {
    const invalid = candidate("accepted");
    mutate(invalid);
    assert.throws(() => normalizeAssetCandidate(invalid), TypeError);
  }
});


test("包级人工复核只发送动作和预期包摘要", () => {
  const pending = skillPackage();
  assert.equal(normalizeSkillPackage(pending), pending);
  assert.deepEqual(buildSkillPackageDecisionRequest(pending, "approve"), {
    schema_version: "skill_package_decision_request.v1",
    action: "approve",
    expected_package_digest: digest("2"),
  });
  assert.deepEqual(buildSkillPackageDecisionRequest(pending, "reject"), {
    schema_version: "skill_package_decision_request.v1",
    action: "reject",
    expected_package_digest: digest("2"),
  });
  assert.throws(() => buildSkillPackageDecisionRequest(pending, "accept"), TypeError);
  assert.throws(
    () => buildSkillPackageDecisionRequest(skillPackage("approved"), "reject"),
    TypeError,
  );
});


test("Skill Package 全层 additionalProperties=false，且允许达到数量门后继续不成 Workflow", () => {
  const base = skillPackage();
  for (const mutate of [
    (value) => { value.model = "manual"; },
    (value) => { value.source.extra = true; },
    (value) => { value.files[0].url = "/unsafe"; },
    (value) => { value.isolation.path = "/agents"; },
    (value) => { value.formation_evidence.extra = true; },
    (value) => { value.formation_evidence.workflow_candidate.extra = true; },
    (value) => { value.formation_evidence.agent_candidate.extra = true; },
  ]) {
    const invalid = structuredClone(base);
    mutate(invalid);
    assert.throws(() => normalizeSkillPackage(invalid), /字段|不受支持/);
  }

  for (const state of ["approved", "rejected"]) {
    const invalid = skillPackage(state);
    invalid.review.extra = true;
    assert.throws(() => normalizeSkillPackage(invalid), /字段|不受支持/);
  }

  const repeated = skillPackage("approved");
  repeated.formation_evidence.independent_work_case_count = 2;
  repeated.formation_evidence.workflow_candidate.reason =
    "requires_stable_multi_skill_composition_evidence";
  assert.equal(normalizeSkillPackage(repeated), repeated);
  assert.equal(repeated.formation_evidence.workflow_candidate.state, "not_formed");
});


test("包级决定响应必须保持全部不可变投影并符合所点动作", () => {
  const pending = skillPackage();
  const approved = skillPackage("approved");
  assert.equal(
    verifySkillPackageDecisionResponse(pending, approved, "approve"),
    approved,
  );

  for (const mutate of [
    (value) => { value.name = "different-method"; },
    (value) => { value.source.task_id = "different-task"; },
    (value) => { value.files[0].sha256 = "7".repeat(64); },
    (value) => { value.storage_relpath = "quarantine/other"; },
    (value) => { value.isolation.zone = "agents"; },
    (value) => { value.created_at = "2026-08-02T00:00:00Z"; },
  ]) {
    const drifted = skillPackage("approved");
    mutate(drifted);
    assert.throws(
      () => verifySkillPackageDecisionResponse(pending, drifted, "approve"),
      TypeError,
    );
  }
  assert.throws(
    () => verifySkillPackageDecisionResponse(pending, skillPackage("rejected"), "approve"),
    /动作|状态/,
  );
});


test("真实包审阅内容逐文件核验 UTF-8 字节数与 SHA-256，并咬合当前包", async () => {
  const pending = skillPackage();
  const content = skillPackageReviewContent();
  assert.equal(
    await normalizeSkillPackageReviewContent(content, {
      expectedPackageId: pending.id,
      expectedPackageDigest: pending.package_digest,
      expectedFiles: pending.files,
    }),
    content,
  );
  for (const mutate of [
    (value) => { value.extra = true; },
    (value) => { value.package_id = `skill_package_${"9".repeat(24)}`; },
    (value) => { value.package_digest = digest("9"); },
    (value) => { value.files[0].html = "<script>"; },
    (value) => { value.files.pop(); },
    (value) => { value.files[0].path = "README.md"; },
    (value) => { value.files[0].text += "tampered"; },
  ]) {
    const invalid = structuredClone(content);
    mutate(invalid);
    await assert.rejects(
      normalizeSkillPackageReviewContent(invalid, {
        expectedPackageId: pending.id,
        expectedPackageDigest: pending.package_digest,
        expectedFiles: pending.files,
      }),
      TypeError,
    );
  }
  await assert.rejects(
    normalizeSkillPackageReviewContent(content, {
      expectedPackageId: pending.id,
      expectedPackageDigest: pending.package_digest,
      expectedFiles: pending.files.map((file, index) => (
        index === 0 ? { ...file, size_bytes: file.size_bytes + 1 } : file
      )),
    }),
    /字节数/,
  );
  await assert.rejects(
    normalizeSkillPackageReviewContent(content, {
      expectedPackageId: pending.id,
      expectedPackageDigest: pending.package_digest,
      expectedFiles: pending.files.map((file, index) => (
        index === 0 ? { ...file, sha256: "0".repeat(64) } : file
      )),
    }),
    /摘要/,
  );

  const originalFetch = globalThis.fetch;
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return new Response(JSON.stringify(content), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    assert.deepEqual(await getSkillPackageReviewContent(pending), content);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(
    observed.path,
    `/api/skill-packages/${encodeURIComponent(pending.id)}/review-content`,
  );
  assert.equal(observed.init?.method || "GET", "GET");
});


test("包级复核 API 只提交精确 CAS 请求并核对原 Package 修订", async () => {
  const originalFetch = globalThis.fetch;
  const pending = skillPackage();
  const approved = skillPackage("approved");
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return new Response(JSON.stringify(approved), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    assert.deepEqual(await decideSkillPackage(pending, "approve"), approved);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(
    observed.path,
    `/api/skill-packages/${encodeURIComponent(pending.id)}/decision`,
  );
  assert.deepEqual(JSON.parse(observed.init.body), {
    schema_version: "skill_package_decision_request.v1",
    action: "approve",
    expected_package_digest: pending.package_digest,
  });
});


test("方案内复用引用只接受后端固定字段与当前执行单元", () => {
  const reference = {
    schema_version: "skill_reuse_ref.v1",
    package_id: `skill_package_${"2".repeat(24)}`,
    package_version: "0.1.0",
    package_digest: digest("2"),
    candidate_digest: digest("a"),
    skill_digest: digest("1"),
    skill_name: "entry-review-method",
    matched_agent_id: "hello_agent",
    review_state: "approved",
    match_policy_version: "skill_reuse_match.v1",
    match_basis_digest: digest("9"),
  };
  assert.equal(
    normalizeSkillReuseRef(reference, { expectedAgentIds: ["hello_agent"] }),
    reference,
  );
  for (const mutate of [
    (value) => { value.review_state = "pending_review"; },
    (value) => { value.match_policy_version = "llm_claimed"; },
    (value) => { value.model = "user_selected"; },
  ]) {
    const invalid = structuredClone(reference);
    mutate(invalid);
    assert.throws(
      () => normalizeSkillReuseRef(invalid, { expectedAgentIds: ["hello_agent"] }),
      TypeError,
    );
  }
  assert.throws(
    () => normalizeSkillReuseRef(reference, { expectedAgentIds: ["other_agent"] }),
    TypeError,
  );
});


test("Guide 成功态仍只有主文字输入与附件入口，候选审核组件零字段", () => {
  assert.equal((guideSource.match(/<el-input/g) || []).length, 1);
  assert.equal((guideSource.match(/<el-upload/g) || []).length, 1);
  assert.doesNotMatch(guideSource, /<form\b|<select\b|contenteditable=|role="combobox"/);
  assert.doesNotMatch(calloutSource, /<el-input\b|<el-upload\b|<input\b|<textarea\b|<select\b|<form\b|contenteditable=/);
  assert.doesNotMatch(calloutSource, /<details\b|<summary\b/);
  assert.match(calloutSource, /class="candidate-evidence-toggle"/);
  assert.match(calloutSource, /接受这个候选/);
  assert.match(calloutSource, /本次不保留/);
  assert.match(calloutSource, /下载待审包/);
  assert.match(calloutSource, /下载候选记录/);
  assert.match(calloutSource, /隔离包待复核/);
  assert.match(calloutSource, /批准复用/);
  assert.match(calloutSource, /本次不批准/);
  assert.match(calloutSource, /相似新任务将自动复用/);
  assert.match(
    calloutSource,
    /candidate\.state === 'awaiting_human_review' && \(phase === 'ready' \|\| phase === 'deciding'\)/,
  );
  assert.match(calloutSource, /packageReviewPhase !== 'ready'/);
  assert.match(calloutSource, /load-package-content/);
  assert.match(calloutSource, /aria-busy/);
  assert.match(calloutSource, /candidate-evidence-toggle[\s\S]*:disabled="phase === 'deciding'"/);
  assert.match(calloutSource, /function toggleEvidence\(\)[\s\S]*phase === "deciding"[\s\S]*return/);
  assert.match(
    calloutSource,
    /\.asset-candidate-callout\.is-awaiting_human_review \.candidate-mark \{ background: var\(--trust-pending\); \}/,
  );
  assert.match(
    calloutSource,
    /\.asset-candidate-callout\.is-accepted \.candidate-mark \{ background: var\(--trust-signed\); \}/,
  );
  assert.match(
    calloutSource,
    /v-if="phase === 'reconcile_required'"[\s\S]*核对真实状态[\s\S]*v-else-if="candidate"/,
  );
});


test("候选只长在主对话轴，并退役任务完成前的团队模板入口", () => {
  assert.match(guideSource, /<AssetCandidateCallout/);
  assert.match(guideSource, /eligibleAssetCandidateTask\(tasks\)/);
  assert.match(guideSource, /ensureAssetCandidateForTasks\(tasks\)/);
  assert.match(
    guideSource,
    /const assetCandidate = ref\(null\);[\s\S]*verifyAssetCandidateIntegrity\([\s\S]*acceptanceAssetCandidate/,
    "验收成功态也必须先过与真实 API 相同的内容地址核验",
  );
  assert.match(guideSource, /assetCandidatePhase\.value !== "ready"/);
  assert.match(
    guideSource,
    /const decisionContext = \{[\s\S]*?seq:[\s\S]*?taskId:[\s\S]*?conversationId:/,
  );
  assert.equal(
    (guideSource.match(/assetCandidateRequestIsCurrent\(decisionContext,/g) || []).length,
    2,
    "决定成功与异常回写前都必须核对请求 freshness",
  );
  assert.match(
    guideSource,
    /const reconcileContext = \{[\s\S]*?seq:[\s\S]*?taskId:[\s\S]*?conversationId:/,
  );
  assert.match(
    guideSource,
    /assetCandidateReconcileCreateReason\([\s\S]*?if \(createReason !== null\)[\s\S]*?createTaskAssetCandidate\(task\.id\)/,
  );
  assert.ok(
    (guideSource.match(/if \(!reconcileIsCurrent\(\)\) return;/g) || []).length >= 3,
    "GET、POST 成功与 POST 异常回写前都必须核对 freshness",
  );
  assert.doesNotMatch(guideSource, /把这套编排存为团队模板|saveTeamFromPlan|createTeam/);
  assert.match(apiSource, /\/api\/tasks\/\$\{encodeURIComponent\((?:normalizedTaskId|taskId)\)\}\/asset-candidate/);
  assert.match(apiSource, /\/api\/asset-candidates\/\$\{encodeURIComponent\(candidateId\)\}\/decision/);
  assert.match(apiSource, /\/api\/skill-packages\/\$\{encodeURIComponent\(packageId\)\}\/decision/);
  assert.equal(
    (apiSource.match(/verifyAssetCandidateIntegrity\(/g) || []).length,
    4,
    "GET、POST、决定前与决定响应都必须重算内容地址",
  );
});
