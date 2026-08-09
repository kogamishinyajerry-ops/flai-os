import test from "node:test";
import assert from "node:assert/strict";

import {
  LIFE_DRAFT_FIELDS,
  assertLifePostMatchesSnapshot,
  isLifeDraftShape,
  lifeDraftFieldEntries,
  normalizeGeneralizationDraftRecord,
  normalizeLifeConversationMessage,
  normalizeLifeConversationSnapshot,
  normalizeLifePostResponse,
  isDefinitelyUncommittedLifePostError,
  reconcileAmbiguousLifePostSnapshot,
  resolveLifeDemoRoute,
  summarizeLifeDraftPreview,
} from "../src/utils/lifeDraft.js";

function validDraft() {
  return {
    title: "家常红烧肉（带皮五花肉版）",
    trigger: "家里想吃红烧肉 + 有 2 小时 + 有炒锅和炖锅",
    desired_outcome: "一盘 4-6 人份、能咬动、咸淡合适的红烧肉",
    inputs: ["带皮五花肉 500-700g", "冰糖", "生抽老抽料酒"],
    outputs: ["一盘红烧肉"],
    steps: ["切块焯水", "炒糖色到琥珀色下肉", "小火炖 50 分钟", "尝咸淡收汁"],
    evidence_requirements: ["糖色琥珀色", "尝咸淡通过"],
    human_decision_points: ["尝咸淡必须人工"],
    limitations: ["不适用高压锅", "不适用其他肉类"],
  };
}

function validPreview() {
  return {
    draft_digest: `sha256:${"a".repeat(64)}`,
    validation: {
      state: "ready_for_human_review",
      blocking_count: 0,
      warning_count: 0,
    },
    review: { state: "awaiting_human_review" },
    effects: {
      writes_database: false,
      executes_work: false,
      registers_asset: false,
      promotes_asset: false,
    },
    generation: { kind: "deterministic_projection", llm_used: false },
  };
}

function validRecord() {
  return {
    id: `gdr_${"a".repeat(32)}`,
    schema_version: "generalization_draft_record.v1",
    payload_schema_version: "life_generalization.v1",
    state: "model_draft",
    review_status: "waiting_review",
    payload: validDraft(),
    content_digest: `sha256:${"b".repeat(64)}`,
    record_digest: `sha256:${"c".repeat(64)}`,
    source_context_digest: `sha256:${"d".repeat(64)}`,
    model_attribution: {
      model_call_id: 17,
      kind: "chat",
      agent_id: "life_guide_agent",
      agent_version: "1.0.0",
      profile: "default",
      model_name: "stub-model",
    },
    lineage: {
      conversation_id: "conv-life-1",
      user_message_id: 40,
      assistant_message_id: 41,
      task_id: null,
    },
    created_at: "2026-08-09T08:00:00+00:00",
  };
}

function validAssistantMessage(record = validRecord()) {
  return {
    id: 41,
    conversation_id: "conv-life-1",
    role: "assistant",
    content: "我整理了一份待审草稿。",
    recommendation: null,
    file_ids: [],
    created_at: "2026-08-09T08:00:00+00:00",
    generalization_draft_record: record,
  };
}

function validUserMessage(id = 40, content = "原始经历") {
  return {
    id,
    conversation_id: "conv-life-1",
    role: "user",
    content,
    recommendation: null,
    file_ids: [],
    created_at: "2026-08-09T07:59:59+00:00",
  };
}

test("9 字段齐全的草稿通过形状校验", () => {
  assert.equal(isLifeDraftShape(validDraft()), true);
});

test("草稿 payload 只能有冻结的九个字段，未知字段 fail-closed", () => {
  assert.equal(
    isLifeDraftShape({ ...validDraft(), approval_state: "approved" }),
    false,
  );
});

test("持久 payload 只接受服务端 canonical NFC 与已裁边界文本", () => {
  const padded = validDraft();
  padded.title = ` ${padded.title}`;
  assert.equal(isLifeDraftShape(padded), false);

  const nfd = validDraft();
  nfd.inputs = ["Cafe\u0301", ...nfd.inputs.slice(1)];
  assert.equal(isLifeDraftShape(nfd), false);
});

