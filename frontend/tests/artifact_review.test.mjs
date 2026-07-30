// frontend/tests/artifact_review.test.mjs — 人工审阅顺序与渐进披露纯函数核。
import test from "node:test";
import assert from "node:assert/strict";
import {
  orderArtifactsForReview,
  shouldCollapseArtifactForReview,
} from "../src/utils/artifactReview.js";

test("orderArtifactsForReview: 人读报告优先，结构化数据与日志随后，组内保持原顺序", () => {
  const artifacts = [
    { fileId: "json", filename: "result.json" },
    { fileId: "md", filename: "report.md" },
    { fileId: "log", filename: "solver.log" },
    { fileId: "pdf", filename: "appendix.pdf" },
    { fileId: "yaml", filename: "manifest.yaml" },
    { fileId: "txt", filename: "readme.txt" },
  ];

  assert.deepEqual(
    orderArtifactsForReview(artifacts).map((item) => item.fileId),
    ["md", "pdf", "txt", "json", "yaml", "log"],
  );
  // 不原地改写调用方数组，避免 Vue 轮询快照被展示层排序污染。
  assert.deepEqual(artifacts.map((item) => item.fileId), ["json", "md", "log", "pdf", "yaml", "txt"]);
});

test("orderArtifactsForReview: 缺文件名或未知格式诚实降级到末尾", () => {
  const artifacts = [
    { fileId: "unknown", filename: "artifact.bin" },
    { fileId: "missing" },
    { fileId: "csv", filename: "cases.csv" },
  ];

  assert.deepEqual(
    orderArtifactsForReview(artifacts).map((item) => item.fileId),
    ["csv", "unknown", "missing"],
  );
});

test("shouldCollapseArtifactForReview: 有人读报告时默认收纳原始数据与日志，但不收纳报告", () => {
  const reviewSet = [
    { filename: "result.json" },
    { filename: "report.md" },
    { filename: "trace.log" },
  ];

  assert.equal(shouldCollapseArtifactForReview(reviewSet[0], reviewSet), true);
  assert.equal(shouldCollapseArtifactForReview(reviewSet[1], reviewSet), false);
  assert.equal(shouldCollapseArtifactForReview(reviewSet[2], reviewSet), true);
});

test("shouldCollapseArtifactForReview: 没有人读报告时保持首份原始产物展开，避免把唯一证据藏起", () => {
  const reviewSet = [
    { filename: "result.json" },
    { filename: "trace.log" },
  ];

  assert.equal(shouldCollapseArtifactForReview(reviewSet[0], reviewSet), false);
  assert.equal(shouldCollapseArtifactForReview(reviewSet[1], reviewSet), true);
});

test("shouldCollapseArtifactForReview: 加载失败的首项仍展开显示错误", () => {
  const reviewSet = [
    { fileId: "broken", filename: "broken.md", error: "下载失败" },
    { fileId: "json", filename: "result.json" },
  ];

  assert.equal(shouldCollapseArtifactForReview(reviewSet[0], reviewSet), false);
});
