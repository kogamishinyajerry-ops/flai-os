<script setup>
// Stage C 工作台原型：合成夹具驱动（SYNTHETIC ONLY）。
// 所有动态都来自 projectObserverEvents 投影快照；没有定时器、随机数或自报进度。
// 信任色锁五槽：clay 工作 / 绿 REAL 见证 / teal 人签 / 红 真失败 / amber 未核。
// 合成夹具永远不进绿槽；本地点击永远不进 teal 槽；取消用中性墨色，不进红槽。
import { computed, ref } from "vue";
import {
  FIXTURE_SCENARIOS,
  FIXTURE_STATES,
  getFixture,
} from "./fixtures.js";

const params = new URLSearchParams(window.location.search);
const scene = ref(FIXTURE_SCENARIOS[params.get("scene")] ? params.get("scene") : "docx");
const state = ref(FIXTURE_STATES.includes(params.get("state")) ? params.get("state") : "");
const submitted = ref(false);
const showSignRequirements = ref(false);
const composerText = ref("");

const inWorkbench = computed(() => Boolean(state.value) || submitted.value);
const effectiveState = computed(() => (submitted.value ? "running" : state.value || "running"));
const fixture = computed(() => getFixture(`${scene.value}:${effectiveState.value}`));
const scenario = computed(() => fixture.value.scenario);
const snap = computed(() => fixture.value.snapshot);

const GLYPH_BY_ACTION = {
  guard: "guard",
  inspect: "inspect",
  rewrite: "rewrite",
  map: "map",
  render: "render",
  hold: "wait",
  stop: null, // 按 mode 区分 failed / cancelled
  deny: "failed",
  signal: "unknown",
  idle: "idle",
  receive: "inspect",
};
const glyphId = computed(() => {
  if (snap.value.action === "stop") return snap.value.mode === "stopped" ? "cancelled" : "failed";
  return GLYPH_BY_ACTION[snap.value.action] || "unknown";
});
const GLYPH_LABEL = {
  guard: "核验",
  inspect: "检查",
  rewrite: "生成可逆稿",
  map: "整理关系",
  render: "渲染预览",
  wait: "等待真人",
  failed: "失败停止",
  cancelled: "已停止",
  unknown: "状态未知",
  idle: "待命",
};

// 信任槽唯一语义：stopped/cancelled 用中性 terminal，绝不进红 fail；
// completed(preview) 同样只给中性终态色，绝不自动给绿。
// 本原型没有任何路径产出 sign（teal）：teal 只属于真实认证签发链。
const trustSlot = computed(() => {
  if (snap.value.mode === "failed") return "fail";
  if (snap.value.mode === "unknown") return "unverified";
  if (snap.value.mode === "stopped") return "terminal";
  if (snap.value.mode === "preview") return "terminal";
  return "work";
});

// 绿槽 REAL 只属于 control-kernel 来源的真实见证；合成夹具一律中性标注
// “形态测试 · 非真实见证”。首页未提交时不显示任何执行类徽标。
const KERNEL_REALITY_BADGE = {
  REAL: { slot: "real", text: "REAL · 有执行见证" },
  MOCK: { slot: "unverified", text: "MOCK · 仅声明" },
  TEST: { slot: "test", text: "TEST · 测试适配器" },
  UNKNOWN: { slot: "unverified", text: "UNKNOWN · 未核" },
};
const realityBadge = computed(() => {
  if (!inWorkbench.value) return null;
  const reality = snap.value.reality;
  if (snap.value.source !== "control-kernel") {
    if (reality === "UNKNOWN") {
      return { slot: "unverified", text: "合成样例 · UNKNOWN 形态 · 未核，非真实见证" };
    }
    return { slot: "test", text: `合成样例 · ${reality} 形态测试 · 非真实见证` };
  }
  return KERNEL_REALITY_BADGE[reality] || KERNEL_REALITY_BADGE.UNKNOWN;
});

const WHY_NOW = {
  working: "Agent 正在处理这个对象，因此把它放在最前。",
  scanning: "Agent 正在接收这个对象，因此把它放在最前。",
  attention: "现在需要真人检查或决定，因此把待检查清单放在最前。",
  preview: "任务已到终态，展示已冻结产物供查看；签发仍只由真人完成。",
  failed: "执行已停止（失败或权限拒绝），展示最后可信对象、影响与恢复入口。",
  stopped: "执行已停止（中性终止，不是失败），保留最后可信对象供检查。",
  unknown: "当前没有可验证的对象，如实显示缺口，不用占位假装进展。",
};
const whyNow = computed(() => WHY_NOW[snap.value.mode] || WHY_NOW.unknown);

