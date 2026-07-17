import { request } from "./client";

export const uploadFile = (file, taskId) => {
  const formData = new FormData();
  formData.append("file", file);
  if (taskId) formData.append("task_id", taskId);
  // 上传给宽限（批次五 C1）：附件体积可到 MB 级，内网慢链路 20s 偏紧，60s 兜底。
  return request("/api/files/upload", { method: "POST", formData, timeoutMs: 60_000 });
};

// 下载走浏览器原生导航（FileResponse 附件头由后端给），不经 fetch。
export const downloadUrl = (fileId) => `/api/files/${fileId}/download`;

function parseContentDispositionName(cd) {
  // 优先 RFC 5987 的 filename*=UTF-8''...，回退 filename="..."。
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      /* 退回普通 filename */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1].trim() : "";
}

const TEXT_EXTS = ["md", "markdown", "txt", "text", "json", "csv", "log", "yaml", "yml"];

// 取输出文件的文件名 + 内容（供签发页内联查看要签的产物）。文本类读为字符串，
// 二进制类只给文件名/大小（仍可下载）。同源请求，Content-Disposition 头可读。
export async function fetchOutputFile(fileId) {
  const resp = await fetch(downloadUrl(fileId));
  if (!resp.ok) throw new Error(`下载失败（${resp.status}）`);
  const filename = parseContentDispositionName(resp.headers.get("content-disposition") || "") || fileId.slice(0, 8);
  const blob = await resp.blob();
  const ext = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
  const isText = TEXT_EXTS.includes(ext);
  const text = isText ? await blob.text() : null;
  return { fileId, filename, ext, size: blob.size, isText, text };
}
