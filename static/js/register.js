// Registration: tabs + inline validation. The server still validates everything on submit.
(() => {
  const $ = id => document.getElementById(id);
  const tabs = [['tab-reg', 'panel-reg'], ['tab-login', 'panel-login']];
  function show(i) {
    tabs.forEach(([t, p], j) => { $(t).setAttribute('aria-selected', i === j); $(p).hidden = i !== j; });
  }
  tabs.forEach(([t], i) => $(t).addEventListener('click', () => show(i)));
  if (document.querySelector('.alert-error') && /not found|enter your team/i.test(document.querySelector('.alert-error').textContent)) show(1);

  const msg = (id, text, kind) => {
    const m = $(id + '-msg'), f = $(id);
    if (!m) return; m.textContent = text; m.className = 'field-msg ' + (kind || '');
    f.classList.toggle('is-invalid', kind === 'err'); f.classList.toggle('is-valid', kind === 'ok');
  };

  let timer;
  $('name').addEventListener('input', () => {
    clearTimeout(timer); const v = $('name').value.trim();
    if (!v) return msg('name', '', '');
    msg('name', 'Checking...', '');
    timer = setTimeout(async () => {
      const { ok, data, network } = await EX0.api('/api/team-name-available?name=' + encodeURIComponent(v));
      if (network || !ok) return msg('name', '', '');
      msg('name', data.available ? '✓ Team name available' : 'Team name already exists', data.available ? 'ok' : 'err');
    }, 350);
  });

  ['member1', 'member2'].forEach((id, i) => $(id).addEventListener('blur', () => {
    $(id).value.trim() ? msg(id, '', 'ok') : msg(id, `Member ${i + 1} required`, 'err');
  }));

  $('panel-reg').addEventListener('submit', e => {
    let bad = false;
    if (!$('name').value.trim()) { msg('name', 'Team name required', 'err'); bad = true; }
    ['member1', 'member2'].forEach((id, i) => { if (!$(id).value.trim()) { msg(id, `Member ${i + 1} required`, 'err'); bad = true; } });
    if (bad) { e.preventDefault(); const f = document.querySelector('#panel-reg .is-invalid'); f && f.focus(); return; }
    $('reg-btn').classList.add('is-loading');
  });
})();
