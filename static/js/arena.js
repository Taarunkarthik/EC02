// Debug Arena controller. Display + input only: score, timer, unlocks and grading are all server-side.
(() => {
  const $ = id => document.getElementById(id);
  const arena = $('arena'); if (!arena) return;
  const teamId = arena.dataset.teamId;
  const meta = JSON.parse($('nav-meta').textContent);
  const first = JSON.parse($('first-q').textContent);
  const cache = {}; if (first) cache[first.id] = first;
  const FIELDS = ['error_location', 'error_type', 'expected_output', 'cause', 'correction'];
  const viewer = $('code-viewer-container');
  let cur = first ? first.id : null, locked = false, score = parseFloat($('arena-team-score').textContent) || 0;
  let remaining = null, paused = false, warned = {};

  /* ---------- navigator ---------- */
  function renderNav() {
    const g = $('qgrid'); g.replaceChildren();
    meta.forEach(q => {
      const b = document.createElement('button'); b.type = 'button'; b.dataset.id = q.id;
      const st = !q.unlocked ? 'locked' : q.id === cur ? 'current' : q.completed ? 'done' : '';
      b.className = 'qbtn ' + st;
      b.setAttribute('aria-current', q.id === cur ? 'true' : 'false');
      b.disabled = !q.unlocked;
      b.dataset.tip = `Question ${q.order} · ${q.difficulty} · ${q.points} pts`;
      const n = document.createElement('span'); n.textContent = String(q.order).padStart(2, '0');
      const s = document.createElement('small'); s.textContent = !q.unlocked ? '🔒' : q.completed ? '✓' : q.id === cur ? '●' : '○';
      b.append(n, s); b.addEventListener('click', () => select(q.id, true)); g.appendChild(b);
    });
    const done = meta.filter(q => q.completed).length;
    $('done-count').textContent = done;
    $('progress-fill').style.width = (meta.length ? done / meta.length * 100 : 0) + '%';
  }

  /* ---------- drafts (local only; never answer keys) ---------- */
  const dkey = id => `ex0:draft:${teamId}:${id}`;
  let draftTimer;
  function saveDraft() {
    if (!cur) return;
    const d = {}; FIELDS.forEach(f => d[f] = $(f).value);
    try {
      if (FIELDS.some(f => d[f])) localStorage.setItem(dkey(cur), JSON.stringify(d)); else localStorage.removeItem(dkey(cur));
      const n = $('draft-note'); n.classList.add('show'); setTimeout(() => n.classList.remove('show'), 1400);
    } catch (_) { /* storage unavailable: ignore */ }
  }
  function loadDraft() {
    let d = {}; try { d = JSON.parse(localStorage.getItem(dkey(cur)) || '{}'); } catch (_) {}
    FIELDS.forEach(f => $(f).value = d[f] || '');
    CodeViewer.pick(viewer, parseInt($('error_location').value, 10) || 0);
  }
  FIELDS.forEach(f => $(f).addEventListener('input', () => { clearTimeout(draftTimer); draftTimer = setTimeout(saveDraft, 600); }));

  /* ---------- show a question ---------- */
  function show(q) {
    cur = q.id; $('form-question-id').value = q.id;
    $('file-name').textContent = CodeViewer.fileName(q.language);
    $('lang-badge').textContent = q.language.toUpperCase(); $('diff-badge').textContent = q.difficulty.toUpperCase(); $('pts-badge').textContent = q.points + ' PTS';
    const m = meta.find(x => x.id === q.id); $('q-title').textContent = `Q${String(m ? m.order : '').padStart(2, '0')} · ${q.title}`;
    CodeViewer.render(viewer, q.code, q.language, n => { $('error_location').value = n; CodeViewer.pick(viewer, n); saveDraft(); });
    $('result-slot').replaceChildren(); $('hint-box').classList.add('hidden');
    loadDraft(); renderNav();
  }

  async function select(id, push) {
    if (id === cur) return;
    const m = meta.find(x => x.id === id); if (!m || !m.unlocked) return;
    saveDraft();
    let q = cache[id];
    if (!q) {
      viewer.replaceChildren(Object.assign(document.createElement('div'), { className: 'skeleton', style: 'height:180px;margin:1rem' }));
      const { ok, data } = await EX0.api('/api/question/' + encodeURIComponent(id));
      if (!ok || !data.question) { EX0.toast('Unable to load question. Please retry.', 'error'); if (cache[cur]) show(cache[cur]); return; }
      q = cache[id] = data.question;
    }
    show(q);
    if (push) history.pushState({ q: id }, '', '/arena?q=' + encodeURIComponent(id));
  }
  window.addEventListener('popstate', e => { const id = (e.state && e.state.q) || new URLSearchParams(location.search).get('q'); if (id) { cur = null; select(id, false); } });

  $('error_location').addEventListener('input', e => CodeViewer.pick(viewer, parseInt(e.target.value, 10) || 0));

  /* ---------- submit ---------- */
  function lock(msg) {
    if (locked) return; locked = true;
    $('bug-fix-form').querySelectorAll('input,select,textarea,button').forEach(el => el.disabled = true);
    $('commit-label').textContent = 'SUBMISSIONS CLOSED';
    const a = document.createElement('div'); a.className = 'alert alert-warning'; a.textContent = msg; $('result-slot').replaceChildren(a);
  }

  $('bug-fix-form').addEventListener('submit', async e => {
    e.preventDefault(); if (locked || !cur) return;
    const body = { question_id: cur }; FIELDS.forEach(f => body[f] = $(f).value.trim());
    if (!FIELDS.some(f => body[f])) { EX0.toast('Fill in at least one field before committing.', 'warning'); return; }
    const btn = $('commit-fix-btn'), label = $('commit-label'); btn.disabled = true; label.textContent = 'VALIDATING...';
    const { ok, status, data, network } = await EX0.api('/api/submit-bug-fix', { json: body });
    btn.disabled = false; label.textContent = 'COMMIT FIX';

    if (network) { EX0.toast('Unable to submit. Please retry.', 'error'); return; }
    if (status === 403) { lock('Submissions are closed.'); return; }
    if (!ok || !data.success) { EX0.toast('Unable to submit. Please retry.', 'error'); return; }

    const r = data.result, delta = data.new_score - score, m = meta.find(x => x.id === cur);
    if (m) { m.completed = true; const nx = meta.find(x => x.order === m.order + 1); if (nx) nx.unlocked = true; if (cache[cur]) cache[cur].is_completed = true; }
    const sc = $('arena-team-score'); EX0.countTo(sc, score, data.new_score); sc.classList.remove('score-flash'); void sc.offsetWidth; sc.classList.add('score-flash'); score = data.new_score;
    try { localStorage.removeItem(dkey(cur)); } catch (_) {}
    renderNav();

    const card = document.createElement('div'); card.className = 'card result-card';
    const t = document.createElement('div'); t.className = 'eyebrow'; t.textContent = '✓ Submission recorded';
    const p = document.createElement('div'); p.className = 'pts'; p.textContent = delta > 0 ? `+${Math.round(delta * 10) / 10} POINTS` : 'RECORDED';
    const s = document.createElement('div'); s.className = 'text-muted'; s.style.fontSize = '.85rem'; s.textContent = `Score awarded: ${r.total_score} / ${r.base_points}`;
    card.append(t, p, s);
    const next = meta.filter(x => x.unlocked && !x.completed && x.id !== cur).sort((a, b) => a.order - b.order)[0];
    if (next) { const nb = document.createElement('button'); nb.type = 'button'; nb.className = 'btn btn-primary btn-block'; nb.style.marginTop = '.8rem'; nb.textContent = 'NEXT QUESTION →'; nb.onclick = () => select(next.id, true); card.appendChild(nb); }
    $('result-slot').replaceChildren(card);
    EX0.toast('Submission recorded', 'success');
  });

  /* ---------- power-ups ---------- */
  const pu = (id, fn) => { const b = $(id); if (b) b.addEventListener('click', fn); };
  async function usePowerup(path, extra) {
    const { ok, data, network } = await EX0.api('/api/powerup/' + path, { json: { question_id: cur } });
    if (network) { EX0.toast('Unable to reach the server. Please retry.', 'error'); return null; }
    if (!ok || !data.success) { EX0.toast(data.error || 'Power-up unavailable.', 'error'); return null; }
    EX0.toast(data.message || 'Power-up activated', 'success'); return data;
  }
  const markUsed = (id, text = 'USED') => { const b = $(id); if (b) b.replaceWith(Object.assign(document.createElement('span'), { className: 'badge badge-muted', textContent: text })); };
  pu('pu-duck', async () => {
    if (!await EX0.confirm('Use Rubber Duck?', 'A hint is revealed and 10% of this question\'s points are deducted.', 'Use hint')) return;
    const d = await usePowerup('rubber-duck'); if (!d) return;
    const h = $('hint-box'); h.textContent = d.hint || ''; h.classList.remove('hidden'); markUsed('pu-duck');
  });
  pu('pu-revert', async () => {
    if (!await EX0.confirm('Use Git Revert?', 'This question is abandoned and swapped for another. It cannot be attempted again.', 'Swap question', true)) return;
    const d = await usePowerup('git-revert'); if (!d) return;
    setTimeout(() => location.href = '/arena' + (d.new_question_id ? '?q=' + encodeURIComponent(d.new_question_id) : ''), 700);
  });
  pu('pu-double', async () => {
    if (!await EX0.confirm('Arm Double Commit?', 'Your next submission on this question earns 2× points if it is at least 60% accurate, otherwise 0.', 'Arm')) return;
    const d = await usePowerup('double-commit'); if (d) { const b = $('pu-double'); b.replaceWith(Object.assign(document.createElement('span'), { className: 'badge badge-primary', textContent: 'ARMED' })); }
  });

  /* ---------- timer: server value is authoritative; local tick only smooths display ---------- */
  function renderTimer() {
    const v = $('event-timer-display'), box = $('timer-box');
    if (remaining === null) return;
    v.textContent = paused ? 'PAUSED' : EX0.fmt(Math.max(0, remaining));
    box.classList.remove('warn10', 'warn5', 'warn1'); box.classList.toggle('paused', paused);
    if (paused) return;
    const cls = remaining <= 60 ? 'warn1' : remaining <= 300 ? 'warn5' : remaining <= 600 ? 'warn10' : '';
    if (cls) box.classList.add(cls);
    [[600, '10 minutes remaining'], [300, '5 minutes remaining'], [60, '1 minute remaining']].forEach(([t, m]) => { if (remaining <= t && remaining > t - 5 && !warned[t]) { warned[t] = 1; EX0.toast(m, 'warning'); } });
  }
  function expire() { lock('Time is up. Submissions are closed.'); setTimeout(() => location.href = '/result', 3000); }
  setInterval(() => { if (remaining === null || paused || locked) return; if (remaining > 0) { remaining--; renderTimer(); } else expire(); }, 1000);
  document.addEventListener('ex0:event', ev => {
    const d = ev.detail; paused = !!d.is_paused || d.event_status === 'PAUSED';
    if (typeof d.remaining_seconds === 'number') remaining = d.remaining_seconds;
    renderTimer();
    if (d.event_status === 'COMPLETED' || (remaining !== null && remaining <= 0 && d.event_status === 'LIVE')) expire();
  });

  /* ---------- boot ---------- */
  renderNav();
  if (first) show(first); else $('q-title').textContent = 'No question available';
  ArenaGuard.init({});
})();
