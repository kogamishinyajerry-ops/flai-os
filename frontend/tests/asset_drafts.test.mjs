import test from "node:test";
import assert from "node:assert/strict";

import {
  ASSET_DRAFT_FOCUS_QUESTIONS,
  AssetDraftContractError,
  assetDraftFocusState,
  assetDraftQuestionForIssue,
  assetDraftEntryPolicy,
  buildAssetDraftPreviewRequest,
  normalizeAssetDraftPreview,
  seedAssetDraftGeneralization,
  serializeAssetDraftDownload,
} from "../src/utils/assetDrafts.js";
import { previewConversationAssetDraft } from "../src/api/assetDrafts.js";

test("Asset Builder 把九项信息组织成单焦点线性问题流", () => {
  assert.deepEqual(
    ASSET_DRAFT_FOCUS_QUESTIONS.map(({ id, field, step }) => ({ id, field, step })),
    [
      { id: "work-title", field: "title", step: 1 },
      { id: "work-trigger", field: "trigger", step: 1 },
      { id: "work-outcome", field: "desired_outcome", step: 1 },
      { id: "method-inputs", field: "inputs", step: 2 },
      { id: "method-outputs", field: "outputs", step: 2 },
      { id: "method-steps", field: "steps", step: 2 },
      { id: "method-evidence", field: "evidence_requirements", step: 2 },
      { id: "method-human-boundaries", field: "human_decision_points", step: 2 },
      { id: "method-limitations", field: "limitations", step: 2 },
    ],
  );

  const boundary = assetDraftFocusState("work-outcome", {
    title: "稳态算例入口边界复核",
    trigger: "   ",
    desired_outcome: "形成复核清单",
    inputs: ["算例清单"],
  });
  assert.equal(boundary.position, 3);
  assert.equal(boundary.total, 9);
  assert.equal(boundary.previousId, "work-trigger");
  assert.equal(boundary.nextId, "method-inputs");
  assert.equal(boundary.step, 1);
  assert.deepEqual(boundary.answeredIds, [
    "work-title",
    "work-outcome",
    "method-inputs",
  ]);
  assert.equal(boundary.answeredCount, 3);

  assert.throws(
    () => assetDraftFocusState("unknown-question", {}),
    /未知资产草稿问题/,
  );
});

test("校验阻断会返回唯一焦点问题，未知路径不猜测", () => {
  for (const [path, questionId] of [
    ["/task_pattern/title", "work-title"],
    ["/task_pattern/trigger", "work-trigger"],
    ["/task_pattern/desired_outcome", "work-outcome"],
    ["/task_pattern/inputs", "method-inputs"],
    ["/task_pattern/outputs", "method-outputs"],
    ["/skill/instructions", "method-steps"],
    ["/skill/verification", "method-evidence"],
    ["/skill/human_boundaries", "method-human-boundaries"],
    ["/skill/when_not_to_use", "method-limitations"],
  ]) {
    assert.equal(assetDraftQuestionForIssue(path), questionId);
  }
  assert.equal(assetDraftQuestionForIssue("/unknown/path"), null);
  assert.equal(assetDraftQuestionForIssue(null), null);
});

const READY_PREVIEW = {
  schema_version: "asset_draft_bundle.v1",
  builder_version: "asset_draft_builder.v1",
  status: "draft",
  work_case: {
    source_kind: "conversation",
    source_id: "conv-asset-1",
    source_state: "platform_resolved",
    conversation_status: "active",
    message_count: 2,
    user_message_count: 1,
    attachment_reference_count: 1,
    source_revision: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  },
  task_pattern: {
    schema_version: "task_pattern_draft.v1",
    status: "draft",
    derived_from_work_case_revision: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
    suggested_id: "task_pattern_candidate_222222222222",
    content_digest: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
    title: "稳态计算输入边界核对",
    trigger: "新算例进入求解前",
    desired_outcome: "输出可审阅的缺口清单",
    inputs: ["边界条件文件", "求解设置"],
    outputs: ["缺口清单", "复核记录"],
    steps: ["读取输入", "按检查表核对", "标记未知项"],
    evidence_requirements: ["原始输入文件", "检查项定位"],
    human_decision_points: ["工程师确认边界适用性"],
    limitations: ["不执行求解", "不代替签发"],
  },
  skill: {
    schema_version: "skill_draft.v1",
    status: "draft",
    operationalizes_task_pattern_digest: "sha256:2222222222222222222222222222222222222222222222222222222222222222",
    suggested_id: "skill_candidate_333333333333",
    content_digest: "sha256:3333333333333333333333333333333333333333333333333333333333333333",
    name: "稳态计算输入边界核对",
    description: "输出可审阅的缺口清单；适用于：新算例进入求解前",
    when_to_use: "新算例进入求解前",
    when_not_to_use: ["不执行求解", "不代替签发"],
    inputs: ["边界条件文件", "求解设置"],
    outputs: ["缺口清单", "复核记录"],
    instructions: ["读取输入", "按检查表核对", "标记未知项"],
    verification: ["原始输入文件", "检查项定位"],
    human_boundaries: ["工程师确认边界适用性"],
  },
  validation: {
    schema_version: "asset_draft_validation.v1",
    policy_version: "core.v1",
    state: "ready_for_human_review",
    blocking_count: 0,
    warning_count: 0,
    issues: [],
  },
  review: {
    required: true,
    ready: true,
    state: "awaiting_human_review",
    decision_state: "not_recorded",
    requirements: ["核对来源和适用边界"],
  },
  generation: { kind: "deterministic_projection", llm_used: false },
  effects: {
    writes_database: false,
    executes_work: false,
    registers_asset: false,
    promotes_asset: false,
  },
  draft_digest: "sha256:4444444444444444444444444444444444444444444444444444444444444444",
};

