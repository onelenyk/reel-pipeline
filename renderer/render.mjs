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
const ACCENT = timeline.style?.accent ?? "#ffd60a";
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
  if (beat.file && !pictures.has(beat.file)) pictures.set(beat.file, await loadImage(beat.file).catch(() => null));
}

// ---------- pictures: a card in the upper part of the frame; the speaker stays visible below ----------
function drawPicture(beat, t) {
  const image = pictures.get(beat.file);
  if (!image) return;
  const a = presence(t, beat.start, beat.end, 0.4, 0.3);
  if (a <= 0) return;
  const x = W * 0.05, w = W * 0.9, h = H * 0.3, y = H * 0.07 - (1 - a) * 60, r = 36;
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
  ctx.save();
  ctx.globalAlpha = a;
  ctx.strokeStyle = "rgba(255,255,255,0.22)"; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.stroke();
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
  ctx.shadowColor = ACCENT; ctx.shadowBlur = 34; ctx.shadowOffsetY = 0; ctx.globalAlpha = a * 0.55;
  ctx.drawImage(titleLayer, -tw / 2, -th / 2);
  ctx.restore();
}

// ---------- subtitles: a short phrase at a time; each word turns solid as it is spoken, key words in the accent colour ----------
const SUB_SIZE = Math.round(W * 0.088), SUB_GAP = SUB_SIZE * 0.26, SUB_MAX = W * 0.86;
function layout(words) {
  font(SUB_SIZE);
  const rows = [[]]; let used = 0;
  for (const word of words) {
    const w = ctx.measureText(word.text).width;
    if (rows.at(-1).length && used + SUB_GAP + w > SUB_MAX) { rows.push([]); used = 0; }
    rows.at(-1).push({ word, w, x: used + (rows.at(-1).length ? SUB_GAP : 0) });
    used = rows.at(-1).at(-1).x + w;
    rows.at(-1).width = used;
  }
  return rows;
}
const laidOut = new Map(timeline.lines.map((line) => [line, layout(line.words)]));

function drawSubtitle(line, t) {
  const a = Math.min(ease((t - line.start + 0.06) / 0.14), ease((line.end - t) / 0.12));
  if (a <= 0) return;
  const rows = laidOut.get(line), rowHeight = SUB_SIZE * 1.16;
  const top = H * 0.715 - (rows.length * rowHeight) / 2 + (1 - a) * 14;
  font(SUB_SIZE);
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  rows.forEach((row, index) => {
    const left = W / 2 - row.width / 2, y = top + rowHeight * (index + 0.5);
    for (const { word, w, x } of row) {
      const said = t >= word.start - 0.04;
      // A small pop as the word is spoken
      const pop = said ? 1 + 0.07 * (1 - ease((t - word.start) / 0.22)) : 1;
      ctx.save();
      ctx.translate(left + x + w / 2, y); ctx.scale(pop, pop);
      ctx.globalAlpha = a * (said ? 1 : 0.5);
      ctx.lineJoin = "round"; ctx.lineWidth = SUB_SIZE * 0.14; ctx.strokeStyle = "rgba(0,0,0,0.5)";
      ctx.shadowColor = "rgba(0,0,0,0.6)"; ctx.shadowBlur = 16; ctx.shadowOffsetY = 5;
      ctx.strokeText(word.text, -w / 2, 0);
      ctx.shadowColor = "transparent";
      ctx.fillStyle = word.hot && said ? ACCENT : "#ffffff";
      ctx.fillText(word.text, -w / 2, 0);
      ctx.restore();
    }
  });
}

// ---------- frames ----------
const frames = Math.ceil(timeline.seconds * fps);
const blank = Buffer.alloc(W * H * 4);
const write = (buffer) => new Promise((resolve) => (process.stdout.write(buffer) ? resolve() : process.stdout.once("drain", resolve)));
process.stdout.on("error", () => process.exit(0)); // ffmpeg has all it needs

for (let frame = 0; frame < frames; frame++) {
  const t = frame / fps;
  const pictureNow = timeline.beats.filter((b) => (b.kind === "cutaway" || b.kind === "backdrop") && t >= b.start - 0.05 && t <= b.end + 0.05);
  const titles = timeline.beats.filter((b) => b.kind === "title" && t >= b.start && t <= b.end);
  const line = timeline.lines.find((l) => t >= l.start - 0.06 && t < l.end);
  if (!pictureNow.length && !titles.length && !line) { await write(blank); continue; }
  ctx.clearRect(0, 0, W, H);
  pictureNow.forEach((beat) => drawPicture(beat, t));
  titles.forEach((beat) => drawTitle(beat, t));
  if (line) drawSubtitle(line, t);
  const pixels = ctx.getImageData(0, 0, W, H).data;
  await write(Buffer.from(pixels.buffer, pixels.byteOffset, pixels.byteLength));
}
