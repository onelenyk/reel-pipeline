// Draws the graphics layer of a video (subtitles, titles, pictures) and writes it to standard output
// as raw RGBA frames with transparency. ffmpeg lays these over the footage.
//
//   node render.mjs timeline.json > frames.rgba
//
// The timeline is already resolved to seconds of the finished video (see engine/project.py: resolve).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire("/opt/renderer/");
const { createCanvas, loadImage, GlobalFonts } = require("@napi-rs/canvas");

const timeline = JSON.parse(readFileSync(process.argv[2], "utf8"));
const { width: W, height: H, fps } = timeline;
const STYLE = timeline.style ?? {};
const ACCENT = STYLE.accent ?? "#ffd60a";
// The style's own font, if it names one, is a file the engine has fetched; Inter stands behind it for any sign it lacks
if (STYLE.font_file) GlobalFonts.registerFromPath(STYLE.font_file, "ReelFont");
const FONT = (STYLE.font_file ? "ReelFont, " : "") + "Inter, 'Noto Sans', sans-serif";
const WEIGHT = STYLE.font_file ? STYLE.font_weight ?? 800 : 800;
if (STYLE.caps) for (const line of timeline.lines) for (const word of line.words) word.text = word.text.toUpperCase();

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const ease = (k) => 1 - Math.pow(1 - clamp(k), 3);
const back = (k) => { k = clamp(k); return 1 + 2.7 * Math.pow(k - 1, 3) + 1.7 * Math.pow(k - 1, 2); };
/** 0 → 1 while something enters, 1 while it stays, 1 → 0 while it leaves. */
const presence = (t, start, end, enter = 0.3, leave = 0.25) => Math.min(ease((t - start) / enter), ease((end - t) / leave));

const canvas = createCanvas(W, H);
const ctx = canvas.getContext("2d");
const font = (size, weight = WEIGHT) => { ctx.font = `${weight} ${size}px ${FONT}`; };

const pictures = new Map();
for (const beat of timeline.beats) {
  if ((beat.kind === "cutaway" || beat.kind === "full") && beat.file && !pictures.has(beat.file)) pictures.set(beat.file, await loadImage(beat.file).catch(() => null));
}

// ---------- pictures: a card in the upper part of the frame; the speaker stays visible below ----------
// The containers a picture above the speaker can sit in. "mix" gives each next picture the next one, so a video with
// several pictures does not show them all the same way.
const CONTAINERS = ["card", "polaroid", "circle"];
const cutaways = timeline.beats.filter((b) => b.kind === "cutaway");
const containerOf = (beat) => (STYLE.picture === "mix" ? CONTAINERS[cutaways.indexOf(beat) % CONTAINERS.length] : STYLE.picture ?? "card");
function drawPicture(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.4, 0.3);
  if (a <= 0) return;
  const kind = containerOf(beat), grow = 1 + 0.05 * clamp((t - beat.start) / Math.max(0.1, beat.end - beat.start));
  // the picture fills its container, cropped rather than squeezed; a slow push-in keeps it alive
  const fill = (x, y, w, h) => { const k = Math.max(w / image.width, h / image.height) * grow; ctx.drawImage(image, x + w / 2 - (image.width * k) / 2, y + h / 2 - (image.height * k) / 2, image.width * k, image.height * k); };
  ctx.save(); ctx.globalAlpha = a;
  if (kind === "polaroid") {
    // a printed photo: a white border, wider at the foot, a little askew, settling as it lands
    const w = W * 0.74, h = H * 0.3, tilt = (cutaways.indexOf(beat) % 2 ? 3.5 : -3.5) * (1 + 1.2 * (1 - ease((t - beat.start) / 0.5)));
    ctx.translate(W / 2, H * 0.225 - (1 - a) * 70); ctx.rotate(tilt * Math.PI / 180);
    ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 44; ctx.shadowOffsetY = 18; ctx.fillStyle = "#fbfaf6"; ctx.fillRect(-w / 2, -h / 2, w, h); ctx.shadowColor = "transparent";
    const pad = w * 0.035; ctx.beginPath(); ctx.rect(-w / 2 + pad, -h / 2 + pad, w - 2 * pad, h - pad - h * 0.15); ctx.clip(); fill(-w / 2 + pad, -h / 2 + pad, w - 2 * pad, h - pad - h * 0.15);
  } else if (kind === "circle") {
    // a round window with a ring in the accent colour
    const r = W * 0.27, cx = W / 2, cy = H * 0.2 - (1 - a) * 60, pop = 0.7 + 0.3 * back((t - beat.start) / 0.45);
    ctx.translate(cx, cy); ctx.scale(pop, pop);
    ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 40; ctx.shadowOffsetY = 14; ctx.beginPath(); ctx.arc(0, 0, r + 12, 0, Math.PI * 2); ctx.fillStyle = ACCENT; ctx.fill(); ctx.shadowColor = "transparent";
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.clip(); fill(-r, -r, 2 * r, 2 * r);
  } else {
    // "card": a rounded card with air around it; "edge": the picture runs to the top and the sides of the frame
    const edge = kind === "edge", x = edge ? 0 : W * 0.05, w = edge ? W : W * 0.9, h = H * (edge ? 0.36 : 0.3), y = (edge ? 0 : H * 0.07) - (1 - a) * 60, r = edge ? 0 : 36;
    ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 40; ctx.shadowOffsetY = 14; ctx.fillStyle = "#000";
    ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.fill(); ctx.shadowColor = "transparent";
    ctx.save(); ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.clip(); fill(x, y, w, h); ctx.restore();
    if (!edge) { ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.stroke(); }
  }
  ctx.restore();
}

