<template>
  <div class="md-lite">
    <template v-for="(blk, i) in blocks" :key="i">
      <component
        :is="`h${blk.level}`"
        v-if="blk.type === 'h'"
        class="md-h"
        :class="`md-h${blk.level}`"
      >{{ blk.text }}</component>
      <blockquote v-else-if="blk.type === 'quote'" class="md-quote" :class="`md-quote--${blk.variant}`">
        {{ blk.text }}
      </blockquote>
      <hr v-else-if="blk.type === 'hr'" class="md-hr" />
      <ul v-else-if="blk.type === 'ul'" class="md-ul">
        <li v-for="(it, j) in blk.items" :key="j">{{ it }}</li>
      </ul>
      <p v-else-if="blk.type === 'p'" class="md-p">{{ blk.text }}</p>
    </template>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  text: { type: String, default: "" },
});

// 去掉行内强调/代码标记（**、`）——纯为可读，不注入任何 HTML（全经插值转义，防 XSS）。
function clean(s) {
  return s.replace(/\*\*/g, "").replace(/`/g, "").trimEnd();
}

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
      out.push({ type: "h", level: h[1].length, text: clean(h[2]) });
      continue;
    }
    if (/^>\s?/.test(line)) {
      flushList();
      const body = line.replace(/^>\s?/, "");
      out.push({ type: "quote", variant: quoteVariant(body), text: clean(body) });
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
      list.push(clean(li[1]));
      continue;
    }
    if (line.trim() === "") {
      flushList();
      continue;
    }
    flushList();
    out.push({ type: "p", text: clean(line) });
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
