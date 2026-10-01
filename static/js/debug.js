// Debug Arena Logic & Anti-Copy Protection

document.addEventListener('DOMContentLoaded', () => {
  setupAntiCopyProtection();
  setupPowerups();
  setupSubmissionHandler();
});

// Strict Anti-Copy Controls on Code Viewer
function setupAntiCopyProtection() {
  const codeViewers = document.querySelectorAll('.code-viewer-body, .code-viewer-container');
  
  codeViewers.forEach(el => {
    // Disable right click
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      showToast('Right-click is disabled inside the Code Viewer.', 'warning');
      return false;
    });

    // Disable copy, cut, paste inside code viewer
    ['copy', 'cut', 'paste', 'selectstart', 'dragstart'].forEach(evtName => {
      el.addEventListener(evtName, e => {
        e.preventDefault();
        showToast('Direct code extraction is disabled for competition integrity.', 'warning');
        return false;
      });
    });

    // Disable keyboard shortcuts for copy/cut within the code viewer
    el.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && ['c', 'x', 'v', 'a', 'u', 's'].includes(e.key.toLowerCase())) {
        e.preventDefault();
        showToast('Keyboard shortcuts disabled within code viewer.', 'warning');
        return false;
      }
    });
  });
}

// Power-Up Actions
function setupPowerups() {
  const duckBtn = document.getElementById('btn-rubber-duck');
  const revertBtn = document.getElementById('btn-git-revert');
  const doubleBtn = document.getElementById('btn-double-commit');

  if (duckBtn) {
    duckBtn.addEventListener('click', async () => {
      const qid = duckBtn.dataset.questionId;
      if (!confirm("Activate Rubber Duck? A hint will be revealed and 10% base points will be deducted.")) return;

      try {
        const res = await fetch('/api/powerup/rubber-duck', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ question_id: qid })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'info');
          const hintContainer = document.getElementById('rubber-duck-hint-box');
          if (hintContainer) {
            hintContainer.style.display = 'block';
            document.getElementById('rubber-duck-hint-text').textContent = data.hint;
          }
          duckBtn.classList.add('used');
          duckBtn.disabled = true;
        } else {
          showToast(data.error || 'Failed to activate Rubber Duck.', 'error');
        }
      } catch (err) {
        showToast('Network error activating power-up', 'error');
      }
    });
  }

  if (revertBtn) {
    revertBtn.addEventListener('click', async () => {
      const qid = revertBtn.dataset.questionId;
      if (!confirm("Activate Git Revert? This will abandon this code challenge and swap for a fresh equivalent.")) return;

      try {
        const res = await fetch('/api/powerup/git-revert', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ question_id: qid })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'info');
          setTimeout(() => window.location.reload(), 1000);
        } else {
          showToast(data.error || 'Failed to activate Git Revert.', 'error');
        }
      } catch (err) {
        showToast('Network error activating Git Revert', 'error');
      }
    });
  }

  if (doubleBtn) {
    doubleBtn.addEventListener('click', async () => {
      const qid = doubleBtn.dataset.questionId;
      if (!confirm("Arm Double Commit? Your submission scores 2x points if accurate (>=60%), but 0 points if wrong!")) return;

      try {
        const res = await fetch('/api/powerup/double-commit', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ question_id: qid })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'warning');
          doubleBtn.classList.add('armed');
          doubleBtn.innerHTML = '<span>⚡ DOUBLE ARMED</span>';
          doubleBtn.disabled = true;
        } else {
          showToast(data.error || 'Failed to arm Double Commit.', 'error');
        }
      } catch (err) {
        showToast('Network error arming Double Commit', 'error');
      }
    });
  }
}

// Submission Handler with Clean In-Place Feedback (No Annoying Popups)
function setupSubmissionHandler() {
  const form = document.getElementById('debug-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const commitBtn = document.getElementById('btn-commit-fix');
    if (commitBtn) {
      commitBtn.disabled = true;
      commitBtn.innerHTML = '<span>EVALUATING FIX...</span>';
    }

    const payload = {
      question_id: form.dataset.questionId,
      error_location: document.getElementById('error_location')?.value || '',
      error_type: document.getElementById('error_type')?.value || '',
      expected_output: document.getElementById('expected_output')?.value || '',
      cause: document.getElementById('cause')?.value || '',
      correction: document.getElementById('correction')?.value || ''
    };

    try {
      const res = await fetch('/api/submit-bug-fix', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (data.success) {
        showInlineResult(data.result, data.new_debug_score);
      } else {
        showToast(data.error || 'Submission failed.', 'error');
        if (commitBtn) {
          commitBtn.disabled = false;
          commitBtn.innerHTML = '<span>[ COMMIT FIX ]</span>';
        }
      }
    } catch (err) {
      showToast('Network connection error during submission.', 'error');
      if (commitBtn) {
        commitBtn.disabled = false;
        commitBtn.innerHTML = '<span>[ COMMIT FIX ]</span>';
      }
    }
  });
}

function showInlineResult(res, newTotal) {
  const inlineCard = document.getElementById('inline-result-card');
  const formCard = document.getElementById('answer-form-card');
  const commitBtn = document.getElementById('btn-commit-fix');

  // Disable all input fields and lock cursor
  if (formCard) {
    formCard.querySelectorAll('input, select, textarea').forEach(el => {
      el.disabled = true;
      el.style.cursor = 'not-allowed';
      el.style.pointerEvents = 'none';
    });
  }
  if (commitBtn) commitBtn.style.display = 'none';

  if (inlineCard) {
    document.getElementById('inline-score-type').textContent = `${res.error_type_score} pts`;
    document.getElementById('inline-score-loc').textContent = `${res.error_loc_score} pts`;
    document.getElementById('inline-score-cause').textContent = `${res.cause_score} pts`;
    document.getElementById('inline-score-output').textContent = `${res.output_score} pts`;
    document.getElementById('inline-score-corr').textContent = `${res.correction_score} pts`;
    document.getElementById('inline-score-total').textContent = `+${res.total_score} / ${res.base_points} PTS`;
    inlineCard.style.display = 'block';
  }

  const totalDisplay = document.getElementById('team-total-score-display');
  if (totalDisplay && newTotal !== undefined) {
    totalDisplay.textContent = newTotal;
  }

  showToast(`Fix committed! Awarded ${res.total_score} points.`, 'info');
}
