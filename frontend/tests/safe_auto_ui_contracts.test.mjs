import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


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


function createGuideSendHarness(guideSource, deps = {}) {
  // Execute the production send coordinator itself with tiny ref/router/API seams. This is
  // deliberately not a reimplementation: route switches and deferred network completions
  // exercise the same functions shipped by GuidePage.vue.
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
  const resetFunction = sourceSlice(
    guideSource,
    "function resetToFresh",
    "// 恢复在途标记",
  );
  const loadFunctions = sourceSlice(
    guideSource,
    "function isCurrentConversationLoad",
    "onMounted(() =>",
  );

  const factory = new Function("deps", `
    const restoring = { value: false };
    const draft = { value: "" };
    const pageError = { value: "" };
    const messages = { value: [] };
    const pendingFiles = { value: [] };
    const sending = { value: false };
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
          (!!routeConversationId.value && conversationId.value !== routeConversationId.value) ||
          (started.value && conversationStatus.value !== "active")
        );
      },
    };
    const router = {
      replace(target) {
        deps.replaces.push(target);
        route.query = { ...(target.query || {}) };
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
    ${resetFunction}
    ${loadFunctions}

    function switchConversation(id, history = []) {
      conversationLoadEpoch++;
      route.query = { c: id };
      restoring.value = false;
      resetToFresh();
      conversationId.value = id;
      conversationStatus.value = "active";
      started.value = true;
      messages.value = history.map((message) => ({ ...message }));
      restoreConversationSendState(id);
    }

    function switchFresh() {
      conversationLoadEpoch++;
      route.query = {};
      restoring.value = false;
      resetToFresh();
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
        pageError: pageError.value,
        retryRequestId: retryTurn && retryTurn.requestId,
      };
    }

    return {
      send,
      state,
      switchConversation,
      switchFresh,
      loadConversation,
      canLeave() { return leaveGuard(); },
      canUpdate(to) { return updateGuard(to); },
      setDraft(value) { draft.value = value; },
      setFiles,
    };
  `);

  return factory({
    replaces: deps.replaces || [],
    loads: deps.loads || [],
    createConversation: deps.createConversation || (async () => ({ id: "created", status: "active" })),
    postMessage: deps.postMessage,
    uploadFile: deps.uploadFile || (async (raw) => ({ id: `uploaded_${raw.name}` })),
    getConversation: deps.getConversation || (async (id) => ({ id, status: "active", messages: [] })),
  });
}


test("guide sends explicit safe_auto intent with a stable request id", async () => {
  const api = await readFile(new URL("../src/api/conversations.js", import.meta.url), "utf8");
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");

  assert.match(api, /execution_mode:\s*executionMode/);
  assert.match(api, /request_id:\s*requestId/);
  assert.match(guide, /executionMode:\s*["']safe_auto["']/);
  assert.match(guide, /turnRequestId\(content, fileIds\)/);
  assert.match(guide, /retryTurn\.fingerprint === fingerprint/);
});


test("fresh safe_auto plans show backend facts instead of a create-task click", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const workbench = await readFile(
    new URL("../src/views/WorkbenchSession.vue", import.meta.url),
    "utf8",
  );

  assert.match(guide, /v-if="!m\.recommendation\.execution" class="agent-actions"/);
  assert.match(guide, /已自动发起，无需手动创建/);
  assert.match(guide, /最终工程签发仍由你完成/);
  assert.match(guide, /当前方案未自动执行，也没有创建任务/);
  assert.match(guide, /decision === 'awaiting_plan'/);
  assert.match(guide, /导引仍在澄清，尚未创建任务/);
  assert.match(workbench, /conversation\.status === 'active' && plan\.execution/);
  assert.match(workbench, /已自动发起，等待任务状态同步/);
  assert.match(workbench, /当前方案被安全门阻断，没有创建任务/);
});


test("A and B sends keep their conversations, UI state, and attachments isolated", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const uploadA = deferred();
  const postA = deferred();
  const postB = deferred();
  const posts = [];
  const harness = createGuideSendHarness(guide, {
    uploadFile: (raw) => raw.name === "A.txt" ? uploadA.promise : Promise.resolve({ id: "file_B" }),
    postMessage: (conversationId, content, fileIds, options) => {
      posts.push({ conversationId, content, fileIds, requestId: options.requestId });
      return conversationId === "A" ? postA.promise : postB.promise;
    },
  });

  harness.switchConversation("A", [{ role: "assistant", content: "A history" }]);
  harness.setDraft("run A");
  harness.setFiles([{ name: "A.txt" }]);
  const sendA = harness.send();
  await waitFor(() => harness.state().pendingFiles[0]?.status === "uploading");

  harness.switchConversation("B", [{ role: "assistant", content: "B history" }]);
  harness.setDraft("run B");
  harness.setFiles([{ name: "B.txt" }]);
  assert.equal(harness.state().sending, false);

  uploadA.resolve({ id: "file_A" });
  await waitFor(() => posts.some((post) => post.conversationId === "A"));
  const sendB = harness.send();
  await waitFor(() => posts.some((post) => post.conversationId === "B"));

  assert.deepEqual(posts.map((post) => [post.conversationId, post.fileIds]), [
    ["A", ["file_A"]],
    ["B", ["file_B"]],
  ]);
  const bBeforeASettles = harness.state();
  postA.resolve({ message: { content: "A result", recommendation: { decision: "orchestrate" } } });
  await sendA;
  assert.deepEqual(harness.state(), bBeforeASettles, "A success/finally must not mutate B UI");

  postB.resolve({ message: { content: "B result", recommendation: null } });
  await sendB;
  assert.equal(harness.state().conversationId, "B");
  assert.deepEqual(harness.state().messages.map((message) => message.content), [
    "B history",
    "run B",
    "B result",
  ]);
  assert.deepEqual(harness.state().pendingFiles, []);
  assert.equal(harness.state().sending, false);
});