// ---------- a picture over the whole frame: a floor plan or a render, while the voice goes on ----------
const edgeColour = new Map(), lightPictures = new Set(); // on a light picture (a plan on white) the subtitles turn dark
function drawFull(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.22, 0.22);
  if (a <= 0) return;
  if (!edgeColour.has(beat.file)) {
    // The frame around the picture takes the picture's own edge colour, so a plan on white stays on white
    const probe = createCanvas(1, 1), p = probe.getContext("2d");
    p.drawImage(image, 2, 2, 1, 1, 0, 0, 1, 1);
    const [r, g, b] = p.getImageData(0, 0, 1, 1).data; edgeColour.set(beat.file, `rgb(${r},${g},${b})`);
    if (0.3 * r + 0.59 * g + 0.11 * b > 170) lightPictures.add(beat.file);
  }
  // A picture close to the frame's shape fills it; anything else is shown whole. A slow push-in keeps it alive.
  const fits = Math.abs(image.width / image.height - W / H) < 0.12;
  const grow = 1 + 0.04 * clamp((t - beat.start) / Math.max(0.1, beat.end - beat.start));
  const k = (fits ? Math.max(W / image.width, H / image.height) : Math.min((W * 0.94) / image.width, (H * 0.6) / image.height)) * grow;
  ctx.save();
  ctx.globalAlpha = a;
  if (fits || lightPictures.has(beat.file)) { ctx.fillStyle = edgeColour.get(beat.file); ctx.fillRect(0, 0, W, H); }
  else {
    // A wide photo sits on a darkened, enlarged copy of itself instead of a flat colour
    const cover = Math.max(W / image.width, H / image.height) * 1.08;
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = a * 0.38; ctx.drawImage(image, W / 2 - (image.width * cover) / 2, H / 2 - (image.height * cover) / 2, image.width * cover, image.height * cover); ctx.globalAlpha = a;
  }
  const left = W / 2 - (image.width * k) / 2, top = (fits ? H / 2 : H * 0.36) - (image.height * k) / 2;
  ctx.drawImage(image, left, top, image.width * k, image.height * k);
  // The room being spoken of lights up on the plan: the accent colour laid over it, with a firm outline
  for (const mark of beat.marks ?? []) {
    const lit = presence(t, mark.start, mark.end, 0.3, 0.2);
    if (lit <= 0) continue;
    ctx.beginPath();
    mark.shape.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](left + x * image.width * k, top + y * image.height * k));
    ctx.closePath();
    ctx.globalAlpha = a * lit * 0.42; ctx.fillStyle = ACCENT; ctx.fill();
    ctx.globalAlpha = a * lit; ctx.strokeStyle = ACCENT; ctx.lineWidth = 7; ctx.lineJoin = "round"; ctx.shadowColor = "rgba(0,0,0,0.35)"; ctx.shadowBlur = 10; ctx.stroke();
    ctx.shadowBlur = 0;
  }
  ctx.restore();
}

