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
  constructor(status, detail, { timeout = false } = {}) {
    super(detail);
    this.status = status;
    this.detail = detail;
    // 超时分型（批次五 C1）：超时（后端挂起/繁忙）≠连接失败（后端没起），
    // 两者 status 均为 0，靠此标志区分——文案与恢复动作不同。
    this.timeout = timeout;
  }
}

// 常规内网 API 毫秒级响应：20s 无响应=后端挂起而非慢。慢操作（内网 LLM 对话
// 「一两分钟」诚实口径）由调用方显式传更长 timeoutMs，绝不放宽默认值。
export const DEFAULT_TIMEOUT_MS = 20_000;

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

export async function request(path, { method = "GET", json, formData, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const init = { method, headers: {} };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  }
  if (formData !== undefined) {
    init.body = formData; // multipart：浏览器自带 boundary，不手写 Content-Type
  }

  // 硬超时（批次五 C1，craft state-coverage「spinner 绝不无限跑」的底座保证）：
  // fetch 对「连接已建立但后端挂起不响应」会无限期悬挂——所有 loading ref 与
  // liveFeed 轮询链都依赖本 promise 落地。AbortController 让挂起请求必落地。
  const controller = new AbortController();
  init.signal = controller.signal;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let resp;
  try {
    resp = await fetch(path, init);
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new ApiError(
        0,
        `请求超时（${Math.round(timeoutMs / 1000)} 秒无响应）——后端可能繁忙或已停止，请稍后重试`,
        { timeout: true },
      );
    }
    throw new ApiError(0, `无法连接后端服务（${err.message}）——请确认后端已启动`);
  } finally {
    clearTimeout(timer);
  }
  if (!resp.ok) {
    // 会话过期中途兜底（ADR-0019 D8）：任意接口 401 → 广播事件，App 重新亮
    // 登录门。登录/探测接口自身除外——它们的 401 是登录门的正常输入。
    if (
      resp.status === 401 &&
      path !== "/api/auth/login" &&
      path !== "/api/auth/me"
    ) {
      window.dispatchEvent(new CustomEvent("flai:unauthorized"));
    }
    throw new ApiError(resp.status, await parseDetail(resp));
  }
  return resp.json();
}
