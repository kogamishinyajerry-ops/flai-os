// frontend/tests/core_visuals.test.mjs — 四组核心模块的 fail-closed 视觉派生核。
import test from "node:test";
import assert from "node:assert/strict";

import { buildPortalCategoryOverview } from "../src/utils/portalVisual.js";
import {
  buildTaskCreateJourney,
  captureTaskSubmission,
} from "../src/utils/taskCreateVisual.js";
import {
  buildGovernanceJourney,
  buildMaturityLadder,
  promotionIdentity,
  summarizeEvalRun,
} from "../src/utils/governanceJourney.js";
import {
  buildEvidenceTrace,
  buildKnowledgeTrace,
  summarizeEvidenceFindings,
} from "../src/utils/evidenceTrace.js";

const byId = (steps, id) => steps.find((step) => step.id === id);
const forbiddenTrustTone = (steps) =>
  steps.some((step) => ["success", "green", "signed", "real"].includes(step.tone));

test("Agent 门户：列表畸形时不编造四类均为零，未知分类单独待核", () => {
  assert.deepEqual(buildPortalCategoryOverview(null), {
    available: false,
    items: [],
    unknownCount: null,
  });

  const overview = buildPortalCategoryOverview([
    { category: "tool_automation" },
    { category: "tool_automation" },
    { category: "future_category" },
    {},
  ]);
  assert.equal(overview.available, true);
  assert.equal(overview.items.find((item) => item.id === "tool_automation").count, 2);
  assert.equal(overview.unknownCount, 2);
  assert.equal(overview.items.reduce((sum, item) => sum + item.count, 0) + overview.unknownCount, 4);
});

test("任务创建：缺 Agent、未知策略和预填草案保持 amber，创建页永不显示签发或绿", () => {
  const steps = buildTaskCreateJourney({
    agentId: "",
    selectedAgent: null,
    prefillOrigin: "guide",
    uploadItems: [],
  });

  assert.equal(byId(steps, "agent").tone, "pending");
  assert.equal(byId(steps, "capability").tone, "pending");
  assert.equal(byId(steps, "input").tone, "pending");
  assert.match(byId(steps, "input").detail, /预填.*待核/);
  assert.equal(byId(steps, "policy").tone, "pending");
  assert.equal(byId(steps, "submit").tone, "pending");
  assert.equal(forbiddenTrustTone(steps), false);
});

test("任务创建：真实输入或上传错误标红；上传中只显示工作态", () => {
  const base = {
    agentId: "agent-1",
    selectedAgent: {
      id: "agent-1",
      name: "试验 Agent",
      category: "structured_gen",
      maturity: "L0",
      clearance: null,
      evidence_policy_required: true,
      limitations: ["不替代工程签字"],
    },
    schemaRenderable: true,
    jsonMode: false,
    prefillOrigin: "",
  };
  const invalid = buildTaskCreateJourney({
    ...base,
    inputsErrors: ["顶事件必填"],
    uploadItems: [{ status: "error" }],
  });
  assert.equal(byId(invalid, "input").tone, "fail");
  assert.match(byId(invalid, "policy").detail, /内部.*保守/);
  assert.equal(forbiddenTrustTone(invalid), false);

  const uploading = buildTaskCreateJourney({
    ...base,
    uploadingFiles: true,
    submitting: true,
    uploadItems: [{ status: "uploading" }],
  });
  assert.equal(byId(uploading, "input").tone, "work");
  assert.equal(byId(uploading, "submit").tone, "work");
});

test("任务创建：错配的 Agent 详情不得冒充当前选择或泄漏旧策略", () => {
  const steps = buildTaskCreateJourney({
    agentId: "agent-b",
    selectedAgent: {
      id: "agent-a",
      name: "旧 Agent",
      category: "structured_gen",
      maturity: "L1",
      clearance: "public",
      evidence_policy_required: false,
      limitations: [],
    },
  });

  assert.equal(byId(steps, "agent").tone, "pending");
  assert.match(byId(steps, "agent").detail, /正在核对/);
  assert.doesNotMatch(byId(steps, "agent").detail, /旧 Agent/);
  assert.equal(byId(steps, "capability").tone, "pending");
  assert.equal(byId(steps, "policy").tone, "pending");
  assert.doesNotMatch(byId(steps, "policy").detail, /公开/);
});

