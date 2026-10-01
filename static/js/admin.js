// EXIT CODE 0 — Admin Dashboard Operations

document.addEventListener('DOMContentLoaded', () => {
  initAdminTelemetrySync();
});

// Real-Time Telemetry Sync on Admin Console
function initAdminTelemetrySync() {
  async function sync() {
    try {
      const res = await fetch('/api/event-status');
      if (res.ok) {
        const data = await res.json();
        const statusEl = document.getElementById('admin-telemetry-status');
        const timerEl = document.getElementById('admin-telemetry-timer');
        const teamsEl = document.getElementById('admin-telemetry-teams');

        if (statusEl && data.event_status) {
          statusEl.innerHTML = `<span class="pulse-dot"></span> ${data.event_status}`;
        }
        if (timerEl && data.formatted_time) {
          timerEl.textContent = data.formatted_time;
        }
        if (teamsEl && data.connected_teams !== undefined) {
          teamsEl.textContent = data.connected_teams;
        }
      }
    } catch (e) {
      console.warn("Admin telemetry sync error:", e);
    }
  }

  setInterval(sync, 3000);
}

// Event Lifecycle Controls (Section 26)
async function adminEventAction(action) {
  const confirmMap = {
    start: "Start the 70-minute debugging competition? All registered teams will gain access to the arena.",
    pause: "Pause the tournament? The 70-minute timer will freeze and remaining time will be preserved.",
    resume: "Resume the tournament from paused state?",
    end: "End the tournament immediately? All submissions will be locked."
  };

  const confirmMsg = confirmMap[action] || `Execute action '${action}'?`;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/admin/event-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.error || 'Action failed.', 'error');
    }
  } catch (err) {
    showToast('Network error executing admin action.', 'error');
  }
}

// Teams Filter
function filterTeamsTable() {
  const query = (document.getElementById('team-search-input')?.value || '').toLowerCase().trim();
  const rows = document.querySelectorAll('.team-row');

  rows.forEach(r => {
    const name = r.dataset.name || '';
    const members = r.dataset.members || '';
    const id = r.dataset.id || '';
    if (name.includes(query) || members.includes(query) || id.includes(query)) {
      r.style.display = '';
    } else {
      r.style.display = 'none';
    }
  });
}

// Toggle Team Active State
async function toggleTeamStatus(teamId) {
  if (!confirm(`Toggle active status for team ${teamId}?`)) return;

  try {
    const res = await fetch('/api/admin/toggle-team', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ team_id: teamId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      setTimeout(() => window.location.reload(), 600);
    } else {
      showToast(data.error || 'Failed to toggle team.', 'error');
    }
  } catch (e) {
    showToast('Network error.', 'error');
  }
}

// Toggle Question Active State
async function toggleQuestionStatus(questionId) {
  if (!confirm(`Toggle active status for question ${questionId}?`)) return;

  try {
    const res = await fetch('/api/admin/toggle-question', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: questionId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      setTimeout(() => window.location.reload(), 600);
    } else {
      showToast(data.error || 'Failed to toggle question.', 'error');
    }
  } catch (e) {
    showToast('Network error.', 'error');
  }
}

// Modal Utilities
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'flex';
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

// Score Override Modal (Section 27)
function openScoreOverrideModal(subId, teamName, qId, currentScore) {
  document.getElementById('modal-sub-id').value = subId;
  document.getElementById('modal-team-name').textContent = teamName;
  document.getElementById('modal-question-id').textContent = qId;
  document.getElementById('modal-new-score').value = currentScore;
  document.getElementById('modal-reason').value = '';
  openModal('score-override-modal');
}

async function submitScoreOverride() {
  const subId = document.getElementById('modal-sub-id').value;
  const newScore = document.getElementById('modal-new-score').value;
  const reason = document.getElementById('modal-reason').value.trim();

  if (!newScore || isNaN(newScore)) {
    showToast('Please enter a valid numeric score.', 'error');
    return;
  }
  if (!reason) {
    showToast('Please provide an override rationale.', 'error');
    return;
  }

  try {
    const res = await fetch('/api/admin/override-score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        submission_id: parseInt(subId),
        new_score: parseFloat(newScore),
        reason: reason
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      closeModal('score-override-modal');
      setTimeout(() => window.location.reload(), 700);
    } else {
      showToast(data.error || 'Failed to override score.', 'error');
    }
  } catch (e) {
    showToast('Network error during score override.', 'error');
  }
}

// Safe Tournament Reset (Section 28)
function openResetModal() {
  document.getElementById('reset-confirmation-input').value = '';
  openModal('reset-modal');
}

async function confirmEventReset() {
  const code = (document.getElementById('reset-confirmation-input')?.value || '').trim();
  if (code !== 'RESET EVENT' && code !== 'RESET') {
    showToast("Confirmation failed. You must type 'RESET EVENT' exactly.", 'error');
    return;
  }

  try {
    const res = await fetch('/api/admin/reset-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: code })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      closeModal('reset-modal');
      setTimeout(() => window.location.reload(), 1000);
    } else {
      showToast(data.error || 'Failed to reset event.', 'error');
    }
  } catch (e) {
    showToast('Network error during event reset.', 'error');
  }
}
