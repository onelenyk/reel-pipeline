# Architecture and implementation plan

Goal: make one person's work simpler. She shoots property videos on a phone (an interview plus a tour, 1-5 minutes, 1-3 takes) and today finishes each one across several apps. The pipeline should take the raw takes and hand back a video that needs only a look and a few taps. Selling it comes after it works for her.

This plan follows from `findings.md`. Where a decision rests on a measurement, the measurement is named; where it rests on a guess, it says so.

## Principles

1. **The transcript is the interface.** Recognition of Ukrainian was close to perfect on real footage (H3), so cutting, subtitles, highlights and titles are all driven from the text. Editing a video means editing sentences.
2. **One document describes the video; rendering is a pure function of it.** Nothing is ever baked into the media. The same idea as the scene in Plan Highlighter.
3. **The pipeline asks for what it lacks.** Half of her edit is inserts: a picture of the house behind the speaker, an aerial view when he talks about the settlement (findings, top). The pipeline cannot invent that material, but it can read the words, plan where inserts belong and produce a list of requests ("an overview of the settlement", "a photo of the bathroom", "the floor plan"). She fills the requests from her phone; unfilled ones are simply skipped. In the experiment the AI's plan from the transcript alone matched two of her own placements (H9).
4. **The machine proposes, the person approves.** Every automatic or AI decision is stored as a suggestion that can be undone. AI may highlight words on its own; it may not change words without being accepted (H5: it "corrected" a village name by guessing).
5. **ffmpeg moves pixels and samples; our renderer draws.** Decode, cut, mix, encode in ffmpeg; all text and graphics in the canvas renderer we already have (H5: ffmpeg's subtitle renderer cannot reach her style).
6. **Heavy steps are measured before they are promised.** Stabilisation, denoising and background replacement each get an experiment on her footage first (H1, H2, H8 are still open).
7. **Local first, movable later.** The engine is a job service from day one, so the Mac can be swapped for a server without changing the app.

## Shape of the system

```
 phone (browser, same Wi-Fi)                    Mac
┌──────────────────────────┐        ┌─────────────────────────────────────────────┐
│ app                      │  HTTP  │ engine (job service)                        │
│  upload takes            │ ─────► │  ingest → analyse → suggest → render        │
│  review: video + text    │ ◄───── │  project store (folders + project.json)     │
│  pick style, export      │  SSE   │  ┌────────────┐  ┌───────────────────────┐  │
│  save / share result     │        │  │ ffmpeg     │  │ renderer (Node)       │  │
└──────────────────────────┘        │  │ whisper    │  │ Plan Highlighter's    │  │
                                    │  │ AI provider│  │ canvas engine → RGBA  │  │
                                    │  └────────────┘  └───────────────────────┘  │
                                    └─────────────────────────────────────────────┘
```

### The project document

One JSON file per video. Everything the app edits is here; everything the engine produces is either here or a cached artifact next to it.

```
project.json
  format        version number, so old projects can be upgraded
  sources[]     { id, file, seconds, width, height, fps, hdr, rotation, loudness }
  transcript    { language, words[]: { id, source, start, end, text, confidence } }
  edit          { segments[]: { source, from_word, to_word } }      ← the cut, expressed in words
  corrections[] { word, text, by: "user" | "ai", accepted }
  emphasis[]    { word, by, accepted }
  title         { text, by, accepted, from, to }
  style         preset id + overrides (font, colours, subtitle size and position, title look)
  audio         { level: -15, denoise: off | light | strong, music: { file, gain, duck } }
  picture       { stabilise: off | on, colour: preset }
  beats[]       { id, kind: "backdrop" | "cutaway" | "title" | "zoom" | "plan",   ← the montage, expressed in words
                  from_word, to_word, need, text, by, accepted }
  needs[]       { id, what, kind: "photo" | "video" | "plan" | "logo", optional,  ← requests to the author
                  status: "open" | "filled" | "skipped", asset }
  assets[]      { id, file, kind, width, height, seconds }
  output        { width, height, fps, codec }
```

A beat says what happens in the frame while a stretch of words is spoken: the speaker over a picture (backdrop), a picture over the whole frame (cutaway), a title, a closer framing (zoom), or the animated floor plan from Plan Highlighter. A beat that needs material points at a need; it is rendered only when that need is filled. This keeps the document valid at every moment: with no material at all it still renders a complete video, and each photo she adds improves it.

Why the cut and the beats are stored in words, not seconds: the user edits text, and word ids survive re-timing; seconds are derived at render time (with a short breath of padding around each kept stretch, as measured in H4).

### Engine

A small service with four stages. Each stage writes artifacts keyed by a hash of its inputs and settings, so nothing is recomputed unless something it depends on changed.

| Stage | Does | Artifacts | Measured cost (40 s clip, CPU in Docker) |
|---|---|---|---|
| **ingest** | probe; make a 540p ordinary-colour proxy for the phone; extract 16 kHz speech audio | `proxy.mp4`, `speech.wav`, source facts | 9 s for a full-size normalise; the proxy will be faster |
| **analyse** | speech to words; loudness; later a shake score and scene changes | `words.json`, `loudness.json` | 27-29 s (+33 s once to load the model) |
| **suggest** | AI: emphasis, title, possible corrections; the montage plan (beats) and the list of material it needs | suggestions, beats and needs in `project.json` | 1.4-2.4 s for emphasis, 2.3 s for the montage plan |
| **render** | build one ffmpeg graph from the document: cut, tone-map, level, overlay the graphics layer, encode | `render-<hash>.mp4` | 9 s |

Interfaces that keep the heavy parts swappable:

- `Transcriber`: `faster-whisper` on CPU (works in Docker today), `whisper.cpp`/MLX on Apple hardware (expected several times faster; to be measured), or a cloud API.
- `Suggester`: DeepSeek today; the prompt and the JSON it must return are ours, the provider is a setting. The first version plans from the transcript only. The model can also take images, so a later version can look at frames of the take and at the material she uploads (to tell which photo is the bathroom); that is untested.
- `Denoiser`, `Stabiliser`, `Matter` (background removal): each optional, each off until its experiment passes.

Service surface: `POST /projects` (create), `PUT /projects/:id/sources` (resumable upload), `GET /projects/:id` (document), `PATCH /projects/:id` (edit the document), `POST /projects/:id/render`, `GET /projects/:id/events` (progress as server-sent events), `GET` for proxy, thumbnails and renders. Pairing by a code shown on the Mac, so only her phone on the local network can talk to it.

Storage is plain folders (`projects/<id>/source`, `artifacts`, `renders`, `project.json`): easy to inspect, back up and delete. Media stays in a folder the engine owns: handing Docker the Downloads folder hung it during the experiments (H7).

Language: Python for the service (ffmpeg, whisper and the audio models live there naturally).

### Renderer

The graphics layer (subtitles, title, later stickers and the plan clip) is drawn by the canvas engine from Plan Highlighter, run in Node with a native canvas, and piped to ffmpeg as raw frames with transparency.

- `src/engine` of Plan Highlighter becomes a shared package used by both the web editor and the pipeline.
- A **subtitle generator** turns transcript + edit + style into ordinary scene elements with timing: phrases of two or three words, the current word lit, emphasised words in the accent colour.
- A **style preset** is data in the same spirit as templates: fonts, colours, sizes, positions, the title's look. Her look is the first preset.
- Code overlays written by users or AI are **not** run in the pipeline in the first version: the pipeline's graphics come from our own presets. If they are needed later they run in the same sandbox, in a headless browser.

Open question to settle in milestone 1 with a spike: native canvas in Node versus a headless browser for rendering. Native canvas is faster and simpler to pipe; a headless browser guarantees identical text rendering to the editor. Decide by rendering the same frame both ways and comparing.

### App

A phone-first web app served by the engine. Three screens:

1. **Videos**: the list, and "new video" (pick takes from the phone; upload shows progress and survives a dropped connection).
2. **Review**: the proxy video on top, the transcript under it. Tap a sentence to drop or restore it; tap a word to highlight it or fix its spelling; AI suggestions appear as marks to accept or dismiss. Above the transcript, **"Needed for this video"**: the requests as cards ("Overview of the settlement: add a photo or video", "Skip"). Each filled card switches on the beats that were waiting for it, visible at once in the preview. The preview shows subtitles live (drawn in the browser by the same renderer), so what she sees is what will be rendered.
3. **Finish**: style preset, sound level, optional steps, export; then save to the phone or share.

Built with the same stack and the same visual language as Plan Highlighter (React, the Studio tokens), in Ukrainian first.

## Milestones

Each ends with something she can try, and a yes/no question.

| # | Deliverable | Done when |
|---|---|---|
| **M0** | Lab and findings | done: `lab/`, `findings.md` |
| **M1 Render core** | Project document format; `render(document) → video` as a command; subtitle generator and her style preset drawn by our renderer; levelling; **beats: title on cue, zoom, cutaway and backdrop from supplied pictures** | The G-Village clip rendered from a hand-written document, with stand-in pictures for the two inserts, is judged by her as "I would post this" next to her own version |
| **M1a Experiments for M1** | Cutting the speaker out of the background (H8) on this clip; a zoom on a phrase; the same frame drawn by native canvas and by a headless browser | Each has a recorded result; backdrop stays in M1 only if the cut-out edges are acceptable, otherwise it becomes a plain cutaway |
| **M2 Engine** | Job service: ingest with proxy, analyse, suggest (emphasis, **montage plan and needs**), cached artifacts, progress events; native transcription measured against Docker | A raw take dropped into the service becomes a rendered video and a list of requests with no manual step; timings recorded for a 1, 3 and 5 minute take |
| **M3 Review app** | Upload from the phone, transcript editing, suggestions, **filling requests with photos from the phone**, export, save to phone | She makes one real video end to end on her phone, with her own inserts, and reports how long it took compared with her usual way (this answers H6) |
| **M4 Her kit** | Brand preset editor; the plan clip from Plan Highlighter as a beat; music bed that ducks under speech; several takes in one video; the AI looks at frames and at uploaded pictures | She stops opening one of her current apps for typical videos |
| **M5 Hard steps, on evidence** | Stabilisation, denoise levels: one experiment each on her footage, built only if it passes | Each feature has a recorded comparison with the app she uses for it today |
| **M6 Packaging** | One-click start on the Mac; or the engine on a server for people without one; first pricing test | Someone other than her completes a video without help |

Order of risk: M1 proves the look, M3 proves the time saved. If either fails, stop and rethink before M4.

## What is deliberately not in the plan

- A timeline editor with tracks, transitions and effects. That is CapCut; the bet here is that an edit described by the words (what to keep, what to show while it is said) with good defaults covers her typical video. If her videos need free-form editing beyond that, this bet is wrong and the plan changes.
- Accounts, sync and payments. Not needed for one user on one network.
- Running on the phone alone. Speech recognition and video encoding at this size do not fit a phone browser.

## Numbers still missing

1. How long one typical video takes her by hand today. Without it "time saved" is a guess.
2. Speech recognition speed natively on the Mac.
3. A walking shot, a noisy location, a take with retakes, and a two-person interview, to close H1, H2 and H4.
5. The pictures she used for the inserts in the G-Village video (or any stand-ins), to render the montage and to test the cut-out (H8).
6. More than one clip for the montage plan: H9 rests on a single run.
4. Whether she will edit on a phone talking to a Mac at home, or wants it to work away from home (which means a server sooner).
