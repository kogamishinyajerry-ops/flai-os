// 会话侧栏标题的数据面（E-4 会话标题人话化），三层诚实回退、零编造：
//   1. 列表 API 投影 first_user_message（服务端截断 120 字，刷新不失效）；
//   2. 本会话内存缓存（GuidePage 拉过全量/刚发的消息，即时性补充）；
//   3. 「与 X 的对话」兜底文案。
// 模块级 Map 跨组件共享（App 侧栏读、GuidePage 写）；标题纯函数 conversationTitle
// 同时被 App.vue 左栏与 QuickSwitcher 消费（同一口径）。
import { ref } from "vue";

const firstUserContentById = new Map();

// 版本号：Map 本身非响应式，侧栏标题据此建立渲染依赖——record 后 bump，
// 正在渲染的 convoTitle 才会重算（否则缓存晚于列表渲染到位，标题停在回退文案）。
export const conversationTitlesVersion = ref(0);

// GuidePage 拿到服务端权威会话后调用：只记首条非空用户消息。
export function recordConversationFirstUserContent(id, messages) {
  if (!id || !Array.isArray(messages)) return;
  const first = messages.find(
    (m) => m && m.role === "user" && typeof m.content === "string" && m.content.trim(),
  );
  if (first) {
    firstUserContentById.set(id, first.content.trim());
    conversationTitlesVersion.value += 1;
  }
}

// 侧栏标题统一 18 字截断（超出加 …）。
function truncateTitle(content) {
  return content.length > 18 ? `${content.slice(0, 18)}…` : content;
}

// 侧栏标题查询：命中返回 18 字截断（超出加 …）；未命中返回空串由调用方回退。
export function cachedConversationTitle(id) {
  const content = firstUserContentById.get(id);
  if (!content) return "";
  return truncateTitle(content);
}

// 侧栏标题 SSOT（纯函数，node --test 直接测）：recommendation 裁决优先，
// 其后三层回退=列表投影 → 内存缓存 → 「与 X 的对话」，任何一层缺失都诚实下落。
export function conversationTitle(c) {
  if (!c) return "与 你 的对话";
  const r = c.recommendation;
  if (r && r.decision === "orchestrate" && r.goal) return r.goal;
  if (r && r.decision === "refuse" && r.reason) return "（未接住）" + r.reason;
  // 1. 列表投影：服务端已截断 120 字，这里再截 18 字展示。
  const preview =
    typeof c.first_user_message === "string" ? c.first_user_message.trim() : "";
  if (preview) return truncateTitle(preview);
  // 2. 内存缓存：会话内刚发的消息列表尚未刷新时保持即时性。
  const cached = cachedConversationTitle(c.id);
  if (cached) return cached;
  // 3. 兜底文案。
  return `与 ${c.created_by || "你"} 的对话`;
}
