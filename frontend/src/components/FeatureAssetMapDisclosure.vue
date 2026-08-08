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
          {{ view.summary.capabilityCount }} 项能力 · {{ view.summary.assetCandidateCount }} 份资产
        </span>
        <span v-else class="map-hint">只读披露</span>
      </summary>

      <div class="map-body">
        <div v-if="phase === 'loading'" class="map-state" role="status" aria-live="polite">
          正在冷读并核验功能与资产来源…
        </div>

        <div v-else-if="phase === 'error'" class="map-state is-error" role="alert">
          <div>
            <strong>地图暂不可用</strong>
            <p>{{ errorMessage }}。为避免假完整，当前未展示任何残缺数据。</p>
          </div>
          <button type="button" class="map-retry" @click="loadMap">重新读取</button>
        </div>

        <template v-else-if="phase === 'ready'">
          <div class="map-ready-bar">
            <div class="map-boundary">
              <span>当前读取快照</span>
              <span>只读</span>
              <span>仅当前账号</span>
              <span>不执行 · 不注册 · 不晋级</span>
            </div>
            <button type="button" class="map-refresh" @click="loadMap">
              重新读取
            </button>
          </div>

          <div class="map-metrics" aria-label="地图摘要">
            <div>
              <b>{{ view.summary.capabilityCount }}</b>
              <span>Registry 能力</span>
            </div>
            <div>
              <b>{{ view.summary.assetCandidateCount }}</b>
              <span>我的 Candidate</span>
            </div>
            <div>
              <b>{{ view.summary.skillPackageCount }}</b>
              <span>隔离 Skill 包</span>
            </div>
            <div>
              <b>{{ view.summary.approvedSkillPackageCount }}</b>
              <span>包级人审通过</span>
            </div>
          </div>

          <div class="map-section">
            <div class="map-section-heading">
              <div>
                <span class="map-kicker">平台功能</span>
                <h3>从 Agent Registry 冷读，不推断可用性</h3>
              </div>
              <span v-if="view.summary.unresolvedReferenceCount" class="map-warning">
                {{ view.summary.unresolvedReferenceCount }} 个引用未解析
              </span>
            </div>
            <div class="capability-grid">
              <article v-for="capability in view.capabilities" :key="capability.id" class="capability-card">
                <div class="card-topline">
                  <h4>{{ capability.name }}</h4>
                  <span class="state-chip is-declared">Registry 声明</span>
                </div>
                <p v-if="capability.summary">{{ capability.summary }}</p>
                <div class="card-meta">
                  <span>{{ capability.category || "类型未声明" }}</span>
                  <span>{{ capability.domain || "领域未声明" }}</span>
                  <span>{{ launchLabel(capability.launchKind) }}</span>
                </div>
                <div class="card-trust">
                  <span>{{ capability.status || "状态未知" }} · {{ capability.maturity || "成熟度未知" }}</span>
                  <span v-if="capability.requiresHumanReview === true">需人工复核</span>
                  <span v-else-if="capability.requiresHumanReview === null">人工复核未声明</span>
                  <span v-if="capability.unresolvedReferenceCount" class="is-pending">
                    {{ capability.unresolvedReferenceCount }} 个引用未解析
                  </span>
                  <span v-if="capability.mockToolCount" class="is-pending">
                    {{ capability.mockToolCount }} 个 mock 工具引用
                  </span>
                </div>
              </article>
            </div>
          </div>

          <div class="map-section">
            <div class="map-section-heading">
              <div>
                <span class="map-kicker">我的资产</span>
                <h3>从完成任务到更高层资产的真实形成状态</h3>
              </div>
            </div>
            <div v-if="view.assets.length" class="asset-list">
              <article v-for="asset in view.assets" :key="asset.id" class="asset-card">
                <div class="card-topline">
                  <div>
                    <span class="asset-kind">Task Pattern · Skill</span>
                    <h4>{{ asset.taskPatternTitle }}</h4>
                  </div>
                  <span class="state-chip" :class="candidatePresentation(asset.state).className">
                    {{ candidatePresentation(asset.state).label }}
                  </span>
                </div>
                <p class="asset-skill"><strong>{{ asset.skillName }}</strong> · {{ asset.skillDescription }}</p>
                <div class="asset-ladder" aria-label="资产形成阶梯">
                  <span :class="candidatePresentation(asset.state).className">
                    Candidate {{ candidatePresentation(asset.state).shortLabel }}
                  </span>
                  <span :class="packagePresentation(asset.packageState).className">
                    Skill 包 {{ packagePresentation(asset.packageState).label }}
                  </span>
                  <span class="is-unformed">Workflow 未形成</span>
                  <span class="is-unformed">Agent 未形成</span>
                </div>
                <div class="card-meta">
                  <span>来源 {{ asset.sourceAgentId }}</span>
                  <span v-if="asset.packageName">{{ asset.packageName }}@{{ asset.packageVersion }}</span>
                  <span v-if="asset.reuseEligible">可进入任务级匹配；仍需开工与签发</span>
                </div>
              </article>
            </div>
            <div v-else class="asset-empty">
              当前账号还没有可冷读核验的资产 Candidate。完成任务不会自动等于资产；只有证据闭合后才会在这里出现。
            </div>
          </div>
        </template>
      </div>
    </details>
  </section>
</template>

<script setup>
import { inject, ref } from "vue";
import { PLATFORM_NAME } from "../utils/branding";

import { getFeatureAssetMap } from "../api/featureAssetMap.js";
import {
  candidatePresentation,
  packagePresentation,
} from "../utils/featureAssetMap.js";


