// An overlay the author puts on words: from the word menu, the kind, its words filled in from what was said, then added.
// The scenario removes what it added.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && !state.busy);
const $ = (id) => document.getElementById(id), span = (id) => $("words").querySelector(`[data-w="${id}"]`), action = (a) => $("wordMenu").querySelector(`[data-pick="${a}"]`);
const figure = state.words.find((w) => w.kept && w.at != null && /^\d+$/.test(w.text.replace(/[.,]$/, ""))) || state.words.find((w) => w.kept && w.at != null);
span(figure.id).scrollIntoView({ block: "center" }); span(figure.id).click(); await wait(150);
checks.push(["the word menu offers an overlay", !!action("overlay")]);
action("overlay").click(); await wait(100);
checks.push(["it asks which kind", ["sticker", "number", "price", "lower"].every((k) => action("ov:" + k))]);
action("ov:price").click(); await wait(100);
const value = $("wordMenu").querySelector('[data-ov-key="value"]');
checks.push(["a price is filled in from the words", value && (!/\d/.test(figure.text) || value.value === figure.text.replace(/[.,]$/, ""))]);
if (!/\d/.test(figure.text)) value.value = "85 000";
const before = state.overlays.length; action("ovGo").click();
checks.push(["and added on that word", await until(() => state.overlays.length === before + 1 && state.overlays.at(-1).kind === "price" && state.overlays.at(-1).from === figure.id && state.overlays.at(-1).by === "user")]);
const made = state.overlays.at(-1); document.querySelector('[data-tab-go="montage"]').click(); await wait(150);
checks.push(["it is listed with the other overlays, as a price tag", [...document.querySelectorAll("#overlays .card .tag")].some((t) => t.textContent === "Цінник")]);
await edit({ overlay: { id: made.id, remove: true } });
checks.push(["and can be removed again", !state.overlays.some((o) => o.id === made.id)]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
