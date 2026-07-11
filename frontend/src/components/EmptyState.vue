<template>
  <!-- 不透传默认 slot：透传会让 el-empty 恒渲染空 .el-empty__bottom（多出 20px
       上边距）；当前 8 个调用方均无 slot 内容，需要时再显式加。 -->
  <el-empty :description="description" :image="img" :image-size="size" />
</template>

<script setup>
// 品牌化空态：收敛全站 8 处裸 el-empty 为三个语义变体，各配一张漫画线稿插画
// （AI 生成，暖白+clay 单强调色，透明底 PNG）。description 文案与既有调用方
// 逐字一致（不动断言面）；插画比默认灰线框图信息密度高，显式尺寸整体上调
// （如 FeedbackPage 80→96）为刻意设计，非等价替换。
import { computed } from "vue";
import imgData from "../assets/illustrations/empty-data.png";
import imgAction from "../assets/illustrations/empty-action.png";
import imgLog from "../assets/illustrations/empty-log.png";

const props = defineProps({
  // data=无数据目录类 / action=待你操作引导类 / log=日志事件类（更小更安静）
  variant: { type: String, default: "data" },
  description: { type: String, default: "暂无数据" },
  imageSize: { type: Number, default: 0 },
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
</style>
