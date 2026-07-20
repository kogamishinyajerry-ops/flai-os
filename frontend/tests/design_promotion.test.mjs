import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  createDesignComparison,
  createDesignReleaseRequest,
  decideDesignReleaseRequest,
  getDesignComparison,
  publishDesignRelease,
  rollbackDesignRelease,
  sensitiveCandidateRoleAxisMessage,
  submitDesignSelection,
} from "../src/api/designPromotions.js";

import {
  DesignPromotionValidationError,
  DESIGN_REJECTION_REASON_OPTIONS,
  buildCandidateSelectionPayload,
  buildComparisonCreatePayload,
  buildPublishPayload,
  buildReleaseDecisionPayload,
  buildReleaseRequestPayload,
  buildRollbackPayload,
  blocksGenericTaskReview,
  createDesignPromotionRequestId,
  isOpenDesignProductionCandidateTask,
  validateDesignPublishResult,
  validateDesignPathId,
  validateDesignComparisonEnvelope,
  validateDesignReleaseDecision,
  validateDesignReleaseRequest,
  validateDesignRollbackResult,
  validateDesignSelection,
} from "../src/utils/designPromotionCore.js";

const REQUEST_ID = "req_0123456789abcdef0123456789abcdef";
const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);
const CANDIDATE_ID = "odc-0123456789abcdef0123456789abcdef";
const COMPARISON_ID = `comparison_${"1".repeat(32)}`;
const FRAME_ID = `frame_${"2".repeat(32)}`;
const SELECTION_ID = `selection_${"3".repeat(32)}`;
const TASK_DECISION_ID = `decision_${"4".repeat(32)}`;
const RELEASE_REQUEST_ID = `release_${"5".repeat(32)}`;
const RELEASE_DECISION_ID = `release_decision_${"6".repeat(32)}`;
const PUBLISH_EVENT_ID = `promotion_event_${"7".repeat(32)}`;
const ROLLBACK_EVENT_ID = `promotion_event_${"8".repeat(32)}`;
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const comparisonEnvelope = () => ({
  schema_version: "flai-design-comparison/v1",
  comparison_id: COMPARISON_ID,
  comparison_sha256: SHA_A,
  task_id: "task_1",
  candidate: {
    candidate_id: CANDIDATE_ID,
    asset_slot: "task_review_summary",
    asset_file_id: "file_1",
    asset_sha256: SHA_B,
    media_type: "image/png",
    execution_trust: "untrusted_generated",
  },
  target: {
    target_id: "open_design_task_review_summary_v1",
    relative_path: "frontend/src/assets/open-design/task-review-summary.png",
    preimage: { kind: "absent" },
  },
  phase: "candidate_pending",
  provenance: {
    mock: false,
    project_id: "project_1",
    run_id: "run_1",
    result_package_sha256: "c".repeat(64),
    design_reference_package_sha256: "d".repeat(64),
    file_set_sha256: "e".repeat(64),
    production_readiness: "trial_not_attested",
  },
  frames: [
    {
      frame_id: FRAME_ID,
      slot_id: "default_desktop_light",
      viewport: { width: 1440, height: 900, dpr: 2 },
      state: "default",
      theme: "light",
      locale: "zh-CN",
      current: {
        sha256: "1".repeat(64),
        width: 2880,
        height: 1800,
        url: `/api/design-comparisons/${COMPARISON_ID}/frames/${FRAME_ID}/current.png`,
      },
      candidate: {
        sha256: "2".repeat(64),
        width: 2880,
        height: 1800,
        url: `/api/design-comparisons/${COMPARISON_ID}/frames/${FRAME_ID}/candidate.png`,
        scan: "passed",
      },
    },
  ],
  workflow: {
    selection: null,
    release_request: null,
    release_decision: null,
    latest_publish: null,
  },
  created_by: { username: "reviewer", display_name: "审核人" },
  created_at: "2026-07-20T09:00:00Z",
});

const selectionEnvelope = () => ({
  schema_version: "flai-design-selection/v1",
  selection_id: SELECTION_ID,
  comparison_id: COMPARISON_ID,
  comparison_sha256: SHA_A,
  task_id: "task_1",
  action: "approve",
  candidate_id: CANDIDATE_ID,
  candidate_sha256: SHA_B,
  task_decision_id: TASK_DECISION_ID,
  selected_by: { username: "candidate_reviewer", display_name: "候选审核人" },
  reason_code: null,
  comment: "逐帧核对通过",
  created_at: "2026-07-20T09:05:00Z",
  task_status: "completed",
});

