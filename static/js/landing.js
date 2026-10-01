// Landing page: looping simulated debugger + sample leaderboard animation (illustrative only).
(() => {
  const body = document.getElementById('ide-body'), con = document.getElementById('ide-console');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wait = ms => new Promise(r => setTimeout(r, reduce ? 0 : ms));

  const BUGGY = [
    '<span class="tk-k">def</span> <span class="tk-f">average</span>(nums):',
    '    total = <span class="tk-n">0</span>',
    '    <span class="tk-k">for</span> i <span class="tk-k">in</span> <span class="tk-f">range</span>(<span class="tk-n">1</span>, <span class="tk-f">len</span>(nums)):',
    '        total += nums[i]',
    '    <span class="tk-k">return</span> total / <span class="tk-f">len</span>(nums)',
    '',
    '<span class="tk-f">print</span>(average([<span class="tk-n">4</span>, <span class="tk-n">8</span>, <span class="tk-n">6</span>]))'
  ];
  const FIXED3 = '    <span class="tk-k">for</span> i <span class="tk-k">in</span> <span class="tk-f">range</span>(<span class="tk-f">len</span>(nums)):';

  function draw(fixed, mark) {
    body.innerHTML = BUGGY.map((l, i) => {
      const cls = mark === i ? (fixed ? 'fixed' : 'bug') : '';
      return `<div class="ide-line ${cls}"><span class="n">${String(i + 1).padStart(2, '0')}</span><span>${(fixed && i === 2) ? FIXED3 : l}</span></div>`;
    }).join('');
  }
  function log(html) { const d = document.createElement('div'); d.innerHTML = html; con.appendChild(d); }

  async function loop() {
    while (true) {
      con.innerHTML = ''; draw(false, -1);
      await wait(1200);  log('<span class="dim">$</span> run average.py');
      await wait(700);   log('Scanning source...');
      await wait(900);   draw(false, 2); log('<span class="bad">Bug detected: line 03</span>');
      await wait(1200);  log('Applying fix...'); draw(true, 2);
      await wait(1000);  log('Running tests...');
      await wait(900);   log('<span class="ok">3 passed</span> &mdash; output: 6.0');
      await wait(500);   log('<span class="ok">EXIT CODE: 0</span>');
      if (reduce) return;
      await wait(4200);
    }
  }
  if (body && con) loop();

  // Sample leaderboard rows swapping rank — clearly labelled SAMPLE in the page.
  const demo = document.getElementById('lb-demo');
  if (demo) {
    let teams = [['Team Alpha', 740], ['Team Beta', 710], ['Team Gamma', 695], ['Team Delta', 640]];
    const render = () => { demo.innerHTML = teams.map((t, i) => `<tr class="lb-row"><td class="rank-cell" style="width:70px">${String(i + 1).padStart(2, '0')}</td><td>${t[0]}</td><td class="mono" style="text-align:right">${t[1]}</td></tr>`).join(''); };
    render();
    if (!reduce) setInterval(() => {
      teams[3][1] += 80; teams.sort((a, b) => b[1] - a[1]); render();
      demo.children[teams.findIndex(t => t[0] === 'Team Delta')].classList.add('bump');
      if (teams[3][0] === 'Team Delta' || teams[0][1] > 1100) teams = [['Team Alpha', 740], ['Team Beta', 710], ['Team Gamma', 695], ['Team Delta', 640]];
    }, 3200);
  }
})();
