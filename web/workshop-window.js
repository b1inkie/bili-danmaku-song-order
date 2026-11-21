/* Window-only controls for the opaque, rounded workshop. */
"use strict";
document.addEventListener("DOMContentLoaded", () => {
  initDrawnIcons();
  document.querySelectorAll('.workshop-windowbar button').forEach(button => {
    button.addEventListener('mousedown', event => event.stopPropagation());
  });
  for (const action of ['minimize', 'maximize', 'close']) {
    document.getElementById('workshop-'+action).onclick = async () => {
      try {
        if (action === 'close' && typeof discard === 'function' && !await discard()) return;
        if (action === 'close') dirty = false;
        await window.pywebview.api.window_action(action);
      } catch (error) { if (typeof status === 'function') status(error.message || String(error), true); }
    };
  }
  const update = () => drawButtonLabel(document.getElementById('workshop-maximize'), document.documentElement.dataset.maximized === 'true' ? 'restore' : 'maximize');
  new MutationObserver(update).observe(document.documentElement, {attributes: true, attributeFilter: ['data-maximized']});
  update();
  document.querySelectorAll('[data-edge]').forEach(handle => {
    handle.addEventListener('pointerdown', async event => {
      if (event.button !== 0 || !window.pywebview?.api) return;
      event.preventDefault(); handle.setPointerCapture(event.pointerId);
      const edge = handle.dataset.edge, x = event.screenX, y = event.screenY;
      let geometry = null, queued = null, sending = false;
      async function send() {
        if (sending || !geometry || !queued) return;
        sending = true;
        try {
          while (queued) {
            const [px, py] = queued; queued = null;
            const width = Math.max(980, Math.min(6000, geometry.w + (edge.includes('e') ? px-x : edge.includes('w') ? x-px : 0)));
            const height = Math.max(680, Math.min(6000, geometry.h + (edge.includes('s') ? py-y : edge.includes('n') ? y-py : 0)));
            await window.pywebview.api.resize_window(Math.round(width), Math.round(height), edge);
          }
        } catch (error) { status(error.message || String(error), true); }
        finally { sending = false; }
      }
      handle.onpointermove = e => { queued = [e.screenX, e.screenY]; send(); };
      const stop = e => {
        if (e.type === 'pointerup') { queued = [e.screenX, e.screenY]; send(); }
        handle.onpointermove = handle.onpointerup = handle.onpointercancel = null;
      };
      handle.onpointerup = handle.onpointercancel = stop;
      try { geometry = await window.pywebview.api.window_geometry(); send(); }
      catch (error) { status(error.message || String(error), true); }
    });
  });
});