test("持久化草稿记录只接受 exact R2 envelope 与当前 assistant lineage", () => {
  const record = validRecord();
  assert.deepEqual(
    normalizeGeneralizationDraftRecord(record, {
      conversationId: "conv-life-1",
      assistantMessageId: 41,
    }),
    record,
  );

  assert.throws(
    () =>
      normalizeGeneralizationDraftRecord(
        { ...record, workflow_claimed_approval: true },
        { conversationId: "conv-life-1", assistantMessageId: 41 },
      ),
    /字段集合/,
  );
});

test("草稿记录对嵌套字段、越权状态、错误 digest 与 task 血缘逐项 fail-closed", () => {
  const record = validRecord();
  const mutations = [
    { ...record, id: `draft_${"a".repeat(32)}` },
    { ...record, state: "approved" },
    { ...record, review_status: "approved" },
    { ...record, content_digest: `sha256:${"A".repeat(64)}` },
    {
      ...record,
      payload: { ...record.payload, approved_by: "model" },
    },
    {
      ...record,
      model_attribution: {
        ...record.model_attribution,
        kind: "embed",
      },
    },
    {
      ...record,
      model_attribution: {
        ...record.model_attribution,
        receipt_summary: "not authoritative",
      },
    },
    {
      ...record,
      lineage: { ...record.lineage, task_id: "task_1" },
    },
    {
      ...record,
      lineage: { ...record.lineage, conversation_id: "conv-foreign" },
    },
  ];
  for (const mutation of mutations) {
    assert.throws(
      () =>
        normalizeGeneralizationDraftRecord(mutation, {
          conversationId: "conv-life-1",
          assistantMessageId: 41,
        }),
      undefined,
      JSON.stringify(mutation),
    );
  }
});

test("消息投影以 public message.id 咬合 lineage；坏记录只抑制卡片并保留文字", () => {
  const valid = normalizeLifeConversationMessage(validAssistantMessage(), {
    conversationId: "conv-life-1",
  });
  assert.equal(valid.id, 41);
  assert.equal(valid.draftRecord?.id, `gdr_${"a".repeat(32)}`);
  assert.equal(valid.draftRecordInvalid, false);

  const mismatched = validAssistantMessage({
    ...validRecord(),
    lineage: { ...validRecord().lineage, assistant_message_id: 999 },
  });
  const suppressed = normalizeLifeConversationMessage(mismatched, {
    conversationId: "conv-life-1",
  });
  assert.equal(suppressed.content, "我整理了一份待审草稿。");
  assert.equal(suppressed.draftRecord, null);
  assert.equal(suppressed.draftRecordInvalid, true);

  assert.throws(
    () =>
      normalizeLifeConversationMessage(
        {
          id: 40,
          conversation_id: "conv-life-1",
          role: "user",
          content: "原始经历",
          generalization_draft_record: null,
        },
        { conversationId: "conv-life-1" },
      ),
    /用户消息不得携带/,
  );

  const missingConversationBinding = validAssistantMessage();
  delete missingConversationBinding.conversation_id;
  assert.throws(
    () =>
      normalizeLifeConversationMessage(missingConversationBinding, {
        conversationId: "conv-life-1",
      }),
    /消息与当前会话不一致/,
  );
});

test("POST 与 GET 走同一消息投影，legacy top-level sidecar 不再可渲染", () => {
  const assistant = validAssistantMessage(null);
  const conversation = {
    id: "conv-life-1",
    agent_id: "life_guide_agent",
    status: "active",
    created_by: "owner",
  };
  const post = normalizeLifePostResponse(
    {
      message: assistant,
      conversation,
      generalization_draft: validDraft(),
    },
    { expectedConversationId: "conv-life-1" },
  );
  const get = normalizeLifeConversationSnapshot(
    { ...conversation, messages: [assistant] },
    { expectedConversationId: "conv-life-1" },
  );

  assert.equal(post.message.draftRecord, null);
  assert.equal(post.message.generalization_draft, undefined);
  assert.deepEqual(post.message, get.messages[0]);
  assert.throws(
    () =>
      normalizeLifeConversationSnapshot(
        { ...conversation, agent_id: "guide_agent", messages: [] },
        { expectedConversationId: "conv-life-1" },
      ),
    /life_guide_agent/,
  );
});

