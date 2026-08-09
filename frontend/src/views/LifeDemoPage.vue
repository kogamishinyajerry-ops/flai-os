<template>
  <!--
    本体论教学 demo 启动页(/demo)。
    路径 A:未选场景 → 渲染 LifeScenarioPicker,工程师三选一。
    路径 B:有效 s 且无 c → 创建一次 life_guide_agent 会话并把 s/c 写回 URL。
    路径 C:有效 s+c → 只冷读既有会话，支持刷新、后退和前进恢复。

    独立于主 GuidePage(工程任务入口),避免污染工程对话主线。
    demo 产出的 Skill Package 走 quarantine 隔离区,不进生产 Registry。
  -->
  <div class="life-demo">
    <!-- 顶栏:回到主对话 + 当前场景 -->
    <div v-if="currentScenario" class="life-demo__bar">
      <router-link to="/" class="life-demo__back">← 回主对话</router-link>
      <span class="life-demo__current">{{ currentScenario?.emoji }} {{ currentScenario?.title }}</span>
      <button type="button" class="life-demo__reset" @click="reset">换个场景</button>
    </div>

    <!-- 路径 A:场景选择 -->
    <LifeScenarioPicker
      v-if="!starting && !startError && !conversation"
      @select="onSelect"
    />

    <!-- 路径 B/C:创建、恢复或对话 -->
    <section v-if="starting || startError || conversation" class="life-demo__session">
      <div v-if="starting" class="life-demo__hint">正在读取会话...</div>
      <div v-else-if="startError" class="life-demo__error">
        <strong>会话不可用</strong> — {{ startError }}
        <button v-if="route.query.c" type="button" @click="reloadCurrent">
          重新读取
        </button>
        <button type="button" @click="reset">返回场景选择</button>
      </div>
      <div v-else-if="conversation" class="life-demo__thread">
        <!-- 起手提示(对话还没开始) -->
        <div v-if="messages.length === 0" class="life-demo__opening">
          <p>
            <b>{{ currentScenario?.emoji }} {{ currentScenario?.title }}</b
            >·{{ currentScenario?.focus }}
          </p>
          <p class="life-demo__opening-hint">{{ openingHint }}</p>
        </div>

        <!-- 消息流：文字气泡；助手回复若带待审候选，气泡下方渲染草稿卡片 -->
        <template v-for="m in messages" :key="m.id">
          <div :class="['life-demo__bubble', m.role]">
            <div class="life-demo__bubble-role">{{ m.role === "user" ? "我" : "主持人" }}</div>
            <div class="life-demo__bubble-text">{{ m.content }}</div>
          </div>
          <LifeDraftCard
            v-if="m.role === 'assistant' && m.draftRecord"
            :key="m.draftRecord.id"
            :record="m.draftRecord"
            :conversation-id="conversation.id"
            @revise="focusComposer"
          />
          <p
            v-else-if="m.role === 'assistant' && m.draftRecordInvalid"
            class="life-demo__record-warning"
            role="status"
          >
            这条回复关联的草稿记录未通过契约校验，已隐藏草稿卡片；回复正文仍按原文保留。
          </p>
        </template>

        <!-- 输入框 -->
        <div class="life-demo__composer">
          <textarea
            ref="composerEl"
            v-model="draft"
            class="life-demo__textarea"
            :placeholder="composerPlaceholder"
            :disabled="sending || reconciliationRequired"
            rows="3"
            @keydown.enter.exact.prevent="send"
          ></textarea>
          <button
            type="button"
            class="life-demo__send"
            :disabled="!draft.trim() || sending || reconciliationRequired"
            @click="send"
          >
            {{ sending ? "发送中..." : "发送 ↵" }}
          </button>
        </div>
        <div v-if="sendError" class="life-demo__error-inline">
          {{ sendError }}
          <button
            v-if="reconciliationRequired"
            type="button"
            :disabled="sending"
            @click="reloadCurrent"
          >
            刷新会话核对
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LifeScenarioPicker from "../components/LifeScenarioPicker.vue";
import LifeDraftCard from "../components/LifeDraftCard.vue";
import {
  createConversation,
  getConversation,
  postMessage,
} from "../api/conversations";
import {
  assertLifePostMatchesSnapshot,
  isDefinitelyUncommittedLifePostError,
  normalizeLifeConversationIdentity,
  normalizeLifeConversationSnapshot,
  normalizeLifePostResponse,
  reconcileAmbiguousLifePostSnapshot,
  resolveLifeDemoRoute,
} from "../utils/lifeDraft.js";

