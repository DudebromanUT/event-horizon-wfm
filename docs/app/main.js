/* Event Horizon: starts each screen, switches tabs, and turns on offline use. */

import { $, $$ } from './dom.js';
import { load, save } from './store.js';
import * as calc from './calc.js';
import * as whatif from './whatif.js';
import * as sites from './sites.js';
import { registerWorker } from './offline.js';

const TABS = ['calc', 'whatif', 'sites'];

function show(tab) {
  if (!TABS.includes(tab)) tab = 'calc';
  for (const t of TABS) $('#' + t).hidden = t !== tab;
  for (const b of $$('.tab')) {
    if (b.dataset.tab === tab) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  }
  save('tab', tab);
  calc.onTab(tab === 'calc');
  if (tab === 'sites') sites.onShow();
  else sites.onHide();
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
}

calc.init();
whatif.init();
sites.init();      // reads a #setup= link first, if there is one
for (const b of $$('.tab')) {
  b.addEventListener('click', () => {
    show(b.dataset.tab);
    window.scrollTo({ top: 0 });
  });
}
const asked = location.hash.slice(1);
show(TABS.includes(asked) ? asked : load('tab', 'calc'));
window.addEventListener('hashchange', () => {
  const t = location.hash.slice(1);
  if (TABS.includes(t)) show(t);
});
registerWorker();
