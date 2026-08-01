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
      <pre v-else-if="blk.type === 'code'" class="md-pre" :class="{ 'md-pre--lang': blk.lang }"><span v-if="blk.lang" class="md-pre-lang">{{ blk.lang }}</span><code class="md-pre-code">{{ blk.code }}</code></pre>
      <ul v-else-if="blk.type === 'ul'" class="md-ul">
        <li v-for="(it, j) in blk.items" :key="j"><MdSegs :segs="it" /></li>
      </ul>
      <p v-else-if="blk.type === 'p'" class="md-p"><MdSegs :segs="blk.segs" /></p>
    </template>
  </div>
</template>

<script setup>
import { computed, defineComponent, h as hv } from "vue";
import { parseMarkdownBlocks } from "../utils/markdownLite.js";

const props = defineProps({
  text: { type: String, default: "" },
});

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

// 解析核在 utils/markdownLite.js（纯函数，可单测）：流式下每次全量重算，
// 未闭合 fence 兜底纯文本；code 块内容走插值转义，零 v-html。
const blocks = computed(() => parseMarkdownBlocks(props.text));
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
/* 围栏代码块：surface-raised 底 + hairline 描边，横向超长内部滚动绝不撑破气泡；
 * lang 标签右上角小字（ink-faint）。无过渡动画——流式逐 delta 重渲染零闪烁。 */
.md-pre {
  position: relative;
  margin: 8px 0;
  padding: var(--space-2) var(--space-3);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  max-width: 100%;
  overflow-x: auto;
}
.md-pre--lang {
  padding-top: calc(var(--space-2) + var(--space-4));
}
.md-pre-lang {
  position: absolute;
  top: var(--space-1);
  right: var(--space-3);
  font-size: var(--fs-xs);
  color: var(--ink-faint);
  user-select: none;
}
.md-pre-code {
  font-family: var(--mono);
  font-size: 0.92em;
  white-space: pre;
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
