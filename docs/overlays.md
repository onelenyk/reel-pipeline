# Overlays: graphics the AI adds over the frame

> Status, 2026-10-11: the room highlight on a plan is built, in a different way from the one sketched here (a network for walls, a person's click for which room). See `docs/plans.md`. The rest of this page is still a design.

Status: design, nothing built. Goal: the things she draws by hand today (a highlighted room on the plan, a number that
counts up, a label with a pointer) appear because the words call for them, placed by the AI and corrected by a sentence
or a drag. No editor is imported from Plan Highlighter: overlays are drawn by the renderer that already draws subtitles.

## What an overlay is

One more list in the project document, next to `beats`:

```
overlays[] { id, kind, from, to,            the words it is on screen for (like a beat)
             on: "frame" | beat id,          the whole frame, or a picture insert (then coordinates are the picture's)
             place: slot | {x, y, w, h},     a named slot, or a box in shares of what it sits on (0..1)
             props, by, accepted }
```

Tied to words, so it survives cuts and re-timing like everything else. Tied to a picture when it marks something in the
picture: a room stays on the room even when the plan is pushed in or laid out differently.

## The kit (small on purpose)

| Kind | What it draws | Typical words |
|---|---|---|
| `area` | a filled, softly pulsing polygon or box on a picture | "заходимо в передпокій" over the plan |
| `pointer` | a dot with a line to a short label | "ось тут тераса" |
| `number` | a large number that counts up, with its unit | "154 метри квадратних" |
| `label` | a chip of text in a slot | a price, a deadline, "2 поверхи" |
| `list` | lines that appear one by one as each is spoken | "є школа, садок і магазин" |
| `caption` | name and role of the speaker, low in the frame | the first seconds |
| `mark` | a hand-drawn circle or underline | emphasis on a detail of a render |

Each kind has a few props (text, value, unit, colour from the style, shape) and one built-in animation in and out.
Seven kinds drawn well beat an open canvas: the AI can only choose and fill them in, so it cannot produce a broken layout.

## Where the AI comes in

1. **From the words** (text model, the planning step). Numbers with units become `number`, enumerations become `list`,
   the opening gets a `caption`. Same contract as beats: checked, accepted by default, one tap to switch off.
2. **From the picture** (vision model, a new step after pictures are assigned). For a plan: the model gets the image and
   the rooms the speaker names, each with its words, and returns a box or polygon per room. Result: `area` overlays that
   light each room as it is named, which is the core of her finished videos. Unproven: see risks.
3. **By request** (the "mark a stretch and ask" box that exists). "Покажи тут цифру великим", "підсвіти кухню",
   "прибери напис": the answer gains overlay operations (add, change, remove) next to cut and respell.

## Placement without an editor

- **Slots, not pixels.** Over the frame the AI picks a slot: `top`, `top-left`, `top-right`, `above-subtitles`, `left`, `right`.
  The renderer turns a slot into a box, keeping clear of subtitles, the title and picture cards.
- **Keeping off the face.** One frame every two seconds through the person-matting model the engine already has gives the
  speaker's outline; slots that would cover the head are not offered. Cheap, local, no AI call.
- **By hand, minimally.** On the page: the frame at that moment with the overlay's box on it. Drag to move, corner to
  resize, a field for the text. For `area`: drag the corners of the polygon. No layers panel, no timeline of keyframes.

## One still frame on demand

`GET /frame/<project>?t=` returns the finished frame at a moment, drawn by the renderer over the decoded source frame,
in about a second. Needed for the drag preview above; also removes the wait for a full rebuild after small edits.

## Order of work

| Step | Deliverable | Proves |
|---|---|---|
| 1 | Data model, renderer for `number`, `label`, `list`, `caption`; the planning step proposes them; ask-box operations | overlays from words look right on the three takes |
| 2 | Still-frame endpoint; drag and resize on the page | a wrong placement is fixed in seconds |
| 3 | **Experiment first:** a vision model marks rooms on her two plans; then `area` and `pointer` on pictures | rooms land on the right rooms often enough to keep |
| 4 | Speaker outline, slots that avoid the face | nothing covers the face without being asked |

## Risks, stated before building

- **Rooms on a plan (step 3) is the valuable part and the unproven one.** Vision models are weak at exact coordinates on
  line drawings. Test on the plans in `media/kit/` before promising it. Fallbacks: she marks rooms once per plan by
  dragging boxes (step 2 makes that possible), or the plan arrives already marked from Plan Highlighter.
- **The model in use has not been checked for image input.** If it has none, a second provider and key are needed.
- **Taste.** Overlays the AI adds by default can make a video busy. Start with few (a number, a caption) and let the
  style switch each kind off.
