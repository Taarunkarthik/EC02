'use client';

import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { InertiaPlugin } from 'gsap/InertiaPlugin';
import './DotGrid.css';

gsap.registerPlugin(InertiaPlugin);

function hexToRgb(hex) {
  const expanded = hex.replace(/^#/, '').replace(/^([a-f\d])([a-f\d])([a-f\d])$/i, '$1$1$2$2$3$3');
  const match = expanded.match(/^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  return match ? { r: parseInt(match[1], 16), g: parseInt(match[2], 16), b: parseInt(match[3], 16) } : { r: 54, g: 30, b: 33 };
}

/** The supplied DotGrid, with its GSAP inertia and elastic return retained. */
export default function DotGrid({
  dotSize = 4,
  gap = 28,
  baseColor = '#442127',
  activeColor = '#ff334b',
  proximity = 150,
  speedTrigger = 100,
  shockRadius = 250,
  shockStrength = 5,
  maxSpeed = 5000,
  resistance = 750,
  returnDuration = 1.5,
  maxDots = 1800,
  maxDpr = 1.5,
  eventTarget = null,
  className = '',
  style,
}) {
  const wrapperRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    const wrap = wrapperRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d', { alpha: true });
    if (!wrap || !canvas || !ctx) return;
    const target = eventTarget || wrap;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const baseRgb = hexToRgb(baseColor);
    const activeRgb = hexToRgb(activeColor);
    const tweens = new Set();
    const pointer = { x: Infinity, y: Infinity, lastX: 0, lastY: 0, lastTime: 0 };
    let dots = [];
    let width = 0;
    let height = 0;
    let dpr = 1;
    let frame = 0;
    let resizeFrame = 0;
    let visible = true;
    let disposed = false;
    const canAnimate = () => !disposed && visible && !document.hidden && !preference.matches;
    const safeProximity = Math.max(1, proximity);
    const proximitySquared = safeProximity * safeProximity;

    function draw() {
      frame = 0;
      if (disposed) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      for (const dot of dots) {
        const dx = dot.cx - pointer.x;
        const dy = dot.cy - pointer.y;
        const squared = dx * dx + dy * dy;
        let color = baseColor;
        if (!preference.matches && squared < proximitySquared) {
          const ratio = 1 - Math.sqrt(squared) / safeProximity;
          color = `rgb(${Math.round(baseRgb.r + (activeRgb.r - baseRgb.r) * ratio)},${Math.round(baseRgb.g + (activeRgb.g - baseRgb.g) * ratio)},${Math.round(baseRgb.b + (activeRgb.b - baseRgb.b) * ratio)})`;
        }
        ctx.beginPath();
        ctx.arc(dot.cx + dot.xOffset, dot.cy + dot.yOffset, Math.max(0.5, dotSize / 2), 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }
    }

    // A single paint per frame, and no render loop at rest.
    function requestDraw() {
      if (!frame && canAnimate()) frame = requestAnimationFrame(draw);
    }

    function clearTweens() {
      for (const tween of tweens) tween.kill();
      tweens.clear();
    }

    function buildGrid() {
      resizeFrame = 0;
      if (disposed) return;
      const rect = wrap.getBoundingClientRect();
      const nextWidth = Math.round(rect.width);
      const nextHeight = Math.round(rect.height);
      const nextDpr = Math.min(window.devicePixelRatio || 1, Math.max(1, maxDpr));
      if (nextWidth === width && nextHeight === height && nextDpr === dpr && dots.length) return;
      clearTweens();
      width = nextWidth;
      height = nextHeight;
      dpr = nextDpr;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      let cell = Math.max(6, dotSize + gap);
      // Large displays keep the same effect without an unbounded number of tweens.
      const limit = Math.max(100, maxDots);
      while (Math.max(1, Math.floor(width / cell)) * Math.max(1, Math.floor(height / cell)) > limit) cell *= 1.08;
      const cols = Math.max(1, Math.floor(width / cell));
      const rows = Math.max(1, Math.floor(height / cell));
      const startX = (width - (cols - 1) * cell) / 2;
      const startY = (height - (rows - 1) * cell) / 2;
      dots = [];
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          dots.push({ cx: startX + col * cell, cy: startY + row * cell, xOffset: 0, yOffset: 0, inertiaApplied: false });
        }
      }
      canvas.dataset.dotCount = String(dots.length);
      draw();
    }

    function displace(dot, velocityX, velocityY) {
      if (dot.inertiaApplied) return;
      dot.inertiaApplied = true;
      wrap.dataset.motion = 'active';
      let inertia;
      inertia = gsap.to(dot, {
        inertia: {
          xOffset: velocityX,
          yOffset: velocityY,
          resistance: Math.max(100, resistance),
          duration: { min: 0.2, max: 1.2 },
        },
        onUpdate: requestDraw,
        onComplete: () => {
          tweens.delete(inertia);
          let rebound;
          rebound = gsap.to(dot, {
            xOffset: 0,
            yOffset: 0,
            duration: Math.max(0.2, returnDuration),
            ease: 'elastic.out(1,0.75)',
            onUpdate: requestDraw,
            onComplete: () => {
              tweens.delete(rebound);
              dot.inertiaApplied = false;
              if (!tweens.size) wrap.dataset.motion = 'idle';
              requestDraw();
            },
          });
          tweens.add(rebound);
        },
      });
      tweens.add(inertia);
    }

    function onMove(event) {
      if (!canAnimate() || event.pointerType === 'touch') return;
      const now = performance.now();
      const elapsed = pointer.lastTime ? Math.max(8, now - pointer.lastTime) : 16;
      if (pointer.lastTime && elapsed < 16) return;
      let vx = pointer.lastTime ? (event.clientX - pointer.lastX) / elapsed * 1000 : 0;
      let vy = pointer.lastTime ? (event.clientY - pointer.lastY) / elapsed * 1000 : 0;
      let speed = Math.hypot(vx, vy);
      if (speed > maxSpeed) {
        const scale = maxSpeed / speed;
        vx *= scale;
        vy *= scale;
        speed = maxSpeed;
      }
      pointer.lastTime = now;
      pointer.lastX = event.clientX;
      pointer.lastY = event.clientY;
      const rect = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rect.left;
      pointer.y = event.clientY - rect.top;
      if (pointer.x < -safeProximity || pointer.x > width + safeProximity || pointer.y < -safeProximity || pointer.y > height + safeProximity) return;
      if (speed > speedTrigger) {
        for (const dot of dots) {
          const dx = dot.cx - pointer.x;
          const dy = dot.cy - pointer.y;
          if (dx * dx + dy * dy < proximitySquared) displace(dot, dx + vx * 0.005, dy + vy * 0.005);
        }
      }
      requestDraw();
    }

    function onClick(event) {
      if (!canAnimate()) return;
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      if (x < 0 || y < 0 || x > width || y > height) return;
      for (const dot of dots) {
        const distance = Math.hypot(dot.cx - x, dot.cy - y);
        if (distance < shockRadius) {
          const falloff = Math.max(0, 1 - distance / Math.max(1, shockRadius));
          displace(dot, (dot.cx - x) * shockStrength * falloff, (dot.cy - y) * shockStrength * falloff);
        }
      }
    }

    function onLeave() {
      pointer.x = pointer.y = Infinity;
      pointer.lastTime = 0;
      requestDraw();
    }

    function syncActivity() {
      const active = canAnimate();
      wrap.dataset.motion = active ? (tweens.size ? 'active' : 'idle') : 'paused';
      if (!active && frame) { cancelAnimationFrame(frame); frame = 0; }
      if (preference.matches) {
        clearTweens();
        for (const dot of dots) { dot.xOffset = dot.yOffset = 0; dot.inertiaApplied = false; }
        pointer.x = pointer.y = Infinity;
        draw();
      } else {
        for (const tween of tweens) active ? tween.resume() : tween.pause();
        if (active) requestDraw();
      }
    }

    const resize = () => {
      if (!resizeFrame) resizeFrame = requestAnimationFrame(buildGrid);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    const intersection = new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      syncActivity();
    }, { rootMargin: '40px' });
    intersection.observe(wrap);
    target.addEventListener('pointermove', onMove, { passive: true });
    target.addEventListener('pointerleave', onLeave, { passive: true });
    target.addEventListener('click', onClick, { passive: true });
    preference.addEventListener('change', syncActivity);
    document.addEventListener('visibilitychange', syncActivity);
    buildGrid();
    syncActivity();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      cancelAnimationFrame(resizeFrame);
      clearTweens();
      observer.disconnect();
      intersection.disconnect();
      target.removeEventListener('pointermove', onMove);
      target.removeEventListener('pointerleave', onLeave);
      target.removeEventListener('click', onClick);
      preference.removeEventListener('change', syncActivity);
      document.removeEventListener('visibilitychange', syncActivity);
    };
  }, [dotSize, gap, baseColor, activeColor, proximity, speedTrigger, shockRadius, shockStrength, maxSpeed, resistance, returnDuration, maxDots, maxDpr, eventTarget]);

  return <section className={`dot-grid ${className}`} style={style} aria-hidden="true">
    <div ref={wrapperRef} className="dot-grid__wrap" data-motion="idle">
      <canvas ref={canvasRef} className="dot-grid__canvas" />
    </div>
  </section>;
}
