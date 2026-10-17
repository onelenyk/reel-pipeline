// The look: frames, one for each look of each decoration, at the top of its tab, one for each look of each decoration; touching one chooses it.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && state.presets);
document.querySelector('[data-tab-go="style"]').click(); await until(() => document.querySelectorAll("#gallery .shot").length > 10);
const shots = [...document.querySelectorAll("#gallery .shot")], loaded = () => shots.filter((s) => { const i = s.querySelector("img"); return i.complete && i.naturalWidth > 100; }).length;
shots.forEach((s) => s.querySelector("img").loading = "eager");
checks.push(["the gallery shows the ready-made styles and every look", shots.length >= state.presets.length + 4 + 3 + 3 + 3]);
checks.push(["its pictures are drawn", await until(() => loaded() >= state.presets.length + 14, 600)]);
const was = state.style.sticker, other = was === "pill" ? "tag" : "pill", pick = shots.find((s) => s.dataset.style === JSON.stringify({ sticker: other }));
pick.click(); checks.push(["touching a look chooses it", await until(() => state.style.sticker === other)]);
await edit({ style: { sticker: was } }); checks.push(["and it can be put back", state.style.sticker === was]);
checks.push(["there is one tab for the look, and no gallery tab", !document.querySelector('[data-tab-go="gallery"]') && document.querySelector('[data-tab-go="style"]').textContent === "Вигляд"]);
checks.push(["what the frames show is not offered again as buttons", !document.querySelector(`#style [data-style='{"sticker":"pill"}']`) && !document.querySelector(`#style [data-style='{"navigator":"steps"}']`)]);
const fold = document.getElementById("moreFold"); checks.push(["the rare choices are folded away", fold && !fold.open && !!fold.querySelector("#level")]);
fold.open = true; await wait(50); await edit({ style: { sounds: state.style.sounds } });
checks.push(["and stay open while they are changed", document.getElementById("moreFold").open]);
await wait(1500); window.scrollTo(0, document.getElementById("gallery").getBoundingClientRect().top + window.scrollY - 120); await wait(400);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n") + `\n${loaded()} of ${shots.length} pictures`;
