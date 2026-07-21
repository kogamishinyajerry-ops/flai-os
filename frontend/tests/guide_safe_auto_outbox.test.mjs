import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  GUIDE_SAFE_AUTO_OUTBOX_KEY,
  createGuideSafeAutoOutbox,
  dispatchGuideSafeAutoIntent,
  filesFromGuideSafeAutoRecord,
  recoverGuideSafeAutoOutbox,
} from "../src/utils/guideSafeAutoOutbox.js";


class FakeStorage {
  constructor(seed = {}) {
    this.values = new Map(Object.entries(seed));
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


const principal = { username: "alice", role: "agent_developer" };

function intent(overrides = {}) {
  return {
    requestId: "turn-00000001",
    agentId: "guide_agent",
    conversationId: "conv-1",
    content: "核查这个方案",
    fileIds: ["file-1"],
    files: [{ id: "file-1", name: "input.txt" }],
    ...overrides,
  };
}

function authority(conversationId, requestId = null) {
  return {
    id: conversationId,
    status: "active",
    messages: requestId
      ? [{
          role: "assistant",
          recommendation: { execution: { request_id: requestId, status: "dispatched" } },
        }]
      : [],
  };
}


test("storage write/readback failure aborts before either conversation POST", async () => {
  let creates = 0;
  let posts = 0;
  const storage = new FakeStorage();
  storage.setItem = () => {
    throw new Error("quota denied");
  };

  await assert.rejects(
    dispatchGuideSafeAutoIntent({
      outbox: createGuideSafeAutoOutbox({ storage }),
      principal,
      intent: intent({ conversationId: null, fileIds: [], files: [] }),
      createConversation: async () => {
        creates += 1;
        return { id: "never" };
      },
      postMessage: async () => {
        posts += 1;
      },
      getConversation: async () => authority("never", "turn-00000001"),
    }),
    /OUTBOX_STORAGE_WRITE_FAILED/,
  );
  assert.equal(creates, 0);
  assert.equal(posts, 0);
});


test("unavailable sessionStorage constructs safely, then blocks dispatch before network", async () => {
  let networkCalls = 0;
  const outbox = createGuideSafeAutoOutbox({ storage: null });
  await assert.rejects(
    dispatchGuideSafeAutoIntent({
      outbox,
      principal,
      intent: intent({ conversationId: null, fileIds: [], files: [] }),
      createConversation: async () => { networkCalls += 1; },
      postMessage: async () => { networkCalls += 1; },
      getConversation: async () => { networkCalls += 1; },
    }),
    /OUTBOX_STORAGE_READ_FAILED/,
  );
  assert.equal(networkCalls, 0);
});


test("request id and principal validation mirrors the backend fail-closed contract", () => {
  for (const requestId of [undefined, "short", "contains space", "x".repeat(65)]) {
    assert.throws(
      () => createGuideSafeAutoOutbox({ storage: new FakeStorage() }).prepare(
        principal,
        intent({ requestId }),
      ),
      /OUTBOX_INTENT_INVALID/,
    );
  }
  for (const invalidPrincipal of [
    { username: "alice", role: "owner" },
    { username: "x".repeat(101), role: "admin" },
  ]) {
    assert.throws(
      () => createGuideSafeAutoOutbox({ storage: new FakeStorage() }).prepare(
        invalidPrincipal,
        intent(),
      ),
      /OUTBOX_PRINCIPAL_INVALID/,
    );
  }
});


test("same-page retry is allowed only when the durable record exactly matches the failed intent", () => {
  const storage = new FakeStorage();
  const outbox = createGuideSafeAutoOutbox({ storage });
  outbox.prepare(principal, intent());

  assert.equal(outbox.matchesIntent(principal, intent()), true);
  assert.equal(outbox.matchesIntent(principal, intent({ content: "另一条消息" })), false);
  assert.equal(outbox.matchesIntent(principal, intent({ requestId: "turn-00000002" })), false);
  assert.equal(outbox.matchesIntent(principal, intent({ fileIds: [], files: [] })), false);
  assert.throws(
    () => outbox.matchesIntent({ username: "bob", role: "business_user" }, intent()),
    /OUTBOX_PRINCIPAL_MISMATCH/,
  );
});


test("a new module instance replays the exact persisted request id and file ids", async () => {
  const storage = new FakeStorage();
  const first = createGuideSafeAutoOutbox({ storage, now: () => "2026-07-21T01:00:00.000Z" });
  first.prepare(principal, intent());

  const raw = storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY);
  assert.doesNotMatch(raw, /raw/);
  assert.deepEqual(JSON.parse(raw).files, [{ id: "file-1", name: "input.txt" }]);
  assert.deepEqual(
    filesFromGuideSafeAutoRecord(first.loadForPrincipal(principal)).map((file) => ({
      fileId: file.fileId,
      raw: file.raw,
      locked: file.locked,
    })),
    [{ fileId: "file-1", raw: null, locked: true }],
  );

  const replayed = [];
  let reads = 0;
  const second = createGuideSafeAutoOutbox({ storage, now: () => "2026-07-21T01:01:00.000Z" });
  const result = await recoverGuideSafeAutoOutbox({
    outbox: second,
    principal,
    createConversation: async () => assert.fail("bound records must not create a conversation"),
    getConversation: async () => {
      reads += 1;
      return authority("conv-1", reads === 2 ? "turn-00000001" : null);
    },
    postMessage: async (call) => {
      replayed.push(call);
      return { ok: true };
    },
  });

  assert.equal(result.status, "confirmed");
  assert.equal(replayed.length, 1);
  assert.equal(replayed[0].requestId, "turn-00000001");
  assert.deepEqual(replayed[0].fileIds, ["file-1"]);
  assert.deepEqual(replayed[0].expectedPrincipal, principal);
  assert.equal("files" in replayed[0], false, "only server file ids cross the replay API seam");
  assert.equal(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
});


test("unknown versions, malformed records, and principal drift are fail-closed with zero POST", async () => {
  const badRecords = [
    { version: 99 },
    { version: 1, principal: { username: "alice", role: "agent_developer" } },
  ];

  for (const bad of badRecords) {
    const storage = new FakeStorage({ [GUIDE_SAFE_AUTO_OUTBOX_KEY]: JSON.stringify(bad) });
    let networkCalls = 0;
    const result = await recoverGuideSafeAutoOutbox({
      outbox: createGuideSafeAutoOutbox({ storage }),
      principal,
      createConversation: async () => { networkCalls += 1; },
      getConversation: async () => { networkCalls += 1; },
      postMessage: async () => { networkCalls += 1; },
    });
    assert.equal(result.status, "blocked");
    assert.equal(networkCalls, 0);
  }

  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  let networkCalls = 0;
  const drift = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal: { username: "bob", role: "business_user" },
    createConversation: async () => { networkCalls += 1; },
    getConversation: async () => { networkCalls += 1; },
    postMessage: async () => { networkCalls += 1; },
  });
  assert.equal(drift.status, "blocked");
  assert.equal(networkCalls, 0);
});