test("前端预览成功路径只 POST v1 请求并校验当前会话来源", async (t) => {
  const nativeFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = nativeFetch;
  });
  let observed = null;
  globalThis.fetch = async (path, init) => {
    observed = { path, init };
    return { ok: true, status: 200, json: async () => READY_PREVIEW };
  };

  assert.equal(
    await previewConversationAssetDraft(" conv-asset-1 ", {
      title: "稳态计算输入边界核对",
      trigger: "新算例进入求解前",
      desired_outcome: "输出可审阅的缺口清单",
      inputs: "边界条件文件\n求解设置",
      outputs: "缺口清单\n复核记录",
      steps: "读取输入\n按检查表核对\n标记未知项",
      evidence_requirements: "原始输入文件\n检查项定位",
      human_decision_points: "工程师确认边界适用性",
      limitations: "不执行求解\n不代替签发",
    }),
    READY_PREVIEW,
  );
  assert.equal(
    observed.path,
    "/api/conversations/conv-asset-1/asset-draft-preview",
  );
  assert.equal(observed.init.method, "POST");
  assert.equal(
    JSON.parse(observed.init.body).schema_version,
    "asset_draft_preview_request.v1",
  );
});

test("前端预览失败保留后端 detail，供第九问原位恢复", async (t) => {
  const nativeFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = nativeFetch;
  });
  globalThis.fetch = async () => ({
    ok: false,
    status: 422,
    json: async () => ({ detail: "至少声明一项核验依据" }),
  });

  await assert.rejects(
    () => previewConversationAssetDraft("conv-asset-1", {}),
    (error) => error.status === 422 && error.detail === "至少声明一项核验依据",
  );
});

test("Asset Builder 入口只对已保存且稳定的会话开放", () => {
  assert.deepEqual(
    assetDraftEntryPolicy({
      conversationId: "conv-asset-1",
      hasSavedUserMessage: true,
      sending: false,
      restoring: false,
      reconciliationRequired: false,
    }),
    { canOpen: true, reason: "" },
  );

  assert.deepEqual(
    assetDraftEntryPolicy({ conversationId: "" }),
    { canOpen: false, reason: "先完成并保存一轮对话，再沉淀为资产。" },
  );
  assert.deepEqual(
    assetDraftEntryPolicy({
      conversationId: "conv-asset-1",
      hasSavedUserMessage: false,
    }),
    { canOpen: false, reason: "当前会话还没有已保存的工程师工作。" },
  );
  assert.match(
    assetDraftEntryPolicy({
      conversationId: "conv-asset-1",
      hasSavedUserMessage: true,
      sending: true,
    }).reason,
    /生成结束/,
  );
  assert.match(
    assetDraftEntryPolicy({
      conversationId: "conv-asset-1",
      hasSavedUserMessage: true,
      restoring: true,
    }).reason,
    /恢复完成/,
  );
  assert.match(
    assetDraftEntryPolicy({
      conversationId: "conv-asset-1",
      hasSavedUserMessage: true,
      reconciliationRequired: true,
    }).reason,
    /刷新会话核对/,
  );
});

test("从会话只提取用户原话作为起始草稿，不臆造触发条件或步骤", () => {
  assert.deepEqual(
    seedAssetDraftGeneralization([
      { role: "assistant", content: "可以。" },
      {
        role: "user",
        content: "  帮我核对稳态计算的输入边界，并标出需要工程师确认的缺口。  ",
      },
      { role: "user", content: "入口总压也要核对。" },
    ]),
    {
      title: "帮我核对稳态计算的输入边界，并标出需要工程师确认的缺口。",
      trigger: "",
      desired_outcome: "帮我核对稳态计算的输入边界，并标出需要工程师确认的缺口。",
      inputs: [],
      outputs: [],
      steps: [],
      evidence_requirements: [],
      human_decision_points: [],
      limitations: [],
    },
  );
});

