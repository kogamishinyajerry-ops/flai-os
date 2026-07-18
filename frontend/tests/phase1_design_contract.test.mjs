// Phase 1 trusted-design cleanup: source-level contracts for shared design tokens
// and keyboard/reduced-motion affordances. These checks intentionally stay
// narrow so they guard the audited regressions without freezing component layout.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appShell = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
const agentPortal = readFileSync(
  new URL("../src/views/AgentPortal.vue", import.meta.url),
  "utf8",
);
const evidenceList = readFileSync(
  new URL("../src/components/EvidenceList.vue", import.meta.url),
  "utf8",
);
const quickSwitcher = readFileSync(
  new URL("../src/components/QuickSwitcher.vue", import.meta.url),
  "utf8",
);

test("Phase 1 surfaces and monospace text use tokens defined by App.vue", () => {
  for (const token of ["surface-raised", "mono", "paper-rail"]) {
    assert.match(appShell, new RegExp(`--${token}\\s*:`));
  }
  assert.doesNotMatch(agentPortal, /var\(--surface\)/);
  assert.match(
    agentPortal,
    /\.team-card\s*\{[\s\S]*?background:\s*var\(--surface-raised\);[\s\S]*?\}/,
  );

  assert.doesNotMatch(evidenceList, /var\(--(?:font-mono|surface-sunken)\b/);
  assert.match(
    evidenceList,
    /\.ev-quote\.is-code\s*\{[\s\S]*?font-family:\s*var\(--mono\);[\s\S]*?background:\s*var\(--paper-rail\);[\s\S]*?\}/,
  );
  assert.match(
    evidenceList,
    /\.ev-withheld\s*\{[\s\S]*?background:\s*var\(--paper-rail\);[\s\S]*?\}/,
  );
});

test("QuickSwitcher exposes a visible token-based keyboard focus indicator", () => {
  assert.match(appShell, /--focus-ring-clay\s*:/);
  assert.match(appShell, /--radius-xs\s*:/);
  assert.match(
    quickSwitcher,
    /\.qs-input:focus-visible\s*\{[\s\S]*?outline:\s*2px solid var\(--focus-ring-clay\);[\s\S]*?outline-offset:\s*2px;[\s\S]*?border-radius:\s*var\(--radius-xs\);[\s\S]*?\}/,
  );
});

test("the touched Agent card hover lift remains disabled for reduced motion", () => {
  assert.match(
    agentPortal,
    /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.agent-card:hover\s*\{\s*transform:\s*none;\s*\}\s*\}/,
  );
});