const releaseSummary = () => ({
  candidate: {
    task_id: "task_1",
    candidate_id: CANDIDATE_ID,
    asset_slot: "task_review_summary",
    asset_sha256: SHA_B,
    comparison_sha256: SHA_A,
    candidate_approval: {
      decision_id: TASK_DECISION_ID,
      username: "candidate_reviewer",
      display_name: "候选审核人",
      at: "2026-07-20T09:05:00Z",
    },
  },
  target: {
    target_id: "open_design_task_review_summary_v1",
    relative_path: "frontend/src/assets/open-design/task-review-summary.png",
    preimage: { kind: "absent" },
    postimage_sha256: SHA_B,
  },
});

const releaseRequestEnvelope = () => ({
  schema_version: "flai-design-release-request/v1",
  release_request_id: RELEASE_REQUEST_ID,
  selection_id: SELECTION_ID,
  comparison_id: COMPARISON_ID,
  state: "awaiting_release_approval",
  summary: releaseSummary(),
  summary_sha256: "c".repeat(64),
  requested_by: { username: "requester", display_name: "发布申请人" },
  created_at: "2026-07-20T09:10:00Z",
});

const releaseDecisionEnvelope = () => ({
  schema_version: "flai-design-release-decision/v1",
  release_request_id: RELEASE_REQUEST_ID,
  state: "release_approved",
  decision_id: RELEASE_DECISION_ID,
  action: "approve",
  summary_sha256: "c".repeat(64),
  decided_by: { username: "release_approver", display_name: "发布批准人" },
  reason_code: null,
  comment: "发布摘要核对通过",
  created_at: "2026-07-20T09:15:00Z",
  release_package: {
    schema_version: "flai-design-release-package/v1",
    release_package_sha256: "d".repeat(64),
    summary: releaseSummary(),
    release_approval: {
      decision_id: RELEASE_DECISION_ID,
      username: "release_approver",
      display_name: "发布批准人",
      at: "2026-07-20T09:15:00Z",
    },
  },
});

test("design promotion mutation identifiers and create payload fail closed", () => {
  const generated = createDesignPromotionRequestId(
    Uint8Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]),
  );
  assert.equal(generated, "req_000102030405060708090a0b0c0d0e0f");
  assert.deepEqual(buildComparisonCreatePayload({ requestId: REQUEST_ID, taskId: "task_1" }), {
    request_id: REQUEST_ID,
    task_id: "task_1",
  });

  for (const requestId of [
    "req_0123456789ABCDEF0123456789abcdef",
    "req_0123456789abcdef",
    "0123456789abcdef0123456789abcdef",
    "req_0123456789abcdef0123456789abcdeg",
  ]) {
    assert.throws(
      () => buildComparisonCreatePayload({ requestId, taskId: "task_1" }),
      DesignPromotionValidationError,
    );
  }
  assert.throws(
    () => createDesignPromotionRequestId(new Uint8Array(15)),
    DesignPromotionValidationError,
  );
  assert.equal(validateDesignPathId(COMPARISON_ID, "comparison_id"), COMPARISON_ID);
  assert.equal(validateDesignPathId(RELEASE_REQUEST_ID, "release_request_id"), RELEASE_REQUEST_ID);
  assert.throws(() => validateDesignPathId("comparison_1", "comparison_id"), DesignPromotionValidationError);
  assert.throws(() => validateDesignPathId("release_1", "release_request_id"), DesignPromotionValidationError);
});

