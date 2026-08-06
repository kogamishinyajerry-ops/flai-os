// frontend/tests/plan_evidence_rollup.test.mjs — map#46 #56（R-B/R-C）：
// 方案卡可见面「依据行」聚合纯函数 mergeEvidenceSummaries 与成员态裁决
// decidePlanEvidenceLine（互审 F2/F3 定稿）的行为核。
// 锁定保守语义：invalid 任一命中即整体降级、置信度取最低档、计数只来自
// 结构合法成员、零占位返回 null、withheld 标记忠实透传不编计数、
// 归属不定 fail-closed 不渲、部分成员未可读时降级「依据结构待核」。
import test from "node:test";
import assert from "node:assert/strict";
import {
  decidePlanEvidenceLine,
  mergeEvidenceSummaries,
  summarizeEvidenceFindings,
} from "../src/utils/evidenceTrace.js";

// 用真实 summarizeEvidenceFindings 产出成员 summary，保证聚合输入与线上同形。
const summaryOf = (findings) => summarizeEvidenceFindings(findings);
const row = (resolved) => ({ kind: "fault_case", source_ref: "FC-1", resolved });

test("零占位：无任何成员数据且无遮蔽项时返回 null", () => {
  assert.equal(mergeEvidenceSummaries([]), null);
  assert.equal(mergeEvidenceSummaries(null), null);
  assert.equal(mergeEvidenceSummaries(undefined), null);
  assert.equal(
    mergeEvidenceSummaries([{ summary: null, withheld: false }, { summary: null }]),
    null,
  );
  // summarizeEvidenceFindings 对空 findings 本就给 null——成员无依据不算数据。
  assert.equal(
    mergeEvidenceSummaries([{ summary: summaryOf([]), withheld: false }]),
    null,
  );
});

test("仅遮蔽项：返回 withheld 占位，计数为 null，绝不编造 N", () => {
  const merged = mergeEvidenceSummaries([
    { summary: null, withheld: true },
    { summary: null, withheld: false },
  ]);
  assert.deepEqual(merged, {
    invalid: false,
    total: null,
    verified: null,
    unverified: null,
    level: "",
    withheld: true,
  });
});

test("混合计数：多成员计数求和，置信度取最低档", () => {
  const high = summaryOf([{
    claim: "c1",
    evidence: [row(true), row(true)],
    confidence: { level: "high" },
  }]);
  const low = summaryOf([{
    claim: "c2",
    evidence: [row(true), row(false), row(false)],
    confidence: { level: "low" },
  }]);
  const merged = mergeEvidenceSummaries([
    { summary: high, withheld: false },
    { summary: low, withheld: false },
    { summary: null, withheld: false }, // 无任务/无依据成员不参与
  ]);
  assert.equal(merged.invalid, false);
  assert.equal(merged.total, 5);
  assert.equal(merged.verified, 3);
  assert.equal(merged.unverified, 2);
  assert.equal(merged.level, "低"); // 最低档（诚实地板）
  assert.equal(merged.withheld, false);
});

test("invalid 短路：任一成员结构不合法即整体 invalid，计数只来自合法成员", () => {
  const good = summaryOf([{
    claim: "ok",
    evidence: [row(true)],
    confidence: { level: "medium" },
  }]);
  const bad = summaryOf([{ claim: "broken", evidence: [] }]); // 结构不合法 → invalid
  assert.equal(bad.invalid, true);
  const merged = mergeEvidenceSummaries([
    { summary: good, withheld: false },
    { summary: bad, withheld: false },
  ]);
  assert.equal(merged.invalid, true);
  assert.equal(merged.total, 1); // 非法成员不贡献计数
  assert.equal(merged.verified, 1);
  assert.equal(merged.unverified, 0);
});

test("全部成员 invalid：整体 invalid，计数归零（展示态只看 invalid 句）", () => {
  const bad = summaryOf([{ claim: "broken", evidence: [] }]);
  const merged = mergeEvidenceSummaries([
    { summary: bad, withheld: false },
    { summary: bad, withheld: false },
  ]);
  assert.equal(merged.invalid, true);
  assert.equal(merged.total, 0);
  assert.equal(merged.level, "");
});

