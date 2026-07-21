import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  GUIDE_SAFE_AUTO_OUTBOX_KEY,
  createGuideSafeAutoOutbox,
  dispatchGuideSafeAutoIntent,
} from "../src/utils/guideSafeAutoOutbox.js";


class FakeStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}


function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}


async function waitFor(predicate, message = "condition was not reached") {
  for (let i = 0; i < 30; i += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.fail(message);
}


function sourceSlice(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(start, -1, `missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `missing source marker: ${endMarker}`);
  return source.slice(start, end);
}


function canonicalConversation(id, requestId, result = "完成") {
  return {
    id,
    status: "active",
    messages: [
      { role: "user", content: "执行" },
      {
        role: "assistant",
        content: result,
        recommendation: {
          execution: { request_id: requestId, status: "dispatched" },
        },
      },
    ],
  };
}


function assistantResponse(requestId, result = "完成") {
  return {
    message: {
      role: "assistant",
      content: result,
      recommendation: {
        execution: { request_id: requestId, status: "dispatched" },
      },
    },
  };
}


function createGuideSendHarness(guideSource, deps = {}) {
  // Execute the production send coordinator itself. The real outbox and real durable
  // dispatcher are injected; missing dependencies hard-fail instead of selecting a fallback.
  const sendHelpers = sourceSlice(
    guideSource,
    "function invalidateSendUi()",
    "function newTurnRequestId()",
  );
  const requestHelpers = sourceSlice(
    guideSource,
    "function newTurnRequestId()",
    "// 时段感问候",
  );
  const uploadFunction = sourceSlice(
    guideSource,
    "async function uploadPendingFiles",
    "function inputCount",
  );
  const sendFunction = sourceSlice(
    guideSource,
    "async function send()",
    "function collectCarriedFiles",
  );

  const storage = deps.storage || new FakeStorage();
  const outbox = createGuideSafeAutoOutbox({ storage });
  const factory = new Function("deps", `
    const restoring = { value: false };
    const draft = { value: "" };
    const pageError = { value: "" };
    const messages = { value: [] };
    const pendingFiles = { value: [] };
    const sending = { value: false };
    const outboxRecoveryBlocked = { value: false };
    const outboxRecoveryActive = { value: false };
    const conversationId = { value: "" };
    const conversationStatus = { value: "" };
    const started = { value: false };
    const route = { query: {} };
    const routeConversationId = {
      get value() {
        return typeof route.query.c === "string" && route.query.c ? route.query.c : "";
      },
    };
    const conversationReadOnly = {
      get value() {
        return (
          outboxRecoveryBlocked.value ||
          (!!routeConversationId.value && conversationId.value !== routeConversationId.value) ||
          (started.value && conversationStatus.value !== "active")
        );
      },
    };
    const router = {
      replace(target) {
        deps.replaces.push(target);
        if (!deps.preventRouteReplace) route.query = { ...(target.query || {}) };
        return Promise.resolve();
      },
    };
    const GUIDE_AGENT_ID = "guide_agent";
    const inFlightSends = new Map();
    const failedSends = new Map();
    let freshInFlightSend = null;
    let failedFreshSend = null;
    let internalConversationNavigation = null;
    let sendUiEpoch = 0;
    let conversationLoadEpoch = 0;
    let retryTurn = null;
    const guideSafeAutoOutbox = deps.outbox;
    const dispatchGuideSafeAutoIntent = deps.dispatchGuideSafeAutoIntent;
    const authenticatedPrincipal = () => deps.principal;
    const fetchMe = () => deps.fetchMe();
    const createConversation = (...args) => deps.createConversation(...args);
    const postMessage = (...args) => deps.postMessage(...args);
    const apiUploadFile = (...args) => deps.uploadFile(...args);
    const getConversation = (...args) => {
      deps.loads.push(args[0]);
      return deps.getConversation(...args);
    };
    const scrollToBottom = async () => {};
    const ensureConversationTasksFeed = () => {};
    const releaseConversationTasksFeed = () => {};
    let leaveGuard = null;
    let updateGuard = null;
    const onBeforeRouteLeave = (guard) => { leaveGuard = guard; };
    const onBeforeRouteUpdate = (guard) => { updateGuard = guard; };

    ${sendHelpers}
    ${requestHelpers}
    ${uploadFunction}
    ${sendFunction}

    async function loadConversation(id) {
      deps.loads.push(id);
      const conv = await deps.getConversation(id);
      if (!conv || conv.id !== id) throw new Error("canonical route mismatch");
      if (routeConversationId.value !== id) return;
      conversationId.value = id;
      conversationStatus.value = conv.status || "";
      started.value = true;
      messages.value = (conv.messages || []).map((message) => ({ ...message }));
    }

    function switchConversation(id, history = []) {
      conversationLoadEpoch++;
      invalidateSendUi();
      route.query = { c: id };
      restoring.value = false;
      messages.value = history.map((message) => ({ ...message }));
      conversationId.value = id;
      conversationStatus.value = "active";
      started.value = true;
      draft.value = "";
      pendingFiles.value = [];
      retryTurn = null;
      restoreConversationSendState(id);
    }

    function switchFresh() {
      conversationLoadEpoch++;
      invalidateSendUi();
      route.query = {};
      restoring.value = false;
      messages.value = [];
      conversationId.value = "";
      conversationStatus.value = "";
      started.value = false;
      draft.value = "";
      pendingFiles.value = [];
      retryTurn = null;
      restoreFreshSendState();
    }

    function setFiles(files) {
      pendingFiles.value = files.map((file, index) => ({
        uid: file.uid || "file_" + index,
        name: file.name,
        raw: file.raw || { name: file.name },
        status: file.status || "pending",
        fileId: file.fileId || null,
        error: "",
      }));
    }

    function outboxSnapshot() {
      try {
        return guideSafeAutoOutbox.read();
      } catch (error) {
        return { error: error.message };
      }
    }

    function state() {
      return {
        conversationId: conversationId.value,
        routeConversationId: route.query.c || "",
        messages: messages.value.map((message) => ({ ...message })),
        draft: draft.value,
        pendingFiles: pendingFiles.value.map((file) => ({
          name: file.name,
          status: file.status,
          fileId: file.fileId,
        })),
        sending: sending.value,
        started: started.value,
        conversationStatus: conversationStatus.value,
        conversationReadOnly: conversationReadOnly.value,
        outboxRecoveryBlocked: outboxRecoveryBlocked.value,
        pageError: pageError.value,
        retryRequestId: retryTurn && retryTurn.requestId,
        outbox: outboxSnapshot(),
      };
    }

    return {
      send,
      state,
      switchConversation,
      switchFresh,
      canLeave() { return leaveGuard(); },
      canUpdate(to) { return updateGuard(to); },
      setDraft(value) { draft.value = value; },
      setFiles,
    };
  `);

  return factory({
    outbox,
    dispatchGuideSafeAutoIntent,
    principal: deps.principal || { username: "alice", role: "agent_developer" },
    fetchMe: deps.fetchMe || (async () => true),
    replaces: deps.replaces || [],
    loads: deps.loads || [],
    preventRouteReplace: deps.preventRouteReplace === true,
    createConversation:
      deps.createConversation || (async () => ({ id: "created", status: "active" })),
    postMessage:
      deps.postMessage || (async () => { throw new Error("postMessage test seam missing"); }),
    uploadFile:
      deps.uploadFile || (async (raw) => ({ id: `uploaded_${raw.name}` })),
    getConversation:
      deps.getConversation || (async () => { throw new Error("canonical GET test seam missing"); }),
  });
}


test("guide sends only through the durable safe_auto coordinator", async () => {
  const api = await readFile(new URL("../src/api/conversations.js", import.meta.url), "utf8");
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");

  assert.match(api, /execution_mode:\s*executionMode/);
  assert.match(api, /request_id:\s*requestId/);
  assert.match(guide, /dispatchGuideSafeAutoIntent\(\{/);
  assert.match(guide, /turnRequestId\(content, fileIds\)/);
  assert.match(guide, /retryTurn\.fingerprint === fingerprint/);
  assert.doesNotMatch(guide, /Executable legacy harness seam|typeof dispatchGuideSafeAutoIntent/);
});


test("safe_auto plans expose backend facts and only legacy plans expose manual creation", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const workbench = await readFile(
    new URL("../src/views/WorkbenchSession.vue", import.meta.url),
    "utf8",
  );

  assert.match(guide, /guidePlanAllowsManualCreate\(m\.recommendation\)/);
  assert.match(guide, /版本化 DAG 缺少权威执行回执/);
  assert.match(guide, /已禁止逐节点创建/);
  assert.match(guide, /decision === 'awaiting_plan'/);
  assert.match(workbench, /guidePlanAllowsManualCreate\(plan\)/);
  assert.match(workbench, /版本化 DAG 没有权威执行回执，已禁止逐节点手动创建/);
});


test("existing conversation clears outbox only after canonical GET confirms request id", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const storage = new FakeStorage();
  const posts = [];
  const loads = [];
  let requestId = null;
  const harness = createGuideSendHarness(guide, {
    storage,
    loads,
    postMessage: async (conversationId, content, fileIds, options) => {
      requestId = options.requestId;
      posts.push({ conversationId, content, fileIds, ...options });
      assert.notEqual(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
      return assistantResponse(requestId);
    },
    getConversation: async (id) => canonicalConversation(id, requestId),
  });

  harness.switchConversation("A");
  harness.setDraft("执行");
  await harness.send();

  assert.equal(posts.length, 1);
  assert.equal(posts[0].conversationId, "A");
  assert.equal(posts[0].executionMode, "safe_auto");
  assert.deepEqual(loads, ["A"]);
  assert.equal(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
  assert.equal(harness.state().pageError, "");
  assert.equal(harness.state().outbox, null);
});


test("fresh create and message share one request id and bind before posting", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const storage = new FakeStorage();
  const createCalls = [];
  const postCalls = [];
  let requestId = null;
  const harness = createGuideSendHarness(guide, {
    storage,
    createConversation: async ({ agentId, requestId: id }) => {
      const record = JSON.parse(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY));
      createCalls.push({ agentId, requestId: id, phase: record.phase });
      requestId = id;
      return { id: "C", status: "active" };
    },
    postMessage: async (conversationId, content, fileIds, options) => {
      const record = JSON.parse(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY));
      postCalls.push({ conversationId, content, fileIds, ...options, bound: record.conversation_id });
      return assistantResponse(options.requestId);
    },
    getConversation: async (id) => canonicalConversation(id, requestId),
  });

  harness.switchFresh();
  harness.setDraft("执行");
  await harness.send();

  assert.deepEqual(createCalls, [{
    agentId: "guide_agent",
    requestId,
    phase: "creating_conversation",
  }]);
  assert.equal(postCalls.length, 1);
  assert.equal(postCalls[0].requestId, requestId);
  assert.equal(postCalls[0].conversationId, "C");
  assert.equal(postCalls[0].bound, "C");
  assert.equal(harness.state().routeConversationId, "C");
  assert.equal(harness.state().conversationId, "C");
  assert.equal(harness.state().outbox, null);
});


test("uncertain canonical state retries in place with the exact same request id", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const postIds = [];
  let canonicalReads = 0;
  const harness = createGuideSendHarness(guide, {
    postMessage: async (_conversationId, _content, _fileIds, options) => {
      postIds.push(options.requestId);
      return assistantResponse(options.requestId);
    },
    getConversation: async (id) => {
      canonicalReads += 1;
      return canonicalReads === 1
        ? { id, status: "active", messages: [] }
        : canonicalConversation(id, postIds[0]);
    },
  });

  harness.switchConversation("A");
  harness.setDraft("执行");
  await harness.send();
  const failed = harness.state();
  assert.match(failed.pageError, /OUTBOX_CONFIRMATION_MISSING/);
  assert.equal(failed.outboxRecoveryBlocked, false);
  assert.equal(failed.conversationReadOnly, false);
  assert.equal(failed.draft, "执行");
  assert.equal(failed.outbox.phase, "awaiting_confirmation");

  await harness.send();
  assert.equal(postIds.length, 2);
  assert.equal(postIds[1], postIds[0]);
  assert.equal(harness.state().outbox, null);
  assert.equal(harness.state().pageError, "");
  assert.equal(harness.state().draft, "");
});


test("a missing durable retry record locks before upload and cannot rotate request id", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const storage = new FakeStorage();
  const postIds = [];
  let uploads = 0;
  const harness = createGuideSendHarness(guide, {
    storage,
    postMessage: async (_conversationId, _content, _fileIds, options) => {
      postIds.push(options.requestId);
      return assistantResponse(options.requestId);
    },
    getConversation: async (id) => ({ id, status: "active", messages: [] }),
    uploadFile: async () => {
      uploads += 1;
      return { id: "must-not-upload" };
    },
  });

  harness.switchConversation("A");
  harness.setDraft("执行");
  await harness.send();
  assert.equal(postIds.length, 1);
  storage.removeItem(GUIDE_SAFE_AUTO_OUTBOX_KEY);

  harness.setFiles([{ name: "new.txt", raw: { name: "new.txt" } }]);
  await harness.send();
  const state = harness.state();

  assert.equal(uploads, 0);
  assert.equal(postIds.length, 1);
  assert.equal(state.retryRequestId, postIds[0]);
  assert.equal(state.outboxRecoveryBlocked, true);
  assert.match(state.pageError, /OUTBOX_RECORD_MISSING/);
  assert.equal(harness.canLeave(), false);
  assert.equal(harness.canUpdate({ query: { c: "B" } }), false);
});


test("route or payload drift against a pending outbox fails before attachment upload", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  let uploads = 0;
  let posts = 0;
  const harness = createGuideSendHarness(guide, {
    postMessage: async (_conversationId, _content, _fileIds, options) => {
      posts += 1;
      return assistantResponse(options.requestId);
    },
    getConversation: async (id) => ({ id, status: "active", messages: [] }),
    uploadFile: async () => {
      uploads += 1;
      return { id: "must-not-upload" };
    },
  });

  harness.switchConversation("A");
  harness.setDraft("执行 A");
  await harness.send();
  assert.equal(posts, 1);
  assert.equal(harness.canUpdate({ query: { c: "B" } }), false);

  // Deliberately bypass the production route guard. The send preflight must still stop B
  // before upload and leave A's one-tab outbox untouched.
  harness.switchConversation("B");
  harness.setDraft("执行 B");
  harness.setFiles([{ name: "b.txt", raw: { name: "b.txt" } }]);
  await harness.send();
  const state = harness.state();

  assert.equal(uploads, 0);
  assert.equal(posts, 1);
  assert.equal(state.outbox.conversation_id, "A");
  assert.equal(state.outboxRecoveryBlocked, true);
  assert.match(state.pageError, /OUTBOX_INTENT_MISMATCH/);
});


test("fresh URL binding mismatch retains the bound outbox and sends no message", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  let creates = 0;
  let posts = 0;
  let gets = 0;
  const harness = createGuideSendHarness(guide, {
    preventRouteReplace: true,
    createConversation: async () => {
      creates += 1;
      return { id: "C", status: "active" };
    },
    postMessage: async () => {
      posts += 1;
      return assistantResponse("never");
    },
    getConversation: async () => {
      gets += 1;
      return canonicalConversation("C", "never");
    },
  });

  harness.switchFresh();
  harness.setDraft("执行");
  await harness.send();
  const state = harness.state();

  assert.equal(creates, 1);
  assert.equal(posts, 0);
  assert.equal(gets, 0);
  assert.equal(state.outbox.conversation_id, "C");
  assert.equal(state.outboxRecoveryBlocked, true);
  assert.equal(state.conversationReadOnly, true);
  assert.match(state.pageError, /URL 绑定失败/);
});


test("forced route drift cannot retarget a fresh durable send or take over the new page", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const createC = deferred();
  const posts = [];
  let requestId = null;
  const harness = createGuideSendHarness(guide, {
    createConversation: ({ requestId: id }) => {
      requestId = id;
      return createC.promise;
    },
    postMessage: async (conversationId, content, fileIds, options) => {
      posts.push({ conversationId, content, fileIds, requestId: options.requestId });
      return assistantResponse(options.requestId, "C result");
    },
    getConversation: async (id) => canonicalConversation(id, requestId, "C result"),
  });

  harness.switchFresh();
  harness.setDraft("执行 C");
  const sendC = harness.send();
  await waitFor(() => harness.state().outbox?.phase === "creating_conversation");
  assert.equal(harness.canLeave(), false);
  assert.equal(harness.canUpdate({ query: { c: "B" } }), false);

  // Deliberately bypass the router guard to prove the coordinator still owns target C.
  harness.switchConversation("B", [{ role: "assistant", content: "B history" }]);
  createC.resolve({ id: "C", status: "active" });
  await sendC;

  assert.deepEqual(posts, [{
    conversationId: "C",
    content: "执行 C",
    fileIds: [],
    requestId,
  }]);
  assert.equal(harness.state().routeConversationId, "B");
  assert.equal(harness.state().conversationId, "B");
  assert.deepEqual(harness.state().messages.map((message) => message.content), ["B history"]);
  assert.equal(harness.state().outbox, null);
  assert.equal(harness.canLeave(), true);
});


test("unwritable session storage fails closed before attachment/create/message POST", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const storage = new FakeStorage();
  storage.setItem = () => {
    throw new Error("quota denied");
  };
  let creates = 0;
  let posts = 0;
  let uploads = 0;
  const harness = createGuideSendHarness(guide, {
    storage,
    createConversation: async () => {
      creates += 1;
      return { id: "never" };
    },
    postMessage: async () => {
      posts += 1;
      return assistantResponse("never");
    },
    uploadFile: async () => {
      uploads += 1;
      return { id: "must-not-upload" };
    },
  });

  harness.switchFresh();
  harness.setFiles([{ name: "evidence.txt", raw: { name: "evidence.txt" } }]);
  harness.setDraft("执行");
  await harness.send();
  const state = harness.state();

  assert.equal(uploads, 0);
  assert.equal(creates, 0);
  assert.equal(posts, 0);
  assert.equal(state.draft, "执行");
  assert.equal(state.outboxRecoveryBlocked, true);
  assert.equal(state.conversationReadOnly, true);
  assert.match(state.pageError, /OUTBOX_STORAGE_WRITE_FAILED/);
  assert.match(guide, /v-if="conversationReadOnly && !pageError"/);
});
