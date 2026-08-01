const BOUNDARY_NAME = "FLAi-OS UI 验收只读边界";

export class UiAcceptanceBoundaryError extends Error {
  constructor(channel) {
    super(`${BOUNDARY_NAME}已阻止 ${channel}`);
    this.name = "UiAcceptanceBoundaryError";
    this.channel = channel;
  }
}

function deny(channel) {
  return () => {
    throw new UiAcceptanceBoundaryError(channel);
  };
}

function replace(target, key, value, channel) {
  if (!target || !(key in target)) return false;
  try {
    Object.defineProperty(target, key, {
      configurable: false,
      enumerable: false,
      writable: false,
      value,
    });
    if (target[key] !== value) {
      throw new Error("替换后校验失败");
    }
  } catch {
    throw new UiAcceptanceBoundaryError(`无法封锁 ${channel}`);
  }
  return true;
}

/**
 * 验收 iframe 的单一副作用边界。
 *
 * 必须在动态 import 正式应用代码之前安装。sandbox 负责隔离同源存储，这里再
 * fail-closed 阻断所有常见主动网络出口与 Storage 写方法：即使未来组件新增
 * mounted 请求或漏掉 acceptanceMode 分支，也只能显式报错，不能碰真实后端。
 */
export function installUiAcceptanceBoundary(runtime = globalThis) {
  if (runtime.__FLAI_UI_ACCEPTANCE_BOUNDARY__) {
    return runtime.__FLAI_UI_ACCEPTANCE_BOUNDARY__;
  }

  // 浏览器中的验收 App 只能在不带 allow-same-origin 的 sandbox 内运行。
  // opaque origin 从根上切断共享 storage/cookie/parent document；不满足即停止。
  if (runtime.document && runtime.origin !== "null") {
    throw new UiAcceptanceBoundaryError("opaque-origin sandbox");
  }

  const blocked = [];
  const block = (target, key, channel, value = deny(channel)) => {
    if (replace(target, key, value, channel)) blocked.push(channel);
  };

  block(runtime, "fetch", "fetch");
  block(
    runtime,
    "XMLHttpRequest",
    "XMLHttpRequest",
    class BlockedXMLHttpRequest {
      constructor() {
        throw new UiAcceptanceBoundaryError("XMLHttpRequest");
      }
    },
  );
  block(
    runtime,
    "WebSocket",
    "WebSocket",
    class BlockedWebSocket {
      constructor() {
        throw new UiAcceptanceBoundaryError("WebSocket");
      }
    },
  );
  block(
    runtime,
    "EventSource",
    "EventSource",
    class BlockedEventSource {
      constructor() {
        throw new UiAcceptanceBoundaryError("EventSource");
      }
    },
  );

  block(runtime.navigator, "sendBeacon", "sendBeacon", () => false);

  for (const method of ["setItem", "removeItem", "clear"]) {
    block(runtime.Storage?.prototype, method, `Storage.${method}`);
  }
  let indexedDatabase = null;
  try {
    indexedDatabase = runtime.indexedDB;
  } catch {
    // opaque-origin sandbox 可能直接拒绝读取；已是 fail-closed 状态。
  }
  for (const method of ["open", "deleteDatabase"]) {
    block(indexedDatabase, method, `indexedDB.${method}`);
  }

  const boundary = Object.freeze({
    mode: "read-only",
    blocked: Object.freeze(blocked),
  });
  Object.defineProperty(runtime, "__FLAI_UI_ACCEPTANCE_BOUNDARY__", {
    configurable: false,
    enumerable: false,
    writable: false,
    value: boundary,
  });
  return boundary;
}