test("all design promotion mutation bodies are exact and invalid decisions stop locally", () => {
  assert.deepEqual(
    buildCandidateSelectionPayload({
      requestId: REQUEST_ID,
      action: "approve",
      expectedComparisonSha256: SHA_A,
      candidateId: CANDIDATE_ID,
      comment: "  已逐帧核对  ",
    }),
    {
      request_id: REQUEST_ID,
      action: "approve",
      expected_comparison_sha256: SHA_A,
      candidate_id: CANDIDATE_ID,
      reason_code: null,
      comment: "已逐帧核对",
    },
  );
  assert.deepEqual(
    buildCandidateSelectionPayload({
      requestId: REQUEST_ID,
      action: "reject",
      expectedComparisonSha256: SHA_A,
      candidateId: null,
      reasonCode: "visual_mismatch",
      comment: "当前页不一致",
    }),
    {
      request_id: REQUEST_ID,
      action: "reject",
      expected_comparison_sha256: SHA_A,
      candidate_id: null,
      reason_code: "visual_mismatch",
      comment: "当前页不一致",
    },
  );
  assert.deepEqual(
    buildReleaseRequestPayload({
      requestId: REQUEST_ID,
      selectionId: SELECTION_ID,
      expectedComparisonSha256: SHA_A,
      expectedCandidateSha256: SHA_B,
      expectedTarget: { kind: "absent" },
    }),
    {
      request_id: REQUEST_ID,
      selection_id: SELECTION_ID,
      expected_comparison_sha256: SHA_A,
      expected_candidate_sha256: SHA_B,
      expected_target: { kind: "absent" },
    },
  );
  assert.deepEqual(
    buildReleaseDecisionPayload({
      requestId: REQUEST_ID,
      action: "approve",
      expectedSummarySha256: SHA_A,
      comment: "发布包摘要已核对",
    }),
    {
      request_id: REQUEST_ID,
      action: "approve",
      expected_summary_sha256: SHA_A,
      reason_code: null,
      comment: "发布包摘要已核对",
    },
  );
  assert.deepEqual(
    buildPublishPayload({
      requestId: REQUEST_ID,
      expectedReleasePackageSha256: SHA_A,
      expectedTarget: { kind: "present", sha256: SHA_B },
      confirm: true,
    }),
    {
      request_id: REQUEST_ID,
      expected_release_package_sha256: SHA_A,
      expected_target: { kind: "present", sha256: SHA_B },
      confirm: true,
    },
  );
  assert.deepEqual(
    buildRollbackPayload({
      requestId: REQUEST_ID,
      expectedReleasePackageSha256: SHA_A,
      expectedCurrentSha256: SHA_B,
      confirm: true,
    }),
    {
      request_id: REQUEST_ID,
      expected_release_package_sha256: SHA_A,
      expected_current_sha256: SHA_B,
      confirm: true,
    },
  );

  const invalid = [
    () => buildCandidateSelectionPayload({ requestId: REQUEST_ID, action: "approve", expectedComparisonSha256: SHA_A, candidateId: null }),
    () => buildCandidateSelectionPayload({ requestId: REQUEST_ID, action: "approve", expectedComparisonSha256: SHA_A, candidateId: "cand_0123456789abcdef0123456789abcdef" }),
    () => buildCandidateSelectionPayload({ requestId: REQUEST_ID, action: "reject", expectedComparisonSha256: SHA_A, candidateId: CANDIDATE_ID, reasonCode: "visual_mismatch" }),
    () => buildCandidateSelectionPayload({ requestId: REQUEST_ID, action: "reject", expectedComparisonSha256: SHA_A, candidateId: null, reasonCode: "other", comment: "   " }),
    () => buildReleaseRequestPayload({ requestId: REQUEST_ID, selectionId: SELECTION_ID, expectedComparisonSha256: SHA_A, expectedCandidateSha256: SHA_B, expectedTarget: { kind: "present" } }),
    () => buildReleaseDecisionPayload({ requestId: REQUEST_ID, action: "approve", expectedSummarySha256: SHA_A, reasonCode: "accessibility" }),
    () => buildPublishPayload({ requestId: REQUEST_ID, expectedReleasePackageSha256: SHA_A, expectedTarget: { kind: "absent" }, confirm: 1 }),
    () => buildRollbackPayload({ requestId: REQUEST_ID, expectedReleasePackageSha256: SHA_A, expectedCurrentSha256: SHA_B, confirm: false }),
  ];
  for (const call of invalid) assert.throws(call, DesignPromotionValidationError);
});

