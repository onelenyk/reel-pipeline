# reel-pipeline

A pipeline that turns raw phone footage of a property into a finished short video:
clean and level the sound, cut the pauses, add subtitles with the key words
highlighted, and (later) insert the animated floor plan made in Plan Highlighter.

Status: **experiments**. `lab/` holds draft commands that test one hypothesis each on
real footage; `docs/findings.md` records what they showed and `docs/plan.md` the
implementation plan that follows from it.

## Using the engine

Everything runs in a container; nothing is installed on the host. Raw takes go in `media/`, projects in `projects/` (neither is committed).

    docker build -t reel .
    ./reel new media/IMG_7821.MOV g-village      # probe, transcribe, ask the AI: writes projects/g-village/project.json
    ./reel show projects/g-village               # the text, the planned beats, the requests for material
    ./reel fill projects/g-village n1 photo.jpg  # answer a request; the beats waiting for it switch on
    ./reel drop projects/g-village 40 52         # cut words 40..52 out of the video
    ./reel render projects/g-village             # build projects/g-village/render.mp4
    ./reel lab probe /in/IMG_7821.MOV            # the experiments in lab/lab.py

Layout: `engine/` (Python: media, speech, suggestions, the project document, the render graph), `renderer/` (Node: draws subtitles, titles and pictures as transparent frames for ffmpeg), `lab/` (experiments), `docs/`.

The AI key goes in `.env` (see `.env.example`); `.env`, media, projects and model weights are never committed.
