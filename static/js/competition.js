/* Browser focus signals are advisory and never change scores or disqualify a team. */
(() => {
  'use strict';
  let started = false, lastSignal = {}, wasAway = false;
  async function log(type) {
    if (!started || App.eventState?.event_status !== 'LIVE') return;
    if ((lastSignal[type] || 0) > Date.now() - 2000) return;
    lastSignal[type] = Date.now();
    try { await App.request('/api/activity', { method: 'POST', body: { event_type: type }, keepalive: true }); } catch (_) { /* Advisory telemetry must not interrupt participation. */ }
  }
  function init() {
    const dialog = document.getElementById('competition-dialog');
    if (!dialog) return;
    const reminder = document.getElementById('fullscreen-reminder');
    const toggle = document.getElementById('fullscreen-toggle');
    const help = document.getElementById('fullscreen-help');
    const fallback = document.getElementById('competition-fallback');
    const closeIntro = () => { started = true; dialog.close(); };
    async function enter() {
      try {
        if (!document.documentElement.requestFullscreen) throw new Error('Fullscreen is not supported by this browser.');
        await document.documentElement.requestFullscreen(); closeIntro(); reminder.hidden = true; log('fullscreen_enter');
      } catch (_) {
        help.textContent = 'This browser could not enter fullscreen. You can continue and ask a volunteer for help.'; fallback.hidden = false;
        if (!dialog.open) { App.toast('Fullscreen is unavailable. You can continue your competition.', 'warning'); started = true; }
      }
    }
    document.getElementById('competition-start').addEventListener('click', enter);
    fallback.addEventListener('click', closeIntro);
    document.getElementById('fullscreen-return').addEventListener('click', enter);
    document.getElementById('fullscreen-dismiss').addEventListener('click', () => { reminder.hidden = true; });
    toggle.addEventListener('click', async () => { if (document.fullscreenElement) { try { await document.exitFullscreen(); } catch (_) { App.toast('Could not change fullscreen mode.', 'warning'); } } else await enter(); });
    dialog.addEventListener('cancel', event => { event.preventDefault(); });
    document.addEventListener('fullscreenchange', () => {
      const fullscreen = !!document.fullscreenElement;
      toggle.querySelector('[data-fullscreen-label]').textContent = fullscreen ? 'Exit fullscreen' : 'Fullscreen'; toggle.setAttribute('aria-label', fullscreen ? 'Exit fullscreen' : 'Enter fullscreen');
      if (started) { reminder.hidden = fullscreen; log(fullscreen ? 'fullscreen_enter' : 'fullscreen_exit'); }
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) { wasAway = true; log('tab_hidden'); } else { log('window_visible'); if (started && wasAway) { App.toast('Competition window regained focus. Window changes may be reviewed by organizers.', 'info'); wasAway = false; } } });
    window.addEventListener('blur', () => log('window_blur'));
    window.addEventListener('focus', () => log('window_focus'));
    if (!document.fullscreenElement) dialog.showModal(); else started = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
