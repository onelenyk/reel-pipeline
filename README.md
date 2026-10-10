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
    ./reel beat projects/g-village backdrop 5 14 photo.jpg   # your own beat over words 5..14
    ./reel serve                                 # the web page: http://127.0.0.1:8787
    ./reel lab probe /in/IMG_7821.MOV            # the experiments in lab/lab.py

The web page (in Ukrainian) shows the pipeline step by step as it runs and plays the result. On it you can:

- **correct the text**: highlight words, fix a misheard word in place (the AI's own suggestions stay as offers), cut a stretch of words or put it back;
- **choose pictures**: every request for material and every picture beat opens a chooser with the project's own pictures, upload from the device, and a search of openly licensed pictures on the internet (labelled as illustrations, with credits to copy into the post);
- **add your own beats** over a range of words: a picture on top, a picture behind the speaker, a title, a zoom;
- **set the style** (accent colour, subtitle size and place, word-by-word or all at once, title glow, picture layout, loudness), **save it under a name**, apply it to another video, or make it the default for new ones;
- upload a new take, and render.

It listens on this machine only. `./reel test` runs the engine's tests (no video or network needed).

Layout: `engine/` (Python: media, speech, matting, suggestions, the project document, the render graph, saved styles, picture search, the web service and its page), `tests/`, `renderer/` (Node: draws subtitles, titles and pictures as transparent frames for ffmpeg), `lab/` (experiments), `docs/`.

The AI key goes in `.env` (see `.env.example`); `.env`, media, projects and model weights are never committed.