test("/demo route intent 固定为 pick/create/load，c 深链永不退化为 create", () => {
  const allowed = ["cooking", "travel", "renovation"];
  assert.deepEqual(resolveLifeDemoRoute({}, allowed), { kind: "pick" });
  assert.deepEqual(resolveLifeDemoRoute({ s: "cooking" }, allowed), {
    kind: "create",
    scenarioId: "cooking",
  });
  assert.deepEqual(
    resolveLifeDemoRoute({ s: "cooking", c: "conv-life-1" }, allowed),
    {
      kind: "load",
      scenarioId: "cooking",
      conversationId: "conv-life-1",
    },
  );
  assert.equal(resolveLifeDemoRoute({ s: "unknown" }, allowed).kind, "invalid");
  assert.equal(
    resolveLifeDemoRoute({ s: "cooking", c: "" }, allowed).kind,
    "invalid",
  );
  assert.equal(
    resolveLifeDemoRoute({ c: "conv-life-1" }, allowed).kind,
    "invalid",
  );
  assert.equal(
    resolveLifeDemoRoute({ s: ["cooking", "travel"] }, allowed).kind,
    "invalid",
  );
});

test("POST assistant 必须在随后的 GET 快照中逐字段一致", () => {
  const assistant = validAssistantMessage();
  const conversation = {
    id: "conv-life-1",
    agent_id: "life_guide_agent",
    status: "active",
    created_by: "owner",
  };
  const post = normalizeLifePostResponse(
    { message: assistant, conversation },
    { expectedConversationId: "conv-life-1" },
  );
  const snapshot = normalizeLifeConversationSnapshot(
    { ...conversation, messages: [assistant] },
    { expectedConversationId: "conv-life-1" },
  );
  assert.equal(assertLifePostMatchesSnapshot(post, snapshot), true);
  assert.throws(
    () =>
      assertLifePostMatchesSnapshot(post, {
        ...snapshot,
        messages: [{ ...snapshot.messages[0], content: "漂移的正文" }],
      }),
    /不一致/,
  );
});

test("POST reject 只有严格 allowlist 的前置 4xx 才可判定未提交", () => {
  for (const status of [401, 403, 404, 413, 415, 422]) {
    assert.equal(isDefinitelyUncommittedLifePostError({ status }), true);
  }
  for (const status of [0, 400, 409, 429, 500, 502, 503]) {
    assert.equal(isDefinitelyUncommittedLifePostError({ status }), false);
  }
  assert.equal(isDefinitelyUncommittedLifePostError(null), false);
});

test("ambiguous POST 只在冷读精确追加一组 user/assistant 且 lineage 咬合时恢复", () => {
  const conversation = {
    id: "conv-life-1",
    agent_id: "life_guide_agent",
    status: "active",
    created_by: "owner",
  };
  const oldUser = validUserMessage(30, "旧一轮");
  const oldAssistant = {
    ...validAssistantMessage(null),
    id: 31,
    content: "旧回复",
  };
  const baseline = normalizeLifeConversationSnapshot(
    { ...conversation, messages: [oldUser, oldAssistant] },
    { expectedConversationId: conversation.id },
  ).messages;
  const snapshot = normalizeLifeConversationSnapshot(
    {
      ...conversation,
      messages: [
        oldUser,
        oldAssistant,
        validUserMessage(),
        validAssistantMessage(),
      ],
    },
    { expectedConversationId: conversation.id },
  );

  const baselineOnlySnapshot = {
    ...snapshot,
    messages: baseline,
  };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    assert.throws(
      () =>
        reconcileAmbiguousLifePostSnapshot(baselineOnlySnapshot, {
          baselineMessages: baseline,
          submittedText: "原始经历",
        }),
      /无法唯一核对/,
    );
  }

  const recovered = reconcileAmbiguousLifePostSnapshot(snapshot, {
    baselineMessages: baseline,
    submittedText: "原始经历",
  });
  assert.equal(recovered.userMessage.id, 40);
  assert.equal(recovered.assistantMessage.id, 41);

  assert.throws(
    () =>
      reconcileAmbiguousLifePostSnapshot(snapshot, {
        baselineMessages: baseline,
        submittedText: "另一段经历",
      }),
    /无法唯一核对/,
  );

  const badLineageRecord = validRecord();
  badLineageRecord.lineage = {
    ...badLineageRecord.lineage,
    user_message_id: 999,
  };
  const badLineageSnapshot = normalizeLifeConversationSnapshot(
    {
      ...conversation,
      messages: [
        oldUser,
        oldAssistant,
        validUserMessage(),
        validAssistantMessage(badLineageRecord),
      ],
    },
    { expectedConversationId: conversation.id },
  );
  assert.throws(
    () =>
      reconcileAmbiguousLifePostSnapshot(badLineageSnapshot, {
        baselineMessages: baseline,
        submittedText: "原始经历",
      }),
    /lineage/,
  );
});

