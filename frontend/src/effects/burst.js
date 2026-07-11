// 迸发引擎（动效系统 E2，SSOT=docs/design/MOTION-SYSTEM.md）——一次性粒子时刻。
// 信任色纪律（硬约束）：teal 迸发 **仅**人签放行成功时刻可用（人签是宪法时刻，
// 值得庆祝且语义诚实）；其余一律中性 ink 尘埃。失败/驳回绝不做庆祝动效。
// reduced-motion → 完全 no-op。一次性 overlay canvas，动画完自动移除，零常驻。

// 快照常量仅作 fail-safe 兜底（暗色主题下真值来自 --trust-signed-rgb/--ink-rgb
// 运行时读取，见 signedRgb()/neutralRgb() ——fail-safe 不 fail-broken：token
// 读不到时仍用这两个亮色主题字面量兜底，不让迸发直接哑掉）。
const SIGNED_TEAL_FALLBACK = "22, 125, 139"; // --trust-signed 的 RGB（亮色主题快照）
const NEUTRAL_INK_FALLBACK = "107, 98, 89"; // --ink-soft 的 RGB（亮色主题快照）

// 运行时读取 CSS 变量：暗色块把 --trust-signed-rgb 重定义为提亮值，迸发色随主题走。
function readRgbToken(varName, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return v || fallback;
}
function signedRgb() {
  return readRgbToken("--trust-signed-rgb", SIGNED_TEAL_FALLBACK);
}
function neutralRgb() {
  // --ink-rgb 是正文墨色（暗色下反相为暖白），比常驻不变的 --ink-soft 更贴合
  // 「中性尘埃随主题走」的意图；读不到时兜底回原 --ink-soft 快照。
  return readRgbToken("--ink-rgb", NEUTRAL_INK_FALLBACK);
}

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function runBurst(cx, cy, rgb, count) {
  const canvas = document.createElement("canvas");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const size = 320; // 局部 overlay，不铺全屏
  canvas.width = size * dpr;
  canvas.height = size * dpr;
  canvas.style.cssText = [
    "position:fixed",
    `left:${cx - size / 2}px`,
    `top:${cy - size / 2}px`,
    `width:${size}px`,
    `height:${size}px`,
    "pointer-events:none",
    "z-index:9999",
  ].join(";");
  canvas.setAttribute("aria-hidden", "true");
  document.body.appendChild(canvas);

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const parts = [];
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 1.2 + Math.random() * 2.6;
    parts.push({
      x: size / 2,
      y: size / 2,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 0.8, // 轻微上抛
      size: 1.2 + Math.random() * 2.4,
      life: 1,
      decay: 0.016 + Math.random() * 0.014,
    });
  }

  let rafId = null;
  function frame() {
    ctx.clearRect(0, 0, size, size);
    let alive = 0;
    for (const p of parts) {
      if (p.life <= 0) continue;
      alive++;
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.045; // 重力：尘埃沉降感
      p.vx *= 0.985;
      p.life -= p.decay;
      ctx.fillStyle = `rgba(${rgb}, ${Math.max(0, p.life * 0.85).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
      ctx.fill();
    }
    if (alive > 0 && document.body.contains(canvas)) {
      rafId = requestAnimationFrame(frame);
    } else {
      if (rafId != null) cancelAnimationFrame(rafId);
      canvas.remove();
    }
  }
  rafId = requestAnimationFrame(frame);
}

function centerOf(el) {
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

/** 人签放行成功时刻（唯一 teal 许可点）。el 缺失/降级时静默不放。 */
export function burstSigned(el) {
  if (!el || prefersReducedMotion()) return;
  const { x, y } = centerOf(el);
  runBurst(x, y, signedRgb(), 26);
}

/** 中性尘埃（completed 等中性时刻；绝不用于失败/驳回）。 */
export function burstNeutral(el) {
  if (!el || prefersReducedMotion()) return;
  const { x, y } = centerOf(el);
  runBurst(x, y, neutralRgb(), 16);
}
