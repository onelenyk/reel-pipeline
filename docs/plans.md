# Rooms on a floor plan

Her finished videos keep the floor plan on screen for most of their length and light up the room being spoken of. This page
says how the pipeline does that. The code is `engine/plan.py` (finding rooms), `engine/suggest.py` `moments` (when a room is
spoken of), `engine/project.py` `set_mark`, `lit` (tying the two and timing them) and `drawFull` in `renderer/render.mjs`.

## Who does what

| Part | Done by | Paid? |
|---|---|---|
| Where the rooms are | a network that marks walls, doors and windows, then plain geometry | no, runs on this machine |
| When a room is spoken of, and what it is called | the AI, from the words alone | a quick text question |
| What each room is | rules and local OCR propose, a person corrects once per plan | no |
| Which room a moment means | the room's name | no |

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
3. Dashes are joined along their own direction (`DASH`), and thin lines that frame a large box on three sides or more stand for the box: a carport is often only a dashed outline.
4. A piece that is large enough (`YARD`) and touches the house is a place.

Each room is kept as an outline in shares of the picture's width and height, with its share of the floor, the rooms its doors
open to, its windows and the fixtures the reader saw in it.

## Saying what each room is

Done once, when the plan is read, by `describe` in `engine/plan.py`, with nothing paid for:

- the number printed in the room is read by Tesseract (`read_numbers`); a number it cannot read is left out;
- a name is guessed from what stands in the room, its size, its windows and where its doors lead: a toilet or a bath is a
  bathroom, a small windowless room with closets a wardrobe, the largest room the kitchen-living room, a middle-sized room
  with a window a bedroom (with a bathroom of its own, the owners' bedroom), a room with the door to the outside the hall;
  outdoors, black ink means cars and so a carport, faint lines a terrace.

A guess is marked as one and a room nothing can be said of stays unnamed. On the page the person corrects the wrong guesses
and fills in the empty ones (`name_room`); their word stays with the plan. On the three plans tried the guesses named 23 of
29 rooms, none of them wrongly after one rule was tightened; that is three plans, not a measure.

A moment of the video ("постірочна") then takes its room by name, with no click and no AI (`match`): names are compared by
word stems, words of one meaning count as one (`SAME`: постірочна and пральня, паркінг and навіс), and words that say nothing
of which room it is are ignored (`GENERIC`). Of several rooms of one name, each next moment takes the next room. A person's
own tie of a moment is never changed by this.

## What is kept, and where

`rooms/<first 20 hex digits of the picture's SHA-1>.json`, so that the same plan in another video is known at once:

```json
{"format": 7, "reader": "cubicasa",
 "rooms": [{"id": "r1", "at": [0.31, 0.24], "shape": [[0.24, 0.13], ...], "share": 0.14, "doors": ["r2", "r5"], "windows": 2, "things": ["closet"],
            "number": "06", "kind": "bedroom", "name": "Спальня", "guess": true}],
 "names": {"техні примі": "r13"}}
```

`names` is what people have clicked: a room's name as the speaker says it (cut to word stems) and the room it means.
`format` (`FORMAT` in `engine/plan.py`) rises whenever the finding changes. A kept answer of an older format is worked out
again when the plan is next read (room tags may then differ, and `names` start empty); until then a video already tied to
its rooms builds from the old answer.

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
- A place outdoors takes the shape of what is drawn there (cars and their shadow), not of the slab meant. A person cannot yet draw a place by hand.
- One name is remembered for one room: "гардеробна" said of three rooms has to be clicked each time, and a moment cannot yet
  light two rooms.
- A picture that is not a plan is told apart only by having fewer than three rooms.

## Checking it

- `./reel test` - two tests of the geometry on a drawn sheet (class `Rooms`).
- `./reel rooms media/kit/shelest-plan-1.jpg` - reads one plan and writes a picture to look at in `out/`.
- `./reel run lab/plans/score.py plans/cubicasa 20` - scores the finder against plans marked by people.
- `./reel page rooms IMG_7824` - the page: picking a room by a click.
- `./reel page zones IMG_7824` - the page: naming a zone.

## How it looks in the video

`drawPlan` in `renderer/render.mjs`: the plan lies on a white card over warm paper; the camera starts on the drawing itself
(without the empty sheet around it) and moves towards each room as it is named; the rest of the plan steps back, the room
takes the accent colour, and its name stands on a plate at the foot of the card. To judge a change without building the
video: `./reel run tools/stills.py IMG_7824 19.5,29.5,43.5`.