test("任务创建：提交快照在 await 前冻结 Agent、输入、附件、会话收口与返回方向", () => {
  const form = { agentId: "agent-a", name: " 原始任务 " };
  const inputs = { nested: { value: "old" } };
  const first = { uid: "one", status: "pending" };
  const uploadItems = [first];
  const draft = captureTaskSubmission({
    form,
    inputs,
    uploadItems,
    conversationId: "conv-1",
    retryOf: "task-old",
    concludeAfter: true,
    returnToChat: false,
  });

  form.agentId = "agent-b";
  form.name = "被切换";
  inputs.nested.value = "new";
  uploadItems.push({ uid: "two", status: "pending" });

  assert.equal(draft.agentId, "agent-a");
  assert.equal(draft.name, "原始任务");
  assert.deepEqual(draft.inputs, { nested: { value: "old" } });
  assert.deepEqual(draft.uploadItems, [first]);
  assert.equal(draft.conversationId, "conv-1");
  assert.equal(draft.retryOf, "task-old");
  assert.equal(draft.concludeAfter, true);
  assert.equal(draft.returnToChat, false);
});

test("治理评测：非法成熟度不得回退 L0", () => {
  const missing = buildMaturityLadder(undefined);
  assert.equal(missing.known, false);
  assert.equal(missing.items.some((item) => item.current), false);
  assert.equal(missing.items.some((item) => item.reached), false);

  const l1 = buildMaturityLadder("L1");
  assert.equal(l1.known, true);
  assert.equal(l1.items.find((item) => item.level === "L1").current, true);
});

test("治理评测：queued/running/畸形 completed 永不假绿，error 只在真实错误时标红", () => {
  assert.equal(summarizeEvalRun({ status: "queued" }).tone, "pending");
  assert.equal(summarizeEvalRun({ status: "running" }).tone, "work");
  assert.equal(summarizeEvalRun({
    status: "completed",
    total: "3",
    passed: 3,
    failed: 0,
    skipped: 0,
    case_results: [],
  }).tone, "pending");
  assert.equal(summarizeEvalRun({
    status: "completed",
    total: 0,
    passed: 0,
    failed: 0,
    skipped: 0,
    case_results: [],
  }).tone, "neutral");
  assert.match(summarizeEvalRun({
    status: "completed",
    total: 0,
    passed: 0,
    failed: 0,
    skipped: 0,
    case_results: [],
  }).detail, /无有效用例/);
  assert.equal(summarizeEvalRun({
    status: "completed",
    total: 0,
    passed: 0,
    failed: 0,
    skipped: 0,
    case_results: [{ verdict: "failed" }],
  }).tone, "pending");
  assert.equal(summarizeEvalRun({ status: "error" }).tone, "fail");
});

test("治理评测：只有严格全通过评测可标 REAL，晋升身份只有认证会话绑定可标 teal", () => {
  const run = {
    status: "completed",
    total: 2,
    passed: 2,
    failed: 0,
    skipped: 0,
    case_results: [
      { verdict: "passed" },
      { verdict: "passed" },
    ],
  };
  assert.equal(summarizeEvalRun(run).tone, "real");

  assert.equal(promotionIdentity({
    confirmed_by: "工程师 A",
    signer_source: "authenticated_session",
    signer_session_bound: true,
  }).tone, "signed");
  assert.equal(promotionIdentity({
    confirmed_by: "工程师 A",
    signer_source: "authenticated_session",
    signer_session_bound: 1,
  }).tone, "pending");
  assert.equal(promotionIdentity({
    confirmed_by: "运维入口",
    signer_source: "server_cli",
    signer_session_bound: false,
  }).tone, "neutral");
  assert.equal(promotionIdentity({
    confirmed_by: "历史记录",
    signer_source: "legacy_unverified",
  }).tone, "pending");
});

test("治理评测：复选框仅表示待提交，truthy 非 true 的准入检查不得通过", () => {
  const steps = buildGovernanceJourney({
    maturity: "L0",
    curatedCasesCount: 3,
    latestRun: null,
    promotionConfirmed: true,
    promotions: [{
      confirmed_by: "历史记录",
      signer_source: "legacy_unverified",
      checks: {
        transition_supported: { ok: "true" },
        manual_confirmation: { ok: true },
      },
    }],
  });
  assert.equal(byId(steps, "confirmation").tone, "pending");
  assert.match(byId(steps, "confirmation").detail, /提交成功后/);
  assert.equal(byId(steps, "gate").tone, "pending");
  assert.equal(byId(steps, "promotion").tone, "pending");
});