// ---------- a floor plan: on a card, with the camera moving to the room being spoken of ----------
const lerp = (a, b, k) => a + (b - a) * k;
const titled = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const planLayer = createCanvas(W, H), planCtx = planLayer.getContext("2d");
let planKey = "";
function drawPlan(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.25, 0.22);
  if (a <= 0) return;
  // Most of the time nothing on the plan moves: the camera has arrived and the room is lit. Such a frame is painted once
  // and laid down again for as long as it stays the same, which is most of the plan's time on screen.
  const marks0 = beat.marks ?? [], index0 = marks0.reduce((last, m, i) => (t >= m.start ? i : last), -1), now0 = marks0[index0];
  const moving = now0 ? Math.min(1, (t - now0.start) / 0.7) : 1;
  const key = [beat.id, a.toFixed(3), index0, moving.toFixed(4), now0 ? presence(t, now0.start, now0.end, 0.35, 0.2).toFixed(3) : "", now0 ? presence(t, now0.start + 0.15, now0.end, 0.35, 0.2).toFixed(3) : ""].join("|");
  if (key !== planKey) { planCtx.clearRect(0, 0, W, H); paintPlan(planCtx, beat, t, image, a); planKey = key; }
  ctx.drawImage(planLayer, 0, 0);
}
function paintPlan(ctx, beat, t, image, a) {
  const font = (size, weight = WEIGHT) => { ctx.font = `${weight} ${size}px ${FONT}`; };
  ctx.save();
  ctx.globalAlpha = a;
  const paper = ctx.createLinearGradient(0, 0, 0, H); paper.addColorStop(0, "#f6f3ec"); paper.addColorStop(1, "#e6e0d4");
  ctx.fillStyle = paper; ctx.fillRect(0, 0, W, H);
  // The card the plan lies on
  const card = { x: W * 0.045, y: H * 0.07, w: W * 0.91, h: H * 0.56 }, round = 44;
  ctx.shadowColor = "rgba(60,45,20,0.22)"; ctx.shadowBlur = 50; ctx.shadowOffsetY = 18;
  ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.roundRect(card.x, card.y, card.w, card.h, round); ctx.fill();
  ctx.shadowColor = "transparent"; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
  ctx.beginPath(); ctx.roundRect(card.x, card.y, card.w, card.h, round); ctx.clip();
  // The camera: the whole plan at first, then towards each room as it is named
  const marks = beat.marks ?? [], fit = Math.min((card.w - 60) / image.width, (card.h - 60) / image.height);
  const view = (mark) => {
    if (!mark) {
      // the whole drawing, without the empty paper around it
      const [x0, y0, x1, y1] = beat.extent ?? [0, 0, 1, 1];
      return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, zoom: clamp(Math.min((card.w - 90) / ((x1 - x0) * image.width * fit), (card.h - 90) / ((y1 - y0) * image.height * fit)), 1, 1.6) };
    }
    const every = [mark.shape, ...(mark.more ?? [])].flat(), xs = every.map((p) => p[0]), ys = every.map((p) => p[1]);   // one room, or the several spoken of together
    const bw = (Math.max(...xs) - Math.min(...xs)) * image.width * fit, bh = (Math.max(...ys) - Math.min(...ys)) * image.height * fit;
    const zoom = clamp(Math.min((card.w * 0.5) / bw, (card.h * 0.5) / bh), home.zoom * 1.1, Math.max(1.9, home.zoom * 1.3));
    // halfway between the room and the middle of the plan: the room comes closer without the rest being lost
    return { x: lerp(home.x, (Math.max(...xs) + Math.min(...xs)) / 2, 0.75), y: lerp(home.y, (Math.max(...ys) + Math.min(...ys)) / 2, 0.75), zoom };
  };
  const home = view();
  const index = marks.reduce((last, m, i) => (t >= m.start ? i : last), -1), now = marks[index];
  const from = view(marks[index - 1]), to = view(now), k = now ? ease((t - now.start) / 0.7) : 1;
  const cam = { x: lerp(from.x, to.x, k), y: lerp(from.y, to.y, k), zoom: lerp(from.zoom, to.zoom, k) };
  const scale = fit * cam.zoom, pw = image.width * scale, ph = image.height * scale;
  // keep the plan inside the card: the camera does not look past its edge
  const left = clamp(card.x + card.w / 2 - cam.x * pw, card.x + card.w - 30 - pw, card.x + 30) , top = clamp(card.y + card.h / 2 - cam.y * ph, card.y + card.h - 30 - ph, card.y + 30);
  const px = pw <= card.w - 60 ? card.x + (card.w - pw) / 2 : left, py = ph <= card.h - 60 ? card.y + (card.h - ph) / 2 : top;
  ctx.drawImage(image, px, py, pw, ph);
  const outline = (shape) => { shape.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](px + x * pw, py + y * ph)); ctx.closePath(); };
  const trace = (mark) => { ctx.beginPath(); [mark.shape, ...(mark.more ?? [])].forEach(outline); };
  if (now) {
    const lit = presence(t, now.start, now.end, 0.35, 0.2);
    // The rest of the plan steps back, the room keeps its ink and takes the accent colour
    ctx.save(); ctx.beginPath(); ctx.rect(card.x, card.y, card.w, card.h); [now.shape, ...(now.more ?? [])].forEach(outline);
    ctx.globalAlpha = a * lit * 0.55; ctx.fillStyle = "#fff"; ctx.fill("evenodd"); ctx.restore();
    trace(now); ctx.globalAlpha = a * lit * 0.3; ctx.fillStyle = ACCENT; ctx.fill();
    trace(now); ctx.globalAlpha = a * lit; ctx.strokeStyle = ACCENT; ctx.lineWidth = 9; ctx.lineJoin = "round"; ctx.shadowColor = "rgba(0,0,0,0.3)"; ctx.shadowBlur = 14; ctx.stroke(); ctx.shadowBlur = 0;
  }
  ctx.restore();
  // The room's name on a plate at the foot of the card
  if (now && now.name) {
    const shown = presence(t, now.start + 0.15, now.end, 0.35, 0.2);
    if (shown > 0) {
      ctx.save(); ctx.globalAlpha = a * shown; font(46);
      const text = titled(now.name), tw = ctx.measureText(text).width, bx = card.x + 34, by = card.y + card.h - 34 - 84 + (1 - shown) * 24;
      ctx.shadowColor = "rgba(0,0,0,0.25)"; ctx.shadowBlur = 18; ctx.shadowOffsetY = 6;
      ctx.fillStyle = "#111"; ctx.beginPath(); ctx.roundRect(bx, by, tw + 64, 84, 42); ctx.fill();
      ctx.shadowColor = "transparent"; ctx.fillStyle = ACCENT; ctx.textBaseline = "middle"; ctx.fillText(text, bx + 32, by + 44);
      ctx.restore();
    }
  }
}

