import { request } from "./client";

// 知识引用回源（ADR-0029）：按检索事件里的 (scope_id, chunk_id) 取当前语料原文。
// chunk_id 含 `#`（f"{doc_id}#{i}"），必须走 URLSearchParams 编码——手拼模板串
// 会被浏览器当 URL fragment 截断，后端根本收不到。
export const readChunk = ({ scopeId, chunkId, source }) => {
  const params = new URLSearchParams({ scope_id: scopeId, chunk_id: chunkId });
  if (source) params.set("source", source);
  return request(`/api/knowledge/chunk?${params.toString()}`);
};
