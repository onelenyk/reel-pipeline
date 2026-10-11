// Draws the graphics layer of a video (subtitles, titles, pictures) and writes it to standard output
// as raw RGBA frames with transparency. ffmpeg lays these over the footage.
//
//   node render.mjs timeline.json > frames.rgba
//
// The timeline is already resolved to seconds of the finished video (see engine/project.py: resolve).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire("/opt/renderer/");
const { createCanvas, loadImage } = require("@napi-rs/canvas");

const timeline = JSON.parse(readFileSync(process.argv[2], "utf8"));
const { width: W, height: H, fps } = timeline;
const STYLE = timeline.style ?? {};
const ACCENT = STYLE.accent ?? "#ffd60a";
const FONT = "Inter, 'Noto Sans', sans-serif";

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const ease = (k) => 1 - Math.pow(1 - clamp(k), 3);
const back = (k) => { k = clamp(k); return 1 + 2.7 * Math.pow(k - 1, 3) + 1.7 * Math.pow(k - 1, 2); };
/** 0 → 1 while something enters, 1 while it stays, 1 → 0 while it leaves. */
const presence = (t, start, end, enter = 0.3, leave = 0.25) => Math.min(ease((t - start) / enter), ease((end - t) / leave));

const canvas = createCanvas(W, H);
const ctx = canvas.getContext("2d");
const font = (size, weight = 800) => { ctx.font = `${weight} ${size}px ${FONT}`; };

const pictures = new Map();
for (const beat of timeline.beats) {
  if ((beat.kind === "cutaway" || beat.kind === "full") && beat.file && !pictures.has(beat.file)) pictures.set(beat.file, await loadImage(beat.file).catch(() => null));
}

// ---------- pictures: a card in the upper part of the frame; the speaker stays visible below ----------
function drawPicture(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.4, 0.3);
  if (a <= 0) return;
  // "card": a rounded card with air around it; "edge": the picture runs to the top and the sides of the frame
  const edge = STYLE.picture === "edge";
  const x = edge ? 0 : W * 0.05, w = edge ? W : W * 0.9, h = H * (edge ? 0.36 : 0.3), y = (edge ? 0 : H * 0.07) - (1 - a) * 60, r = edge ? 0 : 36;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.shadowColor = "rgba(0,0,0,0.45)"; ctx.shadowBlur = 40; ctx.shadowOffsetY = 14;
  ctx.fillStyle = "#000";
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.fill();
  ctx.shadowColor = "transparent";
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.clip();
  // Fill the card, cropping the picture rather than squeezing it; a slow push-in keeps it alive
  const grow = 1 + 0.05 * clamp((t - beat.start) / Math.max(0.1, beat.end - beat.start));
  const k = Math.max(w / image.width, h / image.height) * grow;
  ctx.drawImage(image, x + w / 2 - (image.width * k) / 2, y + h / 2 - (image.height * k) / 2, image.width * k, image.height * k);
  ctx.restore();
  if (edge) return;
  ctx.save();
  ctx.globalAlpha = a;
  ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.stroke();
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
function drawPlan(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.25, 0.22);
  if (a <= 0) return;
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
      ctx.save(); ctx.globalAlpha = a * shown; font(46, 800);
      const text = titled(now.name), tw = ctx.measureText(text).width, bx = card.x + 34, by = card.y + card.h - 34 - 84 + (1 - shown) * 24;
      ctx.shadowColor = "rgba(0,0,0,0.25)"; ctx.shadowBlur = 18; ctx.shadowOffsetY = 6;
      ctx.fillStyle = "#111"; ctx.beginPath(); ctx.roundRect(bx, by, tw + 64, 84, 42); ctx.fill();
      ctx.shadowColor = "transparent"; ctx.fillStyle = ACCENT; ctx.textBaseline = "middle"; ctx.fillText(text, bx + 32, by + 44);
      ctx.restore();
    }
  }
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
  titleCtx.font = `800 ${size}px ${FONT}`;
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
      ctx.save();
      font(SUB_SIZE * (word.hot ? HOT : 1));
      ctx.translate(left + x + w / 2, y); ctx.scale(pop, pop);
      ctx.globalAlpha = a * (said ? 1 : 0.5);
      const hot = word.hot && said, dark = onLight && !hot;
      ctx.lineJoin = "round"; ctx.lineWidth = SUB_SIZE * 0.14; ctx.strokeStyle = dark ? "rgba(255,255,255,0.85)" : onLight ? "rgba(0,0,0,0.85)" : "rgba(0,0,0,0.5)";
      ctx.shadowColor = dark ? "rgba(255,255,255,0.7)" : "rgba(0,0,0,0.6)"; ctx.shadowBlur = 16; ctx.shadowOffsetY = dark ? 0 : 5;
      ctx.strokeText(word.text, -w / 2, 0);
      ctx.shadowColor = "transparent";
      ctx.fillStyle = hot ? ACCENT : dark ? "#16181d" : "#ffffff";
      ctx.fillText(word.text, -w / 2, 0);
      ctx.restore();
    }
  });
}

// ---------- one frame ----------
function drawFrame(t) {
  // Backdrops are composited by ffmpeg behind the speaker; here only pictures that sit on top are drawn
  const pictureNow = timeline.beats.filter((b) => b.kind === "cutaway" && t >= b.start - 0.05 && t <= b.end + 0.05);
  const fullNow = timeline.beats.filter((b) => b.kind === "full" && t >= b.start - 0.05 && t <= b.end + 0.05);
  const titles = timeline.beats.filter((b) => b.kind === "title" && t >= b.start && t <= b.end);
  const line = timeline.lines.find((l) => t >= l.start - 0.06 && t < l.end);
  if (!pictureNow.length && !fullNow.length && !titles.length && !line) return false;
  ctx.clearRect(0, 0, W, H);
  fullNow.forEach((beat) => (beat.plan ? drawPlan(beat, t) : drawFull(beat, t)));
  pictureNow.forEach((beat) => drawPicture(beat, t));
  titles.forEach((beat) => drawTitle(beat, t));
  if (line) drawSubtitle(line, t, fullNow.some((b) => t >= b.start + 0.1 && t <= b.end - 0.1 && (b.plan || lightPictures.has(b.file))));
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
const frames = Math.ceil(timeline.seconds * fps);
const blank = Buffer.alloc(W * H * 4);
const write = (buffer) => new Promise((resolve) => (process.stdout.write(buffer) ? resolve() : process.stdout.once("drain", resolve)));
process.stdout.on("error", () => process.exit(0)); // ffmpeg has all it needs

for (let frame = 0; frame < frames; frame++) {
  const t = frame / fps;
  if (!drawFrame(t)) { await write(blank); continue; }
  const pixels = ctx.getImageData(0, 0, W, H).data;
  await write(Buffer.from(pixels.buffer, pixels.byteOffset, pixels.byteLength));
}