// demo 场景元信息(与 LifeScenarioPicker.vue 的 scenarios 对齐)
const SCENARIOS = {
  cooking: {
    emoji: "🍳",
    title: "周末做红烧肉",
    focus: "单 Skill 完整闭环",
    opening: "讲讲这次红烧肉怎么做出来的吧——什么时候的事,中间有没有翻车?",
  },
  travel: {
    emoji: "🧳",
    title: "家庭旅行规划",
    focus: "多 Skill 组合成 Workflow",
    opening: "讲讲这次旅行——几个人、去哪、几天、最后怎么定下来的?",
  },
  renovation: {
    emoji: "🔨",
    title: "装修一间厨房",
    focus: "多角色长周期 Agent Package",
    opening: "讲讲这次装修——为什么会动这间厨房、找了谁来做、最后结果怎么样?",
  },
};

const route = useRoute();
const router = useRouter();

const scenarioId = ref(null);
const conversation = ref(null);
const starting = ref(false);
const startError = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const sendError = ref("");
const reconciliationRequired = ref(false);
const pendingAmbiguousRound = ref(null);
const composerEl = ref(null);
let routeEpoch = 0;

const currentScenario = computed(() =>
  scenarioId.value ? SCENARIOS[scenarioId.value] : null
);
const openingHint = computed(() => currentScenario.value?.opening || "");
const composerPlaceholder = computed(() =>
  messages.value.length === 0
    ? "先讲一段具体经历(时间/地点/人物/发生了什么)..."
    : "继续补充细节,或回答主持人的追问..."
);

function reset() {
  routeEpoch += 1;
  scenarioId.value = null;
  conversation.value = null;
  messages.value = [];
  draft.value = "";
  startError.value = "";
  sendError.value = "";
  reconciliationRequired.value = false;
  pendingAmbiguousRound.value = null;
  starting.value = false;
  router.replace({ path: "/demo" });
}

function errorText(err) {
  return err?.detail || err?.message || String(err);
}

async function synchronizeRoute() {
  const epoch = ++routeEpoch;
  const intent = resolveLifeDemoRoute(route.query, Object.keys(SCENARIOS));
  scenarioId.value = intent.scenarioId || null;
  conversation.value = null;
  messages.value = [];
  startError.value = "";
  sendError.value = "";
  reconciliationRequired.value = false;
  pendingAmbiguousRound.value = null;
  sending.value = false;

  if (intent.kind === "pick") {
    starting.value = false;
    return;
  }
  if (intent.kind === "invalid") {
    starting.value = false;
    startError.value = intent.reason;
    return;
  }

  starting.value = true;
  try {
    if (intent.kind === "load") {
      const raw = await getConversation(intent.conversationId);
      if (epoch !== routeEpoch) return;
      const restored = normalizeLifeConversationSnapshot(raw, {
        expectedConversationId: intent.conversationId,
      });
      if (epoch !== routeEpoch) return;
      conversation.value = restored;
      messages.value = restored.messages;
      return;
    }

    if (intent.kind === "create") {
      const rawCreated = await createConversation({ agentId: "life_guide_agent" });
      if (epoch !== routeEpoch) return;
      const created = normalizeLifeConversationIdentity(rawCreated);
      await router.replace({
        path: "/demo",
        query: { s: intent.scenarioId, c: created.id },
      });
    }
  } catch (err) {
    if (epoch !== routeEpoch) return;
    startError.value = errorText(err);
  } finally {
    if (epoch === routeEpoch) starting.value = false;
  }
}

