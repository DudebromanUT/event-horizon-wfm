/* Clicks through every screen of the web app on a phone-sized page and checks what it shows,
 * then turns the network off and checks the app still opens.
 *
 *   Run: node tests/browser/clickthrough.cjs
 *   Needs Playwright 1.56.1 and its Chromium: npm install --no-save playwright@1.56.1 && npx playwright install chromium
 *
 * Every run is the same: docs/ is served at /event-horizon/ like GitHub Pages, and the page's clock
 * starts at 15:04 UTC on Tuesday 20 October 2026 (only Date moves; timers are untouched). Expected
 * numbers come from the engine itself (docs/app/engine.js), which tests/web/ checks against Python. */
const { chromium, devices } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const DOCS = path.join(__dirname, '..', '..', 'docs');
const START = Date.parse('2026-10-20T15:04:00Z');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.webmanifest': 'application/manifest+json', '.png': 'image/png', '.woff2': 'font/woff2' };

function serve() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const rel = decodeURIComponent(url.pathname).replace(/^\/event-horizon\//, '');
    const file = path.join(DOCS, rel === '' ? 'index.html' : rel);
    if (!url.pathname.startsWith('/event-horizon/') || !file.startsWith(DOCS + path.sep)) { res.writeHead(404); res.end(); return; }
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end(); return; }
      const type = TYPES[path.extname(file)] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache' });
      res.end(data);
    });
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

const steps = [];
function step(name) { steps.push(name); console.log('  ' + name); }

async function text(page, selector) {
  return (await page.locator(selector).first().innerText()).replace(/\s+/g, ' ').trim();
}

async function until(page, selector, expected) {
  try {
    await page.waitForFunction(([s, e]) => {
      const node = document.querySelector(s);
      // As displayed (innerText), ignoring the uppercase some labels are styled with.
      return node && node.innerText.replace(/\s+/g, ' ').trim().toLowerCase().includes(e.toLowerCase());
    }, [selector, expected], { timeout: 5000 });
  } catch (e) {
    throw new Error(`${selector} never showed "${expected}"; it shows "${await text(page, selector).catch(() => '(missing)')}"`);
  }
}

async function fill(page, selector, value) {
  await page.fill(selector, value);
  await page.waitForTimeout(250);   // inputs recalculate shortly after typing stops
}

