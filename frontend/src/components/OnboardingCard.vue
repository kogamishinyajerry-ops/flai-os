<template>
  <!-- 首登三步引导：纯指引、不伪造完成态。压成一条快速上手带，避免首屏
       被说明文字占满；按钮仍只预填/聚焦，绝不代发代建。 -->
  <div v-if="visible" class="onboarding-card">
    <div class="ob-head">
      <span class="ob-title">第一次用？3 步上手</span>
      <button type="button" class="ob-dismiss" @click="dismiss">不再显示</button>
    </div>
    <ol class="ob-steps">
      <li class="ob-step">
        <span class="ob-num">1</span>
        <span class="ob-step-tx"><b>跑演示任务</b></span>
        <button type="button" class="ob-step-btn" @click="$emit('demo')">演示 →</button>
      </li>
      <li class="ob-step">
        <span class="ob-num">2</span>
        <span class="ob-step-tx"><b>说真实需求</b></span>
        <button type="button" class="ob-step-btn is-quiet" @click="$emit('say')">输入 ↓</button>
      </li>
      <li class="ob-step">
        <span class="ob-num">3</span>
        <span class="ob-step-tx"><b>人工签发结果</b></span>
      </li>
    </ol>
    <div class="ob-foot"><kbd>⌘K</kbd> 搜任务、会话和 Agent <span>· Windows 用 <kbd>Ctrl</kbd><kbd>K</kbd></span></div>
  </div>
</template>

<script setup>
import { ref } from "vue";

// 按浏览器记忆（与 utils/lastSeen.js 同一 localStorage 命名家族）。localStorage
// 不可用（隐私模式等）时静默降级为「本次会话内可见」，不报错不阻断。
const DISMISS_KEY = "flai_onboarding_dismissed_v1";

defineEmits(["demo", "say"]);

function readDismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

const visible = ref(!readDismissed());

function dismiss() {
  visible.value = false;
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch {
    /* 存不进就下次再见——不值得为指引卡报错 */
  }
}
</script>

<style scoped>
.onboarding-card {
  margin-top: 12px;
  text-align: left;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg, 12px);
  padding: 10px 12px 9px;
}
.ob-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}
.ob-title {
  flex: 1 1 auto;
  font-size: 12px;
  font-weight: 700;
  color: var(--ink-soft);
  letter-spacing: 0.3px;
}
.ob-dismiss {
  flex: none;
  border: none;
  background: none;
  padding: 2px 4px;
  font-size: 11px;
  color: var(--ink-faint);
  cursor: pointer;
}
.ob-dismiss:hover { color: var(--ink); }
.ob-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.ob-step {
  min-width: 0;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
}
.ob-num {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 10.5px;
  font-weight: 800;
  color: var(--ink-soft);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
}
.ob-step-tx {
  min-width: 0;
  font-size: 12px;
  line-height: 1.25;
  color: var(--ink-soft);
}
.ob-step-tx b { color: var(--ink); font-weight: 600; }
.ob-step-btn {
  flex: none;
  align-self: center;
  border: 1px solid var(--clay-softer);
  background: var(--surface-raised);
  color: var(--clay);
  font-size: 11px;
  font-weight: 600;
  border-radius: 8px;
  padding: 4px 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out-soft), color var(--motion-fast) var(--ease-out-soft);
}
.ob-step-btn:hover { background: var(--clay-soft); }
.ob-step-btn.is-quiet {
  border-color: var(--hairline);
  color: var(--ink-soft);
}
.ob-step-btn.is-quiet:hover { color: var(--ink); background: var(--paper-cream); }
.ob-foot {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--hairline);
  font-size: 10.5px;
  color: var(--ink-faint);
}
.ob-foot kbd {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 10px;
  border: 1px solid var(--hairline);
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 0 4px;
  background: var(--surface-raised);
  color: var(--ink-soft);
}
@media (prefers-reduced-motion: reduce) {
  .ob-step-btn { transition: none; }
}
@media (max-width: 640px) {
  .ob-steps {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .ob-foot span { display: none; }
}
</style>
