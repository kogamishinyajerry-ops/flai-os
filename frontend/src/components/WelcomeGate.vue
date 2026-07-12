<template>
  <div class="welcome-gate" role="dialog" aria-modal="true" aria-labelledby="welcome-gate-title">
    <main class="welcome-gate__content fx-rise">
      <img class="welcome-gate__art" :src="badgeArt" alt="" />
      <h1 id="welcome-gate-title" class="welcome-gate__title">欢迎来到 FLAi-OS</h1>
      <p class="welcome-gate__note">留下称呼，工作台会记住你——签发永远由你亲手完成。</p>

      <el-input
        v-model="name"
        class="welcome-gate__input"
        placeholder="怎么称呼你？"
        autofocus
        @keyup.enter="submit"
      />
      <el-button
        class="welcome-gate__button"
        type="primary"
        :disabled="!canSubmit"
        @click="submit"
      >
        进入工作台
      </el-button>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { ElMessage } from "element-plus";
import badgeArt from "../assets/welcome-badge.png";
import { saveName } from "../utils/identity";

// 诚实边界：仅保存本地工作称呼，不做认证或代签；内网 SSO 接入递延。
const name = ref("");
const emit = defineEmits(["done"]);
const canSubmit = computed(() => Boolean(name.value.trim()));

function submit() {
  const trimmedName = name.value.trim();
  if (!trimmedName) return;
  const persisted = saveName(trimmedName);
  if (persisted === false) {
    // 隐私模式等存储不可用：内存态照常工作，如实告知边界（不假装记住了）
    ElMessage.warning("浏览器存储不可用——称呼仅本次会话有效，刷新后需重新留名。");
  }
  emit("done");
}
</script>

<style scoped>
.welcome-gate {
  position: fixed;
  inset: 0;
  z-index: 300;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  overflow-y: auto;
  padding: clamp(24px, 6vh, 56px) 20px;
  background: var(--page-bg);
  color: var(--ink);
}

.welcome-gate__content {
  display: flex;
  width: 100%;
  max-width: 360px;
  flex-direction: column;
  align-items: stretch;
  text-align: center;
}

.welcome-gate__art {
  width: 170px;
  max-width: 50vw;
  height: auto;
  margin: 0 auto 24px;
}

.welcome-gate__title {
  margin: 0;
  color: var(--ink);
  font-family: var(--serif);
  font-size: clamp(28px, 5vw, 36px);
  font-weight: 600;
  line-height: 1.2;
}

.welcome-gate__note {
  margin: 12px 0 24px;
  color: var(--ink-soft);
  font-size: 14px;
  line-height: 1.7;
}

.welcome-gate__input {
  --el-input-bg-color: var(--surface-raised);
  --el-input-text-color: var(--ink);
  --el-input-border-color: var(--hairline);
  --el-input-hover-border-color: var(--clay-softer);
  --el-input-focus-border-color: var(--clay);
  --el-input-placeholder-color: var(--ink-faint);
}

.welcome-gate__input :deep(.el-input__wrapper) {
  min-height: 44px;
  padding: 0 14px;
  border-radius: 10px;
  background: var(--surface-raised);
  box-shadow: 0 0 0 1px var(--hairline) inset, var(--shadow-card);
}

.welcome-gate__input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--clay-softer) inset, var(--shadow-card);
}

.welcome-gate__input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--clay) inset, var(--shadow-card);
}

.welcome-gate__button {
  width: 100%;
  height: 44px;
  margin-top: 12px;
  border-radius: 10px;
  font-weight: 600;
  box-shadow: var(--shadow-card);
}
</style>
