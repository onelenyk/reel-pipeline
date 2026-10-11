// Drawing a zone: on IMG_7824 the hall shares its space with the living room; a rectangle drawn over it becomes a zone of
// its own, named "Передпокій", and the moment that speaks of the hall takes it. The zone is left in place.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f) => { for (let i = 0; i < 80; i++) { if (f()) return true; await wait(100); } return false; };
document.querySelector('[data-tab-go="plan"]').click(); await until(() => document.querySelector("[data-sketch]"));
const zones = () => document.querySelectorAll("input[data-zone]").length, before = zones();
const old = [...document.querySelectorAll("input[data-zone]")].find((f) => f.value === "Передпокій");
if (old) { old.parentElement.querySelector("[data-zone-remove]").click(); await until(() => zones() === before - 1); }
const start = zones();
document.querySelector("[data-sketch]").click();
checks.push(["the plan goes into drawing", await until(() => document.querySelector(".plan.drawing"))]);
const box = document.querySelector(".plan.drawing"), rect = () => box.querySelector(".planInner").getBoundingClientRect();
const ev = (type, x, y) => box.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: rect().left + x * rect().width, clientY: rect().top + y * rect().height }));
ev("pointerdown", 0.49, 0.64); ev("pointermove", 0.54, 0.7);
checks.push(["a rectangle follows the pointer", !!document.querySelector(".plan .sketch")]);
ev("pointermove", 0.578, 0.75); ev("pointerup", 0.578, 0.75);
checks.push(["a new zone appears and its field waits for a name", await until(() => zones() === start + 1 && document.activeElement && document.activeElement.matches("input[data-zone]") && !document.activeElement.value)]);
const field = document.activeElement, room = field.dataset.zone; field.value = "Передпокій"; field.dispatchEvent(new Event("change", { bubbles: true }));
checks.push(["the name is saved", await until(() => { const f = document.querySelector(`input[data-zone="${room}"]`); return f && f.value === "Передпокій"; })]);
await wait(1200); const state2 = await (await fetch(`/api/projects/${name}`)).json(), hall = state2.marks.find((m) => /передпок/i.test(m.name || ""));
checks.push(["the moment about the hall takes the new zone", !!hall && hall.room === room]);
const plan = state2.plans.find((p) => p.rooms.some((x) => x.id === room)), made = plan.rooms.find((x) => x.id === room), xs = made.shape.map((q) => q[0]), ys = made.shape.map((q) => q[1]);
checks.push(["it lies where it was drawn", Math.min(...xs) > 0.46 && Math.max(...xs) < 0.6 && Math.min(...ys) > 0.6 && Math.max(...ys) < 0.78]);
window.scrollTo(0, 0); await wait(400);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n") + "\nzone " + room + " " + JSON.stringify(made.shape);