// ---------- overlays: what makes the video livelier while the speaker is in the frame ----------
// A number that counts up, a sticker with a few words and an emoji, a list whose items arrive as they are named.
// They stand beside the head, left and right in turn, above the subtitles and below the title's place.
const EMOJI = "'Noto Color Emoji'";
const plate = (g, x, y, w, h, r, fill) => { g.beginPath(); g.roundRect(x, y, w, h, r); g.fillStyle = fill; g.fill(); };
function fitted(g, text, size, most, weight = WEIGHT) { do { g.font = `${weight} ${size}px ${FONT}`; size -= 2; } while (g.measureText(text).width > most && size > 24); return size + 2; }
function drawOverlay(o, t) {
  const a = presence(t, o.start, o.end, 0.22, 0.25);
  if (a <= 0) return;
  const left = o.side === "left", pop = 0.6 + 0.4 * back((t - o.start) / 0.42);
  ctx.save(); ctx.globalAlpha = a; ctx.textBaseline = "middle"; ctx.textAlign = "left";
  if (o.kind === "sticker") {
    // a paper sticker: white, a little askew, with a soft shadow
    const size = fitted(ctx, o.text, 66, W * 0.42), tw = ctx.measureText(o.text).width, icon = o.icon ? size * 1.25 : 0, w = tw + icon + 70, h = size * 1.9;
    ctx.translate(left ? W * 0.07 + w / 2 : W * 0.93 - w / 2, H * 0.185); ctx.rotate((left ? -5 : 4) * Math.PI / 180 * (1 + 0.6 * (1 - Math.min(1, (t - o.start) / 0.5)))); ctx.scale(pop, pop);
    ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 26; ctx.shadowOffsetY = 10; plate(ctx, -w / 2, -h / 2, w, h, h * 0.32, "#fff"); ctx.shadowColor = "transparent";
    ctx.lineWidth = 7; ctx.strokeStyle = ACCENT; ctx.beginPath(); ctx.roundRect(-w / 2 + 9, -h / 2 + 9, w - 18, h - 18, h * 0.25); ctx.stroke();
    if (o.icon) { ctx.font = `${size * 1.02}px ${EMOJI}`; ctx.fillText(o.icon, -w / 2 + 30, 4); }
    ctx.font = `${WEIGHT} ${size}px ${FONT}`; ctx.fillStyle = "#15171c"; ctx.fillText(o.text, -w / 2 + 35 + icon, 2);
  } else if (o.kind === "number") {
    // the figure itself, large and in the accent colour, counting up to what was said
    const goal = /\d-\d/.test(String(o.value)) ? NaN : parseFloat(String(o.value).replace(",", ".")), k = ease((t - o.start) / 0.75), whole = Number.isInteger(goal) && !/[.,]/.test(String(o.value));
    const shown = !isFinite(goal) ? String(o.value).replace("-", "–") : whole ? String(Math.round(goal * k)) : (goal * k).toFixed(1).replace(".", ",");
    const size = 190; ctx.font = `${WEIGHT} ${size}px ${FONT}`; const full = ctx.measureText(isFinite(goal) ? (whole ? String(goal) : goal.toFixed(1)) : shown).width;
    ctx.font = `${WEIGHT} ${size * 0.4}px ${FONT}`; const uw = o.unit ? ctx.measureText(o.unit).width + 18 : 0, w = full + uw;
    ctx.translate(left ? W * 0.08 + w / 2 : W * 0.92 - w / 2, H * 0.175); ctx.scale(pop, pop);
    ctx.font = `${WEIGHT} ${size}px ${FONT}`; ctx.lineJoin = "round"; ctx.lineWidth = 22; ctx.strokeStyle = "rgba(0,0,0,0.78)"; ctx.shadowColor = "rgba(0,0,0,0.5)"; ctx.shadowBlur = 24; ctx.shadowOffsetY = 8;
    ctx.strokeText(shown, -w / 2, 0); ctx.shadowColor = "transparent"; ctx.fillStyle = ACCENT; ctx.fillText(shown, -w / 2, 0);
    if (o.unit) { ctx.font = `${WEIGHT} ${size * 0.4}px ${FONT}`; ctx.lineWidth = 14; ctx.strokeText(o.unit, -w / 2 + full + 18, size * 0.2); ctx.fillStyle = "#fff"; ctx.fillText(o.unit, -w / 2 + full + 18, size * 0.2); }
    if (o.caption) {
      const cs = fitted(ctx, o.caption, 40, W * 0.42), cw = ctx.measureText(o.caption).width + 44, shownC = presence(t, o.start + 0.25, o.end, 0.3, 0.2);
      ctx.globalAlpha = a * shownC; plate(ctx, left ? -w / 2 : w / 2 - cw, size * 0.62, cw, cs * 1.8, cs * 0.9, "rgba(17,17,17,0.86)");
      ctx.font = `${WEIGHT} ${cs}px ${FONT}`; ctx.fillStyle = "#fff"; ctx.fillText(o.caption, (left ? -w / 2 : w / 2 - cw) + 22, size * 0.62 + cs * 0.93);
    }
  } else if (o.kind === "list") {
    // items come in one by one, each when it is named
    const x = left ? W * 0.06 : W * 0.5, row = 92; let y = H * 0.13;
    if (o.title) { const ts = fitted(ctx, o.title, 44, W * 0.4), tw = ctx.measureText(o.title).width + 48; plate(ctx, x, y - 38, tw, 76, 38, ACCENT); ctx.fillStyle = "#111"; ctx.fillText(o.title, x + 24, y + 2); y += row; }
    for (const item of o.items ?? []) {
      const here = ease((t - item.start) / 0.3);
      if (here > 0) {
        ctx.save(); ctx.globalAlpha = a * here; ctx.translate((1 - here) * -40, 0);
        const is = fitted(ctx, item.text, 46, W * 0.36), iw = ctx.measureText(item.text).width + 104;
        ctx.shadowColor = "rgba(0,0,0,0.4)"; ctx.shadowBlur = 18; ctx.shadowOffsetY = 6; plate(ctx, x, y - 38, iw, 76, 38, "#fff"); ctx.shadowColor = "transparent";
        ctx.beginPath(); ctx.arc(x + 40, y, 22, 0, Math.PI * 2); ctx.fillStyle = ACCENT; ctx.fill();
        ctx.strokeStyle = "#111"; ctx.lineWidth = 6; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.beginPath(); ctx.moveTo(x + 30, y + 1); ctx.lineTo(x + 38, y + 9); ctx.lineTo(x + 51, y - 8); ctx.stroke();
        ctx.font = `${WEIGHT} ${is}px ${FONT}`; ctx.fillStyle = "#15171c"; ctx.fillText(item.text, x + 78, y + 2);
        ctx.restore();
      }
      y += row;
    }
  }
  ctx.restore();
}

