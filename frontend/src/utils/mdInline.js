// Conservative inline Markdown segmentation for trusted text rendering.
// Only paired `code` and **strong** markers become element descriptors. Unpaired
// markers remain literal text, so code such as `def f(**kwargs)` and `2 ** 3`
// is never silently rewritten. MarkdownLite renders every segment as a Vue text
// node; this helper never creates HTML strings.
export const INLINE_RE = /(`([^`\n]+)`)|((?<![A-Za-z0-9_([{\\*])\*\*(?=\S)([^*\n]*?\S)\*\*)/;

export function inlineSegs(value) {
  const segs = [];
  let rest = value.trimEnd();
  while (rest) {
    const match = INLINE_RE.exec(rest);
    if (!match) {
      segs.push({ t: "text", s: rest });
      break;
    }
    if (match.index > 0) segs.push({ t: "text", s: rest.slice(0, match.index) });
    if (match[1]) segs.push({ t: "code", s: match[2] });
    else segs.push({ t: "strong", s: match[4] });
    rest = rest.slice(match.index + match[0].length);
  }
  return segs;
}
