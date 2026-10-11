# Rooms on a floor plan

Her finished videos keep the floor plan on screen for most of their length and light up the room being spoken of. This page
says how the pipeline does that. The code is `engine/plan.py` (finding rooms), `engine/suggest.py` `moments` (when a room is
spoken of), `engine/project.py` `set_mark`, `lit` (tying the two and timing them) and `drawFull` in `renderer/render.mjs`.

## Who does what

| Part | Done by | Paid? |
|---|---|---|
| Where the rooms are | a network that marks walls, doors and windows, then plain geometry | no, runs on this machine |
| When a room is spoken of, and what it is called | the AI, from the words alone | a quick text question |
| Which room that is | a person, by one click; remembered for the plan | no |

The third part was tried with the AI and given up: see `lab/plans/which_room.py`.

## Finding the rooms

Indoors:

1. A reader marks every pixel of the plan that is a wall, a door or a window. Today the reader is the CubiCasa5k network.
2. Marks that stand apart from the house's walls are dropped (`LOOSE`): they are the edge of a rug or a shadow.
3. The spaces the marks enclose are rooms. Whatever reaches the picture's edge is the outside.
4. A gap between two ends of one wall line is bridged (`RUN`, `GAP`), so that a window the reader missed does not open a room.
5. The plan's own room numbers are looked for: small frames with glyphs inside (`numbers`). Two numbers in one space divide
   it: each grows from the widest place first and they meet where the passage is narrowest. A bridge with a number printed
   across it is removed.
6. A part whose edge is mostly open to its neighbour (`OPEN`) goes back to it: the division was a guess.

Outdoors (a terrace, a carport), where there are no walls for the reader to see:

1. The house is cut out of the picture.
2. Everything that is not bare paper (`PAPER`) counts as drawn; gaps between boards and dashes are closed (`HATCH`).
3. A piece that is large enough (`YARD`) and touches the house is a place.

Each room is kept as an outline in shares of the picture's width and height, with its share of the floor, the rooms its doors
open to, its windows and the fixtures the reader saw in it.

## What is kept, and where

`rooms/<first 20 hex digits of the picture's SHA-1>.json`, so that the same plan in another video is known at once:

```json
{"format": 5, "reader": "cubicasa",
 "rooms": [{"id": "r1", "at": [0.31, 0.24], "shape": [[0.24, 0.13], ...], "share": 0.14, "doors": ["r2", "r5"], "windows": 2, "things": ["closet"]}],
 "names": {"техні примі": "r13"}}
```

`names` is what people have clicked: a room's name as the speaker says it (cut to word stems) and the room it means.
`format` rises whenever the finding changes, and kept answers of an older format are worked out again. Room tags may then
differ, so `names` start empty.

In a project document, `marks` tie words to rooms: `{"id", "asset", "room", "from", "to", "name", "by"}`. A mark with no room
waits for a click and is not drawn.

## Changing the reader

The CubiCasa5k code and weights are CC BY-NC 4.0: fine for personal use, not for a product that is sold. They are not in the
repository; `./reel plans-setup` fetches them into `models/cubicasa/`.

A reader is a function that takes the picture (BGR) and returns `{"border": mask}`, True where a room ends. It may add
`"doors"`, `"windows"` and `"things": {name: mask}`. Name it in `READERS` in `engine/plan.py` and pass its name to `outline`;
nothing else changes. `lab/plans/drawing_only.py` is a start on a reader with no network.

## Known limits

- The thresholds above were set on three plans of two house types. Plans of another drawing style may need others.
- On a blurred plan (a frame cut from a video) half of the room numbers are not found, and rooms that share a space stay joined.
- A carport drawn with a thin dashed line is not found. A person cannot yet draw a place by hand.
- One name is remembered for one room: "гардеробна" said of three rooms has to be clicked each time, and a moment cannot yet
  light two rooms.
- A picture that is not a plan is told apart only by having fewer than three rooms.

## Checking it

- `./reel test` - two tests of the geometry on a drawn sheet (class `Rooms`).
- `./reel rooms media/kit/shelest-plan-1.jpg` - reads one plan and writes a picture to look at in `out/`.
- `./reel run lab/plans/score.py plans/cubicasa 20` - scores the finder against plans marked by people.
- `./reel page rooms IMG_7824` - the page: picking a room by a click.