test("fresh recovery uses the same request id for create and message, then CAS-binds once", async () => {
  const storage = new FakeStorage();
  const outbox = createGuideSafeAutoOutbox({ storage });
  outbox.prepare(principal, intent({ conversationId: null, fileIds: [], files: [] }));

  const createCalls = [];
  const postCalls = [];
  let reads = 0;
  const result = await recoverGuideSafeAutoOutbox({
    outbox,
    principal,
    createConversation: async (call) => {
      createCalls.push(call);
      return { id: "conv-fresh", status: "active" };
    },
    getConversation: async () => {
      reads += 1;
      return authority("conv-fresh", reads === 2 ? "turn-00000001" : null);
    },
    postMessage: async (call) => {
      postCalls.push(call);
      return { ok: true };
    },
  });

  assert.equal(result.status, "confirmed");
  assert.equal(createCalls[0].requestId, "turn-00000001");
  assert.deepEqual(createCalls[0].expectedPrincipal, principal);
  assert.equal(postCalls[0].requestId, "turn-00000001");
  assert.deepEqual(postCalls[0].expectedPrincipal, principal);

  const casStorage = new FakeStorage();
  const cas = createGuideSafeAutoOutbox({ storage: casStorage });
  cas.prepare(principal, intent({ conversationId: null, fileIds: [], files: [] }));
  cas.bindConversation(principal, "turn-00000001", "conv-a");
  assert.equal(cas.bindConversation(principal, "turn-00000001", "conv-a").conversation_id, "conv-a");
  assert.throws(
    () => cas.bindConversation(principal, "turn-00000001", "conv-b"),
    /OUTBOX_CONVERSATION_CONFLICT/,
  );
});


