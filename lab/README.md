# Experiments

Everything here was written to answer one question. Nothing in `engine/` imports from this folder. Each script begins with the
question, the command that runs it and what was found; this page is the index. Run any of them with `./reel run <script>`.

| Script | Question | Finding |
|---|---|---|
| `lab.py` | The first hypotheses: HDR footage, levelling, recognition, pauses, matting | `docs/findings.md` |
| `speech/two_languages.py` | Does a second, English pass hear English names better? | No: it translates the speech and is up to three times slower |
| `speech/vocabulary.py` | Does a vocabulary given to the recogniser fix names? | Yes, as an opening sentence; `hotwords` drop punctuation |
| `review/retakes.py` | What does the AI review cut? | Failed attempts and asides, with thinking on; not the same on every run |
| `plans/model_boxes.py` | Can a model with eyes outline rooms? | Roughly: boxes 15-30 px off, rectangles only |
| `plans/snap_boxes.py` | Can those boxes be pulled onto the drawn walls? | Yes: 8 of 8 rooms on a simple plan, 13 of 16 on a complex one |
| `plans/drawing_only.py` | Can rooms be found from the drawing alone? | On her plans' style partly; on scanned plans a third of the rooms |
| `plans/cubicasa_raw.py` | What does the CubiCasa5k network see on her plans? | Walls, doors and windows well; room kinds badly. The engine uses the former |
| `plans/numbers_on_plan.py` | How many room numbers can be found on a plan? | All on clean plans, 7 of 16 on a blurred frame from a video |
| `plans/which_room.py` | Can the AI tell which room the speaker means? | No: one or two of four, in two to three minutes. A person clicks instead |
| `plans/score.py` | How well are rooms outlined, in numbers? | Scores a finder against 232 plans marked by people (`plans/cubicasa`) |

## Data the experiments use

None of it is in the repository.

- `media/` - her raw takes and `media/kit/`, pictures cut from her finished videos.
- `plans/cubicasa/` - 232 plans of the CubiCasa5k set with walls, doors and windows marked (CC BY-NC 4.0). Fetched from
  `huggingface.co/datasets/v1nz/cubicasa5k-yolo`, the `test` folders of `images` and `labels`.
- `models/cubicasa/` - the network's code and weights (CC BY-NC 4.0), fetched by `./reel plans-setup`.

## Adding an experiment

Put it in the folder of its subject, start it with a docstring that states the question and the command, and when it has an
answer write the answer and its date into the docstring and into the table above. A script that the engine comes to depend on
moves to `engine/`; one that is superseded is deleted, with its finding kept in the table.
