<template>
  <!--
    本体论教学 demo 启动页(/demo)。
    路径 A:未选场景 → 渲染 LifeScenarioPicker,工程师三选一。
    路径 B:已选场景 → 创建 life_guide_agent 会话,就地渲染对话流。

    独立于主 GuidePage(工程任务入口),避免污染工程对话主线。
    demo 产出的 Skill Package 走 quarantine 隔离区,不进生产 Registry。
  -->
  <div class="life-demo">
    <!-- 顶栏:回到主对话 + 当前场景 -->
    <div v-if="scenarioId" class="life-demo__bar">
      <router-link to="/" class="life-demo__back">← 回主对话</router-link>
      <span class="life-demo__current">{{ currentScenario?.emoji }} {{ currentScenario?.title }}</span>
      <button type="button" class="life-demo__reset" @click="reset">换个场景</button>
    </div>

    <!-- 路径 A:场景选择 -->
    <LifeScenarioPicker v-if="!conversation" @select="onSelect" />

    <!-- 路径 B:对话 -->
    <section v-else class="life-demo__session">
      <div v-if="starting" class="life-demo__hint">正在起会话...</div>
      <div v-else-if="startError" class="life-demo__error">
        <strong>起会话失败</strong> — {{ startError }}
        <button type="button" @click="reset">重试</button>
      </div>
      <div v-else class="life-demo__thread">
        <!-- 起手提示(对话还没开始) -->
        <div v-if="messages.length === 0" class="life-demo__opening">
          <p>
            <b>{{ currentScenario?.emoji }} {{ currentScenario?.title }}</b
            >·{{ currentScenario?.focus }}
          </p>
          <p class="life-demo__opening-hint">{{ openingHint }}</p>
        </div>

        <!-- 消息流(简化版:只显示文字,不渲染 recommendation/draft 卡片) -->
        <div v-for="(m, idx) in messages" :key="idx" :class="['life-demo__bubble', m.role]">
          <div class="life-demo__bubble-role">{{ m.role === "user" ? "我" : "主持人" }}</div>
          <div class="life-demo__bubble-text">{{ m.content }}</div>
        </div>

        <!-- 输入框 -->
        <div class="life-demo__composer">
          <textarea
            v-model="draft"
            class="life-demo__textarea"
            :placeholder="composerPlaceholder"
            :disabled="sending"
            rows="3"
            @keydown.enter.exact.prevent="send"
          ></textarea>
          <button
            type="button"
            class="life-demo__send"
            :disabled="!draft.trim() || sending"
            @click="send"
          >
            {{ sending ? "发送中..." : "发送 ↵" }}
          </button>
        </div>
        <p v-if="sendError" class="life-demo__error-inline">{{ sendError }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import LifeScenarioPicker from "../components/LifeScenarioPicker.vue";
import { createConversation, postMessage } from "../api/conversations";

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

const scenarioId = ref(route.params.scenarioId || route.query.s || null);
const conversation = ref(null);
const starting = ref(false);
const startError = ref("");
const messages = ref([]);
const draft = ref("");
const sending = ref(false);
const sendError = ref("");

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
  scenarioId.value = null;
  conversation.value = null;
  messages.value = [];
  draft.value = "";
  startError.value = "";
  sendError.value = "";
  router.replace({ path: "/demo" });
}

async function onSelect(id) {
  scenarioId.value = id;
  starting.value = true;
  startError.value = "";
  try {
    conversation.value = await createConversation({ agentId: "life_guide_agent" });
  } catch (err) {
    startError.value = err.detail || String(err.message || err);
  } finally {
    starting.value = false;
  }
}

async function send() {
  const text = draft.value.trim();
  if (!text || sending.value || !conversation.value) return;
  sending.value = true;
  sendError.value = "";
  messages.value.push({ role: "user", content: text });
  draft.value = "";
  try {
    const res = await postMessage(conversation.value.id, text, []);
    const reply = res?.message?.content || "(主持人无回复)";
    messages.value.push({ role: "assistant", content: reply });
  } catch (err) {
    sendError.value = err.detail || String(err.message || err);
  } finally {
    sending.value = false;
  }
}

onMounted(() => {
  // 进入 /demo?s=cooking 直接预选(深链兼容)
  if (route.query.s && SCENARIOS[route.query.s] && !scenarioId.value) {
    onSelect(route.query.s);
  }
});
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
