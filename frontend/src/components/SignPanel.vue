<template>
  <!-- 人签面共享子组件（Gate2-T2 CG-A/CG-B 治本 SSOT）：两处签发面
       （TaskDetail 详情 .review-card / StatusCenter 速览 .peek-review-card）共享此一处
       「签发眉标 + 背书句 + 签发人行 + 意见框 + 动作行」的**结构与文案**，从机制上
       杜绝各改一面（复制必腐烂）。
       纯表现层：签发 API / 二次确认 / 记名 / fail-closed / 先看后签禁批 逻辑全部留在
       父组件，本组件只收 props + 抛 approve/reject/update:comment 事件 + 暴露 approve
       按钮原生 el 供 teal burst 定位（getApproveNativeEl）。
       信任色锁：approve 用 --trust-signed（teal 人签唯一合法槽，走 .sign-approve 一处
       SSOT），reject 走 EP danger plain（真驳回=红语义），绝不引入绿（--trust-real）。
       root 常带 .sign-surface（全局 App.vue 提供容器工艺：teal 顶饰条/边框/圆角/阴影/
       焦点环）；父传入 .review-card / .peek-review-card 作语义与 e2e 选择器锚。 -->
  <div class="sign-surface">
    <div class="sign-heading">签发</div>
    <p class="sign-note">批准即代表你作为工程师背书该产物——签发权在你，平台不代签。</p>
    <div class="sign-signer">签发人：<strong class="sign-signer-name">{{ signerName }}</strong>（登录身份，签发记名不可代填）</div>
    <el-input
      :model-value="comment"
      type="textarea"
      :rows="2"
      placeholder="签发意见（可选）"
      class="sign-input sign-comment"
      @update:model-value="$emit('update:comment', $event)"
    />
    <div class="sign-actions">
      <!-- 批准=人签，teal（--trust-signed）经 .sign-approve 一处 SSOT；approveClass 只作
           e2e/语义锚（approve-btn / peek-approve），不承载配色。ref 供放行成功 teal burst
           定位（动效系统 v1 E2，唯一 teal 许可点）。禁批=先看后签（父传 approveDisabled）。 -->
      <el-button
        ref="approveEl"
        :class="['sign-approve', approveClass]"
        :loading="reviewing"
        :disabled="approveDisabled"
        @click="$emit('approve')"
      >批准放行</el-button>
      <!-- 否定键统一「驳回」+ danger plain（CG-B：让 teal 批准成唯一无争议主操作）。 -->
      <el-button type="danger" plain :loading="reviewing" @click="$emit('reject')">驳回</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  signerName: { type: String, default: "" },
  comment: { type: String, default: "" },
  reviewing: { type: Boolean, default: false },
  // 先看后签禁批（Face2 传 artifactsPending；Face1 无产物门，默认 false）。
  approveDisabled: { type: Boolean, default: false },
  // e2e/语义锚类（review-card 侧传 approve-btn，peek 侧传 peek-approve）——不承载配色。
  approveClass: { type: String, default: "" },
});
defineEmits(["approve", "reject", "update:comment"]);

// 放行成功 teal burst 的定位来源（动效系统 v1 E2）：el-button 组件 ref 通过 .ref
// 暴露原生 DOM（element-plus expose 契约）。以显式 getter 暴露原生 el，避免依赖
// defineExpose 对 ref 的自动解包语义，父组件调用无歧义。
const approveEl = ref(null);
defineExpose({ getApproveNativeEl: () => approveEl.value?.ref });
</script>

<style scoped>
/* ── 签发面内层工艺 SSOT（两面共享，data-v 属本组件）──
 * 容器工艺（.sign-surface 背景/teal 顶饰条/边框/圆角/阴影/焦点环）在全局 App.vue；
 * 意见框剥离（.sign-input textarea.el-textarea__inner）亦在全局。本处只放两面共享的
 * 内层排版：眉标 climax / 背书句 / 签发人行 / 动作行 / teal 批准键。 */

/* 「签发」climax 眉标（CG-A）：专属 serif，比旧 12px 眉标重——人签是「改变工程状态
   的唯一合法通道」，标题本身即高潮，不再是通用版块小标题。 */
.sign-heading {
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 0.2px;
  color: var(--ink);
  margin-bottom: 10px;
}
.sign-note {
  font-size: 12.5px;
  color: var(--ink-soft);
  line-height: 1.6;
  margin: 0 0 10px;
}
/* 签发人行（CG-B）：signerName 抬一档权重（ink + 600），不再是全卡最淡；括注两面统一。 */
.sign-signer {
  font-size: 12.5px;
  color: var(--ink-soft);
  margin-bottom: 10px;
}
.sign-signer-name {
  color: var(--ink);
  font-weight: 600;
}
.sign-comment {
  margin-bottom: 10px;
}
.sign-actions {
  display: flex;
  gap: 10px;
}
/* teal 批准键一处 SSOT（信任色锁：--trust-signed 人签唯一合法槽，绝不用绿）。
   hover/active 深调走 --trust-signed-deep（App.vue color-mix，暗色自动变亮不变暗）。 */
.sign-approve {
  --el-button-bg-color: var(--trust-signed);
  --el-button-border-color: var(--trust-signed);
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: var(--trust-signed-deep);
  --el-button-hover-border-color: var(--trust-signed-deep);
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: var(--trust-signed-deep);
  --el-button-active-border-color: var(--trust-signed-deep);
}
</style>
