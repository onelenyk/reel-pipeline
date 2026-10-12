// The first screen (open with a project of "-"): the workspace's projects as covers, and a project's name can be changed.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => projects.length && document.querySelector(".proj[data-project]"));
const cards = () => [...document.querySelectorAll(".proj[data-project]")], here = projects.filter((p) => p.space === space);
checks.push(["with no project asked for, the shelf is shown and the editor is not", document.body.classList.contains("home") && getComputedStyle(document.querySelector("main")).display === "none"]);
checks.push(["there is a cover for each project of the workspace", cards().length === here.length && here.length > 0]);
checks.push(["a built project shows a picture and how long its video is", cards().some((c) => c.querySelector("img") && /^\d+:\d\d$/.test((c.querySelector(".long") || {}).textContent || ""))]);
checks.push(["a cover leads to its project", cards()[0].getAttribute("href") === "?p=" + encodeURIComponent(here[0].name)]);
checks.push(["the first tile takes a new video", !!document.querySelector('label.proj.add[for="take"]')]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
const one = here[0], was = one.title, made = "Перевірка назви " + Date.now() % 100000;
await api(`/api/projects/${one.name}/title`, { method: "POST", body: JSON.stringify({ title: made }) }); tick.now();
checks.push(["a new name appears on the cover", await until(() => cards().some((c) => c.dataset.project === one.name && c.querySelector(".name").textContent === made))]);
await api(`/api/projects/${one.name}/title`, { method: "POST", body: JSON.stringify({ title: was === one.name ? "" : was }) }); tick.now();
checks.push(["and an empty name brings back the folder's", await until(() => cards().some((c) => c.dataset.project === one.name && c.querySelector(".name").textContent === was))]);
const other = spaceList.find((s) => s !== space && projects.some((p) => p.space === s));
if (other) { const pick = document.getElementById("space"); pick.value = other; pick.dispatchEvent(new Event("change", { bubbles: true }));
  checks.push(["choosing another workspace shows its projects", await until(() => cards().length === projects.filter((p) => p.space === other).length && cards().every((c) => projects.find((p) => p.name === c.dataset.project).space === other))]); }
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
