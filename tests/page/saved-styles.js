// Saved styles: kept under a name, updated, put on with a touch and taken back, renamed, made the default, put on every
// video of a workspace, deleted after a second touch. Everything is undone. Run it on a copy (takes-check): it is moved
// into a workspace of its own for a moment, so no other video is touched.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && !state.busy);
const $ = (id) => document.getElementById(id), post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body) });
const was = { ...state.style }, home = state.space, room = "Стилі " + Date.now() % 100000, named = "Перевірка " + Date.now() % 100000;
document.querySelector('[data-tab-go="style"]').click(); await wait(200);
$("styleName").value = named; $("styleName").dispatchEvent(new Event("input", { bubbles: true }));
checks.push(["a new name offers to save a new style", $("styleSave").textContent === "Зберегти як новий"]);
$("styleSave").click(); await until(() => styles.some((x) => x.name === named));
const key = styles.find((x) => x.name === named).id;
checks.push(["it is saved and shown as this video's", await until(() => $("styleSave").textContent === "Збережено" && /у цьому відео/.test($("style").textContent))]);
checks.push(["and it is among the gallery's frames", await until(() => [...$("gallery").querySelectorAll(".shot span")].some((x) => x.textContent === named))]);
await edit({ style: { accent: was.accent === "#ff375f" ? "#30d158" : "#ff375f" } });
checks.push(["a change since offers to update it", $("styleSave").textContent === `Оновити «${named}»` && !document.querySelector(`[data-apply="${key}"]`) === false]);
// a ready-made style from the gallery, and back
const preset = [...$("gallery").querySelectorAll(".shot")].find((x) => x.querySelector("span").textContent !== named && JSON.parse(x.dataset.style || "{}").name);
preset.click(); await until(() => state.style.name !== named);
checks.push(["a whole style put on offers to take it back", await until(() => !!document.querySelector('[data-style-undo="1"]'))]);
document.querySelector('[data-style-undo="1"]').click();
checks.push(["«Як було» brings the style back", await until(() => state.style.name === named && !document.querySelector('[data-style-undo="1"]'))]);
document.querySelector(`[data-apply="${key}"]`).click();
checks.push(["«Застосувати» puts the saved one on", await until(() => looks(state.style, styles.find((x) => x.id === key)))]);
// renamed, then the default for new videos
document.querySelector(`[data-style-rename="${key}"]`).click(); await wait(100);
$("styleRename").value = named + " б"; document.querySelector(`[data-style-rename-go="${key}"]`).click();
checks.push(["it can be renamed", await until(() => styles.some((x) => x.name === named + " б") && !styles.some((x) => x.id === key))]);
const key2 = styles.find((x) => x.name === named + " б").id, before = styles.find((x) => x.default);
document.querySelector(`[data-default="${key2}"]`).click();
checks.push(["and made the default for new videos", await until(() => (styles.find((x) => x.id === key2) || {}).default)]);
// every video of a workspace
await post("/api/space", { space: room }).catch(() => {}); await post("/api/spaces", { name: room }); await post(`/api/projects/${name}/space`, { space: room }); state = await api(`/api/projects/${name}`); draw(true);
await edit({ style: { accent: "#64d2ff" } });
document.querySelector(`[data-style-space="${key2}"]`).click();
checks.push(["«Усім відео простору» puts it on the workspace's videos", await until(() => /застосовано до 1 відео/.test($("error").textContent) && looks(state.style, styles.find((x) => x.id === key2)))]);
checks.push(["and on its new ones", ((await api("/api/spaces")).settings[room] || {}).style === key2]);
// deleted only on a second touch
document.querySelector(`[data-style-delete="${key2}"]`).click(); await wait(150);
checks.push(["the first touch on «Видалити» only asks", styles.some((x) => x.id === key2) && document.querySelector(`[data-style-delete="${key2}"]`).textContent === "Точно видалити?"]);
document.querySelector(`[data-style-delete="${key2}"]`).click();
checks.push(["the second deletes it", await until(() => !styles.some((x) => x.id === key2))]);
checks.push(["and the workspace no longer starts with it", !((await api("/api/spaces")).settings[room] || {}).style]);
// undone
await post(`/api/projects/${name}/space`, { space: home }); await post("/api/space", { space: room, remove: true });
if (before) await post(`/api/styles/${encodeURIComponent(before.id)}/default`, {}); styles = await api("/api/styles");
await edit({ style: was });
checks.push(["undone", looks(state.style, was) && state.style.name === was.name && !(await api("/api/spaces")).spaces.includes(room) && (styles.find((x) => x.default) || {}).id === (before || {}).id]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