// ---------- title: the accent colour with a glow, a small overshoot on the way in and a light sweep across it ----------
const titleLayer = createCanvas(W, Math.round(H * 0.12));
const titleCtx = titleLayer.getContext("2d");
function drawTitle(beat, t) {
  const a = presence(t, beat.start, beat.end, 0.45, 0.3);
  if (a <= 0 || !beat.text) return;
  const size = Math.min(W * 0.1, (W * 0.86) / (beat.text.length * 0.6));
  const tw = titleLayer.width, th = titleLayer.height;
  titleCtx.clearRect(0, 0, tw, th);
  titleCtx.font = `${WEIGHT} ${size}px ${FONT}`;
  titleCtx.textAlign = "center"; titleCtx.textBaseline = "middle";
  titleCtx.fillStyle = ACCENT;
  titleCtx.fillText(beat.text, tw / 2, th / 2);
  // The sweep: a soft white band crossing the letters once, a moment after the title lands
  const sweep = (t - beat.start - 0.5) / 0.9;
  if (sweep > 0 && sweep < 1) {
    const cx = tw * (0.05 + 0.9 * sweep), band = tw * 0.16;
    const light = titleCtx.createLinearGradient(cx - band, 0, cx + band, 0);
    light.addColorStop(0, "rgba(255,255,255,0)"); light.addColorStop(0.5, "rgba(255,255,255,0.95)"); light.addColorStop(1, "rgba(255,255,255,0)");
    titleCtx.globalCompositeOperation = "source-atop";
    titleCtx.fillStyle = light; titleCtx.fillRect(0, 0, tw, th);
    titleCtx.globalCompositeOperation = "source-over";
  }
  const scale = 0.85 + 0.15 * back((t - beat.start) / 0.45);
  const cy = H * 0.115;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.translate(W / 2, cy); ctx.scale(scale, scale);
  ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
  ctx.drawImage(titleLayer, -tw / 2, -th / 2);
  if (STYLE.title_glow !== false) {
    ctx.shadowColor = ACCENT; ctx.shadowBlur = 34; ctx.shadowOffsetY = 0; ctx.globalAlpha = a * 0.55;
    ctx.drawImage(titleLayer, -tw / 2, -th / 2);
  }
  ctx.restore();
}

