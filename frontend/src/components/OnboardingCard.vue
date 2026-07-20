<template>
  <!-- 首登三步引导（评审 N2）：纯指引卡——不追踪完成态、不打勾表演进度
       （没有真实完成信号就不显示完成标记，诚实地板）；「不再显示」持久
       记忆（localStorage，按浏览器），老手一次点掉永不再扰。所有按钮只
       预填/聚焦，绝不代发代建（人是唯一发起者）。 -->
  <div v-if="visible" class="onboarding-card">
    <div class="ob-head">
      <span class="ob-title">第一次用？三步看懂这个平台</span>
      <button type="button" class="ob-dismiss" @click="dismiss">不再显示</button>
    </div>
    <div class="ob-mobile-summary">
      <span>先跑演示，或直接说需求；结果仍由你亲手签发。</span>
      <div class="ob-mobile-actions">
        <button type="button" class="ob-step-btn" @click="$emit('demo')">跑演示</button>
        <button type="button" class="ob-step-btn is-quiet" @click="$emit('say')">直接说</button>
      </div>
    </div>
    <ol class="ob-steps">
      <li class="ob-step">
        <span class="ob-num">1</span>
        <span class="ob-step-tx"><b>跑一个演示任务</b>——平台自带的 Hello 示例（无业务含义），一分钟看完「提交 → 运行 → 产物」全流程。</span>
        <button type="button" class="ob-step-btn" @click="$emit('demo')">去跑演示 →</button>
      </li>
      <li class="ob-step">
        <span class="ob-num">2</span>
        <span class="ob-step-tx"><b>说一句真实需求</b>——用下方输入框或意图卡；导引产出的是方案草案，创建与提交始终由你亲手完成。</span>
        <button type="button" class="ob-step-btn is-quiet" @click="$emit('say')">开始说 ↓</button>
      </li>
      <li class="ob-step">
        <span class="ob-num">3</span>
        <span class="ob-step-tx"><b>结果等人工签发</b>——创建时点名你后，右上角状态坞会亮「点名请你签」；未点名任务只显示为待人工签发。</span>
      </li>
    </ol>
    <div class="ob-foot">找任务 / 会话 / Agent，按 <kbd>⌘K</kbd>（Windows 用 <kbd>Ctrl</kbd><kbd>K</kbd>）随时搜。</div>
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
  margin-top: 22px;
  text-align: left;
  background: var(--paper-rail);
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg, 12px);
  padding: 14px 16px 12px;
}
.ob-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.ob-mobile-summary { display: none; }
.ob-title {
  flex: 1 1 auto;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--ink-soft);
  letter-spacing: 0.3px;
}
.ob-dismiss {
  flex: none;
  border: none;
  background: none;
  padding: 2px 4px;
  font-size: 11.5px;
  color: var(--ink-faint);
  cursor: pointer;
}
.ob-dismiss:hover { color: var(--ink); }
.ob-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ob-step {
  display: flex;
  align-items: baseline;
  gap: 9px;
}
.ob-num {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  align-self: flex-start;
  font-size: 10.5px;
  font-weight: 800;
  color: var(--ink-soft);
  background: var(--surface-raised);
  border: 1px solid var(--hairline);
}
.ob-step-tx {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--ink-soft);
}
.ob-step-tx b { color: var(--ink); font-weight: 600; }
.ob-step-btn {
  flex: none;
  align-self: center;
  border: 1px solid var(--clay-softer);
  background: var(--surface-raised);
  color: var(--clay);
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  padding: 4px 10px;
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
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed var(--hairline);
  font-size: 11.5px;
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
  .onboarding-card {
    margin-top: var(--space-3);
    padding: var(--space-2) var(--space-3);
  }
  .ob-head { margin-bottom: var(--space-1); }
  .ob-steps,
  .ob-foot { display: none; }
  .ob-mobile-summary {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--ink-soft);
    font-size: var(--fs-xs);
    line-height: 1.45;
  }
  .ob-mobile-summary > span { flex: 1 1 auto; }
  .ob-mobile-actions {
    flex: none;
    display: flex;
    gap: var(--space-1);
  }
  .ob-step-btn { padding: 4px 8px; }
}
</style>