test("预览请求规范化多行输入并固定 v1 契约", () => {
  assert.deepEqual(
    buildAssetDraftPreviewRequest({
      title: "  稳态计算输入边界核对  ",
      trigger: " 新算例进入求解前 ",
      desired_outcome: " 输出可审阅的缺口清单 ",
      inputs: "边界条件文件\n\n求解设置\n边界条件文件",
      outputs: [" 缺口清单 ", "复核记录"],
      steps: "读取输入\n按检查表核对\n标记未知项",
      evidence_requirements: "原始输入文件\n检查项定位",
      human_decision_points: "工程师确认边界适用性",
      limitations: "不执行求解\n不代替签发",
    }),
    {
      schema_version: "asset_draft_preview_request.v1",
      generalization: {
        title: "稳态计算输入边界核对",
        trigger: "新算例进入求解前",
        desired_outcome: "输出可审阅的缺口清单",
        inputs: ["边界条件文件", "求解设置", "边界条件文件"],
        outputs: ["缺口清单", "复核记录"],
        steps: ["读取输入", "按检查表核对", "标记未知项"],
        evidence_requirements: ["原始输入文件", "检查项定位"],
        human_decision_points: ["工程师确认边界适用性"],
        limitations: ["不执行求解", "不代替签发"],
      },
    },
  );
});

test("预览响应对未知状态、LLM 生成或任一副作用 fail-closed", () => {
  assert.deepEqual(normalizeAssetDraftPreview(READY_PREVIEW), READY_PREVIEW);
  assert.deepEqual(
    normalizeAssetDraftPreview(READY_PREVIEW, {
      expectedConversationId: "conv-asset-1",
    }),
    READY_PREVIEW,
  );

  for (const unsafe of [
    { ...READY_PREVIEW, status: "approved" },
    { ...READY_PREVIEW, generation: { kind: "llm", llm_used: true } },
    {
      ...READY_PREVIEW,
      effects: { ...READY_PREVIEW.effects, registers_asset: true },
    },
    {
      ...READY_PREVIEW,
      review: { ...READY_PREVIEW.review, decision_state: "approved" },
    },
    { ...READY_PREVIEW, builder_version: "asset_draft_builder.v2" },
    {
      ...READY_PREVIEW,
      work_case: { ...READY_PREVIEW.work_case, source_state: "client_claimed" },
    },
    {
      ...READY_PREVIEW,
      work_case: { ...READY_PREVIEW.work_case, conversation_status: "corrupt" },
    },
    {
      ...READY_PREVIEW,
      work_case: { ...READY_PREVIEW.work_case, source_id: "x".repeat(129) },
    },
    {
      ...READY_PREVIEW,
      task_pattern: {
        ...READY_PREVIEW.task_pattern,
        inputs: Array.from({ length: 21 }, (_, index) => `input-${index}`),
      },
    },
    {
      ...READY_PREVIEW,
      skill: { ...READY_PREVIEW.skill, description: "x".repeat(4201) },
    },
    {
      ...READY_PREVIEW,
      skill: {
        ...READY_PREVIEW.skill,
        operationalizes_task_pattern_digest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      },
    },
    {
      ...READY_PREVIEW,
      review: { ...READY_PREVIEW.review, requirements: [] },
    },
    {
      ...READY_PREVIEW,
      validation: {
        ...READY_PREVIEW.validation,
        issues: [
          {
            code: "unsupported.issue",
            severity: "green",
            path: "/validation",
            message: "不受支持的状态",
          },
        ],
        warning_count: 1,
      },
    },
    { ...READY_PREVIEW, approved_by: "model" },
    {
      ...READY_PREVIEW,
      work_case: { ...READY_PREVIEW.work_case, untrusted_note: "透传字段" },
    },
  ]) {
    assert.throws(
      () => normalizeAssetDraftPreview(unsafe),
      AssetDraftContractError,
    );
  }

  assert.throws(
    () =>
      normalizeAssetDraftPreview(READY_PREVIEW, {
        expectedConversationId: "conv-other",
      }),
    AssetDraftContractError,
  );
});

test("下载内容保持待审状态与零副作用声明，且不伪造注册结果", () => {
  const serialized = serializeAssetDraftDownload(READY_PREVIEW);
  assert.match(serialized, /"status": "draft"/);
  assert.match(serialized, /"state": "awaiting_human_review"/);
  assert.match(serialized, /"decision_state": "not_recorded"/);
  assert.match(serialized, /"registers_asset": false/);
  assert.doesNotMatch(serialized, /"approved"/);
  assert.ok(serialized.endsWith("\n"));
});
