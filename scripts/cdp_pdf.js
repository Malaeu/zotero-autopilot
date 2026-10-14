#!/usr/bin/env node
// cdp_pdf.js — download a PDF through a real (headless) Chrome via the DevTools protocol.
// Launches its own Chrome with a persistent profile dir, navigates to the URL, waits for the
// application/pdf response and writes its body to <out>. Works through institutional IP access
// (publisher pages that 403 curl) and usually through Cloudflare's passive checks.
// Usage: node cdp_pdf.js <url> <out.pdf> [--profile DIR] [--headful] [--timeout MS]
// Needs: google-chrome-stable (or $CHROME_BIN), Node >= 22 (global WebSocket, fetch).
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const args = process.argv.slice(2);
const url = args[0]; const out = args[1];
if (!url || !out) { console.error('Usage: cdp_pdf.js <url> <out.pdf> [--profile DIR] [--headful] [--timeout MS]'); process.exit(2); }
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const profile = opt('--profile', path.join(os.homedir(), '.cache', 'cdp_pdf_profile'));
const headful = args.includes('--headful');
const timeout = parseInt(opt('--timeout', '90000'), 10);
const port = 9222 + Math.floor(Math.random() * 500);
const chrome = process.env.CHROME_BIN || 'google-chrome-stable';

const flags = [`--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check',
  '--disable-gpu', '--window-size=1280,900', '--remote-allow-origins=*', 'about:blank'];
if (!headful) flags.unshift('--headless=new');
const proc = spawn(chrome, flags, { stdio: 'ignore' });
const die = (code, msg) => { if (msg) console.error(msg); try { proc.kill('SIGTERM'); } catch (_) {} process.exit(code); };
process.on('SIGINT', () => die(130));

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
(async () => {
  let targets;
  for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch (_) { await sleep(200); } }
  if (!targets) die(1, 'chrome did not start');
  const page = targets.find(t => t.type === 'page');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0; const pending = new Map(); const events = [];
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params })); });
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(JSON.stringify(d.error))) : p.res(d.result); } else if (d.method) events.push(d); };
  await new Promise(r => ws.onopen = r);
  await send('Network.enable', { maxResourceBufferSize: 200 * 1024 * 1024, maxTotalBufferSize: 400 * 1024 * 1024 });
  await send('Page.enable');
  // Intercept at response stage: the built-in PDF viewer swallows the body, so grab it here.
  await send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Response' }] });
  let done = false;
  ws.addEventListener('message', async (m) => {
    const d = JSON.parse(m.data);
    if (d.method !== 'Fetch.requestPaused') return;
    const { requestId, responseHeaders, responseStatusCode } = d.params;
    const ct = ((responseHeaders || []).find(h => h.name.toLowerCase() === 'content-type') || {}).value || '';
    if (!done && responseStatusCode === 200 && /pdf/i.test(ct)) {
      try {
        const body = await send('Fetch.getResponseBody', { requestId });
        const buf = Buffer.from(body.body, body.base64Encoded ? 'base64' : 'utf8');
        if (buf.slice(0, 5).toString() === '%PDF-') { done = true; fs.writeFileSync(out, buf); console.log(`saved ${out} ${buf.length} bytes from ${d.params.request.url.slice(0, 120)}`); die(0); }
      } catch (e) { console.error('Fetch.getResponseBody failed: ' + e.message); }
    }
    try { await send('Fetch.continueRequest', { requestId }); } catch (_) {}
  });
  await send('Network.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36' });
  await send('Page.navigate', { url });
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    await sleep(500);
    const resp = events.find(e => e.method === 'Network.responseReceived' && /pdf/i.test(e.params.response.mimeType || '') && e.params.response.status === 200);
    if (resp) {
      const fin = events.find(e => e.method === 'Network.loadingFinished' && e.params.requestId === resp.params.requestId);
      if (!fin) continue;
      try {
        const body = await send('Network.getResponseBody', { requestId: resp.params.requestId });
        const buf = Buffer.from(body.body, body.base64Encoded ? 'base64' : 'utf8');
        if (buf.slice(0, 5).toString() !== '%PDF-') { console.error('body is not a PDF (' + buf.length + ' bytes)'); continue; }
        fs.writeFileSync(out, buf);
        console.log(`saved ${out} ${buf.length} bytes from ${resp.params.response.url.slice(0, 120)}`);
        die(0);
      } catch (e) { console.error('getResponseBody failed: ' + e.message); break; }
    }
  }
  const docs = events.filter(e => e.method === 'Network.responseReceived').map(e => `${e.params.response.status} ${e.params.response.mimeType} ${e.params.response.url.slice(0, 100)}`);
  die(3, 'no PDF response within timeout; responses seen:\n' + docs.slice(0, 15).join('\n'));
})().catch(e => die(1, e.stack));
