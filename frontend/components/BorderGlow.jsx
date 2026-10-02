'use client';

import { useRef, useCallback, useEffect } from 'react';
import './BorderGlow.css';

function parseHSL(hslStr) {
  const match = hslStr.match(/([\d.]+)\s*([\d.]+)%?\s*([\d.]+)%?/);
  if (!match) return { h: 40, s: 80, l: 80 };
  return { h: parseFloat(match[1]), s: parseFloat(match[2]), l: parseFloat(match[3]) };
}

function buildGlowVars(glowColor, intensity) {
  const { h, s, l } = parseHSL(glowColor);
  const base = `${h}deg ${s}% ${l}%`;
  const opacities = [100, 60, 50, 40, 30, 20, 10];
  const keys = ['', '-60', '-50', '-40', '-30', '-20', '-10'];
  const vars = {};
  for (let i = 0; i < opacities.length; i++) {
    vars[`--glow-color${keys[i]}`] = `hsl(${base} / ${Math.min(opacities[i] * intensity, 100)}%)`;
  }
  return vars;
}

const GRADIENT_POSITIONS = ['80% 55%', '69% 34%', '8% 6%', '41% 38%', '86% 85%', '82% 18%', '51% 4%'];
const GRADIENT_KEYS = ['--gradient-one', '--gradient-two', '--gradient-three', '--gradient-four', '--gradient-five', '--gradient-six', '--gradient-seven'];
const COLOR_MAP = [0, 1, 2, 0, 1, 2, 1];

function buildGradientVars(colors) {
  const vars = {};
  for (let i = 0; i < 7; i++) {
    const c = colors[Math.min(COLOR_MAP[i], colors.length - 1)];
    vars[GRADIENT_KEYS[i]] = `radial-gradient(at ${GRADIENT_POSITIONS[i]}, ${c} 0px, transparent 50%)`;
  }
  vars['--gradient-base'] = `linear-gradient(${colors[0]} 0 100%)`;
  return vars;
}

function isLightColor(color) {
  const value = color.trim().replace('#', '');
  if (!/^[\da-f]{3}([\da-f]{3})?$/i.test(value)) return false;
  const hex = value.length === 3 ? value.split('').map(char => char + char).join('') : value;
  const red = parseInt(hex.slice(0, 2), 16);
  const green = parseInt(hex.slice(2, 4), 16);
  const blue = parseInt(hex.slice(4, 6), 16);
  return red * 0.2126 + green * 0.7152 + blue * 0.0722 > 180;
}

function easeOutCubic(x) { return 1 - Math.pow(1 - x, 3); }
function easeInCubic(x) { return x * x * x; }

function animateValue({ start = 0, end = 100, duration = 1000, delay = 0, ease = easeOutCubic, onUpdate, onEnd }) {
  let frame = 0;
  let stopped = false;
  let began = 0;
  function tick(now) {
    if (stopped) return;
    if (!began) began = now;
    const t = Math.max(0, Math.min((now - began) / duration, 1));
    onUpdate(start + (end - start) * ease(t));
    if (t < 1) frame = requestAnimationFrame(tick);
    else if (onEnd) onEnd();
  }
  const timer = setTimeout(() => { if (!stopped) frame = requestAnimationFrame(tick); }, delay);
  return () => { stopped = true; clearTimeout(timer); cancelAnimationFrame(frame); };
}

