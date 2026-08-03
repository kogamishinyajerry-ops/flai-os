import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { parse, compileScript } from "@vue/compiler-sfc";
import * as vueRuntime from "vue";


const calloutSource = readFileSync(
  new URL("../src/components/AssetCandidateCallout.vue", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.vue", import.meta.url),
  "utf8",
);
const statusDockSource = readFileSync(
  new URL("../src/components/StatusDock.vue", import.meta.url),
  "utf8",
);


async function compileScriptSetup(source, filename) {
  const { descriptor, errors } = parse(source, { filename });
  assert.deepEqual(errors, []);
  let code = compileScript(descriptor, {
    id: "ui-p1-contract",
    genDefaultAs: "__sfc__",
  }).content;
  code = code.replace(
    /import\s*\{([^}]+)\}\s*from\s*["']vue["'];?/,
    (_match, names) => `const {${names}} = globalThis.__FLAI_VUE_TEST_RUNTIME__;`,
  );
  code += "\nexport default __sfc__;";
  globalThis.__FLAI_VUE_TEST_RUNTIME__ = vueRuntime;
  const url = `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;
  return (await import(url)).default;
}


function mountSetup(component, props) {
  const renderer = vueRuntime.createRenderer({
    patchProp(element, key, _previous, next) { element.props[key] = next; },
    insert(element, parent) { parent.children.push(element); element.parent = parent; },
    remove(element) {
      if (element.parent) {
        element.parent.children = element.parent.children.filter((item) => item !== element);
      }
    },
    createElement(type) { return { type, props: {}, children: [] }; },
    createText(text) { return { text }; },
    createComment(comment) { return { comment }; },
    setText(node, text) { node.text = text; },
    setElementText(element, text) { element.text = text; },
    parentNode(node) { return node.parent || null; },
    nextSibling() { return null; },
  });
  const app = renderer.createApp(component, props);
  app.config.warnHandler = () => {};
  app.mount({ children: [] });
  return app;
}


test("已挂载的资产候选抽屉随 1440px 与 375px 窗口切换重排", async (context) => {
  const originalWindow = globalThis.window;
  const listeners = new Map();
  const fakeWindow = {
    innerWidth: 1440,
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) {
      listeners.get(type)?.delete(listener);
    },
    dispatchEvent(event) {
      for (const listener of listeners.get(event.type) || []) listener(event);
    },
  };
  globalThis.window = fakeWindow;
  context.after(() => {
    globalThis.window = originalWindow;
    delete globalThis.__FLAI_VUE_TEST_RUNTIME__;
  });

  const component = await compileScriptSetup(calloutSource, "AssetCandidateCallout.vue");
  const app = mountSetup(component, { candidate: null, phase: "idle" });
  let mounted = true;
  context.after(() => {
    if (mounted) app.unmount();
  });

  assert.equal(app._instance.setupState.drawerSize, "min(560px, 92vw)");
  assert.equal(listeners.get("resize")?.size, 1);

  fakeWindow.innerWidth = 375;
  fakeWindow.dispatchEvent({ type: "resize" });
  await vueRuntime.nextTick();
  assert.equal(app._instance.setupState.drawerSize, "100%");

  fakeWindow.innerWidth = 1440;
  fakeWindow.dispatchEvent({ type: "resize" });
  await vueRuntime.nextTick();
  assert.equal(app._instance.setupState.drawerSize, "min(560px, 92vw)");

  app.unmount();
  mounted = false;
  assert.equal(listeners.get("resize")?.size, 0);
});


test("移动菜单与无状态状态坞的触控目标至少为 44×44", () => {
  const hamburgerRule = [...appSource.matchAll(/\.sb-hamburger\s*\{([^}]+)\}/g)]
    .map((match) => match[1])
    .find((rule) => rule.includes("position: fixed")) || "";
  assert.match(hamburgerRule, /width:\s*44px;/);
  assert.match(hamburgerRule, /height:\s*44px;/);

  const dockRule = statusDockSource.match(/\.status-dock\s*\{([^}]+)\}/)?.[1] || "";
  assert.match(dockRule, /min-width:\s*44px;/);
  assert.match(dockRule, /min-height:\s*44px;/);

  const coreRule = statusDockSource.match(/\.dock-core\s*\{([^}]+)\}/)?.[1] || "";
  assert.match(coreRule, /width:\s*32px;/);
  assert.match(coreRule, /height:\s*32px;/);
});


test("移动端资产包内容与来源证据开关的触控高度至少为 44px", () => {
  const mobileRule = calloutSource.match(/@media\s*\(max-width:\s*640px\)\s*\{([\s\S]*?)\n\}/)?.[1] || "";
  const disclosureRule = mobileRule.match(
    /\.candidate-package-content-toggle,\s*\.candidate-evidence-toggle\s*\{([^}]+)\}/,
  )?.[1] || "";

  assert.match(disclosureRule, /min-height:\s*44px;/);
});