test("计数与遮蔽共存：withheld 忠实透传，计数不吞也不涨", () => {
  const good = summaryOf([{
    claim: "ok",
    evidence: [row(false)],
    confidence: { level: "high" },
  }]);
  const merged = mergeEvidenceSummaries([
    { summary: good, withheld: false },
    { summary: null, withheld: true },
  ]);
  assert.equal(merged.invalid, false);
  assert.equal(merged.total, 1);
  assert.equal(merged.unverified, 1);
  assert.equal(merged.withheld, true);
});

test("置信度缺档的成员不拉低也不虚报档位", () => {
  const noLevel = summaryOf([{ claim: "c", evidence: [row(true)] }]);
  assert.equal(noLevel.level, "");
  const merged = mergeEvidenceSummaries([{ summary: noLevel, withheld: false }]);
  assert.equal(merged.level, "");
});

// ── decidePlanEvidenceLine（互审 F2/F3，owner 2026-08-06 裁）────────────
// 成员态由 GuidePage 用确定性信号判定，本组锁定裁决的诚实语义：
// 归属不定 fail-closed 不渲 / 零占位 / 部分可读降级「依据结构待核」。

test("F2：任一成员归属不定（attributionFailed）→ 整行 fail-closed 不渲", () => {
  const data = { state: "data", summary: summaryOf([{ claim: "c", evidence: [row(false)] }]) };
  assert.equal(decidePlanEvidenceLine([data, { state: "attributionFailed" }]), null);
  assert.equal(decidePlanEvidenceLine([{ state: "attributionFailed" }]), null);
  assert.equal(decidePlanEvidenceLine([]), null);
  assert.equal(decidePlanEvidenceLine(null), null);
});

test("零占位：开工前/全员在途/全员已知空都不渲行", () => {
  assert.equal(decidePlanEvidenceLine([{ state: "noTask" }, { state: "noTask" }]), null);
  assert.equal(decidePlanEvidenceLine([{ state: "pending" }, { state: "noTask" }]), null);
  assert.equal(decidePlanEvidenceLine([{ state: "empty" }, { state: "empty" }]), null);
});

test("F3：有可读成员但仍有成员未可读（pending/noTask）→ 降级「依据结构待核」amber", () => {
  const data = { state: "data", summary: summaryOf([{ claim: "c", evidence: [row(true)] }]) };
  for (const pending of [{ state: "pending" }, { state: "noTask" }]) {
    const line = decidePlanEvidenceLine([data, pending]);
    assert.equal(line.text, "依据结构待核");
    assert.equal(line.hasUnverified, true);
    assert.equal(line.withheldOnly, false);
  }
  // 遮蔽是可读的已知态：withheld + pending 同样降级（遮蔽计数也不冒充完整）。
  const line = decidePlanEvidenceLine([{ state: "withheld" }, { state: "pending" }]);
  assert.equal(line.text, "依据结构待核");
  assert.equal(line.hasUnverified, true);
});

test("全员已知：data+empty 正常计数（empty 零占位不贡献），遮蔽共存沿 W7 后缀", () => {
  const data = {
    state: "data",
    summary: summaryOf([{ claim: "c", evidence: [row(true), row(false)], confidence: { level: "low" } }]),
  };
  const line = decidePlanEvidenceLine([data, { state: "empty" }]);
  assert.equal(line.text, "依据 2 条（1 已核验 · 1 未核） · 置信度 低（模型自评）");
  assert.equal(line.hasUnverified, true);
  const mixed = decidePlanEvidenceLine([data, { state: "empty" }, { state: "withheld" }]);
  assert.equal(mixed.text, "依据 2 条（1 已核验 · 1 未核） · 置信度 低（模型自评）·另有密级隐藏项");
});

test("全员已知：仅遮蔽→遮蔽行不编 N；data invalid→待核句（带遮蔽加后缀）", () => {
  const onlyWithheld = decidePlanEvidenceLine([{ state: "withheld" }, { state: "empty" }]);
  assert.deepEqual(onlyWithheld, {
    text: "依据清单〔按密级隐藏〕",
    hasUnverified: false,
    withheldOnly: true,
  });
  const invalidData = { state: "data", summary: summaryOf([{ claim: "broken", evidence: [] }]) };
  const line = decidePlanEvidenceLine([invalidData, { state: "empty" }]);
  assert.equal(line.text, "依据结构待核");
  assert.equal(line.hasUnverified, true);
  const lineWithheld = decidePlanEvidenceLine([invalidData, { state: "withheld" }]);
  assert.equal(lineWithheld.text, "依据结构待核·另有密级隐藏项");
});