const BorderGlow = ({
  children,
  className = '',
  edgeSensitivity = 30,
  glowColor = '40 80 80',
  backgroundColor = '#120F17',
  borderRadius = 28,
  glowRadius = 40,
  glowIntensity = 1.0,
  coneSpread = 25,
  animated = false,
  colors = ['#c084fc', '#f472b6', '#38bdf8'],
  fillOpacity = 0.5,
  eventTarget = null,
  strong = false,
}) => {
  const cardRef = useRef(null);

  const pointerFrame = useRef(0);
  const pendingPointer = useRef(null);

  const handlePointerMove = useCallback((event) => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || event.pointerType === 'touch') return;
    pendingPointer.current = { x: event.clientX, y: event.clientY };
    if (pointerFrame.current) return;
    pointerFrame.current = requestAnimationFrame(() => {
      pointerFrame.current = 0;
      const card = cardRef.current;
      const pointer = pendingPointer.current;
      if (!card || !pointer || document.hidden) return;
      const rect = card.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const dx = pointer.x - rect.left - cx;
      const dy = pointer.y - rect.top - cy;
      const edge = Math.min(Math.max(Math.abs(dx) / Math.max(1, cx), Math.abs(dy) / Math.max(1, cy)), 1);
      const angle = (Math.atan2(dy, dx) * 180 / Math.PI + 450) % 360;
      card.style.setProperty('--edge-proximity', `${(edge * 100).toFixed(3)}`);
      card.style.setProperty('--cursor-angle', `${angle.toFixed(3)}deg`);
      card.style.setProperty('--pointer-x', `${pointer.x - rect.left}px`);
      card.style.setProperty('--pointer-y', `${pointer.y - rect.top}px`);
    });
  }, []);

  useEffect(() => {
    const target = eventTarget || cardRef.current;
    if (!target) return;
    const clear = () => {
      cancelAnimationFrame(pointerFrame.current);
      pointerFrame.current = 0;
      pendingPointer.current = null;
      cardRef.current?.style.setProperty('--edge-proximity', '0');
    };
    const focus = () => { if (strong) cardRef.current?.style.setProperty('--edge-proximity', '100'); };
    target.addEventListener('pointermove', handlePointerMove, { passive: true });
    target.addEventListener('pointerleave', clear);
    target.addEventListener('focusin', focus);
    target.addEventListener('focusout', clear);
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    preference.addEventListener('change', clear);
    document.addEventListener('visibilitychange', clear);
    return () => {
      clear();
      target.removeEventListener('pointermove', handlePointerMove);
      target.removeEventListener('pointerleave', clear);
      target.removeEventListener('focusin', focus);
      target.removeEventListener('focusout', clear);
      preference.removeEventListener('change', clear);
      document.removeEventListener('visibilitychange', clear);
    };
  }, [eventTarget, handlePointerMove, strong]);

  useEffect(() => {
    if (!animated || !cardRef.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const card = cardRef.current;
    const angleStart = 110;
    const angleEnd = 465;
    card.classList.add('sweep-active');
    card.style.setProperty('--cursor-angle', `${angleStart}deg`);

    const animations = [];
    animations.push(animateValue({ duration: 500, onUpdate: v => card.style.setProperty('--edge-proximity', v) }));
    animations.push(animateValue({ ease: easeInCubic, duration: 1500, end: 50, onUpdate: v => {
      card.style.setProperty('--cursor-angle', `${(angleEnd - angleStart) * (v / 100) + angleStart}deg`);
    }}));
    animations.push(animateValue({ ease: easeOutCubic, delay: 1500, duration: 2250, start: 50, end: 100, onUpdate: v => {
      card.style.setProperty('--cursor-angle', `${(angleEnd - angleStart) * (v / 100) + angleStart}deg`);
    }}));
    animations.push(animateValue({ ease: easeInCubic, delay: 2500, duration: 1500, start: 100, end: 0,
      onUpdate: v => card.style.setProperty('--edge-proximity', v),
      onEnd: () => card.classList.remove('sweep-active'),
    }));
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const stop = () => {
      animations.forEach(cancel => cancel());
      card.classList.remove('sweep-active');
      card.style.setProperty('--edge-proximity', '0');
    };
    const onVisibility = () => { if (document.hidden) stop(); };
    preference.addEventListener('change', stop);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stop();
      preference.removeEventListener('change', stop);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [animated]);

  const glowVars = buildGlowVars(glowColor, glowIntensity);
  const lightSurface = isLightColor(backgroundColor);

  return (
    <div
      ref={cardRef}
      className={`border-glow-card${lightSurface ? ' border-glow-card--light' : ''}${strong ? ' border-glow-card--strong' : ''} ${className}`}
      style={{
        '--card-bg': backgroundColor,
        '--edge-sensitivity': edgeSensitivity,
        '--border-radius': `${borderRadius}px`,
        '--glow-padding': `${glowRadius}px`,
        '--cone-spread': coneSpread,
        '--fill-opacity': fillOpacity,
        ...glowVars,
        ...buildGradientVars(colors),
      }}
    >
      <span className="edge-light" />
      <div className="border-glow-inner">
        {children}
      </div>
    </div>
  );
};

export default BorderGlow;
