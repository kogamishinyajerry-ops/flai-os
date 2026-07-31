import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";

import { installUiAcceptanceBoundary } from "./acceptanceBoundary.js";
import { getUiAcceptanceCase } from "./uiAcceptanceCases.js";

const params = new URLSearchParams(window.location.search);
const embedded = params.get("embed") === "1";

function renderFatalError(error) {
  const root = document.querySelector("#app");
  const panel = document.createElement("main");
  const title = document.createElement("h1");
  const detail = document.createElement("p");
  title.textContent = "验收已停止";
  detail.textContent =
    error instanceof Error ? error.message : "UI 验收台遇到未知错误";
  panel.className = "ui-lab-fatal";
  title.className = "ui-lab-fatal__title";
  detail.className = "ui-lab-fatal__detail";
  panel.append(title, detail);
  root.replaceChildren(panel);
  document.title = "验收已停止 · FLAi-OS UI 验收台";
}

async function mountEmbedded(acceptanceCase) {
  // 必须早于正式 App / GuidePage 的动态 import：漏掉任何组件内 acceptanceMode
  // 分支时，请求与存储写入也会在统一边界处 fail-closed。
  installUiAcceptanceBoundary(window);

  const [
    { createApp },
    { provideGlobalConfig },
    { default: zhCn },
    { createMemoryHistory, createRouter },
    { default: App },
    { default: GuidePage },
    { themeMode },
  ] = await Promise.all([
    import("vue"),
    import("element-plus"),
    import("element-plus/es/locale/lang/zh-cn"),
    import("vue-router"),
    import("../App.vue"),
    import("../views/GuidePage.vue"),
    import("../stores/theme"),
  ]);

  const requestedTheme = params.get("theme");
  if (requestedTheme === "light" || requestedTheme === "dark") {
    themeMode.value = requestedTheme;
  }

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: "/",
        name: "ui-acceptance-guide",
        component: GuidePage,
        props: { acceptanceFixture: acceptanceCase.guide },
        meta: { title: "UI 验收" },
      },
      { path: "/:pathMatch(.*)*", redirect: "/" },
    ],
  });

  const app = createApp(App, {
    acceptanceFixture: acceptanceCase.app,
  });
  provideGlobalConfig({ locale: zhCn }, app, true);
  app.use(router).mount("#app");
}

async function mountLab() {
  const [{ createApp }, { default: UiLabApp }] = await Promise.all([
    import("vue"),
    import("./UiLabApp.vue"),
  ]);
  createApp(UiLabApp).mount("#app");
}

async function bootstrap() {
  // 未传 case 才用默认起手页；显式传入未知 ID 会在此停止，绝不回退到错误画面。
  const acceptanceCase = getUiAcceptanceCase(params.get("case"));
  if (embedded) await mountEmbedded(acceptanceCase);
  else await mountLab();
}

bootstrap().catch((error) => {
  renderFatalError(error);
  console.error(error);
});
