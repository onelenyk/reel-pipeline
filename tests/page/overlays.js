// Overlays: they are listed in the Montage tab, one can be switched off and on again, and the preview shows it.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && document.querySelector("#player video"));
document.querySelector('[data-tab-go="montage"]').click(); await until(() => document.getElementById("overlays"));
const rows = () => document.querySelectorAll("#overlays .card");
checks.push(["overlays are listed", rows().length >= 1]);
if (rows().length) {
  const first = state.overlays.slice().sort((a, b) => a.from - b.from)[0], button = () => document.querySelector(`[data-overlay="${first.id}"]`);
  button().click(); checks.push(["one can be switched off", await until(() => state.overlays.find((o) => o.id === first.id).accepted === false)]);
  button().click(); checks.push(["and on again", await until(() => state.overlays.find((o) => o.id === first.id).accepted === true)]);
  document.querySelector("#overlays .jump").click(); await wait(300); await until(() => !video().seeking && video().readyState >= 2, 150); video().pause();   // a long video takes a while to get there
  checks.push(["the paused player shows it in the preview", await until(() => document.getElementById("peek").classList.contains("on"))]);
}
// its words can be changed in place, and changed back
const sticker = state.overlays.find((o) => o.kind === "sticker");
if (sticker) {
  const input = () => document.querySelector(`[data-overlay-field="${sticker.id}:text"]`), was = sticker.text;
  const type = async (text) => { input().value = text; input().dispatchEvent(new Event("change", { bubbles: true })); return until(() => state.overlays.find((o) => o.id === sticker.id).text === text); };
  checks.push(["a sticker has a field with its words", !!input() && input().value === was]);
  checks.push(["typing there changes the sticker", await type("Перевірка")]); checks.push(["and it can be put back", await type(was)]);
}
document.querySelector('[data-tab-go="style"]').click(); await wait(200);
checks.push(["the style offers sounds", !!document.querySelector(`[data-style='{"sounds":"off"}']`)]);
document.querySelector('[data-tab-go="montage"]').click(); await wait(200);
document.getElementById("overlays").scrollIntoView(); window.scrollBy(0, -200); await wait(300);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
