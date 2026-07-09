/**
 * API 客户端底座：所有 HTTP 调用的唯一出口（任务书 §14.3：API 调用集中 src/api）。
 *
 * 约定：
 * - 成功（2xx）返回解析后的 JSON；
 * - 失败抛 ApiError（携带 status 与后端 detail 原文——后端 detail 是给人看的
 *   中文如实描述，页面直接展示，不二次翻译不粉饰）；
 * - 网络层失败（后端没起）抛 ApiError(status=0)。
 */

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function parseDetail(resp) {
  try {
    const body = await resp.json();
    if (typeof body.detail === "string") return body.detail;
    // FastAPI 422 的 detail 是数组：取字段级消息拼接
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d) => `${(d.loc || []).join(".")}: ${d.msg}`)
        .join("；");
    }
    return JSON.stringify(body);
  } catch {
    return `HTTP ${resp.status}`;
  }
}

export async function request(path, { method = "GET", json, formData } = {}) {
  const init = { method, headers: {} };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  }
  if (formData !== undefined) {
    init.body = formData; // multipart：浏览器自带 boundary，不手写 Content-Type
  }

  let resp;
  try {
    resp = await fetch(path, init);
  } catch (err) {
    throw new ApiError(0, `无法连接后端服务（${err.message}）——请确认后端已启动`);
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseDetail(resp));
  }
  return resp.json();
}
