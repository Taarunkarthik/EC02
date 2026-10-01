// Live leaderboard: polls the server; ranks are computed server-side (display + diff animation only).
(() => {
  const $ = id => document.getElementById(id);
  const tbody = $('leaderboard-table-body'); if (!tbody) return;
  let prev = {}, first = true, remaining = null, running = false;
  const STATES = { LIVE: ['live', 'LIVE'], COMPLETED: ['final', 'FINAL'], PAUSED: ['frozen', 'PAUSED'], WAITING: ['frozen', 'NOT STARTED'] };

  const td = (text, cls, style) => { const c = document.createElement('td'); c.textContent = text; if (cls) c.className = cls; if (style) c.style.cssText = style; return c; };

  function podium(teams) {
    const p = $('podium'); p.replaceChildren();
    const top = teams.slice(0, 3).filter(t => t.score > 0 || t.completed_count > 0);
    p.hidden = top.length === 0; if (!top.length) return;
    [1, 0, 2].forEach(i => {   // 2nd | 1st | 3rd
      const t = top[i]; if (!t) return;
      const d = document.createElement('div'); d.className = `card pod p${i + 1}`;
      const m = document.createElement('div'); m.className = 'medal'; m.textContent = ['1ST', '2ND', '3RD'][i];
      const n = document.createElement('div'); n.className = 'nm'; n.textContent = t.name;
      const s = document.createElement('div'); s.className = 'sc'; s.textContent = Number(t.score).toFixed(1);
      d.append(m, n, s); p.appendChild(d);
    });
  }

  function render(teams, me) {
    $('lb-count').textContent = `${teams.length} team${teams.length === 1 ? '' : 's'}`;
    if (!teams.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty"><strong>No teams registered yet.</strong>The leaderboard will appear when the competition begins.</div></td></tr>';
      $('podium').hidden = true; return;
    }
    podium(teams);
    const next = {}; tbody.replaceChildren();
    teams.forEach((t, i) => {
      const rank = i + 1, score = Number(t.score || 0), old = prev[t.id];
      next[t.id] = { rank, score };
      const tr = document.createElement('tr'); tr.className = 'lb-row' + (me && t.id === me ? ' me' : '');
      const rc = td(String(rank).padStart(2, '0'), 'rank-cell');
      if (!first && old && old.rank !== rank) {
        const d = document.createElement('span'); d.className = 'delta ' + (rank < old.rank ? 'up' : 'down');
        d.textContent = (rank < old.rank ? '↑ ' : '↓ ') + Math.abs(old.rank - rank); rc.appendChild(d);
        setTimeout(() => d.remove(), 6000);
      }
      const nm = document.createElement('td'); const b = document.createElement('div'); b.style.fontWeight = '600'; b.textContent = t.name;
      if (me && t.id === me) { const y = document.createElement('span'); y.className = 'badge badge-primary'; y.style.marginLeft = '.5rem'; y.textContent = 'YOU'; b.appendChild(y); }
      const id = document.createElement('div'); id.className = 'mono text-dim'; id.style.fontSize = '.72rem'; id.textContent = t.id; nm.append(b, id);
      const st = document.createElement('td'); st.style.textAlign = 'center';
      const bd = document.createElement('span'); bd.className = 'badge ' + (t.completed_count > 0 ? 'badge-success' : ''); bd.textContent = t.completed_count > 0 ? 'ACTIVE' : 'NO SUBMISSIONS'; st.appendChild(bd);
      tr.append(rc, nm, td(t.completed_count || 0, 'mono', 'text-align:center'), td(score.toFixed(1), 'mono font-bold', 'text-align:right;font-size:1rem'), st);
      if (!first && old && old.score !== score) tr.classList.add('bump');
      tbody.appendChild(tr);
    });
    prev = next; first = false;
  }

  function setState(status) {
    const [cls, text] = STATES[status] || STATES.LIVE;
    $('lb-tag').className = 'live-tag ' + cls; $('lb-tag-text').textContent = text;
  }

  async function refresh(manual) {
    const btn = $('lb-refresh'); if (manual) { btn.disabled = true; btn.textContent = 'Refreshing...'; }
    const { ok, data, network } = await EX0.api('/api/leaderboard-data');
    if (manual) { btn.disabled = false; btn.textContent = 'Refresh'; }
    if (!ok) {
      if (first) tbody.innerHTML = '<tr><td colspan="5"><div class="empty"><strong>Unable to connect to server.</strong>Your progress is safe. Try reconnecting or contact an event volunteer.</div></td></tr>';
      return;
    }
    setState(data.event_status); running = data.event_status === 'LIVE';
    render(data.leaderboard, data.current_team_id);
  }

  document.addEventListener('ex0:event', e => {
    const d = e.detail; remaining = d.remaining_seconds; setState(d.event_status);
    $('lb-timer-countdown').textContent = d.formatted_time || EX0.fmt(remaining || 0);
  });
  $('lb-refresh').addEventListener('click', () => refresh(true));
  refresh(false); setInterval(refresh, 3000);
})();
