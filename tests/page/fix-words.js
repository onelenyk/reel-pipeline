// A correction and what follows it: the same mishearing elsewhere is offered to be corrected too, and the word to be
// remembered for the workspace's next videos. Everything is undone, the vocabulary too. Run it on a copy (takes-check).
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && !state.busy);
const $ = (id) => document.getElementById(id), span = (id) => $("words").querySelector(`[data-w="${id}"]`), action = (a) => $("wordMenu").querySelector(`[data-pick="${a}"]`);
const vocabulary = async () => (await (await fetch(`/api/vocabulary?space=${encodeURIComponent(state.space)}`)).json()).terms, before = await vocabulary();
// a lowercase word heard at least twice, not corrected yet: it is not remembered by itself
const groups = {}; for (const w of state.words) if (!w.fixed && w.kept && /^[а-яіїєґ]{4,}$/.test(letters(w.heard)) && w.heard[0] === w.heard[0].toLowerCase()) (groups[letters(w.heard)] ||= []).push(w.id);
const same = Object.values(groups).find((g) => g.length >= 2), first = same[0], to = "перевіркаслово";
span(first).click(); await wait(100); action("fix").click(); await wait(100);
$("fixInput").value = to; $("fixInput").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
checks.push(["the word is corrected", await until(() => letters(state.words[first].text) === to && state.words[first].fixed)]);
checks.push(["only that word", same.slice(1).every((id) => !state.words[id].fixed)]);
await until(() => $("fixNote").querySelector("[data-note]"));
checks.push(["the note offers the other places heard the same", ($("fixNote").querySelector('[data-note="all"]') || {}).textContent === `Виправити ще ${same.length - 1}`]);
checks.push(["a common word is not remembered by itself", !!$("fixNote").querySelector('[data-note="remember"]') && !(await vocabulary()).some((t) => t.startsWith(to))]);
$("fixNote").querySelector('[data-note="all"]').click();
checks.push(["«Виправити ще» corrects every one of them, each keeping its punctuation", await until(() => same.every((id) => letters(state.words[id].text) === to && state.words[id].text.replace(/[\p{L}]+/u, "") === state.words[id].heard.replace(/[\p{L}]+/u, "")))]);
checks.push(["and the offer is gone", await until(() => !$("fixNote").querySelector('[data-note="all"]'))]);
$("fixNote").querySelector('[data-note="remember"]').click();
checks.push(["«Запам'ятати» puts it into the workspace's vocabulary", await until(() => /запам'ятано/.test($("fixNote").textContent)) && (await vocabulary()).some((t) => t.startsWith(to + " = "))]);
span(first).click(); await wait(100);
checks.push(["a corrected word offers to go back to what was heard", !!action("unfix")]);
action("unfix").click(); checks.push(["↺ brings back what was heard", await until(() => !state.words[first].fixed && state.words[first].text === state.words[first].heard)]);
for (const id of same.slice(1)) await edit({ text: { word: id, to: "" } });
await fetch("/api/vocabulary", { method: "POST", body: JSON.stringify({ terms: before, space: state.space }) });
checks.push(["undone", same.every((id) => !state.words[id].fixed) && JSON.stringify(await vocabulary()) === JSON.stringify(before)]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
