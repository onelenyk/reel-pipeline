// Opens a page in headless Chrome, runs a scenario in it, prints what the scenario returns and saves a screenshot.
// usage: node shot.mjs <width> <height> <out.png> [scenario.js]   env: URL, DSF (pixel density)
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const [w, h, out, setup] = process.argv.slice(2);
const url = process.env.URL || "http://127.0.0.1:8787/";
const port = 9400 + Math.floor(Math.random() * 500);
const dir = mkdtempSync(join(tmpdir(), "ph-"));
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "--no-first-run", "--hide-scrollbars", `--window-size=${w},${h}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) { await sleep(200); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
await send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: +(process.env.DSF || 1), mobile: +w < 600 });
await send("Page.enable"); await send("Runtime.enable");
await send("Page.navigate", { url }); await sleep(2500);
if (setup) { const r = await send("Runtime.evaluate", { expression: `(async()=>{${readFileSync(setup, "utf8")}})()`, awaitPromise: true, returnByValue: true }); const v = r.result?.result?.value ?? r.result?.exceptionDetails?.exception?.description; if (v !== undefined) console.log(typeof v === "string" ? v : JSON.stringify(v)); }
await sleep(700);
const shot = await send("Page.captureScreenshot", { format: "png" });
writeFileSync(out, Buffer.from(shot.result.data, "base64"));
ws.close(); chrome.kill();