// 右栏当前对象随状态切换：只使用投影快照可证明的字段，不编造生产事实。
const railObject = computed(() => {
  const s = snap.value;
  const p = s.preview;
  const evidenceCount = s.evidenceRefs?.length ?? 0;
  if (s.mode === "unknown") {
    return {
      kind: "gap",
      heading: "缺口对象",
      title: "没有可验证的当前对象",
      caption: `原因码：${s.reasonCode}`,
      lines: [s.detail, "缺口状态不复用正常产物卡；等待可靠观察恢复。"],
    };
  }
  if (s.mode === "attention") {
    return {
      kind: "checklist",
      heading: "当前对象 · 待检查清单",
      title: p.title,
      caption: "系统不会自动升级为正式交付，请逐项检查",
      lines: [
        `产物引用：${p.primary}`,
        `证据引用：${evidenceCount} 条（见下方折叠区）`,
        `合同版本：${s.contractVersion}`,
        `对象说明：${p.secondary}`,
      ],
    };
  }
  if (s.mode === "preview") {
    return {
      kind: "frozen",
      heading: "当前对象 · 已冻结产物",
      title: p.title,
      caption: p.caption,
      lines: [p.primary, "任务终态与产物引用一致；正式签发仍只由真人完成。"],
    };
  }
  if (s.mode === "failed") {
    return {
      kind: "failed",
      heading: "最后可信对象",
      title: p.title,
      caption: p.caption,
      lines: [
        p.primary,
        `影响：${s.title}；${s.detail}`,
        "恢复入口：在下方 Composer 修正指令后重新提交目标。",
      ],
    };
  }
  if (s.mode === "stopped") {
    return {
      kind: "stopped",
      heading: "最后可信对象",
      title: p.title,
      caption: p.caption,
      lines: [p.primary, "中性终止说明：执行已停止，这不是失败；已有只读对象仍可用于检查。"],
    };
  }
  return {
    kind: "object",
    heading: "当前对象 · 正在处理",
    title: p.title,
    caption: p.caption,
    lines: [p.primary, p.secondary],
  };
});

const showDelivery = computed(() => ["attention", "preview"].includes(snap.value.mode));
const showGap = computed(() => ["unknown", "failed", "stopped"].includes(snap.value.mode));
const animating = computed(() => snap.value.motion === true);

const steps = computed(() => {
  const match = /(\d+)\/(\d+)/.exec(snap.value.stepLabel);
  if (!match) return null;
  return { current: Number(match[1]), total: Number(match[2]) };
});

function submitGoal() {
  if (!composerText.value.trim()) return;
  composerText.value = "";
  showSignRequirements.value = false;
  submitted.value = true;
}
// 中文输入法 composition 期间（isComposing）快捷键不得提交；
// composition 结束后 Ctrl/Meta+Enter 正常提交。
function onComposerKeydown(event) {
  if (event.isComposing) return;
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    submitGoal();
  }
}
function pickScene(key) {
  scene.value = key;
  showSignRequirements.value = false;
  submitted.value = true;
}
function onFixtureChange() {
  showSignRequirements.value = false;
  submitted.value = false;
}
</script>

