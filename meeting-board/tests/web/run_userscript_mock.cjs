// Drives seats/web/meeting-board-seat.user.js inside a mocked chatgpt.com page.
// Usage: node run_userscript_mock.js <boardUrl> <room> <seatToken> <seconds>
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const [boardUrl, room, token, secs] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('console', m => console.log('[page]', m.text()));
  const html = fs.readFileSync(path.join(__dirname, 'mock_chat_page.html'), 'utf8');
  await page.route('https://chatgpt.com/**', r => r.fulfill({ contentType: 'text/html', body: html }));
  // GM_* shims. GM_xmlhttpRequest goes through Node, like the real extension bypasses page CSP.
  await page.exposeFunction('__gmXhr', async (d) => {
    try {
      const r = await fetch(d.url, { method: d.method, headers: d.headers, body: d.data });
      return { status: r.status, responseText: await r.text() };
    } catch (e) { return { error: String(e) }; }
  });
  const cfg = JSON.stringify({ url: boardUrl, room, token, selectors: '' });
  await page.addInitScript(`
    window.GM_getValue = () => ${JSON.stringify(cfg)}; window.GM_setValue = () => {};
    window.GM_xmlhttpRequest = (d) => { window.__gmXhr({url:d.url, method:d.method, headers:d.headers, data:d.data})
      .then(r => r.error ? d.onerror && d.onerror() : d.onload(r)); };`);
  await page.goto('https://chatgpt.com/');
  await page.addScriptTag({ content: fs.readFileSync(path.join(__dirname, '../../seats/web/meeting-board-seat.user.js'), 'utf8') });
  await page.click('#mbgo');
  const t0 = Date.now();
  while (Date.now() - t0 < secs * 1000) {
    await page.waitForTimeout(1000);
    const st = await page.textContent('#mbstat');
    if (st !== globalThis.__last) { console.log('status:', st); globalThis.__last = st; }
    if (/stopped|error|disconnected/.test(st)) break;
  }
  await browser.close();
})();
