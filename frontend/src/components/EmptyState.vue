<template>
  <!-- 不透传默认 slot：透传会让 el-empty 恒渲染空 .el-empty__bottom（多出 20px
       上边距）；既有调用方均无 slot 内容，需要时再显式加。 -->
  <!-- line 轻量态（W2）：纯数据空态用——无插画单行文字。与 variant 正交，
       不传 tier 时严格走原插画分支，既有调用方零改动。 -->
  <div v-if="tier === 'line'" class="empty-line">{{ description }}</div>
  <el-empty v-else :description="description" :image="img" :image-size="size" />
</template>

<script setup>
// 品牌化空态：收敛全站裸 el-empty 为三个语义变体，各配一张漫画线稿插画
// （AI 生成，暖白+clay 单强调色，透明底 PNG）。description 文案与既有调用方
// 逐字一致（不动断言面）；插画比默认灰线框图信息密度高，显式尺寸整体上调
// （如 FeedbackPage 80→96）为刻意设计，非等价替换。
// tier="line"（W2 新增）：纯数据空态的轻量态，无插画单行文字——variant 语义
// 不变（仍决定 log/action/data 分类），line 态下只是不选图不渲染 el-empty。
// 默认 tier="full" 保持插画渲染路径，向后兼容。
import { computed } from "vue";
import imgData from "../assets/illustrations/empty-data.png";
import imgAction from "../assets/illustrations/empty-action.png";
import imgLog from "../assets/illustrations/empty-log.png";

const props = defineProps({
  // data=无数据目录类 / action=待你操作引导类 / log=日志事件类（更小更安静）
  variant: { type: String, default: "data" },
  description: { type: String, default: "暂无数据" },
  imageSize: { type: Number, default: 0 },
  // full=插画版（默认，向后兼容）/ line=轻量单行态（W2，纯数据空态用）
  tier: { type: String, default: "full" },
});

const IMG = { data: imgData, action: imgAction, log: imgLog };
const DEFAULT_SIZE = { data: 96, action: 104, log: 72 };

const img = computed(() => IMG[props.variant] || imgData);
const size = computed(() => props.imageSize || DEFAULT_SIZE[props.variant] || 96);
</script>

<style scoped>
/* 极轻缓浮动 loop：纯装饰（明示，非信号绑定）——transform-only，不动 el-empty
 * 自身的 width/尺寸样式（那是内联 style，不受此覆盖）。三张插画共用同一节奏。 */
@keyframes empty-illustration-float {
  0%,
  100% {
    transform: translateY(-3px);
  }
  50% {
    transform: translateY(3px);
  }
}
:deep(.el-empty__image img) {
  animation: empty-illustration-float 5.6s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.el-empty__image img) {
    animation: none;
  }
}
/* line 轻量态（W2）：无插画单行文字——密度语法走 token，左对齐跟随父容器
 * （块级元素默认行为，不显式设 text-align，随宿主布局）。 */
.empty-line {
  margin: 0;
  padding: var(--space-2) 0;
  font-size: var(--fs-sm);
  /* ink-soft 而非 ink-faint（Codex R1 P2）：12.5px 正文阈 4.5:1——faint 亮色
   * 仅 ~2.5:1，且去插画后本行是该版块唯一空态指示，必须可读。 */
  color: var(--ink-soft);
  line-height: 1.5;
}
</style>
