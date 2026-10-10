# reel-pipeline

A pipeline that turns raw phone footage of a property into a finished short video:
clean and level the sound, cut the pauses, add subtitles with the key words
highlighted, and (later) insert the animated floor plan made in Plan Highlighter.

Status: **experiments**. `lab/` holds draft commands that test one hypothesis each on
real footage; `docs/findings.md` records what they showed and `docs/plan.md` the
implementation plan that follows from it.

## Running the lab

Everything heavy runs in a container; nothing is installed on the host.

    docker build -t reel-lab lab
    ./lab/run.sh probe /in/IMG_7821.MOV      # source videos are read from media/, read-only
    ./lab/run.sh all /in/IMG_7821.MOV        # the whole chain; the result lands in out/

The AI key goes in `.env` (see `.env.example`); `.env`, media and model weights are never committed.
