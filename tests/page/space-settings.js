// A workspace's own settings on the shelf (open with a project of "-"): a name, a vocabulary of its own, the style its
// new videos start with, and taking it away. The scenario makes a workspace for itself and takes it away again.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => projects.length && document.getElementById("homeShelf"));
const made = "Налаштування " + Date.now() % 100000, renamed = made + " нове";
await api("/api/spaces", { method: "POST", body: JSON.stringify({ name: made }) });
const pick = document.getElementById("space"); await until(() => [...pick.options].some((o) => o.value === made)); pick.value = made; pick.dispatchEvent(new Event("change", { bubbles: true }));
checks.push(["a workspace chosen on the shelf shows its settings", await until(() => space === made && document.getElementById("spaceTitle")?.value === made)]);
checks.push(["a new workspace starts with the common vocabulary", await until(() => /передпокій/.test(document.getElementById("spaceVocab").value))]);
document.getElementById("spaceVocab").value = "Тестовий Двір\nпередпокій\nтестовий двір"; document.getElementById("spaceVocabSave").click();
checks.push(["its vocabulary is saved as its own, without doubles", await until(() => /Збережено: 2/.test(document.getElementById("spaceVocabSaid").textContent))
  && (await api(`/api/vocabulary?space=${encodeURIComponent(made)}`)).terms[0] === "Тестовий Двір" && !(await api("/api/vocabulary")).terms.includes("Тестовий Двір")]);
const select = document.getElementById("spaceStyle");
if (select.options.length > 1) { select.value = select.options[1].value; select.dispatchEvent(new Event("change", { bubbles: true }));
  checks.push(["the style of its new videos can be chosen", await until(async () => false, 5) || (await api("/api/spaces")).settings[made].style === select.options[1].value]); }
document.getElementById("endingText").value = "Пишіть у дірект"; document.getElementById("endingSave").click();
checks.push(["its call to action for the end of its videos is kept", await until(() => (spaceSettings[made] || {}).ending === "Пишіть у дірект" && document.getElementById("endingText").value === "Пишіть у дірект")]);
checks.push(["with no logo yet it offers to add one", !!document.getElementById("logoFile") && !document.querySelector(".spaceBox img.logo")]);
document.getElementById("spaceTitle").value = renamed; document.getElementById("spaceRename").click();
checks.push(["it can be renamed, and keeps its vocabulary", await until(() => space === renamed) && (await api(`/api/vocabulary?space=${encodeURIComponent(renamed)}`)).terms[0] === "Тестовий Двір"]);
await until(() => document.getElementById("spaceRemove")); document.getElementById("spaceRemove").click(); await wait(100);
checks.push(["taking it away asks first", !!document.getElementById("spaceRemoveYes")]);
document.getElementById("spaceRemoveYes").click();
checks.push(["and then it is gone, back on the first workspace", await until(() => space === spaceList[0] && !spaceList.includes(renamed))]);
checks.push(["the first workspace cannot be renamed or taken away", await until(() => !document.getElementById("spaceTitle") && !document.getElementById("spaceRemove"))]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
