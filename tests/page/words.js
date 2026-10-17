// The text without modes: a word's menu emphasises, corrects and cuts one word; dragging over words marks a stretch whose
// menu cuts it and brings it back. Every change is undone, so the project is left as it was.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && !state.busy);
const $ = (id) => document.getElementById(id), span = (id) => $("words").querySelector(`[data-w="${id}"]`), action = (a) => $("wordMenu").querySelector(`[data-pick="${a}"]`);
const kept = state.words.filter((w) => w.kept && w.at != null), one = kept[Math.floor(kept.length / 3)], wasHot = one.hot;
span(one.id).click(); await wait(200);
checks.push(["the menu opens beside the word", !$("wordMenu").hidden && Math.abs($("wordMenu").getBoundingClientRect().top - span(one.id).getBoundingClientRect().bottom) < 20]);
action("hot").click(); checks.push(["★ emphasises the word", await until(() => state.words[one.id].hot === !wasHot) && $("wordMenu").hidden]);
span(one.id).click(); await wait(100); action("hot").click(); checks.push(["and once more takes it back", await until(() => state.words[one.id].hot === wasHot)]);
span(one.id).click(); await wait(100); action("fix").click(); await wait(100);
checks.push(["✎ opens the word for correcting", !!$("fixInput") && $("fixInput").value === one.text]);
$("fixInput").dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
checks.push(["Escape leaves the word as it was", await until(() => !$("fixInput")) && state.words[one.id].text === one.text]); await wait(300);
// a stretch: a mouse pressed on one word and let go on another
const a = kept[Math.floor(kept.length / 2)], b = kept[Math.floor(kept.length / 2) + 4], at = (el) => { const r = el.getBoundingClientRect(); return { clientX: r.left + 3, clientY: r.top + r.height / 2 }; };
span(a.id).scrollIntoView({ block: "center" }); await wait(100);
span(a.id).dispatchEvent(new PointerEvent("pointerdown", { ...at(span(a.id)), pointerType: "mouse", button: 0, bubbles: true }));
document.dispatchEvent(new PointerEvent("pointermove", { ...at(span(b.id)), pointerType: "mouse", bubbles: true }));
document.dispatchEvent(new PointerEvent("pointerup", { ...at(span(b.id)), pointerType: "mouse", bubbles: true })); span(b.id).click(); await wait(200);
checks.push(["dragging over words marks the stretch", pick && pick[0] === a.id && pick[1] === b.id && span(a.id + 1).classList.contains("picked")]);
checks.push(["and its menu offers to cut it, add an insert or ask the AI", !!action("cut") && !!action("beat") && !!action("ask") && !action("fix")]);
action("cut").click(); checks.push(["✂ cuts the whole stretch", await until(() => state.words.slice(a.id, b.id + 1).every((w) => !w.kept))]);
span(a.id).click(); await wait(100); checks.push(["a cut word offers to come back", !!action("restore") && !action("cut")]);
span(a.id).dispatchEvent(new PointerEvent("pointerdown", { ...at(span(a.id)), pointerType: "mouse", button: 0, bubbles: true }));
document.dispatchEvent(new PointerEvent("pointermove", { ...at(span(b.id)), pointerType: "mouse", bubbles: true }));
document.dispatchEvent(new PointerEvent("pointerup", { ...at(span(b.id)), pointerType: "mouse", bubbles: true })); span(b.id).click(); await wait(200);
action("restore").click(); checks.push(["↩ brings the stretch back", await until(() => state.words.slice(a.id, b.id + 1).every((w) => w.kept))]);
// a finger: moving at once scrolls the page and marks nothing; held still for a moment, it marks the stretch it is moved over
const finger = async (hold) => { closePick(); await wait(50); span(a.id).dispatchEvent(new PointerEvent("pointerdown", { ...at(span(a.id)), pointerType: "touch", bubbles: true })); await wait(hold);
  document.dispatchEvent(new PointerEvent("pointermove", { ...at(span(b.id)), pointerType: "touch", bubbles: true })); document.dispatchEvent(new PointerEvent("pointerup", { ...at(span(b.id)), pointerType: "touch", bubbles: true })); await wait(150); return pick; };
checks.push(["a finger that moves at once marks nothing", (await finger(30)) === null]);
checks.push(["a finger held still marks the stretch", JSON.stringify(await finger(500)) === JSON.stringify([a.id, b.id])]);
span(a.id).click(); await wait(100); action("ask") || span(a.id).click();
document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); await wait(100);
checks.push(["a touch outside closes the menu", $("wordMenu").hidden && !pick]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
