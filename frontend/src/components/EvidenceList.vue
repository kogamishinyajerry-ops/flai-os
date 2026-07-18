<template>
  <!-- 依据清单（批七 §1.6，唯一新组件）：findings 的忠实投影——每条依据一行，
       kind 徽 + 出处粗体 + 引文灰字 + 核验态。**任何情况不染绿**（绿=仅 REAL
       实测，五槽信任色锁）：已核验用中性墨 ✓，未核 amber。置信度必带 basis，
       绝不裸报等级（「高」无依据=假权威）。 -->
  <div class="evidence-list">
    <div v-for="(f, fi) in findings" :key="fi" class="ev-finding">
      <p v-if="f.claim" class="ev-claim">{{ f.claim }}</p>
      <div v-for="(ev, ei) in f.evidence || []" :key="ei" class="ev-row">
        <span class="ev-kind" :title="kindLabel(ev.kind)">{{ kindGlyph(ev.kind) }}</span>
        <span class="ev-source">{{ ev.source_ref }}</span>
        <span v-if="withheld" class="ev-withheld">〔敏感内容，按密级隐藏〕</span>
        <span v-else-if="ev.quote" class="ev-quote" :class="{ 'is-code': /\d/.test(ev.quote) }">{{ ev.quote }}</span>
        <span v-if="ev.resolved === true" class="ev-verified">✓ 已回源核验</span>
        <span v-else class="ev-unverified">未核</span>
      </div>
      <p v-if="f.confidence && f.confidence.level" class="ev-confidence">
        置信度：{{ levelLabel(f.confidence.level) }}（{{ f.confidence.basis || "依据未标注" }} · 模型自评）
      </p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  findings: { type: Array, default: () => [] },
  // 密级遮蔽联动（classification_gate 出场面口径）：无权限时只留出处骨架不渲引文。
  withheld: { type: Boolean, default: false },
});

const KIND = {
  regulation_clause: { glyph: "规", label: "规章条款" },
  standard_clause: { glyph: "§", label: "标准条款" },
  type_case: { glyph: "机", label: "机型实例" },
  fault_case: { glyph: "案", label: "故障案例" },
  knowledge_doc: { glyph: "文", label: "知识文档" },
  calculation: { glyph: "算", label: "计算" },
};
const kindGlyph = (k) => KIND[k]?.glyph || "据";
const kindLabel = (k) => KIND[k]?.label || k || "依据";
const LEVEL = { high: "高", medium: "中", low: "低" };
const levelLabel = (l) => LEVEL[l] || l;
</script>

<style scoped>
.evidence-list { display: flex; flex-direction: column; gap: 10px; }
.ev-finding { display: flex; flex-direction: column; gap: 4px; }
.ev-claim { margin: 0; font-size: 13px; line-height: 1.55; color: var(--ink); }
.ev-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 7px;
  font-size: 12.5px;
  line-height: 1.5;
}
.ev-kind {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--hairline);
  border-radius: 5px;
  font-size: 11px;
  color: var(--ink-soft);
  align-self: center;
}
.ev-source { font-weight: 600; color: var(--ink); }
.ev-quote { color: var(--ink-soft); }
.ev-quote.is-code {
  font-family: var(--mono);
  font-size: 12px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: 5px;
  padding: 1px 6px;
}
.ev-withheld { color: var(--ink-soft); background: var(--paper-rail); border-radius: 5px; padding: 1px 8px; }
/* 已核验=中性墨 ✓（绝不绿）；未核=amber（信任色锁：amber=未核/待签唯一语义） */
.ev-verified { color: var(--ink-soft); }
.ev-unverified {
  color: var(--trust-pending);
  border: 1px solid color-mix(in srgb, var(--trust-pending) 45%, transparent);
  border-radius: 5px;
  padding: 0 6px;
  font-size: 11.5px;
}
.ev-confidence { margin: 0; font-size: 12px; color: var(--ink-soft); }
</style>
