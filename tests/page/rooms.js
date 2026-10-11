// Rooms on a plan: needs IMG_7824 with its plan read and its moments found, none of them tied to a room yet.
// It ties three rooms and removes one moment: run `./reel mark projects/IMG_7824` afterwards to get the moments back.
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f) => { for (let i = 0; i < 60; i++) { if (f()) return true; await wait(100); } return false; };
const click = (el) => el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
checks.push(["plan shown with its rooms", await until(() => document.querySelectorAll(".plan polygon").length >= 10)]);
const listed = document.querySelectorAll(".card.mark").length;
checks.push(["moments listed", listed >= 5]);
checks.push(["all wait for a room", document.querySelectorAll(".card.mark.wait").length === listed]);
click(document.querySelector('polygon[data-room="r13"]'));
checks.push(["a room click without a moment opens its corners", await until(() => document.querySelectorAll(".plan .handle").length >= 3)]);
click(document.querySelector("[data-reshape-no]")); await until(() => !document.querySelector(".plan.reshaping"));
const pick = async (word, room) => {
  const card = [...document.querySelectorAll(".card.mark")].find((c) => c.textContent.includes(word)); click(card.querySelector(".what"));
  await until(() => document.querySelector(".plan.picking")); click(document.querySelector(`polygon[data-room="${room}"]`));
  return until(() => { const c = [...document.querySelectorAll(".card.mark")].find((x) => x.textContent.includes(word)); return c && !c.classList.contains("wait") && !document.querySelector(".plan.picking"); });
};
checks.push(["technical room tied to r13", await pick("технічне приміщення", "r13")]);
checks.push(["laundry tied to r10", await pick("постірочна", "r10")]);
checks.push(["kitchen-living tied to r5", await pick("кухня-вітальня", "r5")]);
checks.push(["used rooms shaded", document.querySelectorAll(".plan polygon.used").length === 3]);
const saved = await (await fetch(`/api/projects/${name}`)).json();
checks.push(["saved in the project", saved.marks.filter((m) => m.room).map((m) => m.room).sort().join() === "r10,r13,r5"]);
click([...document.querySelectorAll(".card.mark")].find((c) => c.textContent.includes("навіс")).querySelector("[data-unmark]"));
checks.push(["a moment can be removed", await until(() => document.querySelectorAll(".card.mark").length === listed - 1)]);
document.getElementById("planBox").scrollIntoView(); await wait(300);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
