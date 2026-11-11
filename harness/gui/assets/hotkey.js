(() => {
  if (window.__agyis_hud_active_listener) {
    window.removeEventListener('keydown', window.__agyis_hud_active_listener, true);
  }
  window.__agyis_hud_hotkey_registered = true;
  window.__agyis_hud_last_toggle = window.__agyis_hud_last_toggle || 0;
  window.__agyis_hud_active_listener = (e) => {
    const isF12 = e.key === 'F12';
    const isCtrlShiftT = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'T' || e.key === 't');
    if (isF12 || isCtrlShiftT) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const now = Date.now();
      if (now - (window.__agyis_hud_last_toggle || 0) < 250) return;
      window.__agyis_hud_last_toggle = now;
      let hud = document.getElementById('agyis-trajectory-hud');
      if (!hud && typeof window.__agyis_hud_render === 'function') {
        window.__agyis_hud_render();
        hud = document.getElementById('agyis-trajectory-hud');
      }
      if (hud) {
        const isHidden = (hud.style.display === 'none');
        if (isHidden) {
          const focusedConvoId = (typeof window.__agyis_extract_convo_id === 'function')
            ? window.__agyis_extract_convo_id()
            : ((window.location && window.location.pathname && window.location.pathname.match(/\/c\/([a-zA-Z0-9_-]+)/)) || [])[1] || null;
          const state = window.__agyis_hud_state;
          if (focusedConvoId && state && focusedConvoId !== state.convoId && typeof window.__agyis_hud_load_convo === 'function') {
            window.__agyis_hud_load_convo(focusedConvoId);
          } else if (state) {
            if (typeof window.__agyis_hud_sync === 'function') window.__agyis_hud_sync(state);
            if (typeof window.__agyis_hud_render === 'function') window.__agyis_hud_render();
            const selEl = document.querySelector('.agyis-step-grid-item[data-index="' + state.selectedIndex + '"]');
            if (selEl) selEl.scrollIntoView({ block: 'nearest' });
          }
        }
        hud.style.display = isHidden ? 'flex' : 'none';
      }
    }
    if (e.key === 'Escape') {
      const hud = document.getElementById('agyis-trajectory-hud');
      if (hud && hud.style.display !== 'none') {
        hud.style.display = 'none';
      }
    }
    const hud = document.getElementById('agyis-trajectory-hud');
    if (hud && hud.style.display !== 'none' && e.target && (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA')) {
      const state = window.__agyis_hud_state;
      if (state) {
        const steps = (state.currentData && state.currentData.steps) ? state.currentData.steps : [];
        if (e.key === 'ArrowLeft' && state.selectedIndex > 0) {
          state.selectedIndex -= 1;
          if (typeof window.__agyis_hud_render === 'function') window.__agyis_hud_render();
        }
        if (e.key === 'ArrowRight' && state.selectedIndex < steps.length - 1) {
          state.selectedIndex += 1;
          if (typeof window.__agyis_hud_render === 'function') window.__agyis_hud_render();
        }
      }
    }
  };
  window.addEventListener('keydown', window.__agyis_hud_active_listener, true);
})();
