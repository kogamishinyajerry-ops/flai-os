<template>
  <nav class="create-journey" aria-label="创建任务步骤">
    <div class="create-journey-head">
      <el-icon aria-hidden="true"><Connection /></el-icon>
      <div>
        <h3>一页完成</h3>
        <p>按序核对能力、输入和边界；最后一次点击才真正创建任务。</p>
      </div>
    </div>
    <!-- 纵向步进器：方向恒为上→下（原 3+2 蛇形换行箭头互相矛盾）。节点状态
         三通道表达：状态图标 + 短文字标签 + tone 色彩，绝不只靠颜色。 -->
    <div class="create-journey-map">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        class="create-step"
        :class="[`step-${step.id}`, `tone-${step.tone}`, `state-${step.state}`]"
        :aria-label="`${step.label}：${step.stateLabel}。${step.detail}`"
        @click="$emit('navigate', step.id)"
      >
        <el-icon class="create-step-icon" aria-hidden="true">
          <component :is="ICONS[step.id]" />
        </el-icon>
        <span class="create-step-copy">
          <strong>{{ step.label }}</strong>
          <small>{{ step.detail }}</small>
        </span>
        <span class="create-step-state">
          <el-icon aria-hidden="true">
            <component :is="STATE_ICONS[step.state] || STATE_ICONS.pending" />
          </el-icon>
          <em>{{ step.stateLabel }}</em>
        </span>
      </button>
    </div>
  </nav>
</template>

<script setup>
import {
  Aim,
  CircleCheck,
  CircleClose,
  Clock,
  Connection,
  Cpu,
  EditPen,
  Loading,
  Lock,
  User,
  Warning,
} from "@element-plus/icons-vue";

defineProps({
  steps: { type: Array, default: () => [] },
});
defineEmits(["navigate"]);

const ICONS = {
  agent: Cpu,
  capability: Aim,
  input: EditPen,
  policy: Lock,
  submit: User,
};

// 状态图标（与短标签成对出现，均为 Element Plus 既有图标）：
// ready=已就绪 / review=待人核对 / pending=待处理 / working=在途 / error=真实失败。
const STATE_ICONS = {
  ready: CircleCheck,
  review: Warning,
  pending: Clock,
  working: Loading,
  error: CircleClose,
};
</script>

<style scoped>
.create-journey {
  margin-bottom: 20px;
}
.create-journey-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.create-journey-head > .el-icon {
  flex: none;
  color: var(--ink-soft);
  font-size: 16px;
}
.create-journey h3 {
  margin: 0 0 2px;
  color: var(--ink);
  font-size: 13.5px;
  font-weight: 600;
}
.create-journey p {
  margin: 0;
  color: var(--ink-faint);
  font-size: 11.5px;
  line-height: 1.45;
}
/* 去盒化：无外框无底色，节点间 hairline 分区；图标列左侧一条发丝线连接，
   承担「流向」语义（纯布局 hairline，非图标）。 */
.create-journey-map {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--hairline-soft);
}
.create-step {
  --_row-pad: 9px;
  position: relative;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
  padding: var(--_row-pad) 6px;
  border: none;
  border-top: 1px solid var(--hairline-soft);
  border-radius: 8px;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.create-step:first-child {
  border-top: none;
}
.create-step:hover {
  background: var(--hover-tint);
}
.create-step:focus-visible {
  outline: 2px solid var(--focus-ring-clay);
  outline-offset: 2px;
}
.create-step-icon {
  position: relative;
  flex: none;
  width: 28px;
  height: 28px;
  margin-top: 1px;
  border-radius: 8px;
  background: var(--paper-canvas-b, var(--paper-rail));
  color: var(--ink-soft);
  font-size: 16px;
}
/* 行间连接发丝线：图标恒顶对齐，间距=两行 padding + hairline，与行高无关。 */
.create-step:not(:last-child) .create-step-icon::after {
  content: "";
  position: absolute;
  top: calc(100% + 1px);
  left: 50%;
  width: 1px;
  height: calc(2 * var(--_row-pad) + 1px);
  background: var(--hairline-soft);
}
.create-step-copy {
  min-width: 0;
  flex: 1 1 200px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.create-step strong {
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.3;
}
.create-step small {
  color: var(--ink-faint);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.create-step-state {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 5px;
  color: var(--ink-faint);
  font-size: 11px;
  line-height: 1.2;
}
.create-step-state .el-icon {
  font-size: 13px;
}
.create-step-state em {
  font-style: normal;
  white-space: nowrap;
}
/* 色彩通道（信任色锁）：clay=工作；amber=待核/待签/受限/不确定；红=真实失败；
   就绪/完成类恒中性墨，不给绿。 */
.tone-work .create-step-icon {
  color: var(--clay);
  background: var(--clay-soft);
}
.tone-work .create-step-state {
  color: var(--clay);
}
.tone-pending .create-step-icon,
.tone-pending .create-step-state {
  color: var(--trust-pending);
}
.tone-fail .create-step-icon,
.tone-fail .create-step-state {
  color: var(--trust-fail);
}
@media (max-width: 479px) {
  .create-step-state {
    /* 100% 基值 + margin-left 38px 会让该行比容器宽出 38px（375px 实测溢出
       16px）；基值须先扣掉缩进，flex-shrink:0（flex:none）下才不会撑破视口。 */
    flex-basis: calc(100% - 38px);
    margin-top: 0;
    margin-left: 38px;
  }
}
</style>
