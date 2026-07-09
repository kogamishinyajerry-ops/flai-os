import { request } from "./client";

export const uploadFile = (file, taskId) => {
  const formData = new FormData();
  formData.append("file", file);
  if (taskId) formData.append("task_id", taskId);
  return request("/api/files/upload", { method: "POST", formData });
};

// 下载走浏览器原生导航（FileResponse 附件头由后端给），不经 fetch。
export const downloadUrl = (fileId) => `/api/files/${fileId}/download`;
