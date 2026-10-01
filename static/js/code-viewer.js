// Read-only code viewer: line numbers, lightweight syntax highlighting, click-to-pick error line.
// Builds DOM nodes with textContent — source text is never parsed as HTML.
const CodeViewer = (() => {
  const KW = {
    Python: 'def return if elif else for while in not and or import from class try except finally with as pass break continue lambda None True False is raise yield global',
    C: 'int char float double void long short unsigned signed if else for while do return struct typedef sizeof switch case break continue static const enum NULL include define',
    Java: 'public private protected static final class void int long double float boolean char String if else for while do return new null true false try catch throw throws import package extends implements switch case break continue this super'
  };
  const FILE = { Python: 'main.py', C: 'main.c', Java: 'Main.java' };
  const sets = Object.fromEntries(Object.entries(KW).map(([k, v]) => [k, new Set(v.split(' '))]));

  function tokens(line, lang) {
    const kw = sets[lang] || new Set(), out = [];
    const re = /(\/\/.*|#.*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)|(\s+|.)/g;
    let m;
    while ((m = re.exec(line))) {
      let cls = '';
      if (m[1] !== undefined) { if (lang === 'Python' && m[1][0] !== '#') cls = ''; else cls = 'tk-c'; }
      else if (m[2]) cls = 'tk-s'; else if (m[3]) cls = 'tk-n';
      else if (m[4]) cls = kw.has(m[4]) ? 'tk-k' : 'tk-f';
      else if (m[5]) cls = kw.has(m[5]) ? 'tk-k' : '';
      out.push([m[0], cls]);
    }
    return out;
  }

  function render(container, code, lang, onPick) {
    container.replaceChildren();
    if (!code) { container.innerHTML = '<div class="empty"><strong>No question available.</strong></div>'; return; }
    const frag = document.createDocumentFragment();
    code.split('\n').forEach((line, i) => {
      const row = document.createElement('div'); row.className = 'code-row'; row.dataset.line = i + 1;
      const ln = document.createElement('span'); ln.className = 'ln'; ln.textContent = String(i + 1).padStart(2, '0');
      ln.title = 'Mark line ' + (i + 1) + ' as the error line';
      const src = document.createElement('span'); src.className = 'src';
      tokens(line, lang).forEach(([t, c]) => { if (c) { const s = document.createElement('span'); s.className = c; s.textContent = t; src.appendChild(s); } else src.appendChild(document.createTextNode(t)); });
      if (!line) src.textContent = ' ';
      row.append(ln, src);
      ln.addEventListener('click', () => onPick && onPick(i + 1));
      frag.appendChild(row);
    });
    container.appendChild(frag);
    container.scrollTop = 0;
  }

  function pick(container, n) {
    container.querySelectorAll('.code-row.picked').forEach(r => r.classList.remove('picked'));
    if (n) { const r = container.querySelector(`.code-row[data-line="${n}"]`); if (r) r.classList.add('picked'); }
  }
  return { render, pick, fileName: l => FILE[l] || 'source.txt' };
})();
