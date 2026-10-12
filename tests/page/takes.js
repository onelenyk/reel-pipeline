// The takes of a project (run on one made of two or more): they can be moved and taken out, and nothing changes until applied.
// The scenario applies nothing, so the project is left as it was.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && state.takes && !state.busy, 900);
document.querySelector('#tabs [data-tab-go="montage"]').click(); await wait(200);
const rows = () => [...document.querySelectorAll("#takes .take")], ids = () => rows().map((r) => r.dataset.take), was = state.takes.map((t) => t.id);
if (was.length < 2) return "FAIL this project has one take: run the scenario on a project made of several";
checks.push(["each take has a row named by its first words", ids().join() === was.join() && rows().every((r, n) => r.querySelector(".say").textContent.includes(state.words[state.takes[n].from].text))]);
checks.push(["the first cannot go earlier and the last cannot go later", rows()[0].querySelector('[data-move="-1"]').disabled && rows().at(-1).querySelector('[data-move="1"]').disabled]);
checks.push(["a file can be added as one more take", !!document.getElementById("takeMore")]);
rows()[1].querySelector('[data-move="-1"]').click(); await wait(150);
checks.push(["moving a take earlier changes the order on the page", ids().join() === [was[1], was[0], ...was.slice(2)].join()]);
checks.push(["and asks to apply it, with nothing sent yet", !!document.getElementById("takesGo") && !state.busy && state.takes.map((t) => t.id).join() === was.join()]);
rows()[0].querySelector('[data-move="1"]').click(); await wait(150);
checks.push(["moving it back leaves nothing to apply", ids().join() === was.join() && !document.getElementById("takesGo")]);
rows()[0].querySelector('[data-move="0"]').click(); await wait(150);
checks.push(["a take taken out leaves the list, with a warning", ids().join() === was.slice(1).join() && /Прибрано записів: 1/.test(document.getElementById("takes").textContent)]);
if (was.length === 2) checks.push(["the last take left cannot be taken out", rows()[0].querySelector('[data-move="0"]').disabled]);
document.getElementById("takesNo").click(); await wait(150);
checks.push(["cancelling brings every take back", ids().join() === was.join() && !document.getElementById("takesGo")]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