<template>
  <div class="stage-c" :data-motion="animating ? 'true' : 'false'">
    <header class="topbar">
      <div class="brand">
        <span class="brand-name">FLAi 工作台</span>
        <span class="brand-tag">Stage C 原型 · 合成夹具</span>
      </div>
      <div class="topbar-right">
        <span
          v-if="realityBadge"
          class="badge"
          :data-reality="snap.reality"
          :data-slot="realityBadge.slot"
          data-testid="reality-badge"
        >
          {{ realityBadge.text }}
        </span>
        <label class="fixture-picker">
          <span>合成场景</span>
          <select v-model="scene" data-testid="scene-picker" @change="onFixtureChange">
            <option v-for="(s, key) in FIXTURE_SCENARIOS" :key="key" :value="key">
              {{ s.label }}
            </option>
          </select>
        </label>
        <label class="fixture-picker">
          <span>合成状态</span>
          <select v-model="state" data-testid="state-picker" @change="onFixtureChange">
            <option value="">（首页）</option>
            <option v-for="s in FIXTURE_STATES" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
      </div>
    </header>

    <!-- 低门槛首页：一个 Composer + 少量高价值入口；未提交不显示任何执行徽标 -->
    <main v-if="!inWorkbench" class="home" data-testid="home">
      <h1 class="home-title">要 Agent 做什么？</h1>
      <p class="home-sub">提交目标后自动进入连续执行工作台；高影响动作只在末端由真人签发。</p>
      <form class="composer composer--home" data-testid="composer" @submit.prevent="submitGoal">
        <textarea
          v-model="composerText"
          rows="3"
          autofocus
          placeholder="例如：把本周项目记录整理成可印发的周报文档"
          aria-label="任务目标"
          @keydown="onComposerKeydown"
        ></textarea>
        <div class="composer-bar">
          <span class="hint">⌘/Ctrl + Enter 提交</span>
          <button type="submit" class="btn btn--primary" :disabled="!composerText.trim()">
            提交目标
          </button>
        </div>
      </form>
      <div class="entries">
        <button
          v-for="(s, key) in FIXTURE_SCENARIOS"
          :key="key"
          type="button"
          class="entry-card"
          @click="pickScene(key)"
        >
          <span class="entry-label">{{ s.label }}</span>
          <span class="entry-goal">{{ s.goal }}</span>
        </button>
      </div>
    </main>

    <!-- 三栏 Workspace：左上下文轨 / 中央连续执行叙事 / 右侧当前对象舞台 -->
    <div v-else class="workbench" data-testid="workbench">
      <aside class="left-rail" data-testid="left-rail">
        <div class="left-block">
          <p class="left-heading">当前项目</p>
          <p class="left-item left-item--active">{{ scenario.label }} · {{ scenario.object }}</p>
        </div>
        <nav class="left-block" aria-label="最近工作">
          <p class="left-heading">最近工作</p>
          <button
            v-for="(s, key) in FIXTURE_SCENARIOS"
            :key="key"
            type="button"
            class="left-item left-item--btn"
            :class="{ 'left-item--active': key === scene }"
            @click="pickScene(key)"
          >
            {{ s.label }}
          </button>
        </nav>
        <div class="left-block">
          <p class="left-heading">获准知识上下文</p>
          <p class="left-note">只读对象元数据（合成样例）；本原型不接入真实内网知识。</p>
        </div>
      </aside>

      <main class="main-col">
        <section class="hero" :data-trust="trustSlot" data-testid="hero">
          <div class="hero-glyph" :data-glyph="glyphId" :data-motion="animating ? 'true' : 'false'">
            <svg v-if="glyphId === 'guard'" viewBox="0 0 24 24" aria-hidden="true">
              <path class="g-shape" d="M12 3l7 3v5c0 4.4-3 8.4-7 10-4-1.6-7-5.6-7-10V6z" />
              <path class="g-mark" d="M9 12l2 2 4-4" />
            </svg>
            <svg v-else-if="glyphId === 'inspect'" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="11" cy="11" r="6" />
              <path class="g-shape" d="M15.5 15.5L20 20" />
              <path class="g-scan" d="M7 11h8" />
            </svg>
            <svg v-else-if="glyphId === 'rewrite'" viewBox="0 0 24 24" aria-hidden="true">
              <path class="g-shape" d="M4 20l1-4L16 5l3 3L8 19z" />
              <path class="g-dash" d="M6 21h12" />
            </svg>
            <svg v-else-if="glyphId === 'map'" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="6" cy="6" r="2.5" />
              <circle class="g-shape" cx="18" cy="6" r="2.5" />
              <circle class="g-shape" cx="12" cy="18" r="2.5" />
              <path class="g-link" d="M8 7.5l7.5 8M16 7.5l-7.5 8M8.5 6h7" />
            </svg>
            <svg v-else-if="glyphId === 'render'" viewBox="0 0 24 24" aria-hidden="true">
              <rect class="g-shape" x="4" y="5" width="16" height="12" rx="2" />
              <path class="g-mark" d="M4 13l4-4 4 4 3-3 5 5" />
            </svg>
            <svg v-else-if="glyphId === 'wait'" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="12" cy="8" r="4" />
              <path class="g-shape" d="M5 20c1.5-3.5 4-5 7-5s5.5 1.5 7 5" />
            </svg>
            <svg v-else-if="glyphId === 'failed'" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="12" cy="12" r="8" />
              <path class="g-mark" d="M9 9l6 6M15 9l-6 6" />
            </svg>
            <svg v-else-if="glyphId === 'cancelled'" viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="12" cy="12" r="8" />
              <rect class="g-mark-fill" x="9" y="9" width="6" height="6" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <circle class="g-shape" cx="12" cy="12" r="8" />
              <path class="g-mark" d="M12 8v5M12 16h.01" />
            </svg>
          </div>
          <div class="hero-text">
            <p class="overline">{{ snap.overline }} · {{ GLYPH_LABEL[glyphId] }}</p>
            <h2 class="hero-title" data-testid="hero-title">{{ snap.title }}</h2>
            <p class="hero-detail">{{ snap.detail }}</p>
            <p class="step-line">
              <span v-if="steps" class="step-segments" aria-hidden="true">
                <span
                  v-for="i in steps.total"
                  :key="i"
                  class="seg"
                  :class="{ 'seg--done': i <= steps.current }"
                ></span>
              </span>
              <span data-testid="step-label">{{ snap.stepLabel }}</span>
            </p>
          </div>
        </section>

        <!-- 例外与缺口聚合：不弹窗、不打断；取消用中性色，只有真失败用红 -->
        <section v-if="showGap" class="gap-card" :data-trust="trustSlot" data-testid="gap-card">
          <h3 class="gap-title">当前缺口</h3>
          <p class="gap-reason">原因码：{{ snap.reasonCode }}</p>
          <p class="gap-detail">{{ snap.detail }}</p>
        </section>

        <!-- 末端交付：产物、证据、残余风险；签发只做中性说明，teal 路径不可达 -->
        <section v-if="showDelivery" class="delivery" data-testid="delivery">
          <h3 class="section-title">交付检查</h3>
          <ul class="delivery-list">
            <li><strong>产物</strong>{{ snap.preview.title }}</li>
            <li><strong>证据</strong>{{ snap.evidenceRefs?.length ?? 0 }} 条证据引用（合成样例，非真实见证）</li>
            <li><strong>残余风险</strong>合成夹具不证明内容正确；真实内容结论须在内网重新核验。</li>
          </ul>
          <p class="badge" data-slot="unverified" data-testid="unsigned-badge">
            未签发：等待认证签发链
          </p>
          <button
            type="button"
            class="btn btn--ghost"
            data-testid="sign-requirements-button"
            :aria-expanded="showSignRequirements"
            @click="showSignRequirements = !showSignRequirements"
          >
            查看签发要求
          </button>
          <ul v-if="showSignRequirements" class="sign-requirements" data-testid="sign-requirements">
            <li>认证主体：签发人身份须经内网认证链确认；本原型的本地点击不构成、也不模拟签发。</li>
            <li>时间：签发时间须由可信时间源记录。</li>
            <li>精确版本：签发对象须绑定任务修订与执行世代。</li>
            <li>有效 receipt：签发完成须返回可核验 receipt。缺少任一条件时，本界面不得显示“已签发”。</li>
          </ul>
        </section>

        <form class="composer" data-testid="composer" @submit.prevent="submitGoal">
          <textarea
            v-model="composerText"
            rows="2"
            placeholder="追加指令或提出修正…"
            aria-label="追加指令"
            @keydown="onComposerKeydown"
          ></textarea>
          <div class="composer-bar">
            <span class="hint">⌘/Ctrl + Enter 发送</span>
            <button type="submit" class="btn btn--primary" :disabled="!composerText.trim()">发送</button>
          </div>
        </form>
        <p class="sr-only" role="status" aria-live="polite">{{ snap.title }}</p>
      </main>

      <!-- 右侧当前对象舞台：对象随状态切换，缺口不复用产物卡 -->
      <aside class="rail" data-testid="rail">
        <section
          class="object-card"
          :data-rail-kind="railObject.kind"
          :data-preview-kind="snap.preview.kind"
          data-testid="object-card"
        >
          <p class="rail-overline">{{ railObject.heading }}</p>
          <h3 class="object-title">{{ railObject.title }}</h3>
          <p class="object-caption">{{ railObject.caption }}</p>
          <p v-for="(line, i) in railObject.lines" :key="i" class="object-line">{{ line }}</p>
          <p class="why-now" data-testid="why-now">{{ whyNow }}</p>
        </section>

        <details class="rail-block">
          <summary>证据与来源（{{ snap.evidenceRefs?.length ?? 0 }}）</summary>
          <ul class="evidence-list">
            <li v-for="ref in snap.evidenceRefs || []" :key="ref"><code>{{ ref }}</code></li>
          </ul>
          <p v-if="!(snap.evidenceRefs || []).length" class="hint">没有可验证证据。</p>
        </details>

        <details class="rail-block">
          <summary>低优先级元数据</summary>
          <dl class="meta-list">
            <div><dt>合同版本</dt><dd>{{ snap.contractVersion }}</dd></div>
            <div><dt>观察来源</dt><dd>{{ snap.source || "无" }}</dd></div>
            <div><dt>原因码</dt><dd>{{ snap.reasonCode }}</dd></div>
          </dl>
        </details>
      </aside>
    </div>
  </div>
</template>
