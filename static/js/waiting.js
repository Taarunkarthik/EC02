// Waiting room: live status, redirect on start. The countdown is cosmetic only —
// the server's start time is already in effect, so we never delay the real clock.
(() => {
  const close = document.getElementById('init-close');
  if (close) close.addEventListener('click', () => document.getElementById('init-overlay').remove());

  let leaving = false;
  document.addEventListener('ex0:event', e => {
    const d = e.detail;
    const c = document.getElementById('teams-registered-count'); if (c && d.connected_teams !== undefined) c.textContent = d.connected_teams;
    if (leaving) return;
    if (d.event_status === 'COMPLETED') { leaving = true; location.href = '/result'; }
    else if (d.event_status === 'LIVE') {
      leaving = true;
      const ov = document.getElementById('countdown'), n = document.getElementById('count-num');
      ov.classList.remove('hidden');
      let i = 3; // 3-2-1 then go; shortened to 2s total so participants lose little time
      const tick = () => { if (i === 0) { location.href = '/arena'; return; } n.textContent = i--; n.style.animation = 'none'; void n.offsetWidth; n.style.animation = ''; setTimeout(tick, 650); };
      tick();
    }
  });
})();
