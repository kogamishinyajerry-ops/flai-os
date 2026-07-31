// frontend/tests/markdown_lite_fence.test.mjs — MarkdownLite 围栏代码块（```）解析契约。
// 解析核=纯函数 utils/markdownLite.js；组件侧结构约束（零 v-html / pre+code）读 SFC 源断言。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseMarkdownBlocks } from "../src/utils/markdownLite.js";

const SFC_PATH = fileURLToPath(new URL("../src/components/MarkdownLite.vue", import.meta.url));

// 拍平 segs 便于文本断言。
const segText = (segs) => segs.map((s) => s.s).join("");

test("闭合 fence 成 code 块：内容逐字、不做行内解析", () => {
  const blocks = parseMarkdownBlocks("前文\n```python\ndef f(**kwargs):\n    return `x` ** 2\n```\n后文");
  assert.deepEqual(blocks.map((b) => b.type), ["p", "code", "p"]);
  assert.equal(blocks[1].lang, "python");
  assert.equal(blocks[1].code, "def f(**kwargs):\n    return `x` ** 2");
  // fence 内的 **/反引号绝不触发行内 strong/code 解析（逐字保真）。
  assert.ok(!("segs" in blocks[1]));
  assert.equal(segText(blocks[0].segs), "前文");
  assert.equal(segText(blocks[2].segs), "后文");
});

test("未闭合 fence（流式中途）兜底纯文本：opener 行与后续行按常规解析，不误吞", () => {
  const mid = parseMarkdownBlocks("说明：\n```python\ndef f():\n    pass");
  assert.deepEqual(mid.map((b) => b.type), ["p", "p", "p", "p"]);
  assert.equal(segText(mid[1].segs), "```python");
  assert.equal(segText(mid[2].segs), "def f():");
  // 未闭合 fence 后面的普通段落/列表绝不进 code 块。
  const trailing = parseMarkdownBlocks("```js\nlet a = 1\n\n普通段落\n- 列表项");
  assert.deepEqual(trailing.map((b) => b.type), ["p", "p", "p", "ul"]);
  assert.equal(segText(trailing[2].segs), "普通段落");
  assert.equal(segText(trailing[3].items[0]), "列表项");
  // 流式补齐闭 fence 后同前缀文本成块——纯函数式重算，无状态残留。
  const done = parseMarkdownBlocks("```js\nlet a = 1\n```");
  assert.deepEqual(done.map((b) => b.type), ["code"]);
});

test("fence 内 HTML 逐字保留（组件插值转义的前提：原串不被吞改）", () => {
  const blocks = parseMarkdownBlocks("```html\n<div class=\"x\">a &amp; b</div>\n<script>alert(1)</script>\n```");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].type, "code");
  assert.equal(blocks[0].code, '<div class="x">a &amp; b</div>\n<script>alert(1)</script>');
});

test("lang 标签：有 lang 透传、无 lang 为 null", () => {
  const withLang = parseMarkdownBlocks("```ts\nconst a = 1\n```");
  assert.equal(withLang[0].lang, "ts");
  const bare = parseMarkdownBlocks("```\nplain\n```");
  assert.equal(bare[0].lang, null);
  assert.equal(bare[0].code, "plain");
});

test("fence 后接普通段落不误吞：多个 fence 交替也各归各位", () => {
  const blocks = parseMarkdownBlocks("```\na\n```\n中间段落\n```js\nb\n```\n- 收尾列表");
  assert.deepEqual(blocks.map((b) => b.type), ["code", "p", "code", "ul"]);
  assert.equal(blocks[0].code, "a");
  assert.equal(segText(blocks[1].segs), "中间段落");
  assert.equal(blocks[2].lang, "js");
  assert.equal(blocks[2].code, "b");
});

test("空 fence 成空 code 块（不塌缩、不报错）", () => {
  const blocks = parseMarkdownBlocks("```\n```");
  assert.deepEqual(blocks, [{ type: "code", lang: null, code: "" }]);
  const emptyWithLang = parseMarkdownBlocks("```sh\n```");
  assert.deepEqual(emptyWithLang, [{ type: "code", lang: "sh", code: "" }]);
});

test("既有块型逐字回归：标题/引用/分隔线/列表/段落与旧实现同构", () => {
  const blocks = parseMarkdownBlocks("# 标题\n> ⚠ 警示\n---\n- 甲\n- 乙\n正文 `code` **加粗**");
  assert.deepEqual(blocks.map((b) => b.type), ["h", "quote", "hr", "ul", "p"]);
  assert.equal(blocks[0].level, 1);
  assert.equal(blocks[1].variant, "warn");
  assert.deepEqual(
    blocks[4].segs,
    [
      { t: "text", s: "正文 " },
      { t: "code", s: "code" },
      { t: "text", s: " " },
      { t: "strong", s: "加粗" },
    ],
  );
  // Codex R2 原例：函数语法零误伤（**kwargs 逐字留在文本段，相邻 strong 仍成对解析）。
  const r2 = parseMarkdownBlocks("def f(**kwargs)：**重要**");
  assert.equal(segText(r2[0].segs), "def f(**kwargs)：重要");
  assert.ok(r2[0].segs.some((s) => s.t === "text" && s.s.includes("**kwargs")));
  assert.deepEqual(r2[0].segs.filter((s) => s.t === "strong"), [{ t: "strong", s: "重要" }]);
});

test("组件结构约束：零 v-html，code 块走 pre>code 插值（转义由 Vue 保证）", () => {
  const sfc = readFileSync(SFC_PATH, "utf8");
  assert.ok(!/v-html\s*=/.test(sfc), "MarkdownLite 绝不允许 v-html 指令");
  assert.ok(sfc.includes('<pre v-else-if="blk.type === \'code\'"'));
  assert.ok(sfc.includes("{{ blk.code }}"), "code 内容必须走插值转义");
  assert.ok(sfc.includes("{{ blk.lang }}"), "lang 标签必须走插值转义");
  // 无过渡/动画——流式重渲染零闪烁。
  assert.ok(!/transition|animation/.test(sfc), "不得引入过渡/动画");
});