function onSelect(id) {
  if (!Object.prototype.hasOwnProperty.call(SCENARIOS, id)) return;
  router.replace({ path: "/demo", query: { s: id } });
}

async function reconcilePendingAmbiguousRound(epoch = routeEpoch) {
  const pendingRound = pendingAmbiguousRound.value;
  if (!pendingRound) return false;
  try {
    const rawRecovered = await getConversation(pendingRound.conversationId);
    if (
      epoch !== routeEpoch ||
      pendingAmbiguousRound.value !== pendingRound
    ) {
      return false;
    }
    const recovered = normalizeLifeConversationSnapshot(rawRecovered, {
      expectedConversationId: pendingRound.conversationId,
    });
    reconcileAmbiguousLifePostSnapshot(recovered, {
      baselineMessages: pendingRound.baselineMessages,
      submittedText: pendingRound.submittedText,
    });
    if (
      epoch !== routeEpoch ||
      pendingAmbiguousRound.value !== pendingRound
    ) {
      return false;
    }
    conversation.value = recovered;
    messages.value = recovered.messages;
    pendingAmbiguousRound.value = null;
    reconciliationRequired.value = false;
    sendError.value = "已通过会话冷读确认本轮只保存一次。";
    return true;
  } catch (recoveryError) {
    if (
      epoch !== routeEpoch ||
      pendingAmbiguousRound.value !== pendingRound
    ) {
      return false;
    }
    reconciliationRequired.value = true;
    sendError.value = `本轮可能已经保存，但无法按发送前基线完成唯一核对：${errorText(recoveryError)}。请刷新会话核对，不要盲目重发。`;
    return false;
  }
}

async function reloadCurrent() {
  if (!pendingAmbiguousRound.value) {
    void synchronizeRoute();
    return;
  }
  if (sending.value) return;
  const epoch = routeEpoch;
  sending.value = true;
  try {
    await reconcilePendingAmbiguousRound(epoch);
  } finally {
    if (epoch === routeEpoch) sending.value = false;
  }
}

async function send() {
  const text = draft.value.trim();
  if (
    !text ||
    sending.value ||
    !conversation.value ||
    pendingAmbiguousRound.value
  ) {
    return;
  }
  const epoch = routeEpoch;
  const conversationId = conversation.value.id;
  const baselineMessages = [...messages.value];
  sending.value = true;
  sendError.value = "";
  reconciliationRequired.value = false;
  draft.value = "";
  let postResponseReceived = false;
  try {
    const rawPost = await postMessage(conversationId, text, []);
    postResponseReceived = true;
    const normalizedPost = normalizeLifePostResponse(rawPost, {
      expectedConversationId: conversationId,
    });
    const rawSnapshot = await getConversation(conversationId);
    const restored = normalizeLifeConversationSnapshot(rawSnapshot, {
      expectedConversationId: conversationId,
    });
    assertLifePostMatchesSnapshot(normalizedPost, restored);
    if (epoch !== routeEpoch) return;
    conversation.value = restored;
    messages.value = restored.messages;
    pendingAmbiguousRound.value = null;
  } catch (err) {
    if (epoch !== routeEpoch) return;
    if (
      !postResponseReceived &&
      isDefinitelyUncommittedLifePostError(err)
    ) {
      draft.value = text;
      sendError.value = `请求已在持久化前被拒绝：${errorText(err)}`;
      return;
    }

    // POST 一旦发出，网络 reject、超时、未知 4xx/5xx 都不能证明没有 COMMIT。
    // 保留本轮基线直到精确冷读恢复；重复刷新也只能继续核对，不能重开 composer。
    pendingAmbiguousRound.value = {
      conversationId,
      baselineMessages,
      submittedText: text,
    };
    reconciliationRequired.value = true;
    await reconcilePendingAmbiguousRound(epoch);
  } finally {
    if (epoch === routeEpoch) sending.value = false;
  }
}

