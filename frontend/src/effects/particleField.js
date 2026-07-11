// 粒子场引擎（动效系统 E1，SSOT=docs/design/MOTION-SYSTEM.md）——「石墨尘 + 蓝图连线」。
// canvas 2D 手写实现，零依赖。设计红线：中性 ink 色低透明度（不碰信任色槽）、
// 低速无爆发（诚实地板：常驻 ambient 是明示的装饰，不暗示不存在的活动）、
// prefers-reduced-motion 直接不启动、document.hidden 暂停、单 rAF、DPR 上限 2、
// 粒子上限 120。调用方持有返回句柄负责 destroy（组件 onUnmounted）。
//
// boost ∈ [0,1]：真实信号增强档（如 work-state 任务数/5 封顶）——只微调速度与
// 连线透明度，信号回落动效必须回落（由调用方每次数据刷新后 setBoost）。

const MAX_COUNT = 120;

const DEFAULTS = {
  density: 0.55, // 每 10000px² 粒子数
  speed: 0.14, // px/frame 基速（60fps 下约 8px/s——慢漂）
  color: "43, 38, 34", // --ink 的 RGB；只此一色，透明度分层
  dotAlpha: 0.32,
  linkAlpha: 0.07,
  linkDist: 110, // 近距连线阈值（蓝图感）
  sizeMin: 0.8,
  sizeMax: 2.2,
  pointerRepel: 70, // 指针轻斥力半径；0 = 关闭
};

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function createParticleField(canvas, options = {}) {
  const opts = { ...DEFAULTS, ...options };

  // reduced-motion：不启动、不画（空 canvas 无害）；返回同形状句柄让调用方零分支。
  if (!canvas || prefersReducedMotion()) {
    return { destroy() {}, setBoost() {} };
  }

  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let width = 0;
  let height = 0;
  let particles = [];
  let boost = 0;
  let rafId = null;
  let running = true;
  const pointer = { x: -1, y: -1, active: false };

  function targetCount() {
    return Math.min(MAX_COUNT, Math.round(((width * height) / 10000) * opts.density));
  }

  function makeParticle() {
    const angle = Math.random() * Math.PI * 2;
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      vx: Math.cos(angle),
      vy: Math.sin(angle),
      size: opts.sizeMin + Math.random() * (opts.sizeMax - opts.sizeMin),
      // 相位错开让呼吸不齐步（避免整场同频闪烁的机械感）
      phase: Math.random() * Math.PI * 2,
    };
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = targetCount();
    while (particles.length < n) particles.push(makeParticle());
    if (particles.length > n) particles.length = n;
  }

  let frame = 0;
  function step() {
    rafId = null;
    if (!running) return;
    frame++;
    const speed = opts.speed * (1 + boost * 0.9);
    ctx.clearRect(0, 0, width, height);

    for (const p of particles) {
      p.x += p.vx * speed;
      p.y += p.vy * speed;
      // 指针轻斥力：只推不吸，半径小、力度低——「好玩」而非炫技
      if (opts.pointerRepel > 0 && pointer.active) {
        const dx = p.x - pointer.x;
        const dy = p.y - pointer.y;
        const d2 = dx * dx + dy * dy;
        const r = opts.pointerRepel;
        if (d2 < r * r && d2 > 0.01) {
          const d = Math.sqrt(d2);
          const f = ((r - d) / r) * 0.35;
          p.x += (dx / d) * f;
          p.y += (dy / d) * f;
        }
      }
      // 环形边界（穿出即从对侧回来，无出生/死亡爆发）
      if (p.x < -4) p.x = width + 4;
      else if (p.x > width + 4) p.x = -4;
      if (p.y < -4) p.y = height + 4;
      else if (p.y > height + 4) p.y = -4;
    }

    // 蓝图连线：O(n²) 但 n≤120 且低频页面，预算充裕；透明度随距离衰减
    const linkAlpha = opts.linkAlpha * (1 + boost * 0.6);
    for (let i = 0; i < particles.length; i++) {
      const a = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < opts.linkDist * opts.linkDist) {
          const t = 1 - Math.sqrt(d2) / opts.linkDist;
          ctx.strokeStyle = `rgba(${opts.color}, ${(linkAlpha * t).toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    for (const p of particles) {
      const breathe = 0.75 + 0.25 * Math.sin(frame * 0.01 + p.phase);
      ctx.fillStyle = `rgba(${opts.color}, ${(opts.dotAlpha * breathe).toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }

    rafId = requestAnimationFrame(step);
  }

  function start() {
    if (rafId == null && running && !document.hidden) {
      rafId = requestAnimationFrame(step);
    }
  }
  function onVisibility() {
    if (document.hidden) {
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = null;
    } else {
      start();
    }
  }
  function onPointerMove(e) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = e.clientX - rect.left;
    pointer.y = e.clientY - rect.top;
    pointer.active =
      pointer.x >= 0 && pointer.y >= 0 && pointer.x <= rect.width && pointer.y <= rect.height;
  }
  function onPointerLeave() {
    pointer.active = false;
  }

  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(resize) : null;
  if (ro) ro.observe(canvas);
  document.addEventListener("visibilitychange", onVisibility);
  // 监听挂宿主容器（canvas 自身 pointer-events:none 收不到事件）
  const host = canvas.parentElement || canvas;
  host.addEventListener("pointermove", onPointerMove, { passive: true });
  host.addEventListener("pointerleave", onPointerLeave, { passive: true });

  resize();
  start();

  return {
    setBoost(v) {
      boost = Math.max(0, Math.min(1, Number(v) || 0));
    },
    destroy() {
      running = false;
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = null;
      if (ro) ro.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      host.removeEventListener("pointermove", onPointerMove);
      host.removeEventListener("pointerleave", onPointerLeave);
      particles = [];
    },
  };
}