test("initial fresh dispatch persists before create and clears only after canonical confirmation", async () => {
  const storage = new FakeStorage();
  const seen = [];
  const result = await dispatchGuideSafeAutoIntent({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    intent: intent({ conversationId: null, fileIds: [], files: [] }),
    createConversation: async ({ requestId, expectedPrincipal }) => {
      assert.deepEqual(expectedPrincipal, principal);
      seen.push(["create", requestId, JSON.parse(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY)).phase]);
      return { id: "conv-new", status: "active" };
    },
    postMessage: async ({ requestId, expectedPrincipal }) => {
      assert.deepEqual(expectedPrincipal, principal);
      seen.push(["message", requestId, JSON.parse(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY)).conversation_id]);
      return { message: { recommendation: { execution: { request_id: requestId } } } };
    },
    getConversation: async () => authority("conv-new", "turn-00000001"),
  });

  assert.equal(result.conversation.id, "conv-new");
  assert.deepEqual(seen, [
    ["create", "turn-00000001", "creating_conversation"],
    ["message", "turn-00000001", "conv-new"],
  ]);
  assert.equal(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
});


test("recovery GET can prove a lost response and suppress message replay", async () => {
  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  let posts = 0;
  const result = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    createConversation: async () => assert.fail("already bound"),
    getConversation: async () => authority("conv-1", "turn-00000001"),
    postMessage: async () => { posts += 1; },
  });
  assert.equal(result.status, "confirmed");
  assert.equal(posts, 0);
  assert.equal(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
});


test("an authoritative GET failure retains the record and does not POST", async () => {
  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  let posts = 0;
  const result = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    createConversation: async () => assert.fail("already bound"),
    getConversation: async () => { throw new Error("GET offline"); },
    postMessage: async () => { posts += 1; },
  });

  assert.equal(result.status, "blocked");
  assert.equal(posts, 0);
  assert.notEqual(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
  assert.equal(result.record.payload.content, "核查这个方案");
});


test("a mismatched canonical conversation id is blocked and retained", async () => {
  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  let posts = 0;
  const result = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    createConversation: async () => assert.fail("already bound"),
    getConversation: async () => authority("conv-other", "turn-00000001"),
    postMessage: async () => { posts += 1; },
  });
  assert.equal(result.status, "blocked");
  assert.match(result.error.message, /OUTBOX_AUTHORITY_MISMATCH/);
  assert.equal(posts, 0);
  assert.notEqual(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
});


test("a failed post-success confirmation GET retains the record", async () => {
  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  let reads = 0;
  const result = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    createConversation: async () => assert.fail("already bound"),
    getConversation: async () => {
      reads += 1;
      if (reads === 1) return authority("conv-1");
      throw new Error("confirmation GET offline");
    },
    postMessage: async () => ({ ok: true }),
  });

  assert.equal(result.status, "blocked");
  assert.equal(reads, 2);
  assert.notEqual(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY), null);
});


