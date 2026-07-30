// 人工审阅的产物展示顺序：先给人读报告，再给表格/结构化数据，最后给日志与
// 其它附件。这里只改变展示，不改变 task.output_file_ids、下载地址或持久数据。

const REVIEW_DOCUMENT_EXTS = new Set([
  "md",
  "markdown",
  "txt",
  "text",
  "pdf",
  "doc",
  "docx",
  "rtf",
  "html",
  "htm",
]);
const TABLE_EXTS = new Set(["csv", "xls", "xlsx", "ods"]);
const STRUCTURED_DATA_EXTS = new Set(["json", "yaml", "yml", "xml"]);
const TRACE_EXTS = new Set(["log", "trace"]);

function artifactExtension(artifact) {
  if (typeof artifact?.ext === "string" && artifact.ext.trim()) {
    return artifact.ext.trim().toLowerCase();
  }
  const filename = typeof artifact?.filename === "string" ? artifact.filename.trim() : "";
  const dot = filename.lastIndexOf(".");
  if (dot < 0 || dot === filename.length - 1) return "";
  return filename.slice(dot + 1).toLowerCase();
}
function reviewRank(artifact) {
  const ext = artifactExtension(artifact);
  if (REVIEW_DOCUMENT_EXTS.has(ext)) return 0;
  if (TABLE_EXTS.has(ext)) return 1;
  if (STRUCTURED_DATA_EXTS.has(ext)) return 2;
  if (TRACE_EXTS.has(ext)) return 3;
  return 4;
}

export function orderArtifactsForReview(artifacts) {
  const list = Array.isArray(artifacts) ? artifacts : [];
  return list
    .map((artifact, index) => ({ artifact, index, rank: reviewRank(artifact) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ artifact }) => artifact);
}

function sameArtifact(left, right) {
  if (left === right) return true;
  if (left?.fileId && right?.fileId) return left.fileId === right.fileId;
  return Boolean(left?.filename && right?.filename && left.filename === right.filename);
}

export function shouldCollapseArtifactForReview(artifact, artifacts) {
  if (artifact?.error) return false;
  if (reviewRank(artifact) === 0) return false;

  const ordered = orderArtifactsForReview(artifacts);
  const hasReviewDocument = ordered.some((item) => reviewRank(item) === 0);
  if (hasReviewDocument) return true;

  // 若任务只有机器可读产物，至少把审阅顺序中的第一份展开，避免渐进披露把
  // 唯一证据全部藏起；其余原始数据/日志再收纳。
  return ordered.length > 0 && sameArtifact(ordered[0], artifact) !== true;
}
