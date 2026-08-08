import "element-plus/es/components/message/style/css";
import "element-plus/es/components/message-box/style/css";

import { installUiAcceptanceBoundary } from "./acceptanceBoundary.js";
import { getUiAcceptanceCase } from "./uiAcceptanceCases.js";
import { PLATFORM_NAME } from "../utils/branding.js";

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
  document.title = `验收已停止 · ${PLATFORM_NAME} UI 验收台`;
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
    { buildFeatureAssetMapView },
  ] = await Promise.all([
    import("vue"),
    import("element-plus"),
    import("element-plus/es/locale/lang/zh-cn"),
    import("vue-router"),
    import("../App.vue"),
    import("../views/GuidePage.vue"),
    import("../stores/theme"),
    import("../utils/featureAssetMap.js"),
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
  const mapFixture = acceptanceCase.featureAssetMap;
  if (mapFixture?.kind === "snapshot") {
    const mapViews = [mapFixture.snapshot, mapFixture.refresh_snapshot]
      .filter(Boolean)
      .map((snapshot) => buildFeatureAssetMapView(snapshot));
    if (
      mapViews.length === 0
      || mapViews.some((view) => view.available !== true)
    ) {
      throw new RangeError("功能与资产地图验收快照不完整");
    }
    let readCount = 0;
    app.provide(
      "flaiFeatureAssetMapLoader",
      async () => {
        const index = Math.min(readCount, mapViews.length - 1);
        readCount += 1;
        return structuredClone(mapViews[index]);
      },
    );
  } else if (mapFixture?.kind === "error") {
    app.provide("flaiFeatureAssetMapLoader", async () => {
      const error = new Error(mapFixture.detail);
      error.status = mapFixture.status;
      error.detail = mapFixture.detail;
      throw error;
    });
  } else if (mapFixture) {
    throw new RangeError("功能与资产地图验收 fixture 类型无效");
  }
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