// ---------- subtitles: a short phrase at a time; each word turns solid as it is spoken, key words in the accent colour ----------
const SUB_SIZE = Math.round(W * ({ s: 0.072, m: 0.088, l: 0.104 }[STYLE.subtitle_size] ?? 0.088)), SUB_GAP = SUB_SIZE * 0.26, SUB_MAX = W * 0.86;
const SUB_Y = STYLE.subtitle_place === "middle" ? 0.56 : 0.715;
const KARAOKE = STYLE.karaoke !== false;
const HOT = 1.16; // key words are this much larger
function layout(words) {
  const rows = [[]]; let used = 0;
  for (const word of words) {
    font(SUB_SIZE * (word.hot ? HOT : 1));
    const w = ctx.measureText(word.text).width;
    if (rows.at(-1).length && used + SUB_GAP + w > SUB_MAX) { rows.push([]); used = 0; }
    rows.at(-1).push({ word, w, x: used + (rows.at(-1).length ? SUB_GAP : 0) });
    used = rows.at(-1).at(-1).x + w;
    rows.at(-1).width = used;
  }
  return rows;
}
const laidOut = new Map(timeline.lines.map((line) => [line, layout(line.words)]));

const sprites = new Map();
function drawSubtitle(line, t, onLight = false) {
  const a = Math.min(ease((t - line.start + 0.06) / 0.14), ease((line.end - t) / 0.12));
  if (a <= 0) return;
  const rows = laidOut.get(line), rowHeight = SUB_SIZE * 1.16;
  const top = H * SUB_Y - (rows.length * rowHeight) / 2 + (1 - a) * 14;
  font(SUB_SIZE);
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  rows.forEach((row, index) => {
    const left = W / 2 - row.width / 2, y = top + rowHeight * (index + 0.5);
    for (const { word, w, x } of row) {
      const said = !KARAOKE || t >= word.start - 0.04;
      // A small pop as the word is spoken
      const pop = KARAOKE && said ? 1 + 0.07 * (1 - ease((t - word.start) / 0.22)) : 1;
      const hot = word.hot && said, dark = onLight && !hot;
      // A word with its outline and shadow is painted once for each look it has and laid down from then on:
      // the outline and the blurred shadow are what make drawing text slow
      const look = `${word.text}|${word.hot ? 1 : 0}|${hot ? 1 : 0}|${dark ? 1 : 0}|${onLight ? 1 : 0}`;
      let sprite = sprites.get(look);
      if (!sprite) {
        const size = SUB_SIZE * (word.hot ? HOT : 1), pad = Math.ceil(SUB_SIZE * 0.5);
        sprite = createCanvas(Math.ceil(w) + 2 * pad, Math.ceil(size * 1.3) + 2 * pad); sprite.pad = pad;
        const g = sprite.getContext("2d");
        g.font = `${WEIGHT} ${size}px ${FONT}`; g.textAlign = "left"; g.textBaseline = "middle";
        g.lineJoin = "round"; g.lineWidth = SUB_SIZE * 0.14; g.strokeStyle = dark ? "rgba(255,255,255,0.85)" : onLight ? "rgba(0,0,0,0.85)" : "rgba(0,0,0,0.5)";
        g.shadowColor = dark ? "rgba(255,255,255,0.7)" : "rgba(0,0,0,0.6)"; g.shadowBlur = 16; g.shadowOffsetY = dark ? 0 : 5;
        g.strokeText(word.text, pad, sprite.height / 2);
        g.shadowColor = "transparent";
        g.fillStyle = hot ? ACCENT : dark ? "#16181d" : "#ffffff";
        g.fillText(word.text, pad, sprite.height / 2);
        sprites.set(look, sprite);
      }
      ctx.save();
      // on whole pixels, so that the painted word is laid down as sharp as it was painted
      ctx.translate(Math.round(left + x + w / 2), Math.round(y)); ctx.scale(pop, pop);
      ctx.globalAlpha = a * (said ? 1 : 0.5);
      ctx.drawImage(sprite, -Math.round(w / 2) - sprite.pad, -Math.round(sprite.height / 2));
      ctx.restore();
    }
  });
}

