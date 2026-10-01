// Synchronized Server-Controlled Timer

class EventTimer {
  constructor(displayElementId, onExpireCallback = null) {
    this.displayEl = document.getElementById(displayElementId);
    this.onExpire = onExpireCallback;
    this.remainingSeconds = 0;
    this.isPaused = false;
    this.timerInterval = null;
    this.syncInterval = null;
    this.init();
  }

  init() {
    this.syncWithServer();
    this.timerInterval = setInterval(() => this.tick(), 1000);
    // Periodically re-sync with server to prevent client drift
    this.syncInterval = setInterval(() => this.syncWithServer(), 8000);
  }

  async syncWithServer() {
    try {
      const res = await fetch('/api/event-status');
      if (!res.ok) return;
      const data = await res.json();
      this.remainingSeconds = data.remaining_seconds || 0;
      this.isPaused = data.is_paused || false;
      this.render();
    } catch (e) {
      console.warn('Timer sync error:', e);
    }
  }

  tick() {
    if (this.isPaused) return;

    if (this.remainingSeconds > 0) {
      this.remainingSeconds--;
      this.render();
    } else if (this.remainingSeconds === 0) {
      this.render();
      if (typeof this.onExpire === 'function') {
        this.onExpire();
      }
    }
  }

  render() {
    if (!this.displayEl) return;
    const mins = Math.floor(this.remainingSeconds / 60);
    const secs = this.remainingSeconds % 60;
    const formatted = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    
    this.displayEl.textContent = formatted;

    // Apply visual alert classes
    if (this.remainingSeconds <= 300 && this.remainingSeconds > 60) {
      this.displayEl.parentElement?.classList.add('warning');
      this.displayEl.parentElement?.classList.remove('critical');
    } else if (this.remainingSeconds <= 60 && this.remainingSeconds > 0) {
      this.displayEl.parentElement?.classList.add('critical');
      this.displayEl.parentElement?.classList.remove('warning');
    } else {
      this.displayEl.parentElement?.classList.remove('warning', 'critical');
    }
  }

  destroy() {
    clearInterval(this.timerInterval);
    clearInterval(this.syncInterval);
  }
}
