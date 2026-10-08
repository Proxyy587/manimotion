"use client";

import { useEffect, useRef } from "react";

import { useThemeOptional } from "@/components/theme/theme-provider";
import { cn } from "@/lib/utils";

type Particle = {
  x: number;
  y: number;
  ox: number;
  oy: number;
  vx: number;
  vy: number;
  r: number;
  phase: number;
};

/**
 * Playful magnetic particle field — reacts to cursor with springy push/pull.
 */
export function LandingMark({ className }: { className?: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const themeCtx = useThemeOptional();

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvasEl = canvasRef.current;
    if (!wrap || !canvasEl) return;

    const canvas = canvasEl;
    const ctxMaybe = canvas.getContext("2d");
    if (!ctxMaybe) return;
    const ctx = ctxMaybe;

    const wrapEl = wrap;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    let w = 0;
    let h = 0;
    let raf = 0;
    let particles: Particle[] = [];
    const mouse = { x: -9999, y: -9999, active: false };
    let t = 0;
    let ripples: { x: number; y: number; r: number; life: number }[] = [];

    function inkColor() {
      const styles = getComputedStyle(document.documentElement);
      return (
        styles.getPropertyValue("--ink").trim() ||
        (themeCtx?.theme === "light" ? "#111110" : "#f3f3ef")
      );
    }

    function resize() {
      const rect = wrapEl.getBoundingClientRect();
      w = Math.max(280, Math.floor(rect.width));
      h = Math.max(220, Math.floor(rect.height));
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
    }

    function seed() {
      const count = Math.min(140, Math.floor((w * h) / 900));
      const cx = w / 2;
      const cy = h / 2;
      particles = [];
      for (let i = 0; i < count; i++) {
        const a = Math.random() * Math.PI * 2;
        const rr = Math.sqrt(Math.random());
        const rx = 118 * rr;
        const ry = 78 * rr;
        const x = cx + Math.cos(a) * rx;
        const y = cy + Math.sin(a) * ry;
        particles.push({
          x,
          y,
          ox: x,
          oy: y,
          vx: 0,
          vy: 0,
          r: 1.1 + Math.random() * 1.8,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }

    function onMove(e: PointerEvent) {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      // Keep influence alive slightly outside the canvas so it doesn't feel boxed
      const pad = 80;
      mouse.active =
        mouse.x >= -pad &&
        mouse.y >= -pad &&
        mouse.x <= w + pad &&
        mouse.y <= h + pad;
    }

    function onWindowMove(e: PointerEvent) {
      onMove(e);
    }

    function onDown(e: PointerEvent) {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      ripples.push({
        x,
        y,
        r: 4,
        life: 1,
      });
      for (const p of particles) {
        const dx = p.x - x;
        const dy = p.y - y;
        const dist = Math.hypot(dx, dy) || 1;
        if (dist < 90) {
          const f = ((90 - dist) / 90) * 6;
          p.vx += (dx / dist) * f;
          p.vy += (dy / dist) * f;
        }
      }
    }

    function frame() {
      t += 0.016;
      const ink = inkColor();
      ctx.clearRect(0, 0, w, h);

      // soft orb wash
      const g = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, 140);
      g.addColorStop(0, withAlpha(ink, 0.1));
      g.addColorStop(0.55, withAlpha(ink, 0.035));
      g.addColorStop(1, withAlpha(ink, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(w / 2, h / 2, 130, 90, 0, 0, Math.PI * 2);
      ctx.fill();

      // rings
      ctx.strokeStyle = withAlpha(ink, 0.18);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(w / 2, h / 2, 118, 78, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = withAlpha(ink, 0.12);
      ctx.beginPath();
      ctx.ellipse(w / 2, h / 2, 62, 40, 0, 0, Math.PI * 2);
      ctx.stroke();

      for (const p of particles) {
        if (!reduce) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.hypot(dx, dy);
          const influence = mouse.active ? 110 : 0;

          if (influence && dist < influence && dist > 0.1) {
            // magnetic swirl + push
            const force = (1 - dist / influence) ** 1.4;
            const nx = dx / dist;
            const ny = dy / dist;
            p.vx += nx * force * 0.55;
            p.vy += ny * force * 0.55;
            // tangent swirl
            p.vx += -ny * force * 0.35;
            p.vy += nx * force * 0.35;
          }

          // spring home + idle bob
          const bobX = Math.sin(t * 1.2 + p.phase) * 1.2;
          const bobY = Math.cos(t * 0.9 + p.phase) * 1.2;
          p.vx += (p.ox + bobX - p.x) * 0.045;
          p.vy += (p.oy + bobY - p.y) * 0.045;
          p.vx *= 0.86;
          p.vy *= 0.86;
          p.x += p.vx;
          p.y += p.vy;
        }

        const pulse = reduce
          ? 1
          : 0.75 + 0.35 * Math.sin(t * 2.4 + p.phase);
        ctx.beginPath();
        ctx.fillStyle = withAlpha(ink, 0.28 + pulse * 0.35);
        ctx.arc(p.x, p.y, p.r * pulse, 0, Math.PI * 2);
        ctx.fill();
      }

      // soft cursor influence only via particles — no clipped glow disc
      ripples = ripples.filter((r) => r.life > 0);
      for (const r of ripples) {
        r.r += 2.4;
        r.life -= 0.03;
        ctx.strokeStyle = withAlpha(ink, Math.max(0, r.life) * 0.35);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(r.x, r.y, r.r, 0, Math.PI * 2);
        ctx.stroke();
      }

      raf = requestAnimationFrame(frame);
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrapEl);

    window.addEventListener("pointermove", onWindowMove, { passive: true });
    canvas.addEventListener("pointerdown", onDown);
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onWindowMove);
      canvas.removeEventListener("pointerdown", onDown);
    };
  }, [themeCtx?.theme]);

  return (
    <div
      ref={wrapRef}
      className={cn("lp-mark relative mx-auto touch-none", className)}
      style={{ width: "min(320px, 84vw)", height: 260 }}
      aria-hidden
    >
      <canvas ref={canvasRef} className="block size-full cursor-crosshair" />
    </div>
  );
}

function withAlpha(color: string, alpha: number) {
  if (color.startsWith("#") && (color.length === 7 || color.length === 4)) {
    const hex =
      color.length === 4
        ? `#${color[1]}${color[1]}${color[2]}${color[2]}${color[3]}${color[3]}`
        : color;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return color;
}
