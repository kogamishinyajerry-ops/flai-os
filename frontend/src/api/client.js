/**
 * API 客户端底座：所有 HTTP 调用的唯一出口（任务书 §14.3：API 调用集中 src/api）。
 *
 * 约定：
 * - 成功（2xx）返回解析后的 JSON；
 * - 失败抛 ApiError（携带 status 与后端 detail 原文——后端 detail 是给人看的
 *   中文如实描述，页面直接展示，不二次翻译不粉饰）；
 * - 网络层失败（后端没起）抛 ApiError(status=0)。
 */

import { createNdjsonParser } from "../utils/ndjsonStream.js";

export class ApiError extends Error {
  constructor(status, detail, { timeout = false, retryable, persisted } = {}) {
    super(detail);
    this.status = status;
    this.detail = detail;
    // 超时分型（批次五 C1）：超时（后端挂起/繁忙）≠连接失败（后端没起），
    // 两者 status 均为 0，靠此标志区分——文案与恢复动作不同。
    this.timeout = timeout;
    if (retryable !== undefined) this.retryable = retryable;
    if (persisted !== undefined) this.persisted = persisted;
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

  const timeoutError = () =>
    new ApiError(
      0,
      `请求超时（${Math.round(timeoutMs / 1000)} 秒无响应）——后端可能繁忙或已停止，请稍后重试`,
      { timeout: true },
    );

  // 整个 请求→响应头→响应体 都在同一 abort 生命周期内（Codex R0 审 P2）：
  // 服务端发完响应头后 body 卡死同样会无限悬挂——timer 必须活到 body 读完，
  // 不能在 fetch() 返回响应头时就清掉。
  try {
    let resp;
    try {
      resp = await fetch(path, init);
    } catch (err) {
      if (err && err.name === "AbortError") throw timeoutError();
      throw new ApiError(0, `无法连接后端服务（${err.message}）——请确认后端已启动`);
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
      // parseDetail 内部自吞 json 异常（含 abort）回退 `HTTP <status>`——状态码
      // 已知即如实报状态码，不折成超时分型。
      throw new ApiError(resp.status, await parseDetail(resp));
    }
    try {
      return await resp.json();
    } catch (err) {
      if (err && err.name === "AbortError") throw timeoutError();
      throw err; // 非 abort 的解析错误保持原语义外抛（后端契约恒为 JSON）
    }
  } finally {
    clearTimeout(timer);
  }
}

/**
 * 用 fetch POST 消费服务端 NDJSON 事件流。
 *
 * 这层只处理真实网络分片：收到多少 delta 就向上交多少，不把整包 JSON
 * 拆成逐字动画。总超时覆盖响应头与完整流体，避免连接建立后永久悬挂。
 */
// 后端不可达人话化（Phase B B1，仅流式路径）：proxy/网关裸返 500/502/503 时
// detail 常为空或纯状态码（「HTTP 500」），对用户零信息量——改译人话；带真实
// detail 原文的响应保持如实直出（「不二次翻译不粉饰」约定不变）。status 与
// ApiError 分型语义不动，只换文案。
function humanizeUnreachableDetail(status, detail) {
  if (![0, 500, 502, 503].includes(status)) return detail;
  const bare = !detail || /^HTTP\s*\d{3}$/.test(String(detail).trim());
  return bare ? "后端服务不可达，请联系管理员" : detail;
}

export async function streamRequest(
  path,
  {
    method = "POST",
    json,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    onEvent = () => {},
    // 可选外部中止信号（流式停止钮底座）：调用方 abort 时联动内部 controller，
    // 与 timeoutMs 硬超时共用同一 abort 生命周期——超时语义不变。外部中止与
    // 超时在本层同样落地为 AbortError（超时分型），是否用户主动停止由调用方
    // 用自己的标记区分（见 GuidePage 停止钮），本层不新增失败分型。
    signal,
  } = {},
) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", abortFromCaller, { once: true });
  }
  const init = {
    method,
    headers: { Accept: "application/x-ndjson" },
    signal: controller.signal,
  };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  }

  const timeoutError = () =>
    new ApiError(
      0,
      `流式请求超时（${Math.round(timeoutMs / 1000)} 秒）——保存状态未知，请刷新会话核对`,
      { timeout: true },
    );

  try {
    let resp;
    try {
      resp = await fetch(path, init);
    } catch (err) {
      if (err && err.name === "AbortError") throw timeoutError();
      throw new ApiError(
        0,
        `流式连接失败（${err.message}）——保存状态未知，请刷新会话核对`,
      );
    }

    if (!resp.ok) {
      if (
        resp.status === 401 &&
        path !== "/api/auth/login" &&
        path !== "/api/auth/me"
      ) {
        window.dispatchEvent(new CustomEvent("flai:unauthorized"));
      }
      throw new ApiError(
        resp.status,
        humanizeUnreachableDetail(resp.status, await parseDetail(resp)),
      );
    }
    if (!resp.body || typeof resp.body.getReader !== "function") {
      throw new ApiError(
        0,
        "后端未返回可读取的流式响应——保存状态未知，请刷新会话核对",
      );
    }

    const parser = createNdjsonParser(onEvent);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        parser.push(decoder.decode(value, { stream: true }));
      }
      parser.push(decoder.decode());
      parser.finish();
    } catch (err) {
      if (err && err.name === "AbortError") throw timeoutError();
      if (err instanceof ApiError) throw err;
      throw new ApiError(
        0,
        `${err.message || "流式连接中断"}——保存状态未知，请刷新会话核对`,
      );
    } finally {
      reader.releaseLock();
    }
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", abortFromCaller);
  }
}

// 结构化 detail 解包（批八 Codex R1/R2）：FastAPI object 型 detail 在 parseDetail
// 里被整体 JSON.stringify——需要结构化清单（summon_errors/batch_errors/team_errors）
// 的调用方用本函数解回；非 JSON / 无 detail 键则原样返回，绝不吞原文。
export function unwrapDetail(errDetail) {
  if (typeof errDetail === "string" && errDetail.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(errDetail);
      return (parsed && parsed.detail) || parsed;
    } catch {
      /* 非 JSON：原样返回 */
    }
  }
  return errDetail;
}
