<template>
  <div class="lab-shell">
    <aside class="lab-nav">
      <div class="lab-brand">
        <span class="lab-kicker">{{ PLATFORM_NAME }} / DEV ONLY</span>
        <h1>UI 验收台</h1>
        <p>真实组件、固定状态、精确 viewport。设计基线回到代码，不再维护 Figma 副本。</p>
      </div>

      <nav class="case-list" aria-label="验收视图">
        <button
          v-for="item in cases"
          :key="item.id"
          type="button"
          class="case-button"
          :class="{ 'is-active': item.id === selected.id }"
          @click="selectCase(item.id)"
        >
          <span class="case-label">{{ item.label }}</span>
          <span class="case-summary">{{ item.summary }}</span>
        </button>
      </nav>

      <div class="lab-boundary">
        <strong>边界</strong>
        <span>只读沙箱会阻止网络与存储写入，也不模拟模型打字。流式画面是已接收 delta 的状态快照；真实网络链路仍在正式页面验收。</span>
      </div>
    </aside>

    <main class="lab-main">
      <header class="lab-toolbar">
        <div class="toolbar-copy">
          <span class="toolbar-kicker">当前镜头</span>
          <h2>{{ selected.label }}</h2>
          <p>{{ selected.summary }}</p>
        </div>

        <div class="toolbar-actions">
          <span class="viewport-badge">{{ selected.viewport.label }}</span>
          <label class="theme-field">
            <span>主题</span>
            <select v-model="theme">
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </label>
          <button type="button" class="quiet-button" @click="reloadFrame">重新载入</button>
          <button type="button" class="quiet-button" @click="actualSize = !actualSize">
            {{ actualSize ? "适应画布" : "1:1 查看" }}
          </button>
          <a class="primary-link" href="/" target="_blank" rel="noreferrer">打开真实应用</a>
        </div>
      </header>

      <section class="review-strip" aria-label="本镜头检查点">
        <span class="review-title">逐项看</span>
        <ol>
          <li v-for="point in selected.reviewPoints" :key="point">{{ point }}</li>
        </ol>
      </section>

      <section
        ref="stageEl"
        class="preview-stage"
        :class="{ 'is-actual': actualSize }"
      >
        <div class="stage-grid"></div>
        <div
          class="frame-space"
          :style="{
            width: `${scaledWidth}px`,
            height: `${scaledHeight}px`,
          }"
        >
          <iframe
            :key="frameKey"
            class="preview-frame"
            :src="frameSrc"
            :title="`${selected.label} UI 验收视图`"
            sandbox="allow-scripts"
            :style="{
              width: `${selected.viewport.width}px`,
              height: `${selected.viewport.height}px`,
              transform: `scale(${frameScale})`,
            }"
          ></iframe>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { PLATFORM_NAME } from "../utils/branding.js";
import {
  UI_ACCEPTANCE_CASES,
  getUiAcceptanceCase,
} from "./uiAcceptanceCases.js";

const cases = UI_ACCEPTANCE_CASES;
const initialId = new URLSearchParams(window.location.search).get("case");
const selectedId = ref(getUiAcceptanceCase(initialId).id);
const selected = computed(() => getUiAcceptanceCase(selectedId.value));
const theme = ref("light");
const actualSize = ref(false);
const frameVersion = ref(0);
const stageEl = ref(null);
const stageWidth = ref(0);
const stageHeight = ref(0);
let resizeObserver = null;

const frameScale = computed(() => {
  if (actualSize.value) return 1;
  const horizontal = (stageWidth.value - 48) / selected.value.viewport.width;
  const vertical = (stageHeight.value - 48) / selected.value.viewport.height;
  return Math.max(0.28, Math.min(1, horizontal, vertical));
});
const scaledWidth = computed(
  () => selected.value.viewport.width * frameScale.value
);
const scaledHeight = computed(
  () => selected.value.viewport.height * frameScale.value
);
const frameSrc = computed(() => {
  const query = new URLSearchParams({
    embed: "1",
    case: selected.value.id,
    theme: theme.value,
  });
  return `/ui-lab.html?${query.toString()}`;
});
const frameKey = computed(
  () => `${selected.value.id}:${theme.value}:${frameVersion.value}`
);

