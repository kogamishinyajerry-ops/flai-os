// P2.5 精确签收路由的共享只读投影。key 带认证 username，只用于隔离前端
// channel 世代；服务端仍从 HttpOnly session 自己判定 principal，客户端不能代传。
import { ref, watch } from "vue";
import { currentUser } from "./session.js";
import { acquireChannel, pokeReviewInbox } from "./liveFeed.js";

export const reviewInboxTasks = ref([]);
export const reviewInboxLoaded = ref(false);
export const reviewInboxError = ref("");
export const reviewInboxConnection = ref("idle");
export const reviewInboxLastSuccessAt = ref(null);
export const reviewInboxStale = ref(true);
export const reviewInboxResyncing = ref(false);
export const reviewInboxSyncError = ref("");

let handle = null;
let stops = [];
let refCount = 0;

function resetProjection() {
  reviewInboxTasks.value = [];
  reviewInboxLoaded.value = false;
  reviewInboxError.value = "";
  reviewInboxConnection.value = "idle";
  reviewInboxLastSuccessAt.value = null;
  reviewInboxStale.value = true;
  reviewInboxResyncing.value = false;
  reviewInboxSyncError.value = "";
}

function releaseHandle() {
  stops.forEach((stop) => stop());
  stops = [];
  handle?.release();
  handle = null;
}

function bindForCurrentUser() {
  releaseHandle();
  resetProjection();
  const username = currentUser.value?.username;
  if (!username || refCount <= 0) return;
  handle = acquireChannel(`review-inbox:${username}`);
  stops = [
    watch(handle.state.tasks, (v) => { reviewInboxTasks.value = v; }, { immediate: true }),
    watch(handle.state.loaded, (v) => { reviewInboxLoaded.value = v; }, { immediate: true }),
    watch(handle.state.error, (v) => { reviewInboxError.value = v; }, { immediate: true }),
    watch(handle.state.connection, (v) => { reviewInboxConnection.value = v; }, { immediate: true }),
    watch(handle.state.lastSuccessAt, (v) => { reviewInboxLastSuccessAt.value = v; }, { immediate: true }),
    watch(handle.state.stale, (v) => { reviewInboxStale.value = v; }, { immediate: true }),
    watch(handle.state.resyncing, (v) => { reviewInboxResyncing.value = v; }, { immediate: true }),
    watch(handle.state.syncError, (v) => { reviewInboxSyncError.value = v; }, { immediate: true }),
  ];
}

watch(() => currentUser.value?.username || null, bindForCurrentUser);

export function acquireReviewInbox() {
  refCount += 1;
  if (!handle) bindForCurrentUser();
}

export function releaseReviewInbox() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0) {
    releaseHandle();
    resetProjection();
  }
}

export function refreshReviewInbox() {
  const username = currentUser.value?.username;
  return username ? pokeReviewInbox(username) : Promise.resolve();
}
