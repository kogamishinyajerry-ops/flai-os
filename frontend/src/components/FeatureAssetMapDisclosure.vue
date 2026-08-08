<template>
  <section class="feature-asset-map" :aria-label="`${PLATFORM_NAME} 功能与资产地图`">
    <details @toggle="handleToggle">
      <summary>
        <span class="map-mark" aria-hidden="true">⌘</span>
        <span class="map-heading">
          <strong>{{ PLATFORM_NAME }} 功能与资产地图</strong>
          <small>按需查看平台能力与你的受治理资产</small>
        </span>
        <span v-if="phase === 'ready'" class="map-counts">
          {{ summary.capabilityCount }} 项能力 · {{ summary.assetCandidateCount }} 份资产
        </span>
        <span v-else class="map-hint">只读披露</span>
      </summary>

      <!-- 外壳同步在场，真正的地图读取/投影/卡片只在首次展开后加载。openedOnce
           一旦置位便不回落，折叠只交给原生 details 隐藏，已加载 DOM 与状态保留。 -->
      <div v-if="openedOnce && phase === 'idle'" class="map-body">
        <div class="map-state" role="status" aria-live="polite">
          正在加载地图界面…
        </div>
      </div>
      <FeatureAssetMapBody
        v-if="openedOnce"
        @state-change="syncBodyState"
      />
    </details>
  </section>
</template>

<script setup>
import { defineAsyncComponent, ref } from "vue";

import { PLATFORM_NAME } from "../utils/branding";

const FeatureAssetMapBody = defineAsyncComponent(() => import("./FeatureAssetMapBody.vue"));

const openedOnce = ref(false);
const phase = ref("idle");
const summary = ref(null);

function handleToggle(event) {
  if (event.currentTarget.open) openedOnce.value = true;
}

function syncBodyState(state) {
  if (!["loading", "ready", "error"].includes(state?.phase)) {
    phase.value = "error";
    summary.value = null;
    return;
  }
  phase.value = state.phase;
  summary.value = state.phase === "ready" && state.summary
    ? state.summary
    : null;
}
</script>

<style scoped>
.feature-asset-map {
  width: min(100%, 920px);
  margin: 12px auto 4px;
}

.feature-asset-map details {
  border: 1px solid var(--hairline-soft);
  border-radius: 14px;
  background: color-mix(in srgb, var(--surface-raised) 94%, var(--clay-soft));
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.feature-asset-map summary {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  color: var(--ink);
  cursor: pointer;
  list-style: none;
}

.feature-asset-map summary::-webkit-details-marker { display: none; }
.feature-asset-map summary:focus-visible { outline: 2px solid var(--clay); outline-offset: -3px; }
.feature-asset-map details[open] summary { border-bottom: 1px solid var(--hairline-soft); }

.map-mark {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 9px;
  color: var(--clay);
  background: var(--clay-soft);
  font-size: 13px;
  font-weight: 800;
}

.map-heading { min-width: 0; display: grid; gap: 1px; }
.map-heading strong { font-size: var(--fs-sm); line-height: 1.35; }
.map-heading small { color: var(--ink-faint); font-size: var(--fs-2xs); line-height: 1.35; }
.map-counts, .map-hint { margin-left: auto; flex: 0 0 auto; color: var(--ink-faint); font-size: var(--fs-2xs); }
.map-body { padding: 14px; }
.map-state {
  min-height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-soft);
  font-size: var(--fs-sm);
}

@media (max-width: 640px) {
  .feature-asset-map { margin-top: 8px; }
  .map-counts { display: none; }
  .map-body { padding: 11px; }
}

@media (prefers-reduced-motion: reduce) {
  .feature-asset-map * { scroll-behavior: auto; }
}
</style>
