// EXIT CODE 0 — shared client utilities.
// The browser only DISPLAYS state; the Flask server stays authoritative for
// scores, timer and event status.

const EX0 = (() => {
  /* ---------- toasts ---------- */
  const ICONS = { success: '✓', error: '✕', warning: '⚠', info: 'i' };
  function toast(message, type = 'info', ms = 4000) {
    let box = document.getElementById('toast-container');
    if (!box) { box = document.createElement('div'); box.id = 'toast-container'; document.body.appendChild(box); }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    const ic = document.createElement('span'); ic.className = 'toast-icon'; ic.textContent = ICONS[type] || 'i';
    const tx = document.createElement('span'); tx.textContent = message;   // textContent: never inject HTML
    el.append(ic, tx);
    box.appendChild(el);
    while (box.children.length > 4) box.firstChild.remove();
    setTimeout(() => { el.classList.add('leaving'); setTimeout(() => el.remove(), 260); }, ms);
  }

  /* ---------- connection indicator ---------- */
  let online = true, restoreTimer = null;
  function setConn(ok) {
    const el = document.getElementById('conn-indicator'), tx = document.getElementById('conn-text');
    document.querySelectorAll('[data-conn]').forEach(n => n.dataset.state = ok ? 'ok' : 'down');
    if (!el || ok === online) { online = ok; return; }
    const wasDown = !online; online = ok;
    clearTimeout(restoreTimer);
    if (!ok) { el.className = 'conn reconnecting'; tx.textContent = 'RECONNECTING...'; }
    else if (wasDown) {
      el.className = 'conn restored'; tx.textContent = '✓ CONNECTION RESTORED';
      restoreTimer = setTimeout(() => { el.className = 'conn'; tx.textContent = 'SERVER ONLINE'; }, 3000);
    }
  }

  /* ---------- fetch wrapper: JSON in/out, connection tracking, no raw errors ---------- */
  async function api(url, opts = {}) {
    const init = { credentials: 'same-origin', ...opts };
    if (opts.json !== undefined) {
      init.method = init.method || 'POST';
      init.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
      init.body = JSON.stringify(opts.json);
    }
    try {
      const res = await fetch(url, init);
      setConn(true);
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
      return { ok: res.ok, status: res.status, data: data || {} };
    } catch (_) {
      setConn(false);
      return { ok: false, status: 0, data: { error: 'Unable to reach the server. Your progress is safe — retrying.' }, network: true };
    }
  }

  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  const el = (id) => document.getElementById(id);

  /* animate a number from → to (used for score changes) */
  function countTo(node, from, to, ms = 700) {
    if (!node) return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) { node.textContent = to; return; }
    const t0 = performance.now();
    (function step(t) {
      const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      node.textContent = Number.isInteger(to) && Number.isInteger(from) ? Math.round(from + (to - from) * e) : (from + (to - from) * e).toFixed(1);
      if (p < 1) requestAnimationFrame(step); else node.textContent = to;
    })(t0);
  }

  /* ---------- scroll reveal ---------- */
  function initReveal() {
    const items = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) { items.forEach(i => i.classList.add('in')); return; }
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .12 });
    items.forEach(i => io.observe(i));
  }

  /* ---------- global event-state poll (navbar + auto redirects) ---------- */
  let last = null;
  async function pollEvent() {
    const { ok, data } = await api('/api/event-status');
    if (!ok) return;
    const g = el('global-event-status'); if (g && data.event_status) g.textContent = data.event_status;
    const c = el('connected-teams-count'); if (c && data.connected_teams !== undefined) c.textContent = data.connected_teams;
    document.dispatchEvent(new CustomEvent('ex0:event', { detail: data }));
    last = data.event_status;
  }

  document.addEventListener('DOMContentLoaded', () => {
    initReveal();
    pollEvent(); setInterval(pollEvent, 4000);
  });

  /* ---------- promise-based confirm modal (replaces window.confirm) ---------- */
  function confirmDialog(title, text, okLabel = 'Confirm', danger = false) {
    return new Promise(resolve => {
      const bd = document.createElement('div'); bd.className = 'modal-backdrop';
      const box = document.createElement('div'); box.className = 'modal-dialog'; box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true');
      const h = document.createElement('h3'); h.textContent = title; h.style.marginBottom = '.5rem';
      const p = document.createElement('p'); p.className = 'text-muted'; p.style.fontSize = '.9rem'; p.textContent = text;
      const row = document.createElement('div'); row.style.cssText = 'display:flex;gap:.6rem;justify-content:flex-end;margin-top:1.3rem';
      const no = document.createElement('button'); no.className = 'btn btn-outline'; no.textContent = 'Cancel';
      const yes = document.createElement('button'); yes.className = 'btn ' + (danger ? 'btn-danger' : 'btn-primary'); yes.textContent = okLabel;
      const done = v => { document.removeEventListener('keydown', onKey); bd.remove(); resolve(v); };
      const onKey = e => { if (e.key === 'Escape') done(false); };
      no.onclick = () => done(false); yes.onclick = () => done(true);
      bd.addEventListener('click', e => { if (e.target === bd) done(false); });
      document.addEventListener('keydown', onKey);
      row.append(no, yes); box.append(h, p, row); bd.appendChild(box); document.body.appendChild(bd); yes.focus();
    });
  }

  return { toast, api, setConn, fmt, el, countTo, confirm: confirmDialog };
})();

// Backwards-compatible global used by older templates
function showToast(message, type = 'info') { EX0.toast(message, type === 'warning' ? 'warning' : type); }