function selectCase(id) {
  selectedId.value = getUiAcceptanceCase(id).id;
  actualSize.value = false;
  const query = new URLSearchParams(window.location.search);
  query.set("case", selectedId.value);
  query.delete("embed");
  query.delete("theme");
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}?${query.toString()}`
  );
}

function reloadFrame() {
  frameVersion.value += 1;
}

onMounted(() => {
  resizeObserver = new ResizeObserver(([entry]) => {
    stageWidth.value = entry.contentRect.width;
    stageHeight.value = entry.contentRect.height;
  });
  resizeObserver.observe(stageEl.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
});
</script>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(html),
:global(body),
:global(#app) {
  width: 100%;
  min-width: 0;
  height: 100%;
  margin: 0;
}

:global(body) {
  overflow: hidden;
  color: #2b2622;
  background: #f4f0e9;
  font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
}

button,
select,
a {
  font: inherit;
}

.lab-shell {
  display: grid;
  grid-template-columns: 264px minmax(0, 1fr);
  width: 100%;
  height: 100%;
}

.lab-nav {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 24px 18px 18px;
  border-right: 1px solid #ded7cd;
  background: #fbf9f5;
}

.lab-brand {
  padding: 0 6px 18px;
}

.lab-kicker,
.toolbar-kicker {
  color: #9b765f;
  font-family: "SF Mono", ui-monospace, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.9px;
}

.lab-brand h1 {
  margin: 6px 0 8px;
  font-family: "Iowan Old Style", "Songti SC", serif;
  font-size: 28px;
  font-weight: 600;
}

.lab-brand p,
.toolbar-copy p {
  margin: 0;
  color: #786f66;
  font-size: 12px;
  line-height: 1.6;
}

.case-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow: auto;
}

.case-button {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 9px;
  color: #342e29;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.case-button:hover {
  background: #f4eee8;
}

.case-button.is-active {
  border-color: #e4c9ba;
  background: #f5e8e1;
}

.case-label {
  font-size: 12.5px;
  font-weight: 700;
}

.case-summary {
  color: #81786f;
  font-size: 10.5px;
  line-height: 1.45;
}

.lab-boundary {
  display: grid;
  gap: 4px;
  margin-top: 14px;
  padding: 10px;
  border: 1px solid #ead9c2;
  border-radius: 9px;
  color: #82652c;
  background: #fbf3e6;
  font-size: 10.5px;
  line-height: 1.5;
}

.lab-main {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}

.lab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 76px;
  padding: 14px 22px;
  border-bottom: 1px solid #ded7cd;
  background: rgba(251, 249, 245, 0.94);
}

.toolbar-copy h2 {
  margin: 2px 0;
  font-size: 17px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.viewport-badge,
.theme-field {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 9px;
  border: 1px solid #ded7cd;
  border-radius: 8px;
  color: #6b6259;
  background: #fff;
  font-size: 11px;
}

.theme-field select {
  border: 0;
  color: #332d28;
  background: transparent;
  outline: none;
}

.quiet-button,
.primary-link {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid #ded7cd;
  border-radius: 8px;
  color: #4b433d;
  background: #fff;
  text-decoration: none;
  cursor: pointer;
}

.primary-link {
  border-color: #b65b3b;
  color: #fff;
  background: #c15f3c;
}

.review-strip {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-height: 48px;
  padding: 9px 22px;
  border-bottom: 1px solid #ded7cd;
  background: #f8f5ef;
}

.review-title {
  flex: none;
  padding-top: 2px;
  color: #9b765f;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.6px;
}

.review-strip ol {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 24px;
  margin: 0;
  padding-left: 18px;
  color: #625a52;
  font-size: 11px;
  line-height: 1.55;
}

.preview-stage {
  position: relative;
  display: grid;
  min-width: 0;
  min-height: 0;
  place-items: center;
  overflow: auto;
  padding: 24px;
}

.preview-stage.is-actual {
  place-items: start;
}

.stage-grid {
  position: absolute;
  inset: 0;
  opacity: 0.5;
  background-image:
    linear-gradient(#ded7cd 1px, transparent 1px),
    linear-gradient(90deg, #ded7cd 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
}

.frame-space {
  position: relative;
  flex: none;
  box-shadow: 0 18px 60px rgba(55, 45, 37, 0.16);
}

.preview-frame {
  position: absolute;
  inset: 0 auto auto 0;
  display: block;
  border: 0;
  background: #faf7f2;
  transform-origin: top left;
}

@media (max-width: 900px) {
  .lab-shell {
    grid-template-columns: 214px minmax(0, 1fr);
  }

  .lab-toolbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .toolbar-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
