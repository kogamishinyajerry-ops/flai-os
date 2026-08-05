<template>
  <div class="welcome-gate" role="dialog" aria-modal="true" aria-labelledby="welcome-gate-title">
    <!-- ≥900px 品牌氛围面（W6 登录门仪式感）：纯装饰，aria-hidden 让屏幕阅读器
         直达下方真正的登录对话框；<900px 隐去，不占位不影响现状单卡布局。 -->
    <div class="welcome-gate__brand fx-rise" aria-hidden="true">
      <div class="welcome-gate__brand-inner">
        <img class="welcome-gate__brand-art" :src="badgeArt" alt="" />
        <p class="welcome-gate__tagline">平台提议，你拍板。</p>
        <p class="welcome-gate__tagline-sub">二所工程智能体运行底座——任务在这里拆解、执行、留痕。</p>
      </div>
    </div>
    <main class="welcome-gate__content fx-rise">
      <img class="welcome-gate__art" :src="badgeArt" alt="" />
      <h1 id="welcome-gate-title" class="welcome-gate__title">欢迎来到 FLAi-OS</h1>
      <p class="welcome-gate__note">登录后开始工作——最终放行由你亲手确认。</p>

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

/* 品牌氛围面：<900px 不渲染（现状式单卡回落），≥900px 布局见文末 media query。 */
.welcome-gate__brand {
  display: none;
}

.welcome-gate__brand-inner {
  display: flex;
  max-width: 420px;
  flex-direction: column;
  align-items: flex-start;
}

.welcome-gate__brand-art {
  width: clamp(190px, 20vw, 300px);
  height: auto;
  margin: 0 0 var(--space-6);
}

.welcome-gate__tagline {
  margin: 0 0 var(--space-3);
  color: var(--ink);
  font-family: var(--serif);
  font-size: clamp(32px, 3.2vw, 50px);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: 0.2px;
}

.welcome-gate__tagline-sub {
  margin: 0;
  max-width: 34ch;
  color: var(--ink-soft);
  font-size: var(--fs-body);
  line-height: 1.7;
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

/* ≥900px 登录门仪式感（W6，docs/design/UI-DESKTOP-CRAFT.md）：左右分屏——
   左=品牌氛围面（暖纸渐变+放大插画+标语），右=登录卡（原内容原样迁入，不改
   动、不改样式）。<900px 本块整体不生效，回落现状单卡居中。 */
@media (min-width: 900px) {
  .welcome-gate {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    padding: 0;
  }

  .welcome-gate__brand {
    display: flex;
    box-sizing: border-box;
    place-self: stretch;
    align-items: center;
    justify-content: center;
    padding: var(--space-12) clamp(40px, 6vw, 96px);
    background: linear-gradient(155deg, var(--paper-cream), var(--paper-canvas-b) 60%, var(--paper-rail));
    border-right: 1px solid var(--hairline);
  }

  /* 品牌氛围面已放大陈列同一插画，卡内小徽标隐去避免两处重复视觉锚点。 */
  .welcome-gate__art {
    display: none;
  }
}
</style>
