// 兼容 shim（批A 迁移期）：导出名/语义与旧 taskFeed 完全一致,内部直连
// liveFeed 'tasks' channel。全部消费方直连 liveFeed 后本文件删除。
import { ref, watch } from "vue";
import { acquireChannel } from "./liveFeed";

export const feedTasks = ref([]);
export const feedLoaded = ref(false);
export const feedError = ref("");

let handle = null;
let stops = [];
let refCount = 0;

export function acquireTaskFeed() {
  if (!handle) {
    handle = acquireChannel("tasks");
    stops = [
      watch(handle.state.tasks, (v) => { feedTasks.value = v; }, { immediate: true }),
      watch(handle.state.loaded, (v) => { feedLoaded.value = v; }, { immediate: true }),
      watch(handle.state.error, (v) => { feedError.value = v; }, { immediate: true }),
    ];
  }
  refCount += 1;
}

export function releaseTaskFeed() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0 && handle) {
    stops.forEach((s) => s());
    stops = [];
    handle.release();
    handle = null;
    // 票 #65 互审 F1：末位订阅者释放后清空共享快照——链已停，旧任务列表不得
    // 残留充当信号（侧栏 brand 动态涡轮在登出/身份失效后必须回落静止，诚实
    // 地板：信号消失必须回落）。此时全部持有方已卸载/释放，无人再读这三枚 ref；
    // 重新 acquire 时 watch immediate 会从新 channel 重新水合。
    feedTasks.value = [];
    feedLoaded.value = false;
    feedError.value = "";
  }
}
