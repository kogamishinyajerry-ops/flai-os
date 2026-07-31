// frontend/src/utils/markdownLite.js — MarkdownLite 的纯函数解析核（从 SFC 抽出，
// 组件对外 props 不变；抽出只为可单测）。按行 markdown → 结构块：
// 标题/引用/分隔线/无序列表/段落 + 围栏代码块（```lang … ```）。
// 流式安全：未闭合 fence（流式中途）整段按纯文本兜底——opener 行当普通行重新走
// 常规解析，后续普通段落绝不误吞进 code 块；每次调用纯函数式全量重算，无状态。
// 所有文本经 Vue 插值转义，此模块绝不产出 HTML 字符串。

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

export function inlineSegs(s) {
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

// 引用块变体：🚨=截断危险（红），⚠=草案警示（amber），其余=普通引用。
export function quoteVariant(s) {
  if (s.includes("🚨")) return "danger";
  if (s.includes("⚠")) return "warn";
  return "plain";
}

const FENCE_OPEN_RE = /^```(.*)$/;

// 极简、按行的 markdown → 结构块。fence 处理：opener 行匹配后向前找独立成行的
// 闭 fence（```）——找到则其间行逐字成 code 块（不做行内解析，组件插值转义）；
// 找不到（流式中途未闭合）则 opener 行落回常规行解析，与旧行为逐字一致。
export function parseMarkdownBlocks(text) {
  const lines = String(text || "").split(/\r?\n/);
  const out = [];
  let list = null;
  const flushList = () => {
    if (list) {
      out.push({ type: "ul", items: list });
      list = null;
    }
  };
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trimEnd();
    const fence = FENCE_OPEN_RE.exec(line);
    if (fence) {
      let close = -1;
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].trimEnd() === "```") {
          close = j;
          break;
        }
      }
      if (close !== -1) {
        flushList();
        const lang = fence[1].trim();
        out.push({
          type: "code",
          lang: lang || null,
          code: lines.slice(i + 1, close).map((l) => l.trimEnd()).join("\n"),
        });
        i = close;
        continue;
      }
      // 未闭合：兜底为纯文本，opener 行继续走下方常规解析。
    }
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
}
