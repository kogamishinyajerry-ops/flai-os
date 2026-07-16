// 响应式本地日界（批次三 G4，抽取自 CompletionSeal 午夜翻页修复 Codex R1-P3）：
// 终态/静态面停轮询后，裸读 new Date() 的 computed 永不重算——页面跨过本地
// 午夜后「昨日完成」的裸 HH:MM 会被误读成今天。单发 setTimeout 对准下一个
// 本地午夜 +1s 翻一次并再武装（零轮询）；组件卸载即清。
// SSOT 分工：只需要「日界」的面（CompletionSeal 落定时刻 / MePage 行级时钟）
// 用本 composable；已有 1s ticker 的面（StatusCenter 活跳时长）由自己的
// nowTick 派生日界，不重复挂第二只表。
import { ref, onMounted, onUnmounted } from "vue";

export function useTodayKey() {
  const todayKey = ref(new Date().toDateString());
  let timer = null;
  function arm() {
    const now = new Date();
    const nextMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
    timer = setTimeout(() => {
      todayKey.value = new Date().toDateString();
      arm();
    }, nextMidnight.getTime() - now.getTime());
  }
  onMounted(arm);
  onUnmounted(() => {
    if (timer !== null) clearTimeout(timer);
  });
  return todayKey;
}
