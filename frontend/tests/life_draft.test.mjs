import test from "node:test";
import assert from "node:assert/strict";

import {
  LIFE_DRAFT_FIELDS,
  isLifeDraftShape,
  lifeDraftFieldEntries,
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

test("9 字段齐全的草稿通过形状校验", () => {
  assert.equal(isLifeDraftShape(validDraft()), true);
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
