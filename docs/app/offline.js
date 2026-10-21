/* Working offline: the service worker, the "Offline ready" pill, and the new-version banner.
 * Where service workers aren't available (a preview, an old browser), the app still runs; it
 * just needs the network to load. */

import { $, el, toast } from './dom.js';

function pill(text, good) {
  const node = $('#offline');
  node.hidden = false;
  node.className = 'pill' + (good ? ' good' : '');
  node.replaceChildren(el('span', { class: 'dot' }), text);
}

export function registerWorker() {
  const secure = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  if (!('serviceWorker' in navigator) || !secure) return;
  let updating = false;
  let waiting = null;
  const showUpdate = worker => {
    waiting = worker;
    $('#update').hidden = false;
  };
  $('#update-btn').addEventListener('click', () => {
    if (!waiting) return;
    updating = true;
    waiting.postMessage('ACTIVATE');
  });
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (updating) location.reload();
  });
  navigator.serviceWorker.register('sw.js', { scope: './', updateViaCache: 'none' }).then(reg => {
    const watch = w => {
      if (!w) return;
      w.addEventListener('statechange', () => {
        if (w.state === 'installed' && navigator.serviceWorker.controller) showUpdate(w);
        if (w.state === 'activated' && !updating) {
          pill('Offline ready', true);
          toast('Ready offline. Event Horizon now works with no signal.');
        }
      });
    };
    if (reg.waiting && navigator.serviceWorker.controller) showUpdate(reg.waiting);
    if (reg.active) pill('Offline ready', true);
    else {
      pill('Saving for offline…', false);
      watch(reg.installing || reg.waiting);
    }
    reg.addEventListener('updatefound', () => watch(reg.installing));
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && navigator.onLine !== false) reg.update().catch(() => {});
    });
  }).catch(() => { /* Not allowed here; the app works while online. */ });
}
