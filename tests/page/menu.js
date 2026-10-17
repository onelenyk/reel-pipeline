// The project's header: the way back to its workspace, its name, and its menu (name, workspace, delete), which closes again.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words);
const $ = (id) => document.getElementById(id), shown = (id) => getComputedStyle($(id)).display !== "none" && !$(id).hidden;
checks.push(["the header names the project and its workspace, with no lists of projects", $("projTitle").textContent === state.title && $("crumb").textContent === state.space && !shown("space") && !$("pick")]);
checks.push(["the way back leads to the shelf", $("crumb").getAttribute("href") === "?"]);
checks.push(["the menu is closed at first", $("menu").hidden]);
$("menuBtn").click(); await wait(100);
checks.push(["its button opens it, with the name, the workspace and delete", !$("menu").hidden && $("title").value === state.title && $("move").value === state.space && !!$("trash") && /с у ролику/.test($("facts").textContent)]);
$("trash").click(); await wait(50);
checks.push(["delete asks first, inside the menu", !!$("trashYes") && !!$("trashNo")]);
document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
checks.push(["a touch outside closes it, and the question with it", $("menu").hidden && !!$("trash") && !$("trashYes")]);
$("menuBtn").click(); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
checks.push(["so does Escape", $("menu").hidden]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
