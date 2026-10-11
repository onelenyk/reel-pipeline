const sleep = (ms) => new Promise((r) => setTimeout(r, ms)); const out = [];
const ok = (label, pass, detail = "") => out.push(`${pass ? "ok  " : "FAIL"} ${label}${pass ? "" : " (" + detail + ")"}`);
await sleep(1500);
const v = document.querySelector("video"); v.muted = true;
ok("status says the video is ready", document.querySelector(".status .big").textContent === "Відео готове", document.querySelector(".status .big").textContent);
ok("listening is the first mode", document.querySelector("[data-mode].on").dataset.mode === "play");
const word = state.words.find((w) => w.at > 12);
document.querySelector(`.w[data-w="${word.id}"]`).click(); await sleep(900);
ok("a tap on a word moves the video there", Math.abs(v.currentTime - word.at) < 1.2 && !v.paused, `${v.currentTime} vs ${word.at}`);
await sleep(600); const lit = document.querySelector(".w.now");
ok("the word being spoken is lit", lit && Math.abs(+lit.dataset.w - word.id) <= 4, lit && lit.dataset.w);
const cut = state.words.find((w) => !w.kept);
if (cut) { document.querySelector(`.w[data-w="${cut.id}"]`).click(); await sleep(500); ok("a tap on a cut word goes to the next kept one", Math.abs(v.currentTime - state.words.slice(cut.id).find((w) => w.at != null).at) < 1.2, v.currentTime); }
document.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", bubbles: true })); await sleep(300);
ok("space pauses", v.paused);
const jump = document.querySelector("#beats .jump"); jump.click(); await sleep(600);
ok("an insert's button jumps to it", Math.abs(v.currentTime - +jump.dataset.seek) < 1.2, v.currentTime);
const join = document.querySelector("#cuts .jump"); if (join) { join.click(); await sleep(600); ok("a cut's button plays the join", Math.abs(v.currentTime - +join.dataset.seek) < 1.2, v.currentTime); }
v.pause(); const before = [...document.querySelectorAll(".w.hot")].length;
document.querySelector('[data-mode="hot"]').click(); await sleep(200);
ok("other modes still work (no seek)", document.querySelector("[data-mode].on").dataset.mode === "hot");
document.querySelector('[data-mode="play"]').click(); const place = v.currentTime;
document.getElementById("render").click(); await sleep(2500);
ok("while building, the status names the step", /Крок \d з \d: Збираю відео/.test(document.querySelector(".status .big").textContent) && !!document.querySelector(".status .clock") && document.title.startsWith("⏳"), document.querySelector(".status .big").textContent + " | " + document.title);
for (let i = 0; i < 300 && state.busy; i++) await sleep(1000);  // a video with plans takes two minutes to build
await sleep(3500);
ok("after building, ready again and the place is kept", document.querySelector(".status .big").textContent === "Відео готове" && Math.abs(document.querySelector("video").currentTime - place) < 1.5, document.querySelector(".status .big").textContent + " " + document.querySelector("video").currentTime + " vs " + place);
window.scrollTo(0, 0);
return out.join("\n");