test("an old A failure cannot overwrite an in-flight B send", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const postA = deferred();
  const postB = deferred();
  const posted = [];
  const harness = createGuideSendHarness(guide, {
    postMessage: (conversationId) => {
      posted.push(conversationId);
      return conversationId === "A" ? postA.promise : postB.promise;
    },
  });

  harness.switchConversation("A");
  harness.setDraft("run A");
  const sendA = harness.send();
  harness.switchConversation("B", [{ role: "assistant", content: "B history" }]);
  harness.setDraft("run B");
  const sendB = harness.send();
  await waitFor(() => posted.includes("B"));
  const bBeforeASettles = harness.state();

  postA.reject(new Error("A failed"));
  await sendA;
  assert.deepEqual(harness.state(), bBeforeASettles, "A failure/finally must not mutate B UI");

  postB.resolve({ message: { content: "B result", recommendation: null } });
  await sendB;
  assert.equal(harness.state().pageError, "");
  assert.deepEqual(harness.state().messages.map((message) => message.content), [
    "B history",
    "run B",
    "B result",
  ]);
});


test("fresh create in flight posts only to C and never takes B back", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const createC = deferred();
  const postC = deferred();
  const posts = [];
  const replaces = [];
  const harness = createGuideSendHarness(guide, {
    replaces,
    createConversation: () => createC.promise,
    postMessage: (conversationId, content, fileIds) => {
      posts.push({ conversationId, content, fileIds });
      return postC.promise;
    },
    uploadFile: async () => ({ id: "file_C" }),
  });

  harness.switchFresh();
  harness.setDraft("run C");
  harness.setFiles([{ name: "C.txt" }]);
  const sendC = harness.send();
  await new Promise((resolve) => setImmediate(resolve));
  harness.switchConversation("B", [{ role: "assistant", content: "B history" }]);
  createC.resolve({ id: "C", status: "active" });
  await waitFor(() => posts.length === 1);

  assert.deepEqual(posts, [{ conversationId: "C", content: "run C", fileIds: ["file_C"] }]);
  assert.deepEqual(replaces, []);
  postC.resolve({ message: { content: "C result", recommendation: null } });
  await sendC;
  assert.equal(harness.state().routeConversationId, "B");
  assert.equal(harness.state().conversationId, "B");
  assert.deepEqual(harness.state().messages.map((message) => message.content), ["B history"]);
});


test("returning to A keeps it locked until success resyncs canonical history", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const postA = deferred();
  const loads = [];
  const harness = createGuideSendHarness(guide, {
    loads,
    postMessage: () => postA.promise,
    getConversation: async (id) => ({
      id,
      status: "active",
      messages: [
        { role: "user", content: "run A" },
        { role: "assistant", content: "A result" },
      ],
    }),
  });

  harness.switchConversation("A");
  harness.setDraft("run A");
  const sendA = harness.send();
  harness.switchConversation("B");
  harness.switchConversation("A");
  assert.equal(harness.state().sending, true, "A must remain locked while its POST is in flight");

  postA.resolve({ message: { content: "A result", recommendation: null } });
  await sendA;
  assert.deepEqual(loads, ["A"], "stale success must perform a post-commit A refresh");
  assert.deepEqual(harness.state().messages.map((message) => message.content), ["run A", "A result"]);
  assert.equal(harness.state().sending, false);
});


