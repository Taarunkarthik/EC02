// Competition-mode guards: fullscreen, focus/visibility signals, anti-copy deterrents.
// These are DETERRENTS and ORGANISER SIGNALS only — never an authority, never auto-punitive.
const ArenaGuard = (() => {
  const $ = id => document.getElementById(id);
  const supportsFS = !!(document.documentElement.requestFullscreen);
  let wasFullscreen = false, hiddenAt = 0;

  const report = type => EX0.api('/api/activity', { json: { type } });
  const inFS = () => !!document.fullscreenElement;
  const enter = () => supportsFS ? document.documentElement.requestFullscreen().catch(() => {}) : Promise.resolve();

  function syncPill() {
    const p = $('fs-pill'); if (!p) return;
    p.className = 'fs-pill ' + (inFS() ? 'on' : 'off'); p.textContent = inFS() ? 'FULLSCREEN ON' : 'FULLSCREEN OFF';
  }

  function init({ onReady }) {
    const gate = $('gate-start'), exit = $('gate-exit');
    if (!supportsFS) { $('gate-go').textContent = 'START'; $('gate-note').textContent = 'Fullscreen is not supported by this browser; continuing without it.'; }
    gate.classList.remove('hidden');
    $('gate-go').addEventListener('click', async () => { await enter(); gate.classList.add('hidden'); wasFullscreen = inFS(); syncPill(); onReady && onReady(); });
    $('gate-return').addEventListener('click', async () => { await enter(); });
    $('fs-pill').addEventListener('click', () => inFS() ? document.exitFullscreen() : enter());

    document.addEventListener('fullscreenchange', () => {
      syncPill();
      if (inFS()) { exit.classList.add('hidden'); report('fullscreen_enter'); wasFullscreen = true; }
      else if (wasFullscreen && supportsFS && gate.classList.contains('hidden')) {
        exit.classList.remove('hidden'); EX0.toast('Fullscreen exited', 'warning'); report('fullscreen_exit');
      }
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { hiddenAt = Date.now(); report('tab_hidden'); }
      else { report('tab_visible'); if (hiddenAt) EX0.toast('Competition window lost focus.', 'warning'); hiddenAt = 0; }
    });
    window.addEventListener('blur', () => { if (!document.hidden) report('focus_lost'); });
    window.addEventListener('focus', () => report('focus_regained'));
    initAntiCopy();
  }

  function initAntiCopy() {
    const v = $('code-viewer-container'); if (!v) return;
    const warn = () => EX0.toast('Copying code is restricted during the competition.', 'warning', 2200);
    v.addEventListener('contextmenu', e => { e.preventDefault(); warn(); });
    ['selectstart', 'dragstart', 'copy', 'cut'].forEach(t => v.addEventListener(t, e => { e.preventDefault(); if (t !== 'selectstart') warn(); }));
    document.addEventListener('keydown', e => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase(), t = e.target;
      const inForm = t && t.closest && t.closest('#bug-fix-form');
      if (['u', 's', 'p'].includes(k) || (!inForm && ['c', 'x', 'a'].includes(k))) { e.preventDefault(); warn(); }
    });
    // Answer areas: paste restricted per competition rules
    document.querySelectorAll('#bug-fix-form input, #bug-fix-form textarea').forEach(f =>
      f.addEventListener('paste', e => { e.preventDefault(); EX0.toast('Pasting is disabled in answer fields.', 'warning', 2200); }));
  }
  return { init, enter };
})();
