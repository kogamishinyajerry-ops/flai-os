// 兼容 shim（批A 迁移期）：导出名/语义与旧 taskFeed 完全一致,内部直连
// liveFeed 'tasks' channel。全部消费方直连 liveFeed 后本文件删除。
import { ref, watch } from "vue";
import { acquireChannel } from "./liveFeed";

export const feedTasks = ref([]);
export const feedLoaded = ref(false);
export const feedError = ref("");
export const feedConnection = ref("idle");
export const feedLastSuccessAt = ref(null);
export const feedStale = ref(true);
export const feedResyncing = ref(false);
export const feedSyncError = ref("");

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
      watch(handle.state.connection, (v) => { feedConnection.value = v; }, { immediate: true }),
      watch(handle.state.lastSuccessAt, (v) => { feedLastSuccessAt.value = v; }, { immediate: true }),
      watch(handle.state.stale, (v) => { feedStale.value = v; }, { immediate: true }),
      watch(handle.state.resyncing, (v) => { feedResyncing.value = v; }, { immediate: true }),
      watch(handle.state.syncError, (v) => { feedSyncError.value = v; }, { immediate: true }),
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
  }
}
