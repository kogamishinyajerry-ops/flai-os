// 流式滚动跟随守卫（GuidePage 流式跟随 + 「回到底部」浮钮的判定内核）。
//
// 语义契约：
// - 距底 ≤ FOLLOW_THRESHOLD_PX 视为「贴底」，新 delta 允许程序性滚底跟随；
// - 用户上滚超过阈值即脱离跟随——此后新内容不再拉回，改喂浮钮计数指示；
// - 程序性滚动（scrollToBottom / 浮钮归底的平滑滚动）在飞期间的 scroll 事件
//   不改判跟随态：平滑动画中途会经过「距底 > 阈值」的区间，若照用户滚动
//   同法判定会把跟随误杀在半路上；
// - 程序性滚动结束后必须用真实距底重判一次（动画可能被用户 wheel 打断，
//   此时绝不可替用户恢复跟随）。

export const FOLLOW_THRESHOLD_PX = 100;

/**
 * 视口底缘距文档底的像素数（最小 0，内容不足一屏时为 0=天然贴底）。
 */
export function distanceFromBottom({ scrollHeight, clientHeight, scrollTop }) {
  for (const [name, value] of Object.entries({ scrollHeight, clientHeight, scrollTop })) {
    if (typeof value !== "number" || Number.isNaN(value)) {
      throw new TypeError(`${name} 必须是数字`);
    }
  }
  return Math.max(0, scrollHeight - clientHeight - scrollTop);
}

/**
 * 一次 scroll 事件后是否仍处于跟随态。
 * programmatic=true（程序性滚动在飞）时不改判，原样返回当前跟随语义 true。
 */
export function shouldFollowScroll(
  distance,
  { programmatic = false, threshold = FOLLOW_THRESHOLD_PX } = {},
) {
  if (typeof distance !== "number" || Number.isNaN(distance)) {
    throw new TypeError("distance 必须是数字");
  }
  if (programmatic === true) return true;
  return distance <= threshold;
}
