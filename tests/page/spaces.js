// Workspaces: the header lists them, a new one can be made, and the project's menu moves the project into it and back.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && projects.length);
const home = space, made = "Перевірка " + Date.now() % 100000, options = (id) => [...document.getElementById(id).options].map((o) => o.value);
checks.push(["the header leads back to the workspace of the open project", options("space").includes(home) && document.getElementById("crumb").textContent === home]);
await api("/api/spaces", { method: "POST", body: JSON.stringify({ name: made }) }); tick.now();
checks.push(["a new workspace appears in the list", await until(() => options("space").includes(made))]);
checks.push(["and the open project can be moved there", await until(() => options("move").includes(made))]);
const move = document.getElementById("move"); move.value = made; move.dispatchEvent(new Event("change", { bubbles: true }));
checks.push(["after the move the header shows the new workspace, which holds this one project", await until(() => space === made && document.getElementById("crumb").textContent === made && projects.filter((p) => p.space === made).map((p) => p.name).join() === name)]);
const back = document.getElementById("move"); await until(() => options("move").includes(home)); back.value = home; back.dispatchEvent(new Event("change", { bubbles: true }));
checks.push(["and it can be moved back", await until(() => space === home && document.getElementById("crumb").textContent === home)]);
await api("/api/space", { method: "POST", body: JSON.stringify({ space: made, remove: true }) });   // the workspace made for the check goes again
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
