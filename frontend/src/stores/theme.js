// 主题状态源（美化批「夜航图纸」）：三段 system | light | dark。
// - system 跟随 prefers-color-scheme 并监听热切换（Claude Desktop 同款三段）；
// - 显式选择持久到 localStorage，选回 system 则清除（隐私模式静默降级）；
// - 解析结果挂 documentElement 的 data-theme，CSS 端 :root[data-theme="dark"]
//   整面翻转 token——信任色锁五槽只做明度适配，语义槽位一个不动。
import { ref, computed, watchEffect } from "vue";

const KEY = "flai_theme_mode";

function readMode() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export const themeMode = ref(readMode());

const media = window.matchMedia("(prefers-color-scheme: dark)");
const systemDark = ref(media.matches);
media.addEventListener?.("change", (e) => {
  systemDark.value = e.matches;
});

export const resolvedTheme = computed(() =>
  themeMode.value === "system" ? (systemDark.value ? "dark" : "light") : themeMode.value
);

export function setThemeMode(mode) {
  themeMode.value = mode === "light" || mode === "dark" ? mode : "system";
  try {
    if (themeMode.value === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, themeMode.value);
  } catch {
    /* 隐私模式静默降级：本次会话内仍生效，不持久 */
  }
}

// 模块 import 即生效（App 入口引入）；watchEffect 常驻同步 DOM 属性。
watchEffect(() => {
  document.documentElement.dataset.theme = resolvedTheme.value;
});
