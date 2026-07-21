// 会话身份单例（ADR-0019 D8）：登录态与当前用户的唯一前端来源。
// 取代 utils/identity.js 的 localStorage 自报称呼——身份从此来自服务端会话
// （GET /api/auth/me），前端只读不自造。记名字段（created_by/reviewer/…）
// 已全部服务端派生，前端不再随请求发送任何身份文本。

import { ref } from "vue";
import { request } from "../api/client";

// null = 未登录（或尚未探测）；{ username, display_name, role } = 已登录。
// role 原样保留服务端值，不在前端猜默认值；safe_auto outbox 用 username+role
// 检测跨标签页换号/换角色，任何缺失都 fail-closed，绝不把持久化意图当授权。
export const currentUser = ref(null);

// 单调序号防陈旧 /me 响应覆盖新结果（Codex R4 审 P1）：多标签页换号时可能有
// 多个 fetchMe 在飞，旧请求后到会把 currentUser 写回旧身份。只有最新一次的
// 响应允许落地。
let meSeq = 0;

// 启动探测：401 是「未登录」的正常答案，不是错误——吞掉并返回 false。
// 网络层失败（后端没起）同样返回 false，由登录门如实展示后端不可达。
export async function fetchMe() {
  const seq = ++meSeq;
  try {
    const me = await request("/api/auth/me");
    if (seq !== meSeq) return currentUser.value !== null; // 陈旧响应：不覆盖
    currentUser.value = me;
    return true;
  } catch {
    if (seq !== meSeq) return currentUser.value !== null; // 陈旧响应：不覆盖
    currentUser.value = null;
    return false;
  }
}

// 登录失败把 ApiError 原样抛给登录门展示（401 凭据错/429 节流，后端 detail 如实上屏）
export async function login(username, password) {
  // 身份转换先作废所有在途 /me；否则旧主体的迟到响应可能覆盖新 cookie 对应身份，
  // 使 safe_auto outbox 的 username+role 前置校验观察到错误 principal。
  const seq = ++meSeq;
  const loggedIn = await request("/api/auth/login", {
    method: "POST",
    json: { username, password },
  });
  if (seq !== meSeq) return;
  currentUser.value = loggedIn;
}

// 只在服务端确认吊销后才清本地态（Codex R1 审 P1）：若请求失败就清空并
// 「假装登出成功」，HttpOnly cookie 与会话行仍有效——重连后 reload 免密又登入，
// 用户却以为已登出。失败时如实抛出，让调用方保留登录态并提示重试。
export async function logout() {
  // 与 login 同理：请求发出前就作废在途 /me。失败时仍保留当前身份，但旧响应
  // 不得在 cookie 状态不明的窗口里重新宣告另一主体。
  const seq = ++meSeq;
  await request("/api/auth/logout", { method: "POST" });
  if (seq !== meSeq) return;
  currentUser.value = null;
}

export function displayName() {
  return currentUser.value ? currentUser.value.display_name : "";
}

export function authenticatedPrincipal() {
  const value = currentUser.value;
  if (
    !value ||
    typeof value.username !== "string" ||
    !value.username ||
    typeof value.role !== "string" ||
    !value.role
  ) {
    return null;
  }
  return { username: value.username, role: value.role };
}