(async () => {
  const E = await import(path.join(DOCS, 'app', 'engine.js'));
  const F = await import(path.join(DOCS, 'app', 'format.js'));
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/event-horizon/`;
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['iPhone 13'], locale: 'en-US', timezoneId: 'America/Denver' });
  await ctx.addInitScript(start => {
    const RealDate = Date, offset = start - RealDate.now();
    window.Date = class extends RealDate {
      constructor(...args) { if (args.length) super(...args); else super(RealDate.now() + offset); }
      static now() { return RealDate.now() + offset; }
    };
  }, START);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('page error: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  console.log('Event Horizon click-through');
  await page.goto(base, { waitUntil: 'networkidle' });

  step('Calc opens on the example interval, with hang-ups and caps');
  const a = E.requiredAgents({ calls: 100, aht: 300, patience: 120, maxAbandon: 0.05, maxOccupancy: 0.9 });
  await until(page, '#calc-agents', String(a.agents));
  assert.equal(await text(page, '#k-sl'), F.pct(a.sl));
  assert.equal(await text(page, '#k-ab'), F.pct(a.abandon));
  assert.match(await text(page, '#calc-verdict'), /Meets 80\/20, hang-ups at or under 5%, occupancy at or under 90%\./);
  assert.equal(await page.locator('#cliff .bar').count(), 9);
  assert.equal(await page.locator('#cliff .bar.pick').count(), 1);

  step('A bar shows its numbers on focus');
  await page.locator('#cliff .hit').nth(3).focus();
  await until(page, '#cliff-tip', `${a.agents - 1} agents`);
  assert.equal(await page.locator('#cliff-tip').isVisible(), true);

  step('Blank patience switches to Erlang C');
  await fill(page, '#c-pat', '');
  const c = E.requiredAgents({ calls: 100, aht: 300, maxOccupancy: 0.9 });
  await until(page, '#calc-agents', String(c.agents));
  await until(page, '#calc-model', 'Erlang C');
  assert.equal(await text(page, '#k-ab'), '—');

  step('Costs find the cheapest staffing on a merchant counter line');
  await fill(page, '#c-calls', '60');
  await fill(page, '#c-aht', '240');
  await fill(page, '#c-pat', '90');
  await fill(page, '#c-maxab', '');
  await fill(page, '#c-maxocc', '');
  await fill(page, '#c-shrink', '');
  await fill(page, '#c-cost', '28');
  await fill(page, '#c-abcost', '75');
  const best = E.cheapestStaffing(60, 240, 90, 28, 75);
  const goal = E.requiredAgents({ calls: 60, aht: 240, patience: 90 });
  await until(page, '#calc-money-list', `${best.agents} agents`);
  await until(page, '#calc-money-list', `${F.money(best.total)} cheapest vs ${F.money(E.costAt(goal.agents, 60, 240, 90, 28, 75).total)} at your goal`);

  step('A bad entry says which field to fix');
  await fill(page, '#c-aht', 'abc');
  await until(page, '#calc-error', 'Handle time needs a number.');
  assert.equal(await page.getAttribute('#c-aht', 'aria-invalid'), 'true');
  await fill(page, '#c-aht', '240');
  assert.equal(await page.locator('#calc-error').isVisible(), false);

  step('Inputs come back after a reload');
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.inputValue('#c-calls'), '60');
  await until(page, '#calc-agents', String(goal.agents));

  step('What-if: AI containment');
  await page.click('.tab[data-tab="whatif"]');
  const ai = E.containment({ calls: 100, aht: 300, contained: 0.2, ahtChange: 0.1 });
  await until(page, '#a-before', String(ai.before.agents));
  await until(page, '#a-after', String(ai.after.agents));
  await until(page, '#a-bars', `${F.pct(ai.savedShare, 0)} (${ai.saved})`);

  step('What-if: pooling, and adding and removing a queue');
  await page.click('#w-mode button[data-mode="pool"]');
  const pool = E.pooling([{ calls: 120, aht: 330 }, { calls: 80, aht: 330 }, { calls: 40, aht: 330 }]);
  await until(page, '#p-apart', String(pool.agentsSeparate));
  await until(page, '#p-pooled', String(pool.pooled.agents));
  await page.click('#p-add');
  assert.equal(await page.locator('#p-queues .row').count(), 4);
  await page.locator('#p-queues .row').nth(3).getByRole('button', { name: 'Remove queue 4' }).click();
  assert.equal(await page.locator('#p-queues .row').count(), 3);
  await until(page, '#p-apart', String(pool.agentsSeparate));

  step('What-if: lending agents');
  await page.click('#w-mode button[data-mode="move"]');
  const mv = E.moveAgents({ calls: 100, aht: 300, agents: 22, patience: 180 }, { calls: 40, aht: 420, agents: 9, patience: 180 }, 2);
  await until(page, '#m-table', F.pct(mv.sourceAfter.sl));
  await until(page, '#m-table', F.pct(mv.destAfter.sl));

  step('What-if: chat concurrency');
  await page.click('#w-mode button[data-mode="chat"]');
  await until(page, '#h-note', 'Fewest agents at 2 chats at once.');

  step('Sites: clocks, hours and the coming changes at 15:04 UTC on 20 October');
  await page.click('.tab[data-tab="sites"]');
  await until(page, '#s-heading', 'At Tue 20 Oct 15:04 UTC');
  assert.equal(await page.locator('#s-grid .clock').count(), 5);
  await until(page, '#s-grid .clock:nth-child(1)', 'Denver Open until 19:00 09:04 Tue · UTC-6');
  await until(page, '#s-grid .clock:nth-child(4)', 'Manila Open all week 23:04 Tue · UTC+8');
  await until(page, '#s-changes', 'Sun 25 Oct London changes to UTC+0');
  await until(page, '#s-changes', 'Sun 1 Nov New York changes to UTC-5 (customer clock)');
  await until(page, '#s-anchors', 'from 1 Nov 06 13 08 21 16');
  assert.equal(await page.locator('#s-example').isVisible(), true);

  step('Edit a site and save it');
  await page.click('#s-edit');
  await page.locator('details.site-edit summary').first().click();
  await fill(page, '#e0-name', 'Head office');
  await page.click('#e0-sat-closed');
  await page.click('#e-save');
  await until(page, '#s-grid .clock:nth-child(1)', 'Head office');
  assert.equal(await page.locator('#s-example').isVisible(), false);

  step('A pasted setup code replaces the sites');
  await page.click('#s-edit');
  const seven = { anchors: [{ label: '8:00 New York', zone: 'America/New_York', time: '08:00' }],
    sites: ['America/Denver', 'Europe/London', 'Africa/Lagos', 'Asia/Manila', 'America/Puerto_Rico', 'America/Guatemala', 'Asia/Kolkata']
      .map((zone, i) => ({ id: 'S' + (i + 1), name: 'Site ' + (i + 1), zone, hours: { 'mon-fri': '08:00-20:00' } })) };
  await page.fill('#e-code', JSON.stringify(seven));
  await page.click('#e-load');
  await until(page, '#toast', 'Sites loaded from the setup code.');
  assert.equal(await page.locator('#s-grid .clock').count(), 7);
  await until(page, '#s-anchors', 'S7');

  step('A setup link loads sites on another device');
  const link = await page.evaluate(() => {
    const json = JSON.stringify({ note: 'Hours are placeholders until you set them.', sites: [{ id: 'LOS', name: 'Lagos', zone: 'Africa/Lagos', hours: { daily: '24h' } }] });
    const bytes = new TextEncoder().encode(json);
    return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  });
  const other = await ctx.newPage();
  other.on('pageerror', e => errors.push('page error (setup link): ' + e.message));
  await other.goto(base + '#setup=' + link, { waitUntil: 'networkidle' });
  await until(other, '#toast', 'Loaded 1 sites from your setup link.');
  await until(other, '#s-grid', 'Lagos');
  assert.equal(await other.locator('#s-grid .clock').count(), 1);
  await until(other, '#s-example', 'Hours are placeholders until you set them.');
  assert.equal(new URL(other.url()).hash, '#sites');
  await other.close();

  step('Going back to the example sites takes two taps');
  await page.reload({ waitUntil: 'networkidle' });
  await page.click('.tab[data-tab="sites"]');
  await page.click('#s-edit');
  await page.click('#e-reset');
  await until(page, '#e-reset', 'Tap again to replace your sites');
  await page.click('#e-reset');
  assert.equal(await page.locator('#s-grid .clock').count(), 5);

  step('It works with the network off');
  await until(page, '#offline', 'Offline ready');
  await ctx.setOffline(true);
  await page.reload({ waitUntil: 'load' });
  await page.click('.tab[data-tab="calc"]');
  await until(page, '#calc-agents', String(goal.agents));
  await page.click('.tab[data-tab="sites"]');
  await until(page, '#s-heading', 'At Tue 20 Oct');
  await ctx.setOffline(false);

  step('Nothing scrolls sideways, and dark mode loads');
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
  assert.ok(widths[0] <= widths[1], `page is ${widths[0]}px wide on a ${widths[1]}px screen`);
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.click('.tab[data-tab="calc"]');
  await until(page, '#calc-agents', String(goal.agents));

  assert.deepEqual(errors, [], 'the page logged errors');
  await browser.close();
  server.close();
  console.log(`All ${steps.length} steps passed.`);
})().catch(e => {
  console.error('FAILED at: ' + steps[steps.length - 1]);
  console.error(e);
  process.exit(1);
});
