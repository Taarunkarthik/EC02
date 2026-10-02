/* Participant state stays server-controlled; only unsent drafts and review flags are local. */
(() => {
  'use strict';
  const fields = ['error_location', 'error_type', 'expected_output', 'cause', 'correction'];
  let root, form, qid, progress, generation, draftKey, dirty = false, busy = false, switching = false, submitted = false, requestID = null, reviews = {}, saveTimeout, syncPending = false, loadSerial = 0;
  const byId = id => document.getElementById(id);
  const canSubmit = () => App.eventState?.event_status === 'LIVE' && Number(App.eventState.remaining_seconds) > 0;
  const current = () => progress?.questions.find(q => q.id === qid);
  const value = () => Object.fromEntries(fields.map(name => [name, byId(name).value]));
  const draftNamespace = () => `ex0:draft:${generation}:${root.dataset.teamId}:`;
  function setDraftKey() { draftKey = `${draftNamespace()}${qid}`; }
  function saveDraft() {
    if (!dirty || !draftKey || submitted) return;
    const saved = App.storage.set(draftKey, { ...value(), request_id: requestID, saved_at: Date.now() });
    byId('draft-status').textContent = saved ? 'Saved locally ✓' : 'Local storage unavailable';
  }
  function restoreDraft() {
    setDraftKey();
    const draft = App.storage.get(draftKey);
    fields.forEach(name => { byId(name).value = typeof draft?.[name] === 'string' ? draft[name] : ''; byId(name).removeAttribute('aria-invalid'); document.querySelector(`[data-error-for="${name}"]`).textContent = ''; });
    requestID = draft?.request_id || null; dirty = !!draft; submitted = false;
    byId('draft-status').textContent = draft ? 'Draft restored from this device' : 'Drafts save on this device';
    CodeEditor.selectLine(byId('error_location').value, false);
    byId('form-feedback-alert').hidden = true; byId('next-question').hidden = true; byId('submission-trace').hidden = true;
    updateReview(); updateControls();
  }
  function updateReview() {
    const reviewed = !!reviews[qid];
    byId('review-toggle').setAttribute('aria-pressed', String(reviewed));
    byId('review-toggle').textContent = reviewed ? '⚑ Marked' : '⚑ Review';
    document.querySelectorAll('[data-question]').forEach(button => {
      const reviewedQuestion = !!reviews[button.dataset.question];
      button.classList.toggle('review', reviewedQuestion);
      if (reviewedQuestion && button.dataset.completed !== '1') button.querySelector('.question-symbol').textContent = '⚑';
    });
  }
  function updateControls() {
    const disabled = !canSubmit() || busy || switching || !qid || !progress;
    byId('commit-fix-btn').disabled = disabled;
    byId('commit-fix-btn').classList.toggle('loading', busy);
    byId('commit-fix-btn').textContent = busy ? 'VALIDATING…' : !canSubmit() ? (App.eventState?.event_status === 'PAUSED' ? 'EVENT PAUSED' : 'SUBMISSIONS CLOSED') : submitted ? 'COMMIT UPDATED FIX →' : '⑂  COMMIT FIX  →';
    document.querySelectorAll('[data-powerup]').forEach(button => {
      const key = button.dataset.powerup.toUpperCase().replaceAll('-', '_');
      const pu = progress?.powerups?.[key];
      button.disabled = disabled || !!pu?.is_used || !!pu?.is_armed;
      const label = button.querySelector('[data-powerup-status]');
      const descriptions = { 'rubber-duck': 'Get a hint · −10% base points', 'git-revert': 'Replace this challenge', 'double-commit': 'Double points or zero' };
      label.textContent = pu?.is_used ? 'Used' : pu?.is_armed ? 'Armed for next submission' : descriptions[button.dataset.powerup];
      if (button.dataset.powerup === 'git-revert' && current()?.is_completed) button.disabled = true;
    });
    fields.forEach(name => { byId(name).disabled = busy || switching; });
  }
  function renderProgress(data) {
    progress = data;
    const score = byId('arena-team-score');
    const newScore = String(data.score);
    if (score.textContent.trim() !== newScore) { score.textContent = newScore; score.classList.remove('score-changed'); void score.offsetWidth; score.classList.add('score-changed'); }
    byId('completed-count').textContent = data.completed_count; byId('question-total').textContent = data.total_questions; byId('sidebar-question-total').textContent = data.total_questions;
    byId('question-progress').value = data.completed_count; byId('question-progress').max = data.total_questions || 1;
    const list = byId('question-list'); const fragment = document.createDocumentFragment();
    for (const question of data.questions) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'question-item'; button.dataset.question = question.id; button.dataset.order = question.question_order; button.dataset.completed = question.is_completed ? '1' : '0';
      button.disabled = !question.is_unlocked; button.classList.toggle('current', question.id === qid); button.classList.toggle('completed', !!question.is_completed);
      if (question.id === qid) button.setAttribute('aria-current', 'true');
      button.title = `Question ${question.question_order} · ${question.difficulty} · ${question.points} points`;
      const number = document.createElement('span'); number.className = 'question-number'; number.textContent = String(question.question_order).padStart(2, '0');
      const label = document.createElement('span'); label.className = 'question-label'; const language = document.createElement('strong'); language.textContent = question.language; const info = document.createElement('small'); info.textContent = `${question.points} pts · ${question.difficulty}`; label.append(language, info);
      const symbol = document.createElement('span'); symbol.className = 'question-symbol'; symbol.textContent = question.is_completed ? '✓' : question.id === qid ? '●' : question.is_unlocked ? '○' : '−'; symbol.setAttribute('aria-label', question.is_completed ? 'Submitted' : question.is_unlocked ? 'Available' : 'Locked');
      button.append(number, label, symbol); fragment.append(button);
    }
    const scroll = list.scrollTop; list.replaceChildren(fragment); list.scrollTop = scroll; updateReview(); updateControls();
  }
  async function syncProgress() {
    if (syncPending) return;
    syncPending = true;
    try {
      const data = await App.request('/api/team-progress');
      if (generation && data.generation !== generation) { location.replace('/register'); return; }
      generation = data.generation; renderProgress(data); return data;
    } catch (err) { if (err.status === 401 || err.status === 403) { byId('arena-state-notice').hidden = false; byId('arena-state-notice').textContent = err.message; progress = null; updateControls(); } }
    finally { syncPending = false; }
  }
  async function selectQuestion(id, push = true) {
    if (!id || busy || switching || id === qid) return;
    saveDraft(); switching = true; updateControls();
    const serial = ++loadSerial;
    document.querySelector('.arena-workspace').classList.add('is-loading');
    try {
      const data = await App.request(`/api/question/${encodeURIComponent(id)}`);
      if (serial !== loadSerial) return;
      const q = data.question; qid = q.id; byId('form-question-id').value = qid;
      byId('breadcrumb-question').textContent = qid; byId('question-title').textContent = q.title; byId('question-difficulty').textContent = q.difficulty; byId('question-points').textContent = `${q.points} PTS`; byId('source-language').textContent = q.language;
      byId('source-filename').textContent = ({ Python: 'main.py', Java: 'Main.java', C: 'main.c', 'C++': 'main.cpp' })[q.language] || 'source';
      byId('challenge-number').textContent = `CHALLENGE ${String(current()?.question_order || qid).padStart(2, '0')}`;
      CodeEditor.render(q.code); restoreDraft(); byId('rubber-duck-hint-box').hidden = true;
      if (progress) renderProgress(progress);
      if (push) history.pushState({ question: qid }, '', `/arena?q=${encodeURIComponent(qid)}`);
      document.title = `${qid} · Debug Arena — EXIT CODE 0`;
    } catch (err) { App.toast(err.message, 'error'); }
    finally { switching = false; document.querySelector('.arena-workspace').classList.remove('is-loading'); updateControls(); }
  }
  function validate() {
    let firstInvalid;
    for (const name of fields) {
      const input = byId(name); const invalid = !input.value.trim() || !input.validity.valid;
      input.setAttribute('aria-invalid', String(invalid));
      document.querySelector(`[data-error-for="${name}"]`).textContent = invalid ? name === 'error_location' ? 'Choose a line in the source.' : 'This field is required.' : '';
      if (invalid && !firstInvalid) firstInvalid = input;
    }
    firstInvalid?.focus(); return !firstInvalid;
  }
  async function submit(event) {
    event.preventDefault(); if (busy || !canSubmit() || !validate()) return;
    busy = true; submitted = false;
    requestID ||= (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
    dirty = true; saveDraft(); updateControls();
    const activity = App.activity(byId('submission-trace'), 'Waiting for server validation…');
    try {
      const data = await App.request('/api/submit-bug-fix', { method: 'POST', body: { question_id: qid, request_id: requestID, ...value() } });
      activity.finish(true, 'Submission recorded');
      submitted = true; dirty = false; App.storage.remove(draftKey); requestID = null;
      const alert = byId('form-feedback-alert'); alert.hidden = false; alert.className = 'alert alert-success'; alert.textContent = `Submission recorded. Score awarded: ${data.result.total_score} / ${data.result.base_points} base points${data.result.is_double_commit ? ' · Double Commit applied' : ''}. Your best score is retained.`;
      byId('draft-status').textContent = 'Submission saved to server ✓';
      byId('arena-team-score').textContent = data.new_score;
      byId('arena-team-score').classList.add('score-changed');
      App.toast('Submission recorded.', 'success');
      await syncProgress();
      const next = progress?.questions.find(q => q.is_unlocked && !q.is_completed && q.id !== qid);
      byId('next-question').hidden = !next; byId('next-question').dataset.next = next?.id || '';
      alert.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' });
    } catch (err) {
      activity.finish(false, 'Submission not confirmed');
      const alert = byId('form-feedback-alert'); alert.hidden = false; alert.className = 'alert alert-warning'; alert.textContent = err.message;
      if (!err.offline && err.status < 500) requestID = null;
      App.toast(err.message, 'error'); EventClock.sync();
    } finally { busy = false; updateControls(); }
  }
  async function usePowerup(button) {
    if (busy || !canSubmit()) return;
    const type = button.dataset.powerup;
    const descriptions = { 'rubber-duck': ['Use Rubber Duck?', 'Reveal one hint. This deducts 10% of the base points from this challenge’s scored submission.'], 'git-revert': ['Replace this challenge?', 'Git Revert abandons this challenge permanently and assigns an alternative. You can use it once.'], 'double-commit': ['Arm Double Commit?', 'Your next submission scores 2× if it earns at least 60% accuracy; otherwise it scores zero. You can use this once.'] };
    if (!await App.confirm(descriptions[type][1], { title: descriptions[type][0], confirmText: 'Activate' })) return;
    busy = true; updateControls(); button.classList.add('loading');
    try {
      const data = await App.request(`/api/powerup/${type}`, { method: 'POST', body: { question_id: qid } });
      App.toast(data.message, 'success');
      if (data.hint) { byId('rubber-duck-hint-box').textContent = data.hint; byId('rubber-duck-hint-box').hidden = false; }
      await syncProgress();
      if (data.new_question_id) { busy = false; dirty = false; App.storage.remove(draftKey); await selectQuestion(data.new_question_id); }
    } catch (err) { App.toast(err.message, 'error'); }
    finally { busy = false; button.classList.remove('loading'); updateControls(); }
  }
  function onState(state) {
    if (!root) return;
    const notice = byId('arena-state-notice');
    if (state.event_status === 'PAUSED') { notice.hidden = false; notice.textContent = 'Competition paused by the organizers. Your draft is saved; submissions will resume with the event.'; }
    else if (state.event_status === 'COMPLETED') { saveDraft(); notice.hidden = false; notice.textContent = 'Debugging complete. Submissions are locked. Opening your results…'; setTimeout(() => location.replace('/result'), 1400); }
    else if (state.event_status === 'WAITING') { saveDraft(); location.replace('/waiting'); }
    else notice.hidden = true;
    updateControls();
  }
  async function init() {
    root = byId('arena'); if (!root) return;
    form = byId('bug-fix-form'); qid = byId('form-question-id').value;
    if (qid) history.replaceState({ question: qid }, '', `/arena?q=${encodeURIComponent(qid)}`);
    form.addEventListener('submit', submit);
    form.addEventListener('input', () => { dirty = true; submitted = false; requestID = null; byId('draft-status').textContent = 'Saving draft…'; clearTimeout(saveTimeout); saveTimeout = setTimeout(saveDraft, 350); updateControls(); });
    form.addEventListener('paste', event => { event.preventDefault(); App.toast('Pasting answers is restricted in competition mode.', 'warning'); });
    byId('question-list').addEventListener('click', event => { const button = event.target.closest('[data-question]'); if (button && !button.disabled) selectQuestion(button.dataset.question); });
    byId('next-question').addEventListener('click', () => selectQuestion(byId('next-question').dataset.next));
    byId('review-toggle').addEventListener('click', () => { reviews[qid] = !reviews[qid]; App.storage.set(`${draftNamespace()}reviews`, reviews); if (progress) renderProgress(progress); else updateReview(); });
    document.querySelectorAll('[data-powerup]').forEach(button => button.addEventListener('click', () => usePowerup(button)));
    document.addEventListener('eventstate', event => onState(event.detail));
    window.addEventListener('pagehide', saveDraft);
    window.addEventListener('popstate', () => { const target = new URLSearchParams(location.search).get('q') || progress?.questions.find(q => q.is_unlocked && !q.is_completed)?.id || progress?.questions[0]?.id; selectQuestion(target, false); });
    document.addEventListener('visibilitychange', () => { if (document.hidden) saveDraft(); else syncProgress(); });
    const data = await syncProgress();
    if (data) { reviews = App.storage.get(`${draftNamespace()}reviews`, {}); restoreDraft(); }
    else { byId('draft-status').textContent = 'Reconnect to enable saved drafts'; }
    if (App.eventState) onState(App.eventState);
    setInterval(async () => { if (!document.hidden) { const first = !generation; const data = await syncProgress(); if (first && data) { reviews = App.storage.get(`${draftNamespace()}reviews`, {}); if (dirty) { setDraftKey(); saveDraft(); } else restoreDraft(); } } }, 10000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
