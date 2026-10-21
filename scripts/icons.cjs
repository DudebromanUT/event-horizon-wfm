/* Draws the app icons (docs/icons/*.png) from the Event Horizon mark, using Playwright's Chromium.
 * The mark: a dark core with an amber ring tilted around it; the ring's far side passes behind the
 * core and its near side in front.
 *
 *   Run: node scripts/icons.cjs   (needs Playwright: npm install --no-save playwright@1.56.1) */
const { chromium } = require('playwright');
const path = require('node:path');

const OUT = path.join(__dirname, '..', 'docs', 'icons');

function mark(size, inset) {
  const k = (100 - 2 * inset) / 100;
  return `<!doctype html><html><body style="margin:0">
<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 100 100">
  <defs><clipPath id="near"><rect x="0" y="50" width="100" height="50"/></clipPath></defs>
  <rect width="100" height="100" fill="#10151d"/>
  <g transform="translate(50 50) scale(${k}) translate(-50 -50)">
    <g transform="rotate(-18 50 50)">
      <ellipse cx="50" cy="50" rx="45" ry="14.5" fill="none" stroke="#e9861f" stroke-width="5"/>
    </g>
    <circle cx="50" cy="50" r="21" fill="#06080b" stroke="#f4f6f9" stroke-opacity="0.22" stroke-width="1.2"/>
    <g transform="rotate(-18 50 50)">
      <ellipse cx="50" cy="50" rx="45" ry="14.5" fill="none" stroke="#f0a14a" stroke-width="5" clip-path="url(#near)"/>
    </g>
  </g>
</svg></body></html>`;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const [name, size, inset] of [['icon-180.png', 180, 4], ['icon-192.png', 192, 4], ['icon-512.png', 512, 4],
    ['icon-maskable-512.png', 512, 14]]) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(mark(size, inset));
    await page.screenshot({ path: path.join(OUT, name), clip: { x: 0, y: 0, width: size, height: size } });
    console.log('wrote docs/icons/' + name);
  }
  await browser.close();
})();