test("comparison envelopes and production-task gating reject partial or active content", () => {
  const valid = comparisonEnvelope();
  assert.equal(validateDesignComparisonEnvelope(valid), valid);

  const invalidEnvelopes = [];
  const missingFrameUrl = comparisonEnvelope();
  delete missingFrameUrl.frames[0].candidate.url;
  invalidEnvelopes.push(missingFrameUrl);
  const activeContentUrl = comparisonEnvelope();
  activeContentUrl.frames[0].candidate.url = "data:image/svg+xml,<svg onload=alert(1)>";
  invalidEnvelopes.push(activeContentUrl);
  const externalPng = comparisonEnvelope();
  externalPng.frames[0].current.url = "https://example.invalid/current.png";
  invalidEnvelopes.push(externalPng);
  const unscanned = comparisonEnvelope();
  unscanned.frames[0].candidate.scan = "pending";
  invalidEnvelopes.push(unscanned);
  const mockProvenance = comparisonEnvelope();
  mockProvenance.provenance.mock = true;
  invalidEnvelopes.push(mockProvenance);
  const overstatedProductionReadiness = comparisonEnvelope();
  overstatedProductionReadiness.provenance.production_readiness = "production_ready";
  invalidEnvelopes.push(overstatedProductionReadiness);
  const rawMarkup = comparisonEnvelope();
  rawMarkup.frames[0].candidate.raw_html = "<script>alert(1)</script>";
  invalidEnvelopes.push(rawMarkup);
  const sourceCodeTarget = comparisonEnvelope();
  sourceCodeTarget.target.relative_path = "frontend/src/views/TaskDetail.vue";
  invalidEnvelopes.push(sourceCodeTarget);
  const unknownAssetSlot = comparisonEnvelope();
  unknownAssetSlot.candidate.asset_slot = "task_detail";
  invalidEnvelopes.push(unknownAssetSlot);
  const mismatchedAllowlistedTarget = comparisonEnvelope();
  mismatchedAllowlistedTarget.target.relative_path = "frontend/src/assets/open-design/agent-activity-indicator.png";
  invalidEnvelopes.push(mismatchedAllowlistedTarget);
  const shortComparisonId = comparisonEnvelope();
  shortComparisonId.comparison_id = "comparison_1";
  shortComparisonId.frames[0].current.url = `/api/design-comparisons/comparison_1/frames/${FRAME_ID}/current.png`;
  shortComparisonId.frames[0].candidate.url = `/api/design-comparisons/comparison_1/frames/${FRAME_ID}/candidate.png`;
  invalidEnvelopes.push(shortComparisonId);
  const shortFrameId = comparisonEnvelope();
  shortFrameId.frames[0].frame_id = "frame_1";
  shortFrameId.frames[0].current.url = `/api/design-comparisons/${COMPARISON_ID}/frames/frame_1/current.png`;
  shortFrameId.frames[0].candidate.url = `/api/design-comparisons/${COMPARISON_ID}/frames/frame_1/candidate.png`;
  invalidEnvelopes.push(shortFrameId);

  for (const envelope of invalidEnvelopes) {
    assert.throws(() => validateDesignComparisonEnvelope(envelope), DesignPromotionValidationError);
  }

  const task = {
    id: "task_1",
    status: "waiting_review",
    agent_id: "open_design_daemon_candidate_agent",
    metadata: {
      review_contract: "open-design-candidate/v1",
      generator_kind: "open_design_daemon",
      candidate_manifest_sha256: SHA_A,
    },
  };
  assert.equal(isOpenDesignProductionCandidateTask(task), true);
  assert.equal(isOpenDesignProductionCandidateTask({ ...task, status: "completed" }), true);
  assert.equal(isOpenDesignProductionCandidateTask({ ...task, status: "queued" }), false);
  assert.equal(isOpenDesignProductionCandidateTask({ ...task, agent_id: "lookalike_agent" }), false);
  assert.equal(isOpenDesignProductionCandidateTask({ ...task, metadata: { ...task.metadata, review_contract: "open-design-candidate/v2" } }), false);
  assert.equal(isOpenDesignProductionCandidateTask({ ...task, metadata: { ...task.metadata, candidate_manifest_sha256: "A".repeat(64) } }), false);

  assert.equal(blocksGenericTaskReview(task), true);
  assert.equal(blocksGenericTaskReview({ ...task, metadata: {} }), true);
  assert.equal(blocksGenericTaskReview({ ...task, agent_id: "other_agent" }), true);
  assert.equal(
    blocksGenericTaskReview({ ...task, agent_id: "other_agent", metadata: {}, status: "waiting_review" }),
    false,
  );
});

