// The crop of a photo: on an insert the author drags a frame of the insert's own shape over the photo; the part kept is
// saved with the photo and the frame of the video changes with it. The insert is removed again. Run it on a copy (takes-check).
const wait = (ms) => new Promise((r) => setTimeout(r, ms)); const checks = [];
const until = async (f, n = 80) => { for (let i = 0; i < n; i++) { if (f()) return true; await wait(100); } return false; };
await until(() => state && state.words && !state.busy);
const $ = (id) => document.getElementById(id), asset = state.assets[0], had = new Set(state.beats.map((b) => b.id));
const kept = state.words.filter((w) => w.kept && w.at != null), from = kept[3].id, to = kept[9].id;
await edit({ add_beat: { kind: "cutaway", from, to, asset: asset.id } });
const beat = state.beats.find((b) => !had.has(b.id));
document.querySelector('[data-tab-go="montage"]').click(); await wait(200);
const button = document.querySelector(`[data-crop="${beat.id}"]`);
checks.push(["an insert with a photo offers «Кадр»", !!button]);
button.click(); await until(() => $("cropFrame") && !$("cropFrame").hidden);
const image = $("cropImg").getBoundingClientRect(), frame = $("cropFrame").getBoundingClientRect();
checks.push(["the frame has the insert's shape", Math.abs(frame.width / frame.height - 972 / 576) < 0.03]);
checks.push(["and lies inside the photo", frame.left >= image.left - 1 && frame.right <= image.right + 1 && frame.top >= image.top - 1 && frame.bottom <= image.bottom + 1]);
const frameAt = async (focus) => { await edit({ focus: { asset: asset.id, at: focus } }); const r = await fetch(`/frame/${name}/frame.jpg?t=${(kept[5].at + 0.6).toFixed(2)}&n=${Math.random()}`); return new Uint8Array(await r.arrayBuffer()).join(","); };
// dragging to the top left corner of the photo
const box = $("cropBox"), at = (x, y) => ({ clientX: x, clientY: y, pointerId: 1, bubbles: true, pointerType: "mouse", button: 0 });
box.dispatchEvent(new PointerEvent("pointerdown", at(image.left + 2, image.top + 2))); document.dispatchEvent(new PointerEvent("pointerup", at(image.left + 2, image.top + 2)));
const moved = $("cropFrame").getBoundingClientRect(), wide = frame.width < image.width - 2;   // the photo is wider than the insert, or taller
checks.push(["dragging moves the frame to where the finger is", Math.abs((wide ? moved.left - image.left : moved.top - image.top)) < 1.5]);
checks.push(["it is saved with the photo", await until(() => { const a = state.assets.find((x) => x.id === asset.id).focus; return a && a[wide ? 0 : 1] === 0; })]);
checks.push(["and the preview shows that part", $("cropPreview").style.backgroundPosition === (wide ? "0% 50%" : "50% 0%")]);
document.querySelector('[data-crop-do="middle"]').click();
checks.push(["«По центру» brings the frame back to the middle", await until(() => String(state.assets.find((x) => x.id === asset.id).focus) === "0.5,0.5")]);
document.querySelector('.sheet [data-crop-do="close"]').click(); await wait(100);
checks.push(["«Готово» closes it", !$("crop").innerHTML]);
checks.push(["the video's frame follows the crop", (await frameAt([0, 0])) !== (await frameAt([1, 1]))]);
await edit({ focus: { asset: asset.id, at: null } }); await edit({ remove_beat: beat.id });
checks.push(["undone", !state.beats.some((b) => b.id === beat.id) && !state.assets.find((x) => x.id === asset.id).focus]);
checks.push(["the page is no wider than the screen", document.documentElement.scrollWidth <= window.innerWidth]);
return checks.map(([n, ok]) => (ok ? "ok   " : "FAIL ") + n).join("\n");
