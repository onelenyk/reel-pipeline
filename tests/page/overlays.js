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
  document.querySelector("#overlays .jump").click(); await wait(300); video().pause();
  checks.push(["the paused player shows it in the preview", await until(() => document.getElementById("peek").classList.contains("on"))]);
}
document.getElementById("overlays").scrollIntoView(); window.scrollBy(0, -200); await wait(300);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
