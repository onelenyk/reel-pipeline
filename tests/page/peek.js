// The frame preview: after a change the paused player shows the moment as it would be built. Changes the accent colour and puts it back.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => document.querySelector("#player video") && state && state.style);
const layer = () => document.getElementById("peek"), was = state.style.accent, other = was === "#30d158" ? "#ffd60a" : "#30d158";
checks.push(["no preview while nothing has changed", layer() && !layer().classList.contains("on")]);
await edit({ style: { accent: other } });
checks.push(["after a change the paused player shows a preview", await until(() => layer().classList.contains("on") && layer().querySelector("img").naturalWidth > 100)]);
const first = layer().querySelector("img").src;
video().currentTime = 30; 
checks.push(["moving through the video redraws it", await until(() => layer().querySelector("img").src !== first && layer().classList.contains("on"))]);
layer().dispatchEvent(new MouseEvent("click", { bubbles: true }));
checks.push(["a tap brings the video back", !layer().classList.contains("on")]);
const took = performance.now(); await (await fetch(`/frame/${name}/frame.jpg?t=12`)).blob();
checks.push(["a frame is drawn in under two seconds", performance.now() - took < 2000]);
await edit({ style: { accent: was } }); await wait(600);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n") + `\nframe in ${Math.round(performance.now() - took)} ms`;
