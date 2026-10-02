/* Submission fallback if the locally bundled React enhancement fails to load. */
(() => {
  App.activity = (host, label) => {
    if (!host) return {finish() {}};
    host.hidden = false; host.dataset.working = 'true'; host.textContent = label;
    return {finish(success, message) { host.dataset.working = 'false'; host.dataset.success = String(success); host.textContent = message; }};
  };
})();
