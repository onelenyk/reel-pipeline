// Zones of a plan: needs a project whose plan has been read. It renames one zone and puts its name back.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f) => { for (let i = 0; i < 60; i++) { if (f()) return true; await wait(100); } return false; };
document.querySelector('[data-tab-go="plan"]').click();
checks.push(["every zone has a field and a tag on the plan", await until(() => document.querySelectorAll("input[data-zone]").length >= 5) && document.querySelectorAll(".plan .pin").length === document.querySelectorAll("input[data-zone]").length]);
checks.push(["guesses are marked as guesses", document.querySelectorAll("input[data-zone].guess").length > 0 && document.querySelectorAll(".plan .pin.guess").length > 0]);
const field = document.querySelector("input[data-zone].guess"), room = field.dataset.zone, was = field.value;
const set = async (value) => { const f = document.querySelector(`input[data-zone="${room}"]`); f.value = value; f.dispatchEvent(new Event("change", { bubbles: true })); };
await set("Кабінет");
checks.push(["a typed name is saved and stops being a guess", await until(() => { const f = document.querySelector(`input[data-zone="${room}"]`); return f && f.value === "Кабінет" && !f.classList.contains("guess"); })]);
const saved = await (await fetch(`/api/projects/${name}`)).json();
checks.push(["the name is kept with the plan", saved.plans.some((p) => p.rooms.some((r) => r.id === room && r.name === "Кабінет" && !r.guess))]);
checks.push(["the pin on the plan carries it", document.querySelector(`.plan .pin[data-pin="${room}"]`).title === "Кабінет" && !document.querySelector(`.plan .pin[data-pin="${room}"]`).classList.contains("guess")]);
await set(was); await until(() => document.querySelector(`input[data-zone="${room}"]`).value === was);
window.scrollTo(0, 0); await wait(300);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
