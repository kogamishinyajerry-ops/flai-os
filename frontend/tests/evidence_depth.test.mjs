// frontend/tests/evidence_depth.test.mjs — 批次 D：依据/知识链的语义深度核。
// 锁定五槽信任色锁与 fail-closed：未核/漂移/缺失/拒答/withheld 各自语义不串，
// 受限数量与内容绝不泄露，resolved=true 恒中性，任何输入组合都不染绿槽。
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildEvidenceTrace,
  buildKnowledgeTrace,
  summarizeEvidenceFindings,
} from "../src/utils/evidenceTrace.js";

const byId = (steps, id) => steps.find((step) => step.id === id);
const ALLOWED_TONES = new Set(["neutral", "pending", "fail"]);
const tonesClean = (steps) => steps.every((step) => ALLOWED_TONES.has(step.tone));

const validRow = { kind: "knowledge_doc", source_ref: "DOC-1", resolved: true };

test("withheld：不泄露受限数量与内容，链上零数字零出处零引文", () => {
  const steps = buildEvidenceTrace({
    findings: [{
      claim: "含机密引文的主张",
      evidence: [
        { kind: "regulation_clause", source_ref: "SECRET-CL-042", quote: "不可泄露的条款原文", resolved: true },
        { kind: "fault_case", source_ref: "SECRET-FC-007", quote: "另一段受限引文", resolved: false },
      ],
    }],
    withheld: true,
  });
  assert.equal(tonesClean(steps), true);
  for (const step of steps) {
    assert.doesNotMatch(step.detail, /\d/, `${step.id} 泄露了数量`);
    assert.doesNotMatch(step.detail, /SECRET|不可泄露|受限引文/, `${step.id} 泄露了内容`);
  }
  assert.match(byId(steps, "source").detail, /按密级隐藏/);
  // 人签节点不因为遮蔽而消失——结论仍由有权限人员判断（amber 待判语义）。
  assert.equal(byId(steps, "decision").tone, "pending");
});

test("withheld 与可读 findings 混合时整体走遮蔽语义， Readable 部分由 EvidenceList 另行投影", () => {
  // buildKnowledgeTrace 的 withheld 语义不得削弱：遮蔽分支优先于一切计数——
  // 即便 findings 完全合法，也不回退出「N 条可展示依据」的泄露口径。
  const steps = buildEvidenceTrace({
    findings: [{ claim: "可读主张", evidence: [validRow] }],
    withheld: true,
  });
  assert.doesNotMatch(byId(steps, "source").detail, /1 条/);
  assert.match(byId(steps, "source").detail, /按密级隐藏/);
});

test("resolved=true 恒中性；resolved=false 计未核且 amber，两端都不染绿", () => {
  const resolved = buildEvidenceTrace({
    findings: [{ claim: "主张", evidence: [validRow] }],
  });
  assert.equal(byId(resolved, "resolution").tone, "neutral");
  assert.match(byId(resolved, "resolution").detail, /已回源核对/);
  assert.equal(tonesClean(resolved), true);

  const unresolved = buildEvidenceTrace({
    findings: [{
      claim: "主张",
      evidence: [validRow, { kind: "fault_case", source_ref: "FC-2", resolved: false }],
    }],
  });
  assert.equal(byId(unresolved, "resolution").tone, "pending");
  assert.match(byId(unresolved, "resolution").detail, /1 条未回源核对/);
  assert.equal(tonesClean(unresolved), true);
});

test("畸形输入逐型 fail-closed：缺证据、非布尔 resolved、空 finding、非数组 findings", () => {
  const cases = [
    { findings: null },
    { findings: "not-an-array" },
    { findings: [{ claim: "空依据", evidence: [] }] },
    { findings: [{ claim: "非布尔", evidence: [{ kind: "knowledge_doc", source_ref: "D", resolved: "yes" }] }] },
    { findings: [{ claim: "缺出处", evidence: [{ kind: "knowledge_doc", resolved: true }] }] },
  ];
  for (const input of cases) {
    const steps = buildEvidenceTrace(input);
    assert.equal(byId(steps, "source").tone, "pending", JSON.stringify(input));
    assert.match(byId(steps, "source").detail, /待核/);
    assert.equal(byId(steps, "decision").tone, "pending");
    assert.equal(tonesClean(steps), true);
  }
});

test("声明必需但零依据：来源与回源双 amber，措辞是「需要依据」而非「暂无」", () => {
  const steps = buildEvidenceTrace({ findings: [], requiredMissing: true });
  assert.equal(byId(steps, "source").tone, "pending");
  assert.match(byId(steps, "source").detail, /需要依据/);
  assert.equal(byId(steps, "resolution").tone, "pending");
  // 未声明必需时零依据是正常态（如纯计算任务），不制造 amber 噪音。
  const optional = buildEvidenceTrace({ findings: [] });
  assert.equal(byId(optional, "source").tone, "neutral");
});

test("知识链：一致/漂移/缺指纹/非数组四态严格分开，漂移 amber 而非红", () => {
  const consistent = buildKnowledgeTrace([{ searchFingerprint: "a", currentFingerprint: "a" }]);
  assert.equal(byId(consistent, "compare").tone, "neutral");

  const drifted = buildKnowledgeTrace([{ searchFingerprint: "a", currentFingerprint: "b" }]);
  assert.equal(byId(drifted, "compare").tone, "pending");
  assert.match(byId(drifted, "compare").detail, /变动/);

  const incomplete = buildKnowledgeTrace([{ searchFingerprint: "a" }]);
  assert.equal(byId(incomplete, "compare").tone, "pending");
  assert.match(byId(incomplete, "compare").detail, /不完整/);

  const malformed = buildKnowledgeTrace("not-an-array");
  assert.equal(byId(malformed, "source").tone, "pending");
  assert.match(byId(malformed, "source").detail, /待核/);

  for (const steps of [consistent, drifted, incomplete, malformed]) {
    assert.equal(byId(steps, "decision").tone, "pending");
    assert.equal(tonesClean(steps), true);
  }
});

test("依据摘要：部分畸形即整体 invalid，置信度取最低档，绝不留最高档假权威", () => {
  const mixed = summarizeEvidenceFindings([
    { claim: "好", evidence: [validRow] },
    { claim: "坏", evidence: [null] },
  ]);
  assert.equal(mixed.invalid, true);
  assert.equal(mixed.total, null);

  const leveled = summarizeEvidenceFindings([
    { claim: "高", evidence: [validRow], confidence: { level: "high" } },
    { claim: "低", evidence: [{ kind: "fault_case", source_ref: "FC", resolved: false }], confidence: { level: "low" } },
  ]);
  assert.equal(leveled.invalid, false);
  assert.equal(leveled.level, "低");
  assert.equal(leveled.verified, 1);
  assert.equal(leveled.unverified, 1);

  const noLevel = summarizeEvidenceFindings([{ claim: "无自评", evidence: [validRow] }]);
  assert.equal(noLevel.level, "");
});
