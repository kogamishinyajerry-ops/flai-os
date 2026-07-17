import { request } from "./client";

export const uploadFile = (file, taskId) => {
  const formData = new FormData();
  formData.append("file", file);
  if (taskId) formData.append("task_id", taskId);
  // 上传宽限（批次五 C1，3-lens 双镜 P2 校准）：后端上限 FLAI_MAX_UPLOAD_MB
  // 默认 100MB（backend/app/api/files.py），60s 隐含要求 ≥1.7MB/s——慢链路
  // （VPN/拥塞 WiFi）传接近上限的附件会被硬掐成「从慢但能传完→直接判超时」。
  // 300s 对应 ~0.33MB/s 地板，覆盖内网最差链路；上限外的真挂起仍会落地。
  return request("/api/files/upload", { method: "POST", formData, timeoutMs: 300_000 });
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
