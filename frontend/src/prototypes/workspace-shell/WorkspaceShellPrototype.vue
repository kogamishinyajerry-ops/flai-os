<script setup>
// Workspace Shell V1 原型：合成夹具驱动（SYNTHETIC ONLY）。
// 默认体验是一个连续 Workspace：左轨（搜索/最近/固定/轻状态）、
// 中央（当前动作 + 紧凑执行历史 + 固定 Composer + 独立指令队列）、
// 右侧 Focus Surface（当前最值得看的对象/差异/缺口/例外）。
// 不使用 v-html、不执行任何模型提供的 HTML/JS/Python/shell、不发网络请求。
// 信任不变量：合成夹具永不进 real(绿)/sign(teal) 槽；completed 中性；
// motion 只由 fresh 活动观察驱动；缺口态 fail closed 并清空敏感预览。
import { computed, reactive, ref } from "vue";
import {
  DISPLAY_FORMS,
  OVERLAY_STATES,
  WORKFLOWS,
  WORKSPACE_STATES,
  getWorkspaceFixture,
} from "./fixtures.js";
import {
  GLYPH_LABELS,
  appendInstruction,
  createCommandQueue,
  resolveView,
} from "./workspace-view.js";

const params = new URLSearchParams(window.location.search);
const workflow = ref(WORKFLOWS[params.get("workflow")] ? params.get("workflow") : "docx");
const ALL_STATES = [...WORKSPACE_STATES, ...OVERLAY_STATES];
const state = ref(ALL_STATES.includes(params.get("state")) ? params.get("state") : "running");
// 缺省形态是合成 REAL 显示形态；显式非法输入 fail-closed 到 UNKNOWN，
// 绝不静默伪装成 REAL。UNKNOWN 形态不构造观察事件，只投影观察缺口。
const requestedForm = params.get("form");
const form = ref(
  requestedForm === null
    ? "REAL"
    : (DISPLAY_FORMS.includes(requestedForm) ? requestedForm : "UNKNOWN"),
);

// UNKNOWN 形态的渲染事实固定为 fail-closed 缺口；状态选择器同步显示并禁用。
const effectiveState = computed(() => (form.value === "UNKNOWN" ? "observation-invalid" : state.value));
const visibleState = computed({
  get: () => (form.value === "UNKNOWN" ? "observation-invalid" : state.value),
  set: (value) => {
    state.value = value;
  },
});
const fixtureKey = computed(() => `${workflow.value}:${effectiveState.value}@${form.value}`);
const view = computed(() => resolveView(getWorkspaceFixture(fixtureKey.value)));
const scenario = computed(() => WORKFLOWS[workflow.value]);

// 命令队列：每条补充指令独立 ID、保序、各自 synthetic receipt
// （ACCEPTED 只表示已受理/已排队，不代表完成）。
const queue = reactive(createCommandQueue());
const composerText = ref("");
function submitInstruction() {
  const item = appendInstruction(queue, composerText.value);
  if (item) composerText.value = "";
}
// 中文 IME composition 期间（isComposing）快捷键不得提交；Enter 单独
// 按下始终只是换行，只有 ⌘/Ctrl+Enter 提交。
function onComposerKeydown(event) {
  if (event.isComposing) return;
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    submitInstruction();
  }
}

// 左轨：搜索过滤最近工作；固定工作；轻量状态（文本 + 点，颜色不是唯一信号）。
const railQuery = ref("");
const RAIL_STATUS = Object.freeze({
  docx: "进行中（合成）",
  meeting: "待审阅（合成）",
  cfd: "已完成（合成）",
});
const PINNED = Object.freeze(["docx", "cfd"]);
const recentWorkflows = computed(() => {
  const query = railQuery.value.trim();
  return Object.entries(WORKFLOWS)
    .filter(([key, wf]) => (
      !query || wf.label.includes(query) || wf.title.includes(query) || key.includes(query)
    ))
    .map(([key, wf]) => ({ key, ...wf }));
});
const pinnedWorkflows = computed(() => (
  PINNED.filter((key) => recentWorkflows.value.some((item) => item.key === key))
));
function pickWorkflow(key) {
  workflow.value = key;
  state.value = "running";
}

const showDelivery = computed(() => ["waiting_review", "completed"].includes(effectiveState.value)
  && view.value.focus.kind !== "gap");
const showGap = computed(() => view.value.focus.kind === "gap");
const showBoundary = computed(() => effectiveState.value === "permission-denied");
const showException = computed(() => effectiveState.value === "failed");
const showStopped = computed(() => effectiveState.value === "cancelled");
const showSignConditions = ref(false);

function timeOf(iso) {
  return typeof iso === "string" && iso.length >= 19 ? iso.slice(11, 19) : "--:--:--";
}
</script>

