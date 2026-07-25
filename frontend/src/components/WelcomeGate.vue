<template>
  <div class="welcome-gate" role="dialog" aria-modal="true" aria-labelledby="welcome-gate-title">
    <main class="welcome-gate__content fx-rise">
      <img class="welcome-gate__art" :src="badgeArt" alt="" width="170" height="170" />
      <h1 id="welcome-gate-title" class="welcome-gate__title">欢迎来到 FLAi-OS</h1>
      <p class="welcome-gate__note">登录后开始工作——签发永远由你亲手完成。</p>

      <el-input
        v-model="username"
        class="welcome-gate__input"
        placeholder="用户名"
        autofocus
        @keyup.enter="submit"
      />
      <el-input
        v-model="password"
        class="welcome-gate__input welcome-gate__password"
        type="password"
        placeholder="密码"
        show-password
        @keyup.enter="submit"
      />
      <p v-if="errorText" class="welcome-gate__error" data-test="login-error">{{ errorText }}</p>
      <el-button
        class="welcome-gate__button"
        type="primary"
        :disabled="!canSubmit"
        :loading="pending"
        @click="submit"
      >
        登录
      </el-button>
      <p class="welcome-gate__hint">没有账户？请联系平台管理员开通（不提供自助注册）。</p>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import badgeArt from "../assets/welcome-badge.png";
import { login } from "../stores/session";

// ADR-0019 D8：真登录门。错误如实展示后端 detail（401 凭据错/429 节流），
// 不粉饰不翻译；成功后 emit done，App 收门。
const username = ref("");
const password = ref("");
const errorText = ref("");
const pending = ref(false);
const emit = defineEmits(["done"]);
const canSubmit = computed(() => Boolean(username.value.trim()) && Boolean(password.value));

async function submit() {
  if (!canSubmit.value || pending.value) return;
  pending.value = true;
  errorText.value = "";
  try {
    await login(username.value.trim(), password.value);
    emit("done");
  } catch (err) {
    errorText.value = err.detail || String(err.message || err);
    password.value = "";
  } finally {
    pending.value = false;
  }
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

.welcome-gate__password {
  margin-top: 10px;
}

.welcome-gate__error {
  margin: 10px 0 0;
  color: var(--trust-fail);
  font-size: 13px;
  line-height: 1.6;
}

.welcome-gate__hint {
  margin: 14px 0 0;
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.6;
}
</style>
