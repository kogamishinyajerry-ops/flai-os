<template>
  <div class="md-lite">
    <template v-for="(blk, i) in blocks" :key="i">
      <component
        :is="`h${blk.level}`"
        v-if="blk.type === 'h'"
        class="md-h"
        :class="`md-h${blk.level}`"
      ><MdSegs :segs="blk.segs" /></component>
      <blockquote v-else-if="blk.type === 'quote'" class="md-quote" :class="`md-quote--${blk.variant}`">
        <MdSegs :segs="blk.segs" />
      </blockquote>
      <hr v-else-if="blk.type === 'hr'" class="md-hr" />
      <ul v-else-if="blk.type === 'ul'" class="md-ul">
        <li v-for="(it, j) in blk.items" :key="j"><MdSegs :segs="it" /></li>
      </ul>
      <p v-else-if="blk.type === 'p'" class="md-p"><MdSegs :segs="blk.segs" /></p>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h as hv } from "vue";

const props = defineProps({
  text: { type: String, default: "" },
});

// 行内分段（Codex R1+R2 P1 两轮修订）：只把**成对**的 `code` / **strong** 落成
// 真实元素；配不上对的 ** 与 ` 逐字保留——绝不无差别删字符（助手回复是任意
// 字符串，`def f(**kwargs)`、`2 ** 3` 必须保真）。strong 配对=侧翼扫描子集：
//   开标记：后必贴非空白，且**前禁 ASCII 代码上下文字符**（字母/数字/_/([{/\）
//     ——f(**kwargs 的 ** 永不当开标记（R2 例证 def f(**kwargs)：**重要** 若无
//     此卫，'：**' 会被当闭标记吃掉函数语法）；
//   闭标记：前必贴非空白。
// 刻意收窄于 CommonMark（ASCII 词内加粗 word**b**word 不解析）换取代码字面量
// 零误伤；中文惯用「**关键**是」不受影响。全程文本节点零 v-html。
const INLINE_RE = /(`([^`\n]+)`)|((?<![A-Za-z0-9_([{\\*])\*\*(?=\S)([^*\n]*?\S)\*\*)/;
function inlineSegs(s) {
  const segs = [];
  let rest = s.trimEnd();
  while (rest) {
    const m = INLINE_RE.exec(rest);
    if (!m) {
      segs.push({ t: "text", s: rest });
      break;
    }
    if (m.index > 0) segs.push({ t: "text", s: rest.slice(0, m.index) });
    if (m[1]) segs.push({ t: "code", s: m[2] });
    else segs.push({ t: "strong", s: m[4] });
    rest = rest.slice(m.index + m[0].length);
  }
  return segs;
}

// 行内段渲染器（函数式，纯文本子节点——不产出 HTML 字符串）。
const MdSegs = defineComponent({
  props: { segs: { type: Array, default: () => [] } },
  setup(p) {
    return () =>
      p.segs.map((sg) =>
        sg.t === "code" ? hv("code", { class: "md-code" }, sg.s)
        : sg.t === "strong" ? hv("strong", null, sg.s)
        : hv("span", null, sg.s)
      );
  },
});

// 引用块变体：🚨=截断危险（红），⚠=草案警示（amber），其余=普通引用。
function quoteVariant(s) {
  if (s.includes("🚨")) return "danger";
  if (s.includes("⚠")) return "warn";
  return "plain";
}

// 极简、按行的 markdown → 结构块（仅块级：标题/引用/分隔线/无序列表/段落）。
// 所有文本都走 Vue 插值转义，绝不产出 HTML 字符串——安全优先于花哨。
const blocks = computed(() => {
  const lines = String(props.text || "").split(/\r?\n/);
  const out = [];
  let list = null;
  const flushList = () => {
    if (list) {
      out.push({ type: "ul", items: list });
      list = null;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      flushList();
      out.push({ type: "h", level: h[1].length, segs: inlineSegs(h[2]) });
      continue;
    }
    if (/^>\s?/.test(line)) {
      flushList();
      const body = line.replace(/^>\s?/, "");
      out.push({ type: "quote", variant: quoteVariant(body), segs: inlineSegs(body) });
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line)) {
      flushList();
      out.push({ type: "hr" });
      continue;
    }
    const li = /^[-*+]\s+(.*)$/.exec(line) || /^\d+\.\s+(.*)$/.exec(line);
    if (li) {
      if (!list) list = [];
      list.push(inlineSegs(li[1]));
      continue;
    }
    if (line.trim() === "") {
      flushList();
      continue;
    }
    flushList();
    out.push({ type: "p", segs: inlineSegs(line) });
  }
  flushList();
  return out;
});
</script>

<style scoped>
.md-lite {
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink);
  word-break: break-word;
}
.md-h {
  font-family: var(--serif);
  font-weight: 600;
  line-height: 1.35;
  margin: 16px 0 8px;
}
.md-h:first-child {
  margin-top: 0;
}
.md-h1 {
  font-size: 20px;
}
.md-h2 {
  font-size: 17px;
}
.md-h3,
.md-h4 {
  font-size: 15px;
}
.md-p {
  margin: 8px 0;
}
.md-ul {
  margin: 8px 0;
  padding-left: 20px;
}
.md-ul li {
  margin: 3px 0;
}
/* MdSegs 由运行时 h() 产出，不带本 SFC 的 scoped 属性——必须 :deep 命中。 */
.md-lite :deep(.md-code) {
  font-family: var(--mono);
  font-size: 0.92em;
  background: var(--paper-rail);
  border: 1px solid var(--hairline-soft);
  border-radius: var(--radius-xs);
  padding: 0 4px;
}
.md-hr {
  border: none;
  border-top: 1px solid var(--hairline);
  margin: 14px 0;
}
.md-quote {
  margin: 10px 0;
  padding: 10px 14px;
  border-radius: 8px;
  border-left: 3px solid var(--ink-faint);
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 13.5px;
}
/* 草案水印 / 截断告警是关键信任信号——用语义色让它们跳出来，绝不淹没在正文里。 */
.md-quote--warn {
  border-left-color: var(--trust-pending);
  background: color-mix(in srgb, var(--trust-pending) 10%, var(--paper-surface));
  color: var(--ink);
  font-weight: 500;
}
.md-quote--danger {
  border-left-color: var(--trust-fail);
  background: color-mix(in srgb, var(--trust-fail) 10%, var(--paper-surface));
  color: var(--ink);
  font-weight: 600;
}
</style>