// ---------- one frame ----------
const parts = {};
function drawFrame(t) {
  // Backdrops are composited by ffmpeg behind the speaker; here only pictures that sit on top are drawn
  const pictureNow = timeline.beats.filter((b) => b.kind === "cutaway" && t >= b.start - 0.05 && t <= b.end + 0.05);
  const fullNow = timeline.beats.filter((b) => b.kind === "full" && t >= b.start - 0.05 && t <= b.end + 0.05);
  const titles = timeline.beats.filter((b) => b.kind === "title" && t >= b.start && t <= b.end);
  const line = timeline.lines.find((l) => t >= l.start - 0.06 && t < l.end);
  const overlays = (timeline.overlays ?? []).filter((o) => t >= o.start && t <= o.end);
  if (!pictureNow.length && !fullNow.length && !titles.length && !line && !overlays.length) return false;
  ctx.clearRect(0, 0, W, H);
  const clock = (what, work) => { if (!process.env.REEL_PROFILE) return work(); const a = performance.now(); work(); parts[what] = (parts[what] ?? 0) + performance.now() - a; };
  clock("pictures", () => { fullNow.forEach((beat) => (beat.plan ? drawPlan(beat, t) : drawFull(beat, t))); pictureNow.forEach((beat) => drawPicture(beat, t)); });
  clock("titles", () => titles.forEach((beat) => drawTitle(beat, t)));
  clock("overlays", () => overlays.forEach((o) => drawOverlay(o, t)));
  clock("subtitles", () => { if (line) drawSubtitle(line, t, fullNow.some((b) => t >= b.start + 0.1 && t <= b.end - 0.1 && (b.plan || lightPictures.has(b.file)))); });
  return true;
}

