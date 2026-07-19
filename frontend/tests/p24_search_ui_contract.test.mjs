import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("QuickSwitcher uses four independent server scopes without false-empty debounce", () => {
  const source = read("../src/components/QuickSwitcher.vue");
  for (const scope of ["conversation", "message", "task", "artifact"]) {
    assert.match(source, new RegExp(`key: ["']${scope}["']`));
  }
  assert.match(source, /setTimeout\(\(\) => \{[\s\S]*?runServerSearch\(searchQuery, seq\)[\s\S]*?\}, 220\)/);
  assert.match(source, /resetServerSearch\(\{ pending: true \}\)/);
  assert.match(source, /Promise\.all\(SERVER_SCOPE_META\.map\(oneScope\)\)/);
  assert.match(source, /seq !== searchSeq \|\| normalizedQuery\.value !== searchQuery/);
  assert.match(source, /reconcileSearchSelection\(keys, selectedKey\.value\)/);
  assert.match(source, /此来源暂不可用/);
  assert.match(source, /此来源没有匹配结果/);
  assert.match(source, /group\.hasMore/);
  assert.match(source, /filteredAgents/);
  assert.match(source, /localDisplayNameTaskMatches/);
  assert.match(source, /mergeSearchItems\(\s*scopeStates\.task\.items/);
  assert.doesNotMatch(source, /router\.push\(`\/workbench\/\$\{item\.id\}`\)/);
});

test("message and artifact anchors focus exact stable IDs and warn on stale targets", () => {
  const guide = read("../src/views/GuidePage.vue");
  const detail = read("../src/views/TaskDetail.vue");

  assert.match(guide, /:data-message-id="m\.message_id \|\| undefined"/);
  assert.match(guide, /route\.query\.m/);
  assert.match(guide, /element\.dataset\.messageId === targetId/);
  assert.match(guide, /消息定位失效/);
  assert.match(guide, /target\.focus\(\{ preventScroll: true \}\)/);

  assert.match(detail, /:data-file-id="a\.fileId"/);
  assert.match(detail, /route\.query\.file/);
  assert.match(detail, /outputIds\.includes\(fileId\)/);
  assert.match(detail, /artifactsExpanded\.value = true/);
  assert.match(detail, /artifacts\.value\[artifactIndex\]\.collapsed = false/);
  assert.match(detail, /target\.querySelector\("\.artifact-toggle"\)/);
  assert.match(detail, /产物定位失效/);
  const anchorStart = detail.indexOf("async function focusRequestedArtifact");
  const anchorEnd = detail.indexOf("\nwatch(", anchorStart);
  assert.doesNotMatch(detail.slice(anchorStart, anchorEnd), /downloadUrl|fetchFilePreview/);
});