<template>
  <div
    class="ws-shell"
    data-source-kind="synthetic-fixture"
    :data-motion="view.motion ? 'true' : 'false'"
  >
    <!-- 左轨：紧凑 Workspace 导航；治理与演示控制默认折叠 -->
    <aside class="ws-rail" data-testid="ws-rail">
      <div class="rail-head">
        <span class="rail-workspace">FLAi Workspace</span>
        <span class="rail-tag">原型 · 合成夹具</span>
      </div>
      <label class="rail-search">
        <span class="sr-only">搜索工作</span>
        <input
          v-model="railQuery"
          type="search"
          placeholder="搜索工作…"
          data-testid="rail-search"
        />
      </label>

      <nav class="rail-section" aria-label="固定的工作" data-testid="rail-pinned">
        <p class="rail-heading">固定</p>
        <button
          v-for="key in pinnedWorkflows"
          :key="key"
          type="button"
          class="rail-item"
          :class="{ 'rail-item--current': key === workflow }"
          @click="pickWorkflow(key)"
        >
          <span class="rail-item-label">{{ WORKFLOWS[key].label }}</span>
          <span class="rail-item-status">{{ RAIL_STATUS[key] }}</span>
        </button>
        <p v-if="!pinnedWorkflows.length" class="rail-empty">没有匹配的固定工作。</p>
      </nav>

      <nav class="rail-section" aria-label="最近工作" data-testid="rail-recent">
        <p class="rail-heading">最近</p>
        <button
          v-for="item in recentWorkflows"
          :key="item.key"
          type="button"
          class="rail-item"
          :class="{ 'rail-item--current': item.key === workflow }"
          @click="pickWorkflow(item.key)"
        >
          <span class="rail-item-label">{{ item.label }}</span>
          <span class="rail-item-status">{{ RAIL_STATUS[item.key] }}</span>
        </button>
        <p v-if="!recentWorkflows.length" class="rail-empty">没有匹配的最近工作。</p>
      </nav>

      <div class="rail-foot">
        <details class="rail-details" data-testid="rail-governance">
          <summary>治理与权限</summary>
          <p class="rail-note">
            治理对象默认折叠；只有动作真正跨越边界时才在当前上下文就地展开（合成演示）。
          </p>
        </details>
        <details class="rail-details" data-testid="demo-console" :open="form === 'UNKNOWN'">
          <summary>合成演示控制</summary>
          <label class="console-row">
            <span>工作流</span>
            <select v-model="workflow" data-testid="ws-workflow-picker">
              <option v-for="(wf, key) in WORKFLOWS" :key="key" :value="key">{{ wf.label }}</option>
            </select>
          </label>
          <label class="console-row">
            <span>观察状态</span>
            <select
              v-model="visibleState"
              data-testid="ws-state-picker"
              :disabled="form === 'UNKNOWN'"
            >
              <option v-for="s in WORKSPACE_STATES" :key="s" :value="s">{{ s }}</option>
              <option value="stale">stale（过期叠加）</option>
            </select>
          </label>
          <label class="console-row">
            <span>显示形态</span>
            <select v-model="form" data-testid="ws-form-picker">
              <option v-for="f in DISPLAY_FORMS" :key="f" :value="f">{{ f }}</option>
            </select>
          </label>
          <p v-if="form === 'UNKNOWN'" class="rail-note" data-testid="unknown-form-hint">
            UNKNOWN 不是合法执行事实，只由 fail-closed 观察缺口给出。
          </p>
        </details>
      </div>
    </aside>

    <!-- 中央：当前动作 + 紧凑执行历史 + 队列 + 固定 Composer -->
    <main class="ws-center" data-testid="ws-center">
      <header class="center-head">
        <div class="center-title">
          <p class="center-overline">{{ scenario.label }} · 合成任务</p>
          <h1 class="center-h1" data-testid="task-title">{{ scenario.title }}</h1>
        </div>
        <span
          class="ws-badge"
          :data-reality-form="view.badge.form"
          :data-source-kind="view.badge.sourceKind"
          :data-slot="view.badge.slot"
          data-testid="reality-badge"
        >{{ view.badge.text }}</span>
      </header>

      <section class="action-card" :data-trust="view.trustSlot" data-testid="action-card">
        <div
          class="action-glyph"
          :data-glyph="view.glyph"
          :data-motion="view.motion ? 'true' : 'false'"
          data-testid="action-glyph"
          role="img"
          :aria-label="GLYPH_LABELS[view.glyph]"
        >
          <svg v-if="view.glyph === 'search'" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="g-line" cx="10.5" cy="10.5" r="5.5" />
            <path class="g-line" d="M14.8 14.8L19.5 19.5" />
            <path class="g-anim" d="M7.5 10.5h6" />
          </svg>
          <svg v-else-if="view.glyph === 'read'" viewBox="0 0 24 24" aria-hidden="true">
            <path class="g-line" d="M12 6c-2-1.4-4.5-1.6-7-1v12c2.5-.6 5-.4 7 1 2-1.4 4.5-1.6 7-1V5c-2.5-.6-5-.4-7 1z" />
            <path class="g-anim" d="M12 6v12" />
          </svg>
          <svg v-else-if="view.glyph === 'parse'" viewBox="0 0 24 24" aria-hidden="true">
            <rect class="g-line" x="9" y="3.5" width="6" height="4" rx="1" />
            <rect class="g-line" x="3.5" y="16.5" width="6" height="4" rx="1" />
            <rect class="g-line" x="14.5" y="16.5" width="6" height="4" rx="1" />
            <path class="g-anim" d="M12 7.5v4m0 0l-5.5 5m5.5-5l5.5 5" />
          </svg>
          <svg v-else-if="view.glyph === 'compute'" viewBox="0 0 24 24" aria-hidden="true">
            <rect class="g-line" x="5" y="5" width="14" height="14" rx="2" />
            <rect class="g-anim-fill" x="9.5" y="9.5" width="5" height="5" rx="1" />
            <path class="g-line" d="M9 2.5v2.5M15 2.5v2.5M9 19v2.5M15 19v2.5M2.5 9H5M2.5 15H5M19 9h2.5M19 15h2.5" />
          </svg>
          <svg v-else-if="view.glyph === 'render'" viewBox="0 0 24 24" aria-hidden="true">
            <rect class="g-line" x="3.5" y="5" width="17" height="14" rx="2" />
            <path class="g-anim" d="M3.5 15.5l4.5-4.5 4 4 3-3 5.5 5.5" />
            <circle class="g-line" cx="9" cy="9" r="1.2" />
          </svg>
          <svg v-else-if="view.glyph === 'waiting-review'" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="g-line" cx="12" cy="7.5" r="3.5" />
            <path class="g-line" d="M5.5 20c1.4-3.2 3.8-4.8 6.5-4.8s5.1 1.6 6.5 4.8" />
            <path class="g-anim" d="M16.5 4.5l1.2 1.2 2.3-2.3" />
          </svg>
          <svg v-else-if="view.glyph === 'failed'" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="g-line" cx="12" cy="12" r="8" />
            <path class="g-line" d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6" />
          </svg>
          <svg v-else-if="view.glyph === 'cancelled'" viewBox="0 0 24 24" aria-hidden="true">
            <circle class="g-line" cx="12" cy="12" r="8" />
            <rect class="g-fill" x="9.3" y="9.3" width="5.4" height="5.4" />
          </svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true">
            <circle class="g-line" cx="12" cy="12" r="8" />
            <path class="g-line" d="M12 8v4.5M12 15.8h.01" />
          </svg>
        </div>
        <div class="action-text">
          <p class="action-overline">{{ view.overline }} · {{ GLYPH_LABELS[view.glyph] }}</p>
          <p class="action-title" data-testid="action-title">{{ view.title }}</p>
          <p class="action-detail">{{ view.detail }}</p>
          <p class="action-step" data-testid="step-label">{{ view.stepLabel }}</p>
        </div>
      </section>

      <!-- 边界 / 例外 / 缺口：就地聚合披露，不弹窗、不假装执行仍在继续 -->
      <section
        v-if="showBoundary"
        class="notice-card"
        data-notice-kind="boundary"
        data-testid="boundary-card"
      >
        <h2 class="notice-title">权限边界</h2>
        <p class="notice-code">公开原因码：{{ view.focus.reasonCode }}</p>
        <p class="notice-detail">对 {{ scenario.object }} 的访问被拒绝；执行已在边界停止，不会悄悄降级继续。</p>
        <p class="notice-detail">可申请权限，或改用已获权的工作对象。</p>
      </section>
      <section
        v-if="showException"
        class="notice-card"
        data-notice-kind="exception"
        data-testid="exception-card"
      >
        <h2 class="notice-title">执行例外</h2>
        <p class="notice-code">公开原因码：{{ view.focus.reasonCode }}</p>
        <p class="notice-detail">{{ view.detail }}</p>
      </section>
      <section
        v-if="showStopped"
        class="notice-card"
        data-notice-kind="stopped"
        data-testid="stopped-card"
      >
        <h2 class="notice-title">已停止</h2>
        <p class="notice-code">公开原因码：{{ view.focus.reasonCode }}</p>
        <p class="notice-detail">{{ view.detail }}</p>
      </section>
      <section
        v-if="showGap"
        class="notice-card"
        data-notice-kind="gap"
        data-testid="gap-card"
      >
        <h2 class="notice-title">观察缺口</h2>
        <p class="notice-code">原因码：{{ view.focus.reasonCode }}</p>
        <p class="notice-detail">{{ view.detail }}</p>
      </section>

      <!-- 紧凑执行历史：只展示投影可证明的事件 -->
      <section v-if="view.history.length" class="history" data-testid="history">
        <h2 class="section-h">执行历史</h2>
        <ol class="history-list" data-testid="history-list">
          <li v-for="item in view.history" :key="item.seq" class="history-row">
            <span class="history-time">{{ timeOf(item.observedAt) }}</span>
            <span class="history-glyph" :data-glyph="item.glyph">{{ GLYPH_LABELS[item.glyph] }}</span>
            <span class="history-title">{{ item.title }}</span>
          </li>
        </ol>
      </section>

      <!-- 指令队列：独立 ID、保序、各自 receipt；receipt 只表示已受理 -->
      <section v-if="queue.items.length" class="queue" data-testid="queue">
        <h2 class="section-h">已排队指令（{{ queue.items.length }}）</h2>
        <ol class="queue-list" data-testid="queue-list">
          <li
            v-for="item in queue.items"
            :key="item.id"
            class="queue-item"
            :data-command-id="item.id"
            :data-receipt-status="item.receipt.status"
            data-testid="queue-item"
          >
            <span class="queue-id">{{ item.id }}</span>
            <span class="queue-text">{{ item.text }}</span>
            <span class="queue-receipt">{{ item.receipt.receiptRef }} · {{ item.receipt.note }}</span>
          </li>
        </ol>
      </section>

      <!-- 交付：只有 waiting_review / completed 出现；永不显示 teal 签发 -->
      <section v-if="showDelivery" class="delivery" data-testid="delivery">
        <h2 class="section-h">交付</h2>
        <p class="ws-badge" data-slot="unverified" data-testid="unsigned-badge">
          未签发 · 合成样例没有签发链
        </p>
        <p class="delivery-note">
          正式交付只由具名真人在可验证签发链上完成；本界面不能创建、伪造或缓存签发事实。
        </p>
        <button
          type="button"
          class="btn-ghost"
          data-testid="sign-conditions-button"
          :aria-expanded="showSignConditions"
          @click="showSignConditions = !showSignConditions"
        >
          查看签发条件
        </button>
        <ul v-if="showSignConditions" class="sign-conditions" data-testid="sign-conditions">
          <li>认证主体：签发人身份须经认证链确认；本地点击不构成、也不模拟签发。</li>
          <li>可信时间：签发时间须由可信时间源记录。</li>
          <li>精确版本：签发对象须绑定任务修订与执行世代。</li>
          <li>有效 receipt：缺少任一条件时，本界面不得显示任何签发完成措辞。</li>
        </ul>
      </section>

      <form class="ws-composer" data-testid="composer" @submit.prevent="submitInstruction">
        <label class="sr-only" for="ws-composer-input">补充指令</label>
        <textarea
          id="ws-composer-input"
          v-model="composerText"
          rows="2"
          placeholder="补充指令或提出修正…（每条独立排队，互不拼接）"
          data-testid="composer-input"
          @keydown="onComposerKeydown"
        ></textarea>
        <div class="composer-bar">
          <span class="composer-hint">⌘/Ctrl + Enter 发送 · Enter 换行</span>
          <button type="submit" class="btn-primary" :disabled="!composerText.trim()">发送</button>
        </div>
      </form>
      <p class="sr-only" role="status" aria-live="polite">{{ view.title }}</p>
    </main>

    <!-- 右侧 Focus Surface：此刻最值得看的对象；缺口态不复用产物预览 -->
    <aside class="ws-focus" data-testid="ws-focus">
      <section
        class="focus-card"
        :data-focus-kind="view.focus.kind"
        data-testid="focus-card"
      >
        <p class="focus-overline">
          {{ view.focus.kind === "gap" ? "证据缺口" : "当前焦点" }}
        </p>
        <h2 class="focus-title">{{ view.focus.title }}</h2>
        <p v-if="view.focus.reasonCode" class="focus-code">{{ view.focus.reasonCode }}</p>
        <p v-for="(line, i) in view.focus.lines" :key="i" class="focus-line">{{ line }}</p>
      </section>
      <details class="focus-meta">
        <summary>低优先级元数据</summary>
        <dl>
          <div><dt>观察来源</dt><dd>source-kind=synthetic-fixture</dd></div>
          <div><dt>原因码</dt><dd>{{ view.reasonCode }}</dd></div>
          <div><dt>渲染器</dt><dd>{{ scenario.artifact.rendererKind }}（静态描述，不执行内容）</dd></div>
        </dl>
      </details>
    </aside>
  </div>
</template>