function focusComposer() {
  composerEl.value?.focus();
}

watch(
  () => [route.query.s, route.query.c],
  () => void synchronizeRoute(),
  { immediate: true },
);
</script>

<style scoped>
.life-demo {
  max-width: 860px;
  margin: 0 auto;
  padding: clamp(20px, 4vh, 40px) 22px 64px;
}

.life-demo__bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 0 18px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 22px;
  font-size: 13px;
  color: var(--ink-soft);
}

.life-demo__back {
  color: var(--clay);
  text-decoration: none;
}

.life-demo__current {
  flex: 1 1 auto;
  font-weight: 600;
  color: var(--ink);
}

.life-demo__reset {
  appearance: none;
  font: inherit;
  border: 1px solid var(--hairline);
  background: var(--surface-raised);
  color: var(--ink-soft);
  padding: 5px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
}

.life-demo__reset:hover {
  color: var(--ink);
  border-color: var(--clay-softer);
}

.life-demo__hint {
  padding: 24px;
  text-align: center;
  color: var(--ink-soft);
  font-size: 14px;
}

.life-demo__error {
  padding: 16px;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: 10px;
  color: var(--trust-fail);
  font-size: 13px;
  line-height: 1.6;
}

.life-demo__error button {
  margin-left: 8px;
  font: inherit;
  border: 1px solid var(--clay-softer);
  background: var(--surface-raised);
  color: var(--clay);
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.life-demo__opening {
  padding: 18px 20px;
  background: var(--paper-cream);
  border-left: 3px solid var(--clay);
  border-radius: 8px;
  margin-bottom: 22px;
}

.life-demo__opening p {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--ink);
}

.life-demo__opening-hint {
  color: var(--ink-soft) !important;
  font-size: 13px !important;
  line-height: 1.6;
}

.life-demo__thread {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.life-demo__bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.life-demo__bubble.user {
  align-self: flex-end;
  background: var(--clay-soft, #f0e6da);
  color: var(--ink);
  border-bottom-right-radius: 4px;
}

.life-demo__bubble.assistant {
  align-self: flex-start;
  background: var(--surface-raised);
  color: var(--ink);
  border: 1px solid var(--hairline);
  border-bottom-left-radius: 4px;
}

.life-demo__bubble-role {
  font-size: 11px;
  color: var(--ink-faint);
  margin-bottom: 4px;
}

.life-demo__composer {
  margin-top: 14px;
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.life-demo__textarea {
  flex: 1 1 auto;
  resize: vertical;
  min-height: 56px;
  padding: 10px 12px;
  border: 1px solid var(--hairline);
  border-radius: 10px;
  background: var(--surface-raised);
  color: var(--ink);
  font: inherit;
  font-size: 14px;
  line-height: 1.5;
  font-family: var(--mono, ui-monospace, monospace);
}

.life-demo__textarea:focus {
  outline: none;
  border-color: var(--clay);
  box-shadow: 0 0 0 2px rgba(207, 122, 48, 0.15);
}

.life-demo__send {
  flex: none;
  height: 56px;
  padding: 0 18px;
  border: 1px solid var(--clay);
  border-radius: 10px;
  background: var(--clay);
  color: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity var(--motion-fast) var(--ease-out-soft);
}

.life-demo__send:hover:not(:disabled) {
  opacity: 0.9;
}

.life-demo__send:disabled {
  background: var(--hairline);
  border-color: var(--hairline);
  color: var(--ink-faint);
  cursor: not-allowed;
}

.life-demo__error-inline {
  margin: 6px 0 0;
  color: var(--trust-fail);
  font-size: 12px;
}

@media (max-width: 640px) {
  .life-demo__bubble {
    max-width: 92%;
  }
  .life-demo__composer {
    flex-direction: column;
    align-items: stretch;
  }
  .life-demo__send {
    width: 100%;
  }
}
</style>
