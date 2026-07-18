import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { projectEvidencePreview } from "../src/stores/taskEvidenceCore.js";

test("truncated JSON never becomes an empty successful evidence projection", () => {
  assert.deepEqual(
    projectEvidencePreview({
      isText: true,
      truncated: true,
      text: '{"findings":[{"title":"partial',
    }),
    {
      findings: [],
      refusals: [],
      truncated: true,
      error: "",
    },
  );
});

test("invalid or unavailable JSON becomes an explicit unavailable projection", () => {
  assert.equal(projectEvidencePreview({ isText: true, truncated: false, text: "{" }).error, "invalid_json");
  assert.equal(projectEvidencePreview({ isText: false, truncated: false, text: null }).error, "preview_unavailable");
});

test("valid findings and refusals remain exact", () => {
  const findings = [{ title: "核验项", evidence: [] }];
  const refusals = [{ reason: "超出范围" }];
  assert.deepEqual(
    projectEvidencePreview({
      isText: true,
      truncated: false,
      text: JSON.stringify({ findings, refusals }),
    }),
    { findings, refusals, truncated: false, error: "" },
  );
});

test("Guide, Workbench, and Delivery surfaces expose evidence projection issues", () => {
  for (const relative of [
    "../src/views/GuidePage.vue",
    "../src/views/WorkbenchSession.vue",
    "../src/components/DeliveryCard.vue",
  ]) {
    const source = readFileSync(new URL(relative, import.meta.url), "utf8");
    assert.match(source, /taskEvidenceIssue/);
  }
});

test("Workbench never hides classification withholding behind a preview issue", () => {
  const source = readFileSync(
    new URL("../src/views/WorkbenchSession.vue", import.meta.url),
    "utf8",
  );
  const functionStart = source.indexOf("function doneEvidenceText(a)");
  const functionEnd = source.indexOf("\n}\n", functionStart);
  const body = source.slice(functionStart, functionEnd);

  assert.match(body, /const withheld = taskEvidenceWithheld\(t\.id\) === true;/);
  assert.match(
    body,
    /if \(issue\) return \{ text: withheld \? `\$\{issue\.text\}·另有密级隐藏项` : issue\.text, unverified: 1 \};/,
  );
});
