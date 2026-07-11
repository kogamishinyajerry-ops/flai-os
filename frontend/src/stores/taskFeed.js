// 任务清单共享轮询源（范式 2c）：StatusDock 与任务台左栏此前各自维护一条
// 5s 轮询链，拉的是同一个 listTasks(limit=100)——合并为模块级单例，引用计数
// 订阅，页面上有几个订阅者都只有一条链、一份数据。
// 诚实口径全承袭：最近窗口 100 条（窗口外不虚报）；轮询失败保留上次数据下
// tick 自愈；从未成功过 loaded=false（无数据不装有数据）。
import { ref } from "vue";
import { listTasks } from "../api/tasks";

export const feedTasks = ref([]);
export const feedLoaded = ref(false); // 至少成功拉到过一次
export const feedError = ref(""); // 仅从未成功过时非空，供订阅者如实报首载失败

let refCount = 0;
let pollTimer = null;
let inflight = null; // 并发 acquire / tick 去重：同一时刻至多一个在途请求

async function refresh() {
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      feedTasks.value = await listTasks({ limit: 100 });
      feedLoaded.value = true;
      feedError.value = "";
    } catch (err) {
      if (feedLoaded.value === false) feedError.value = err.detail || err.message || "加载失败";
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

// 链式轮询纪律（与全站一致）：上一轮落地才排下一轮；hidden 跳过本轮仍续轮；
// refCount 归零即停链（兼任 disposed 语义——in-flight finally 不再续排）。
function schedulePoll() {
  clearPoll();
  pollTimer = setTimeout(async () => {
    try {
      if (!document.hidden) await refresh();
    } finally {
      if (refCount > 0) schedulePoll();
    }
  }, 5000);
}

function clearPoll() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

// 组件 onMounted 调 acquire、onUnmounted 调 release。acquire 总触发一次即时
// refresh（inflight 去重，新订阅者不吃 5s 陈旧窗口）；!pollTimer 守卫保证
// 同帧多订阅者只排一条链。
export function acquireTaskFeed() {
  refCount += 1;
  refresh().finally(() => {
    if (refCount > 0 && !pollTimer) schedulePoll();
  });
}

export function releaseTaskFeed() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0) clearPoll();
}
