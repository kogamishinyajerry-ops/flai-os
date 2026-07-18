import { request } from "./client.js";

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

// 签发面只取后端有界、已过密级与完整性闸的预览 JSON。真实 blob 下载仅由上方
// downloadUrl 对应的用户显式点击触发；页面加载/展开绝不暗中拉完整二进制。
export async function fetchFilePreview(fileId) {
  const body = await request(`/api/files/${fileId}/preview`);
  return {
    fileId: body.file_id,
    filename: body.filename,
    ext: body.extension,
    size: body.size_bytes,
    previewKind: body.preview_kind,
    isText: body.is_text,
    truncated: body.truncated,
    text: body.text,
  };
}
