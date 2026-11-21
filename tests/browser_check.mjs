// Abre a tela do EasyRGB num Chrome/Edge sem janela e confere: sem erros de JavaScript, sem código
// injetado rodando (XSS), sem rolagem para o lado e com os botões principais funcionando.
// Uso: node tests/browser_check.mjs http://127.0.0.1:PORTA/   -> imprime um JSON com o resultado
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const url = process.argv[2];
const chrome = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
if (!chrome) { console.log(JSON.stringify({ skip: "sem Chrome/Edge" })); process.exit(0); }

const port = 9400 + Math.floor(Math.random() * 400);
const profile = mkdtempSync(join(tmpdir(), "easyrgb-e2e-"));
const proc = spawn(chrome, ["--headless=new", "--disable-gpu", "--no-first-run", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = { errors: [], widths: {}, clicks: 0 };
try {
  let targets;
  for (let i = 0; i < 80 && !targets; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(250); }
  }
  const ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const wait = new Map();
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") out.errors.push("EXCEPTION " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
      out.errors.push("CONSOLE " + m.params.args.map(a => a.value ?? a.description).join(" "));
    if (m.method === "Page.javascriptDialogOpening") { out.errors.push("DIALOG " + m.params.message); }
  };
  const send = (method, params = {}) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const evalJs = async expr => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
  await send("Runtime.enable"); await send("Page.enable");
  for (const w of [1440, 768, 375]) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: w < 500 });
    await send("Page.navigate", { url });
    await sleep(3500);
    out.widths[w] = await evalJs(`({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth,
      xss: !!window.__xss, connected: document.querySelector('#status')?.classList.contains('on'),
      presets: document.querySelectorAll('#presets .preset, #presets button').length})`);
  }
  // clica nos botões principais: efeitos, presets e pílulas dos periféricos
  out.clicks = await evalJs(`(async () => {
    let n = 0; const sleep = ms => new Promise(r => setTimeout(r, ms));
    for (const sel of ['#fxseg button', '#presets .preset', '[data-pe]', '#mode button']) {
      for (const b of [...document.querySelectorAll(sel)].slice(0, 12)) { b.click(); n++; await sleep(60); }
    }
    return n;
  })()`);
  await sleep(1500);
  out.xss_after_clicks = await evalJs("!!window.__xss");
  ws.close();
} catch (e) {
  out.errors.push("SCRIPT " + e);
} finally {
  proc.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
console.log(JSON.stringify(out));
process.exit(0);