test("治理评测：旧晋升不得与新的评测结果拼成同一闭环，新增失败门不得被忽略", () => {
  const latestRun = {
    id: "run-new",
    status: "completed",
    total: 1,
    passed: 1,
    failed: 0,
    skipped: 0,
    case_results: [{ verdict: "passed" }],
  };
  const checks = Object.fromEntries([
    "transition_supported",
    "min_eval_coverage",
    "eval_evidence",
    "changelog_nonempty",
    "feedback_channel",
    "manual_confirmation",
    "package_snapshot",
  ].map((name) => [name, { ok: true }]));
  const stalePromotion = {
    eval_run_id: "run-old",
    confirmed_by: "工程师 A",
    signer_source: "authenticated_session",
    signer_session_bound: true,
    checks,
  };
  const staleSteps = buildGovernanceJourney({
    maturity: "L1",
    curatedCasesCount: 3,
    latestRun,
    promotions: [stalePromotion],
  });
  assert.equal(byId(staleSteps, "result").tone, "real");
  assert.equal(byId(staleSteps, "confirmation").tone, "pending");
  assert.equal(byId(staleSteps, "gate").tone, "pending");
  assert.equal(byId(staleSteps, "promotion").tone, "pending");

  const matchedSteps = buildGovernanceJourney({
    maturity: "L1",
    curatedCasesCount: 3,
    latestRun,
    promotions: [{
      ...stalePromotion,
      eval_run_id: "run-new",
      checks: { ...checks, future_integrity_gate: { ok: false } },
    }],
  });
  assert.equal(byId(matchedSteps, "confirmation").tone, "signed");
  assert.equal(byId(matchedSteps, "gate").tone, "fail");
  assert.equal(byId(matchedSteps, "promotion").tone, "signed");
});

test("依据链：resolved=true 仍是中性；畸形、未回源、缺依据均 fail-closed", () => {
  const resolved = buildEvidenceTrace({
    findings: [{
      claim: "主张",
      evidence: [{ kind: "knowledge_doc", source_ref: "DOC-1", resolved: true }],
    }],
  });
  assert.equal(byId(resolved, "resolution").tone, "neutral");
  assert.equal(forbiddenTrustTone(resolved), false);

  const malformed = buildEvidenceTrace({ findings: { items: [] } });
  assert.equal(byId(malformed, "source").tone, "pending");
  assert.match(byId(malformed, "source").detail, /待核/);

  for (const row of [null, { resolved: true }, {
    kind: "knowledge_doc",
    source_ref: "DOC-1",
    resolved: "true",
  }]) {
    const invalidRow = buildEvidenceTrace({
      findings: [{ claim: "主张", evidence: [row] }],
    });
    assert.equal(byId(invalidRow, "source").tone, "pending");
    assert.match(byId(invalidRow, "source").detail, /结构待核/);
  }
  const emptyFinding = buildEvidenceTrace({
    findings: [{ claim: "无依据主张", evidence: [] }],
  });
  assert.equal(byId(emptyFinding, "source").tone, "pending");
  assert.equal(summarizeEvidenceFindings([{
    claim: "无依据主张",
    evidence: [],
  }]).invalid, true);

  const missing = buildEvidenceTrace({ findings: [], requiredMissing: true });
  assert.equal(byId(missing, "source").tone, "pending");
  assert.match(byId(missing, "source").detail, /需要依据/);
});

test("依据链：withheld 不泄露数量；知识指纹一致、漂移、缺失严格分开", () => {
  const withheld = buildEvidenceTrace({
    findings: [{ evidence: [{ source_ref: "SECRET", quote: "不可泄露" }] }],
    withheld: true,
  });
  assert.match(byId(withheld, "source").detail, /按密级隐藏/);
  assert.doesNotMatch(byId(withheld, "source").detail, /\d/);

  assert.equal(byId(buildKnowledgeTrace([{
    searchFingerprint: "abc",
    currentFingerprint: "abc",
  }]), "compare").tone, "neutral");
  assert.match(byId(buildKnowledgeTrace([{
    searchFingerprint: "abc",
    currentFingerprint: "def",
  }]), "compare").detail, /变动/);
  assert.equal(byId(buildKnowledgeTrace([{
    searchFingerprint: "abc",
  }]), "compare").tone, "pending");
  assert.match(byId(buildKnowledgeTrace([{
    searchFingerprint: "abc",
  }]), "compare").detail, /不完整/);
});

test("依据摘要：畸形 finding 或依据行不可计入已核验数字", () => {
  for (const findings of [
    [null],
    [{ evidence: [null] }],
    [{ evidence: [{ resolved: true }] }],
  ]) {
    assert.deepEqual(summarizeEvidenceFindings(findings), {
      invalid: true,
      total: null,
      verified: null,
      unverified: null,
      level: "",
    });
  }
  assert.deepEqual(summarizeEvidenceFindings([{
    evidence: [{
      kind: "knowledge_doc",
      source_ref: "DOC-1",
      resolved: true,
    }],
    confidence: { level: "high" },
  }]), {
    invalid: false,
    total: 1,
    verified: 1,
    unverified: 0,
    level: "高",
  });
});