test("route guards prevent fresh-send remount and duplicate creation until settlement", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const createC = deferred();
  const postC = deferred();
  let createCount = 0;
  const harness = createGuideSendHarness(guide, {
    createConversation: () => {
      createCount += 1;
      return createC.promise;
    },
    postMessage: () => postC.promise,
  });

  harness.switchFresh();
  harness.setDraft("run once");
  const firstSend = harness.send();
  await waitFor(() => createCount === 1);
  assert.equal(harness.canLeave(), false, "component leave must be blocked while create is pending");
  assert.equal(
    harness.canUpdate({ query: { c: "B" } }),
    false,
    "query switch must be blocked while create is pending",
  );

  harness.setDraft("run twice");
  await harness.send();
  assert.equal(createCount, 1, "programmatic second send must also be rejected");

  createC.resolve({ id: "C", status: "active" });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(harness.canUpdate({ query: { c: "B" } }), false, "POST in flight remains guarded");
  postC.resolve({ message: { content: "C result", recommendation: null } });
  await firstSend;
  assert.equal(harness.canLeave(), true);
});


test("failed canonical resync keeps the target loaded as fail-closed", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  let postCount = 0;
  const harness = createGuideSendHarness(guide, {
    postMessage: async () => {
      postCount += 1;
      return {
        execution: { replayed: true },
        message: { content: "already committed", recommendation: null },
      };
    },
    getConversation: async () => {
      throw new Error("GET failed");
    },
  });

  harness.switchConversation("A");
  harness.setDraft("run A");
  await harness.send();
  assert.equal(harness.state().conversationId, "A");
  assert.equal(harness.state().started, true);
  assert.equal(harness.state().conversationStatus, "");
  assert.equal(harness.state().conversationReadOnly, true);
  assert.equal(harness.state().pageError, "GET failed");

  harness.setDraft("must not create fresh");
  await harness.send();
  assert.equal(postCount, 1, "unknown target status must reject another send");
});


test("commit-loss retry keeps its request id and replay reloads one canonical history", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const posts = [];
  let canonicalRequestId = null;
  const harness = createGuideSendHarness(guide, {
    postMessage: async (_conversationId, _content, _fileIds, options) => {
      posts.push(options.requestId);
      if (posts.length === 1) {
        canonicalRequestId = options.requestId;
        throw new Error("response lost after commit");
      }
      return {
        execution: { replayed: true },
        message: {
          content: "A result",
          recommendation: { execution: { request_id: options.requestId, replayed: true } },
        },
      };
    },
    getConversation: async (id) => ({
      id,
      status: "active",
      messages: [
        { role: "user", content: "run A" },
        {
          role: "assistant",
          content: "A result",
          recommendation: { execution: { request_id: canonicalRequestId, replayed: false } },
        },
      ],
    }),
  });

  harness.switchConversation("A");
  harness.setDraft("run A");
  await harness.send();
  assert.equal(harness.state().draft, "run A");
  assert.equal(harness.state().pageError, "response lost after commit");

  await harness.send();
  assert.equal(posts.length, 2);
  assert.equal(posts[1], posts[0], "retry must reuse the original safe_auto request id");
  assert.deepEqual(harness.state().messages.map((message) => message.content), ["run A", "A result"]);
  assert.equal(harness.state().draft, "");
  assert.equal(harness.state().pageError, "");
});


test("canonical GET clears a remembered commit-loss failure", async () => {
  const guide = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  let requestId = null;
  const harness = createGuideSendHarness(guide, {
    postMessage: async (_conversationId, _content, _fileIds, options) => {
      requestId = options.requestId;
      throw new Error("response lost after commit");
    },
    getConversation: async (id) => ({
      id,
      status: "active",
      messages: [
        { role: "user", content: "run A" },
        {
          role: "assistant",
          content: "A result",
          recommendation: { execution: { request_id: requestId } },
        },
      ],
    }),
  });

  harness.switchConversation("A");
  harness.setDraft("run A");
  await harness.send();
  assert.equal(harness.state().draft, "run A");
  await harness.loadConversation("A");
  assert.equal(harness.state().draft, "");
  assert.equal(harness.state().pageError, "");
  assert.deepEqual(harness.state().messages.map((message) => message.content), ["run A", "A result"]);
});