test("409 keeps the original request id and never rotates the pending record", async () => {
  const storage = new FakeStorage();
  createGuideSafeAutoOutbox({ storage }).prepare(principal, intent());
  const ids = [];
  const conflict = Object.assign(new Error("request conflict"), { status: 409 });
  const result = await recoverGuideSafeAutoOutbox({
    outbox: createGuideSafeAutoOutbox({ storage }),
    principal,
    createConversation: async () => assert.fail("already bound"),
    getConversation: async () => authority("conv-1"),
    postMessage: async ({ requestId }) => {
      ids.push(requestId);
      throw conflict;
    },
  });

  assert.equal(result.status, "blocked");
  assert.deepEqual(ids, ["turn-00000001"]);
  assert.equal(JSON.parse(storage.getItem(GUIDE_SAFE_AUTO_OUTBOX_KEY)).request_id, "turn-00000001");
});


test("login and logout invalidate an older in-flight /me identity response", async () => {
  const source = await readFile(new URL("../src/stores/session.js", import.meta.url), "utf8");
  const executable = source
    .replace(/import \{ ref \} from "vue";\s*/, "")
    .replace(/import \{ request \} from "\.\.\/api\/client";\s*/, "")
    .replaceAll("export ", "");
  const oldMe = deferred();
  const calls = [];
  const request = async (path) => {
    calls.push(path);
    if (path === "/api/auth/me") return oldMe.promise;
    if (path === "/api/auth/login") {
      return { username: "bob", display_name: "Bob", role: "business_user" };
    }
    if (path === "/api/auth/logout") return { ok: true };
    assert.fail(`unexpected request ${path}`);
  };
  const session = new Function("ref", "request", `${executable}\nreturn { currentUser, fetchMe, login, logout };`)(
    (value) => ({ value }),
    request,
  );

  const staleFetch = session.fetchMe();
  await session.login("bob", "secret");
  oldMe.resolve({ username: "alice", display_name: "Alice", role: "admin" });
  await staleFetch;
  assert.equal(session.currentUser.value.username, "bob");

  const staleAfterLogin = deferred();
  let useDeferred = true;
  const logoutSession = new Function("ref", "request", `${executable}\nreturn { currentUser, fetchMe, login, logout };`)(
    (value) => ({ value }),
    async (path) => {
      if (path === "/api/auth/login") {
        return { username: "alice", display_name: "Alice", role: "admin" };
      }
      if (path === "/api/auth/me" && useDeferred) return staleAfterLogin.promise;
      if (path === "/api/auth/logout") return { ok: true };
      assert.fail(`unexpected request ${path}`);
    },
  );
  await logoutSession.login("alice", "secret");
  const staleLogoutFetch = logoutSession.fetchMe();
  await logoutSession.logout();
  useDeferred = false;
  staleAfterLogin.resolve({ username: "alice", display_name: "Alice", role: "admin" });
  await staleLogoutFetch;
  assert.equal(logoutSession.currentUser.value, null);
  assert.deepEqual(calls, ["/api/auth/me", "/api/auth/login"]);
});