const featureAssetMapLoader = inject(
  "flaiFeatureAssetMapLoader",
  getFeatureAssetMap,
);
const phase = ref("idle");
const view = ref(null);
const errorMessage = ref("");

async function loadMap() {
  if (phase.value === "loading") return;
  phase.value = "loading";
  errorMessage.value = "";
  try {
    view.value = await featureAssetMapLoader();
    phase.value = "ready";
  } catch (error) {
    view.value = null;
    errorMessage.value = error?.detail || error?.message || "来源核验失败";
    phase.value = "error";
  }
}

function handleToggle(event) {
  if (event.currentTarget.open && phase.value === "idle") loadMap();
}

function launchLabel(kind) {
  if (kind === "task") return "任务执行";
  if (kind === "conversation") return "会话回答";
  return "启动方式未知";
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

.map-state.is-error {
  justify-content: space-between;
  gap: 18px;
  padding: 12px;
  border: 1px solid color-mix(in srgb, var(--trust-pending) 34%, transparent);
  border-radius: 10px;
  background: rgba(var(--trust-pending-rgb), 0.07);
}
.map-state.is-error strong { color: var(--trust-pending); }
.map-state.is-error p { margin: 4px 0 0; color: var(--ink-soft); line-height: 1.5; }
.map-retry { min-height: 44px; padding: 0 14px; border: 1px solid var(--hairline); border-radius: 9px; background: var(--surface-raised); color: var(--ink); cursor: pointer; }
.map-retry:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }

.map-ready-bar { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.map-boundary { display: flex; flex-wrap: wrap; gap: 6px; }
.map-boundary span { padding: 4px 8px; border: 1px solid var(--hairline); border-radius: 999px; color: var(--ink-soft); background: var(--surface-raised); font-size: var(--fs-2xs); }
.map-refresh { flex: 0 0 auto; min-height: 32px; padding: 0 11px; border: 1px solid var(--hairline); border-radius: 9px; background: var(--surface-raised); color: var(--ink-soft); font-size: var(--fs-2xs); cursor: pointer; }
.map-refresh:hover { border-color: var(--clay-softer); color: var(--clay); }
.map-refresh:focus-visible { outline: 2px solid var(--clay); outline-offset: 2px; }

.map-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.map-metrics > div { display: grid; gap: 2px; padding: 10px; border: 1px solid var(--hairline-soft); border-radius: 10px; background: var(--surface-raised); }
.map-metrics b { color: var(--ink); font-size: var(--fs-h3); font-variant-numeric: tabular-nums; }
.map-metrics span { color: var(--ink-faint); font-size: var(--fs-2xs); }

.map-section { margin-top: 18px; }
.map-section-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.map-kicker { color: var(--clay); font-size: var(--fs-2xs); font-weight: 700; letter-spacing: .08em; }
.map-section h3 { margin: 3px 0 0; color: var(--ink); font-size: var(--fs-sm); }
.map-warning { color: var(--trust-pending); font-size: var(--fs-2xs); }

.capability-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.capability-card, .asset-card { min-width: 0; padding: 11px; border: 1px solid var(--hairline-soft); border-radius: 11px; background: var(--surface-raised); }
.card-topline { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card-topline h4 { margin: 0; color: var(--ink); font-size: var(--fs-sm); line-height: 1.4; }
.capability-card > p, .asset-skill { margin: 6px 0 0; color: var(--ink-soft); font-size: var(--fs-xs); line-height: 1.5; }
.card-meta, .card-trust, .asset-ladder { display: flex; flex-wrap: wrap; gap: 5px 8px; margin-top: 8px; color: var(--ink-faint); font-size: var(--fs-2xs); }
.card-meta span + span::before { content: "·"; margin-right: 8px; color: var(--hairline); }
.card-trust { padding-top: 8px; border-top: 1px dashed var(--hairline-soft); }
.card-trust .is-pending { color: var(--trust-pending); }

.state-chip, .asset-ladder span { padding: 3px 7px; border-radius: 999px; white-space: nowrap; font-size: var(--fs-2xs); }
.state-chip.is-declared { color: var(--clay); background: var(--clay-soft); }
.is-signed { color: var(--trust-signed); background: rgba(var(--trust-signed-rgb), .09); }
.is-pending { color: var(--trust-pending); background: rgba(var(--trust-pending-rgb), .09); }
.is-failed { color: var(--trust-fail); background: color-mix(in srgb, var(--trust-fail) 9%, transparent); }
.is-rejected { color: var(--ink-soft); background: var(--hover-tint); }
.is-unformed { color: var(--ink-soft); background: var(--hover-tint); }
.asset-kind { color: var(--clay); font-size: var(--fs-2xs); }
.asset-kind + h4 { margin-top: 3px; }
.asset-list { display: grid; gap: 8px; }
.asset-empty { padding: 14px; border: 1px dashed var(--hairline); border-radius: 10px; color: var(--ink-soft); font-size: var(--fs-xs); line-height: 1.6; }

@media (max-width: 640px) {
  .feature-asset-map { margin-top: 8px; }
  .map-counts { display: none; }
  .map-body { padding: 11px; }
  .map-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .capability-grid { grid-template-columns: 1fr; }
  .map-section-heading { align-items: flex-start; flex-direction: column; }
  .map-state.is-error { align-items: stretch; flex-direction: column; }
  .map-retry { width: 100%; }
  .map-ready-bar { align-items: stretch; flex-direction: column; }
  .map-refresh { min-height: 44px; width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .feature-asset-map * { scroll-behavior: auto; }
}
</style>