// Stills, for looking at a design without building the video:  node render.mjs timeline.json --stills 12.5,31 out/still
if (process.argv[3] === "--stills") {
  const { writeFileSync } = await import("node:fs");
  for (const t of process.argv[4].split(",").map(Number)) {
    if (!drawFrame(t)) ctx.clearRect(0, 0, W, H);
    writeFileSync(`${process.argv[5]}-${t.toFixed(1)}.png`, canvas.toBuffer("image/png"));
  }
  process.exit(0);
}

// ---------- frames ----------
const PROFILE = !!process.env.REEL_PROFILE, spent = { draw: 0, read: 0, write: 0 };   // REEL_PROFILE=1 says where the time went
const frames = Math.ceil(timeline.seconds * fps);
const blank = Buffer.alloc(W * H * 4);
const write = (buffer) => new Promise((resolve) => (process.stdout.write(buffer) ? resolve() : process.stdout.once("drain", resolve)));
process.stdout.on("error", () => process.exit(0)); // ffmpeg has all it needs

for (let frame = 0; frame < frames; frame++) {
  const t = frame / fps, t0 = PROFILE ? performance.now() : 0;
  if (!drawFrame(t)) { await write(blank); continue; }
  if (PROFILE) spent.draw += performance.now() - t0;
  const t1 = PROFILE ? performance.now() : 0;
  const pixels = ctx.getImageData(0, 0, W, H).data;
  if (PROFILE) spent.read += performance.now() - t1;
  const t2 = PROFILE ? performance.now() : 0;
  await write(Buffer.from(pixels.buffer, pixels.byteOffset, pixels.byteLength));
  if (PROFILE) spent.write += performance.now() - t2;
}
if (PROFILE) console.error(`frames ${frames}: drawing ${(spent.draw / 1000).toFixed(1)} s, reading pixels ${(spent.read / 1000).toFixed(1)} s, writing ${(spent.write / 1000).toFixed(1)} s; of the drawing: ${Object.entries(parts).map(([k, v]) => `${k} ${(v / 1000).toFixed(1)} s`).join(", ")}`);