test("GuidePage route guards stay closed for the whole durable recovery window", async () => {
  const source = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const start = source.indexOf("function hasActiveGuideSend()");
  const end = source.indexOf("function newTurnRequestId()", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const productionGuards = source.slice(start, end);
  const harness = new Function(`
    const sending = { value: false };
    const outboxRecoveryActive = { value: true };
    const outboxRecoveryBlocked = { value: false };
    let retryTurn = null;
    let freshInFlightSend = null;
    const inFlightSends = new Map();
    let pendingOutbox = false;
    const hasPendingGuideOutbox = () => pendingOutbox;
    let internalConversationNavigation = null;
    let leaveGuard = null;
    let updateGuard = null;
    const onBeforeRouteLeave = (guard) => { leaveGuard = guard; };
    const onBeforeRouteUpdate = (guard) => { updateGuard = guard; };
    ${productionGuards}
    return {
      canLeave: () => leaveGuard(),
      canUpdate: (to) => updateGuard(to),
      allowInternal: (id) => { internalConversationNavigation = id; },
      finishRecoveryWithPendingOutbox: () => {
        outboxRecoveryActive.value = false;
        pendingOutbox = true;
      },
      clearPendingOutbox: () => { pendingOutbox = false; },
      lockMissingOutboxRetry: () => {
        outboxRecoveryBlocked.value = true;
        retryTurn = { requestId: "turn-missing" };
      },
    };
  `)();
  assert.equal(harness.canLeave(), false);
  assert.equal(harness.canUpdate({ query: { c: "other" } }), false);
  harness.allowInternal("conv-restored");
  assert.equal(harness.canUpdate({ query: { c: "conv-restored" } }), true);
  harness.allowInternal(null);
  harness.finishRecoveryWithPendingOutbox();
  assert.equal(harness.canLeave(), false);
  assert.equal(harness.canUpdate({ query: { c: "other" } }), false);
  harness.clearPendingOutbox();
  assert.equal(harness.canLeave(), true);
  harness.lockMissingOutboxRetry();
  assert.equal(harness.canLeave(), false);
  assert.equal(harness.canUpdate({ query: { c: "other" } }), false);
});


test("a reload route mismatch loads the URL authority before projecting outbox content", async () => {
  const source = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const start = source.indexOf("visibleRecord = guideSafeAutoOutbox.loadForPrincipal(principal)");
  const routeCheck = source.indexOf("const routeId = routeConversationId.value", start);
  const fallback = source.indexOf("return keepOutboxBlockedAndLoadRoute(", routeCheck);
  const draftProjection = source.indexOf("draft.value = visibleRecord.payload.content", start);

  assert.notEqual(start, -1);
  assert.notEqual(routeCheck, -1);
  assert.notEqual(fallback, -1);
  assert.notEqual(draftProjection, -1);
  assert.ok(routeCheck < fallback && fallback < draftProjection);
});


test("GuidePage cannot remove immutable restored attachment chips", async () => {
  const source = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const start = source.indexOf("function removePendingFile(item)");
  const end = source.indexOf("async function uploadPendingFiles", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const productionRemove = source.slice(start, end);
  const remaining = new Function(`
    const pendingFiles = { value: [
      { uid: "restored", locked: true },
      { uid: "editable", locked: false },
    ] };
    const sending = { value: false };
    const outboxRecoveryActive = { value: false };
    const outboxRecoveryBlocked = { value: true };
    ${productionRemove}
    removePendingFile(pendingFiles.value[0]);
    return pendingFiles.value.map((file) => file.uid);
  `)();
  assert.deepEqual(remaining, ["restored", "editable"]);
});


test("blocked outbox storage still loads a valid route read-only", async () => {
  const source = await readFile(new URL("../src/views/GuidePage.vue", import.meta.url), "utf8");
  const start = source.indexOf("async function keepOutboxBlockedAndLoadRoute(errorText)");
  const end = source.indexOf("async function resumePersistedGuideTurn()", start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  const productionRecoveryFallback = source.slice(start, end);
  const result = await new Function(`
    const restoring = { value: true };
    const outboxRecoveryActive = { value: true };
    const outboxRecoveryBlocked = { value: true };
    const routeConversationId = { value: "conv-deep-link" };
    const pageError = { value: "" };
    let gets = 0;
    let posts = 0;
    const loadConversation = async (id) => {
      if (id !== "conv-deep-link") throw new Error("wrong target");
      gets += 1;
    };
    const postMessage = async () => { posts += 1; };
    ${productionRecoveryFallback}
    return keepOutboxBlockedAndLoadRoute("OUTBOX_STORAGE_READ_FAILED").then(() => ({
      gets,
      posts,
      blocked: outboxRecoveryBlocked.value,
      active: outboxRecoveryActive.value,
      restoring: restoring.value,
      error: pageError.value,
    }));
  `)();
  assert.deepEqual(result, {
    gets: 1,
    posts: 0,
    blocked: true,
    active: false,
    restoring: false,
    error: "OUTBOX_STORAGE_READ_FAILED",
  });
});