test("字段顺序与教学标签固定（投影格式不可漂移）", () => {
  assert.deepEqual(
    LIFE_DRAFT_FIELDS.map(({ id }) => id),
    [
      "title",
      "trigger",
      "desired_outcome",
      "inputs",
      "outputs",
      "steps",
      "evidence_requirements",
      "human_decision_points",
      "limitations",
    ],
  );
});

test("任一字段残缺 → fail-closed 拒绝渲染", () => {
  for (const field of LIFE_DRAFT_FIELDS) {
    const draft = validDraft();
    delete draft[field.id];
    assert.equal(isLifeDraftShape(draft), false, `缺 ${field.id} 应拒绝`);
  }
  assert.equal(isLifeDraftShape(null), false);
  assert.equal(isLifeDraftShape("not-a-draft"), false);
  assert.equal(isLifeDraftShape([]), false);
});

test("列表字段为空 / steps 不足 2 条 → 拒绝", () => {
  const empty = validDraft();
  empty.limitations = [];
  assert.equal(isLifeDraftShape(empty), false);

  const oneStep = validDraft();
  oneStep.steps = ["一步到位"];
  assert.equal(isLifeDraftShape(oneStep), false);
});

test("标量超长 / 列表项空白 / 列表超 20 项 → 拒绝", () => {
  const longTitle = validDraft();
  longTitle.title = "名".repeat(161);
  assert.equal(isLifeDraftShape(longTitle), false);

  const blankItem = validDraft();
  blankItem.inputs = ["正常输入", "   "];
  assert.equal(isLifeDraftShape(blankItem), false);

  const tooMany = validDraft();
  tooMany.outputs = Array.from({ length: 21 }, (_, i) => `产物${i}`);
  assert.equal(isLifeDraftShape(tooMany), false);
});

test("形状不合规时渲染条目为空数组（不渲染半份候选）", () => {
  assert.deepEqual(lifeDraftFieldEntries({}), []);
  assert.deepEqual(lifeDraftFieldEntries(null), []);
});

test("形状合规时按固定顺序投影 9 个条目", () => {
  const entries = lifeDraftFieldEntries(validDraft());
  assert.equal(entries.length, 9);
  assert.deepEqual(
    entries.map(({ id }) => id),
    LIFE_DRAFT_FIELDS.map(({ id }) => id),
  );
  const title = entries.find(({ id }) => id === "title");
  assert.equal(title.kind, "text");
  assert.equal(title.value, "家常红烧肉（带皮五花肉版）");
  const steps = entries.find(({ id }) => id === "steps");
  assert.equal(steps.kind, "list");
  assert.equal(steps.value.length, 4);
});

test("preview 摘要投影 digest、校验态与四铁律声明", () => {
  const summary = summarizeLifeDraftPreview(validPreview());
  assert.ok(summary);
  assert.equal(summary.digest, `sha256:${"a".repeat(64)}`);
  assert.equal(summary.digestShort, "aaaaaaaaaaaa");
  assert.equal(summary.validationState, "ready_for_human_review");
  assert.equal(summary.blockingCount, 0);
  assert.equal(summary.reviewState, "awaiting_human_review");
  assert.equal(summary.effectsAllFalse, true);
  assert.equal(summary.deterministic, true);
  assert.equal(summary.effectRows.length, 4);
});

test("preview 摘要 fail-closed：残缺响应返回 null，不猜测", () => {
  assert.equal(summarizeLifeDraftPreview(null), null);
  assert.equal(summarizeLifeDraftPreview({}), null);
  const badDigest = validPreview();
  badDigest.draft_digest = "sha256:zzz";
  assert.equal(summarizeLifeDraftPreview(badDigest), null);
});

test("effects 出现非 False 值 → 按未知展示，绝不洗绿", () => {
  const dirty = validPreview();
  dirty.effects.registers_asset = true;
  const summary = summarizeLifeDraftPreview(dirty);
  assert.ok(summary);
  assert.equal(summary.effectsAllFalse, false);
  const row = summary.effectRows.find(({ key }) => key === "registers_asset");
  assert.equal(row.value, null);
});

test("generation 声明不是确定性投影 → deterministic 为 false", () => {
  const llm = validPreview();
  llm.generation = { kind: "llm_authored", llm_used: true };
  const summary = summarizeLifeDraftPreview(llm);
  assert.ok(summary);
  assert.equal(summary.deterministic, false);
});
