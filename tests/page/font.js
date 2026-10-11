// Fonts: choosing a family changes the style and the preview shows it; the style is put back afterwards.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 100) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.style && document.querySelector("#player video"));
document.querySelector('[data-tab-go="style"]').click(); await until(() => document.getElementById("fontPick"));
const was = { font: state.style.font, caps: state.style.caps }, pick = document.getElementById("fontPick");
checks.push(["the list offers a dozen families", pick.options.length >= 12]);
const other = was.font === "Unbounded" ? "Montserrat" : "Unbounded"; pick.value = other; pick.dispatchEvent(new Event("change", { bubbles: true }));
checks.push(["choosing one changes the style", await until(() => state.style.font === other)]);
checks.push(["and the paused player shows a frame in it", await until(() => document.getElementById("peek").classList.contains("on"))]);
const frame = async () => new Uint8Array(await (await fetch(`/frame/${name}/frame.jpg?t=12`)).arrayBuffer()).length, inOther = await frame();
document.getElementById("fontOther").value = "Lobster"; document.getElementById("fontSet").click();
checks.push(["a family typed by name is taken too", await until(() => state.style.font === "Lobster")]);
checks.push(["the frame is drawn differently in it", (await frame()) !== inOther]);
await edit({ style: { caps: !was.caps } }); checks.push(["capitals switch", state.style.caps === !was.caps]);
await edit({ style: was }); await wait(500);
checks.push(["the style is back as it was", state.style.font === was.font && state.style.caps === was.caps]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
