import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const shellContextSource = readFileSync(
  new URL("../src/components/ShellContextPanel.vue", import.meta.url),
  "utf8",
);

test("Agent picker keeps a focusable dialog fallback and exposes Escape dismissal", () => {
  assert.match(shellContextSource, /ref="panelEl"/);
  assert.match(shellContextSource, /:tabindex="isPicker \? -1 : undefined"/);
  assert.match(
    shellContextSource,
    /\(searchEl\.value \|\| panelEl\.value\)\?\.focus\(\)/,
  );
  assert.match(shellContextSource, /@keydown="onPanelKeydown"/);
  assert.match(shellContextSource, /const emit = defineEmits\(\[[\s\S]*?"request-close"[\s\S]*?\]\)/);
  assert.match(
    shellContextSource,
    /function onPanelKeydown\(event\) \{[\s\S]*?!isPicker\.value \|\| event\.key !== "Escape"[\s\S]*?event\.preventDefault\(\);[\s\S]*?event\.stopPropagation\(\);[\s\S]*?emit\("request-close"\);[\s\S]*?\}/,
  );
});

test("work-type facets expose one labelled pressed-button group", () => {
  assert.match(
    shellContextSource,
    /<div class="context-facets" role="group" aria-label="按工作类型筛选">/,
  );
  assert.match(shellContextSource, /:aria-pressed="workType === 'all'"/);
  assert.match(shellContextSource, /:aria-pressed="workType === item\.id"/);
});

test("Agent option accessible names include relation and governance boundaries", () => {
  assert.match(shellContextSource, /:aria-label="agentAriaLabel\(agent\)"/);
  assert.match(
    shellContextSource,
    /function agentAriaLabel\(agent\) \{[\s\S]*?agent\.detail[\s\S]*?pickerGateText\(agent\)[\s\S]*?\}/,
  );
  assert.match(shellContextSource, /agent\.referenceState === "unresolved"/);
  assert.match(shellContextSource, /项引用待核/);
  assert.match(shellContextSource, /clearanceState\(agent\.clearance, agent\.clearanceSource\)/);
  assert.match(shellContextSource, /agent\.reviewRequired === true[\s\S]*?需人工复核/);
  assert.match(shellContextSource, /agent\.reviewRequired === null[\s\S]*?复核待核/);
  assert.match(shellContextSource, /agent\.evidenceRequired === true[\s\S]*?需可核依据/);
  assert.match(shellContextSource, /agent\.evidenceRequired === null[\s\S]*?依据待核/);
});

test("Agent registry loading motion stops for reduced-motion users", () => {
  assert.match(shellContextSource, /<el-icon class="is-loading"/);
  assert.match(
    shellContextSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.context-loading \.is-loading \{ animation: none; \}/,
  );
});