test("selection, release, publish, and rollback responses require complete named-human evidence", () => {
  assert.equal(validateDesignSelection(selectionEnvelope()).action, "approve");
  assert.equal(validateDesignReleaseRequest(releaseRequestEnvelope()).state, "awaiting_release_approval");
  assert.equal(validateDesignReleaseDecision(releaseDecisionEnvelope()).state, "release_approved");

  const publish = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "published",
    publish_event_id: PUBLISH_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: null,
    after_sha256: SHA_B,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    published_by: { username: "publisher", display_name: "发布执行人" },
    published_at: "2026-07-20T09:20:00Z",
  };
  assert.equal(validateDesignPublishResult(publish).after_sha256, SHA_B);

  const rollback = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "rolled_back",
    rollback_event_id: ROLLBACK_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: SHA_B,
    after_sha256: null,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    rolled_back_by: { username: "rollback_operator", display_name: "回退执行人" },
    rolled_back_at: "2026-07-20T09:25:00Z",
  };
  assert.equal(validateDesignRollbackResult(rollback).state, "rolled_back");

  const invalidSelection = selectionEnvelope();
  invalidSelection.selected_by = { username: "candidate_reviewer" };
  assert.throws(() => validateDesignSelection(invalidSelection), DesignPromotionValidationError);
  const invalidRelease = releaseRequestEnvelope();
  invalidRelease.summary.target.raw_markup = "<svg><script /></svg>";
  assert.throws(() => validateDesignReleaseRequest(invalidRelease), DesignPromotionValidationError);
  const invalidDecision = releaseDecisionEnvelope();
  invalidDecision.decided_by = null;
  assert.throws(() => validateDesignReleaseDecision(invalidDecision), DesignPromotionValidationError);
  assert.throws(
    () => validateDesignSelection({ ...selectionEnvelope(), selection_id: "selection_1" }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignSelection({ ...selectionEnvelope(), task_decision_id: "decision_1" }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignReleaseRequest({ ...releaseRequestEnvelope(), release_request_id: "release_1" }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignReleaseDecision({ ...releaseDecisionEnvelope(), decision_id: "release_decision_1" }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignPublishResult({ ...publish, state: "published", after_sha256: null }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignPublishResult({ ...publish, publish_event_id: "promotion_event_1" }),
    DesignPromotionValidationError,
  );
  assert.throws(
    () => validateDesignRollbackResult({ ...rollback, before_sha256: "not-a-hash" }),
    DesignPromotionValidationError,
  );
});

test("comparison workflow projection restores every confirmed gate without local storage", () => {
  const approved = comparisonEnvelope();
  approved.phase = "publish_ready";
  approved.workflow.selection = selectionEnvelope();
  approved.workflow.release_request = releaseRequestEnvelope();
  approved.workflow.release_decision = releaseDecisionEnvelope();
  assert.equal(
    validateDesignComparisonEnvelope(approved).workflow.release_decision.state,
    "release_approved",
  );

  const inconsistentPhase = structuredClone(approved);
  inconsistentPhase.phase = "candidate_pending";
  assert.throws(
    () => validateDesignComparisonEnvelope(inconsistentPhase),
    DesignPromotionValidationError,
  );
  const missingSelection = structuredClone(approved);
  missingSelection.workflow.selection = null;
  assert.throws(
    () => validateDesignComparisonEnvelope(missingSelection),
    DesignPromotionValidationError,
  );
  const wrongReleaseLink = structuredClone(approved);
  wrongReleaseLink.workflow.release_request.selection_id = "selection_" + "f".repeat(32);
  assert.throws(
    () => validateDesignComparisonEnvelope(wrongReleaseLink),
    DesignPromotionValidationError,
  );
});

test("all nine comparison phases require their exact server-ledger projection", () => {
  const candidateRejected = comparisonEnvelope();
  candidateRejected.phase = "candidate_rejected";
  candidateRejected.workflow.selection = {
    ...selectionEnvelope(),
    action: "reject",
    candidate_id: null,
    candidate_sha256: null,
    reason_code: "visual_mismatch",
    comment: "候选视觉不一致",
    task_status: "failed",
  };

  const candidateApproved = comparisonEnvelope();
  candidateApproved.phase = "candidate_approved";
  candidateApproved.workflow.selection = selectionEnvelope();

  const releasePending = structuredClone(candidateApproved);
  releasePending.phase = "release_pending";
  releasePending.workflow.release_request = releaseRequestEnvelope();

  const releaseRejected = structuredClone(releasePending);
  releaseRejected.phase = "release_rejected";
  releaseRejected.workflow.release_decision = {
    ...releaseDecisionEnvelope(),
    state: "release_rejected",
    action: "reject",
    reason_code: "trust_semantics",
    comment: "发布信任语义不符",
    release_package: null,
  };

  const publishReady = structuredClone(releasePending);
  publishReady.phase = "publish_ready";
  publishReady.workflow.release_decision = releaseDecisionEnvelope();

  const manualIntervention = structuredClone(publishReady);
  manualIntervention.phase = "manual_intervention";

  const published = structuredClone(publishReady);
  published.phase = "published";
  published.workflow.latest_publish = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "published",
    publish_event_id: PUBLISH_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: null,
    after_sha256: SHA_B,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    published_by: { username: "publisher", display_name: "发布执行人" },
    published_at: "2026-07-20T09:20:00Z",
  };

  const rolledBack = structuredClone(publishReady);
  rolledBack.phase = "rolled_back";
  rolledBack.workflow.latest_publish = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "rolled_back",
    rollback_event_id: ROLLBACK_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: SHA_B,
    after_sha256: null,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    rolled_back_by: { username: "rollback_operator", display_name: "回退执行人" },
    rolled_back_at: "2026-07-20T09:25:00Z",
  };

  const exactNine = [
    comparisonEnvelope(),
    candidateRejected,
    candidateApproved,
    releasePending,
    releaseRejected,
    publishReady,
    published,
    rolledBack,
    manualIntervention,
  ];
  assert.deepEqual(
    exactNine.map((envelope) => validateDesignComparisonEnvelope(envelope).phase),
    [
      "candidate_pending",
      "candidate_rejected",
      "candidate_approved",
      "release_pending",
      "release_rejected",
      "publish_ready",
      "published",
      "rolled_back",
      "manual_intervention",
    ],
  );

  const manualWithCommit = structuredClone(manualIntervention);
  manualWithCommit.workflow.latest_publish = published.workflow.latest_publish;
  assert.throws(
    () => validateDesignComparisonEnvelope(manualWithCommit),
    DesignPromotionValidationError,
  );
});

test("comparison rendering dimensions and matrix size stay inside closed backend bounds", () => {
  const invalid = [];
  const oversizedViewport = comparisonEnvelope();
  oversizedViewport.frames[0].viewport.width = 4097;
  invalid.push(oversizedViewport);
  const oversizedImage = comparisonEnvelope();
  oversizedImage.frames[0].candidate.height = 4097;
  invalid.push(oversizedImage);
  const oversizedDpr = comparisonEnvelope();
  oversizedDpr.frames[0].viewport.dpr = 5;
  invalid.push(oversizedDpr);
  const unknownTheme = comparisonEnvelope();
  unknownTheme.frames[0].theme = "system";
  invalid.push(unknownTheme);
  const tooManyFrames = comparisonEnvelope();
  tooManyFrames.frames = Array.from({ length: 17 }, (_, index) => {
    const frame = structuredClone(tooManyFrames.frames[0]);
    frame.frame_id = `frame_${index}`;
    frame.state = `state_${index}`;
    frame.frame_id = `frame_${index.toString(16).padStart(32, "0")}`;
    frame.current.url = `/api/design-comparisons/${COMPARISON_ID}/frames/${frame.frame_id}/current.png`;
    frame.candidate.url = `/api/design-comparisons/${COMPARISON_ID}/frames/${frame.frame_id}/candidate.png`;
    return frame;
  });
  invalid.push(tooManyFrames);
  const oversizedTaskId = comparisonEnvelope();
  oversizedTaskId.task_id = "t".repeat(161);
  invalid.push(oversizedTaskId);

  for (const envelope of invalid) {
    assert.throws(
      () => validateDesignComparisonEnvelope(envelope),
      DesignPromotionValidationError,
    );
  }
});

test("design promotion API sends each frozen endpoint an exact body", async () => {
  const publishResult = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "published",
    publish_event_id: PUBLISH_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: null,
    after_sha256: SHA_B,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    published_by: { username: "publisher", display_name: "发布执行人" },
    published_at: "2026-07-20T09:20:00Z",
  };
  const rollbackResult = {
    schema_version: "flai-design-publish-result/v1",
    release_request_id: RELEASE_REQUEST_ID,
    state: "rolled_back",
    rollback_event_id: ROLLBACK_EVENT_ID,
    target_id: "open_design_task_review_summary_v1",
    before_sha256: SHA_B,
    after_sha256: null,
    backup_sha256: null,
    release_package_sha256: "d".repeat(64),
    rolled_back_by: { username: "rollback_operator", display_name: "回退执行人" },
    rolled_back_at: "2026-07-20T09:25:00Z",
  };
  const calls = [];
  const responses = [
    comparisonEnvelope(),
    comparisonEnvelope(),
    selectionEnvelope(),
    releaseRequestEnvelope(),
    releaseDecisionEnvelope(),
    publishResult,
    rollbackResult,
  ];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (path, init) => {
    calls.push({
      path,
      method: init.method,
      cache: init.cache,
      body: init.body === undefined ? undefined : JSON.parse(init.body),
    });
    return { ok: true, json: async () => responses.shift() };
  };
  try {
    await createDesignComparison({ requestId: REQUEST_ID, taskId: "task_1" });
    await getDesignComparison(COMPARISON_ID);
    await submitDesignSelection(COMPARISON_ID, {
      requestId: REQUEST_ID,
      action: "approve",
      expectedComparisonSha256: SHA_A,
      candidateId: CANDIDATE_ID,
      comment: null,
    });
    await createDesignReleaseRequest({
      requestId: REQUEST_ID,
      selectionId: SELECTION_ID,
      expectedComparisonSha256: SHA_A,
      expectedCandidateSha256: SHA_B,
      expectedTarget: { kind: "absent" },
    });
    await decideDesignReleaseRequest(RELEASE_REQUEST_ID, {
      requestId: REQUEST_ID,
      action: "approve",
      expectedSummarySha256: "c".repeat(64),
      comment: null,
    });
    await publishDesignRelease(RELEASE_REQUEST_ID, {
      requestId: REQUEST_ID,
      expectedReleasePackageSha256: "d".repeat(64),
      expectedTarget: { kind: "absent" },
      confirm: true,
    });
    await rollbackDesignRelease(RELEASE_REQUEST_ID, {
      requestId: REQUEST_ID,
      expectedReleasePackageSha256: "d".repeat(64),
      expectedCurrentSha256: SHA_B,
      confirm: true,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(calls, [
    {
      path: "/api/design-comparisons",
      method: "POST",
      cache: undefined,
      body: { request_id: REQUEST_ID, task_id: "task_1" },
    },
    {
      path: `/api/design-comparisons/${COMPARISON_ID}`,
      method: "GET",
      cache: "no-store",
      body: undefined,
    },
    {
      path: `/api/design-comparisons/${COMPARISON_ID}/selection`,
      method: "POST",
      cache: undefined,
      body: {
        request_id: REQUEST_ID,
        action: "approve",
        expected_comparison_sha256: SHA_A,
        candidate_id: CANDIDATE_ID,
        reason_code: null,
        comment: null,
      },
    },
    {
      path: "/api/design-release-requests",
      method: "POST",
      cache: undefined,
      body: {
        request_id: REQUEST_ID,
        selection_id: SELECTION_ID,
        expected_comparison_sha256: SHA_A,
        expected_candidate_sha256: SHA_B,
        expected_target: { kind: "absent" },
      },
    },
    {
      path: `/api/design-release-requests/${RELEASE_REQUEST_ID}/decision`,
      method: "POST",
      cache: undefined,
      body: {
        request_id: REQUEST_ID,
        action: "approve",
        expected_summary_sha256: "c".repeat(64),
        reason_code: null,
        comment: null,
      },
    },
    {
      path: `/api/design-release-requests/${RELEASE_REQUEST_ID}/publish`,
      method: "POST",
      cache: undefined,
      body: {
        request_id: REQUEST_ID,
        expected_release_package_sha256: "d".repeat(64),
        expected_target: { kind: "absent" },
        confirm: true,
      },
    },
    {
      path: `/api/design-release-requests/${RELEASE_REQUEST_ID}/rollback`,
      method: "POST",
      cache: undefined,
      body: {
        request_id: REQUEST_ID,
        expected_release_package_sha256: "d".repeat(64),
        expected_current_sha256: SHA_B,
        confirm: true,
      },
    },
  ]);
});

test("comparison panel is PNG-only and names the three human gates separately", () => {
  const panel = read("../src/components/DesignComparisonPanel.vue");

  assert.match(panel, /LOOPBACK TRIAL · 未证明生产就绪/);
  assert.doesNotMatch(panel, /REAL · 来源合同已完整核验|--trust-real/);
  assert.match(panel, /候选审批（不是发布批准）/);
  assert.match(panel, /候选资产 · 尚未发布/);
  assert.match(panel, /发布批准（不会自动发布）/);
  assert.match(panel, /显式发布确认/);
  assert.match(panel, /回退已发布资产/);
  assert.match(panel, /:src="frame\.current\.url"/);
  assert.match(panel, /:src="frame\.candidate\.url"/);
  assert.match(panel, /frame\.current\.sha256/);
  assert.match(panel, /frame\.candidate\.sha256/);
  assert.match(panel, /frame\.slot_id/);
  assert.match(panel, /submitDesignSelection/);
  assert.match(panel, /createDesignReleaseRequest/);
  assert.match(panel, /decideDesignReleaseRequest/);
  assert.match(panel, /publishDesignRelease/);
  assert.match(panel, /rollbackDesignRelease/);
  assert.match(panel, /comparison\.workflow/);
  assert.match(panel, /需要人工介入核对发布事务/);
  assert.match(panel, /confirm:\s*true/);
  assert.match(panel, /err\.status === 409/);
  assert.match(panel, /reloadComparison/);
  assert.match(panel, /@click="retryComparisonLoad"/);
  assert.match(panel, /function clearComparisonSnapshot/);
  assert.match(
    panel,
    /catch \(reloadErr\)[\s\S]{0,420}clearComparisonSnapshot\(\)/,
  );

  assert.doesNotMatch(
    panel,
    /v-html|srcdoc|innerHTML|DOMParser|<iframe|<object|<embed|raw_html|raw_markup/i,
  );
  assert.doesNotMatch(panel, /reviewTask/);
});

test("TaskDetail routes production candidate review only through the comparison panel", () => {
  const detail = read("../src/views/TaskDetail.vue");
  assert.match(detail, /import DesignComparisonPanel from "\.\.\/components\/DesignComparisonPanel\.vue"/);
  assert.match(detail, /isOpenDesignProductionCandidateTask/);
  assert.match(detail, /<DesignComparisonPanel[\s\S]{0,160}v-if="isOpenDesignCandidateTask"/);
  assert.match(detail, /isWaitingReview && !blocksGenericReview/);
  assert.match(detail, /blocksGenericReview/);
  assert.match(detail, /候选审查合同不完整，通用任务签发已停用/);
  assert.match(
    detail,
    /if \(reviewing\.value \|\| reviewSettled\.value \|\| blocksGenericReview\.value\) return false/,
  );
  assert.match(
    detail,
    /if \(\s*blocksGenericReview\.value \|\|\s*!isReviewContextCurrent/,
  );
});

test("design rejection labels stay frozen and explicit", () => {
  assert.deepEqual(DESIGN_REJECTION_REASON_OPTIONS, [
    { value: "visual_mismatch", label: "视觉不一致" },
    { value: "trust_semantics", label: "信任语义不符" },
    { value: "accessibility", label: "可访问性问题" },
    { value: "incomplete_matrix", label: "比较矩阵不完整" },
    { value: "other", label: "其他" },
  ]);
  assert.equal(Object.isFrozen(DESIGN_REJECTION_REASON_OPTIONS), true);
});

test("sensitive candidate isolation error is recognized only from the exact 403 detail contract", () => {
  const exact = {
    status: 403,
    detail: JSON.stringify({
      detail: {
        code: "sensitive_candidate_requires_role_axis",
        message: "role mapping is not configured",
      },
    }),
  };
  assert.equal(sensitiveCandidateRoleAxisMessage(exact), "role mapping is not configured");

  const invalidDetails = [
    { ...exact, status: 409 },
    { ...exact, detail: "sensitive_candidate_requires_role_axis" },
    { ...exact, detail: JSON.stringify({ detail: { code: "sensitive_candidate_requires_role_axis", message: "" } }) },
    { ...exact, detail: JSON.stringify({ detail: { code: "sensitive_candidate_requires_role_axis", message: "blocked", extra: true } }) },
    { ...exact, detail: JSON.stringify({ detail: { code: "other_forbidden", message: "blocked" } }) },
  ];
  for (const err of invalidDetails) assert.equal(sensitiveCandidateRoleAxisMessage(err), null);

  const panel = read("../src/components/DesignComparisonPanel.vue");
  assert.match(panel, /候选已生成，但需角色轴\/受证明隔离后才能比较/);
  assert.match(panel, /sensitiveCandidateRoleAxisMessage/);
  assert.match(panel, /v-if="policyStopMessage"/);
  assert.match(panel, /class="panel-policy-stop"/);
  assert.match(panel, /策略停点/);
  assert.match(panel, /if \(isolationMessage\) \{[\s\S]{0,420}policyStopMessage\.value/);
});
