"""Command line of the engine.

  new VIDEO [NAME]            a project from a raw take: probe, transcribe, ask the AI
  render PROJECT              build the video from the project document
  fill PROJECT NEED FILE      give the project the material one of its requests asks for
  drop PROJECT FROM TO        cut the words FROM..TO (numbers) out of the video
  beat PROJECT KIND FROM TO [FILE|TEXT]   add your own beat over the words FROM..TO: backdrop, cutaway (with a picture), title (with a text), zoom
  unbeat PROJECT ID           remove a beat
  replan PROJECT              ask the AI for the montage again, keeping the words and the cuts
  show PROJECT                what the project holds: the text, the beats and the open requests
  serve [PORT]                the web page: watch the pipeline, edit the text, answer requests, render
"""
import json, sys, time
from pathlib import Path
from . import HOME, media, project, render, speech, styles, suggest

ROOT = HOME / "projects"


def say(data): print(json.dumps(data, ensure_ascii=False, indent=2))


def create(video, folder):
    """A project from a raw take. Each step reports its progress, so the page can show it live."""
    took = {}
    def step(name, work):
        project.progress(folder, name, "running"); started = time.time()
        try: result = work()
        except Exception as error: project.progress(folder, name, "failed", error=str(error)[-300:]); raise
        took[name] = round(time.time() - started, 1); project.progress(folder, name, "done", seconds=took[name]); return result
    for name in ("probe", "transcribe", "review", "suggest", "render"): project.progress(folder, name, "waiting")
    facts = step("probe", lambda: usable(video))
    transcript = step("transcribe", lambda: heard(speech.transcribe(video)))
    cuts = step("review", lambda: suggest.review(transcript["words"]))
    ideas = step("suggest", lambda: suggest.suggest(transcript["words"], {i for c in cuts for i in range(c["from"], c["to"] + 1)}))
    project.save(folder, project.new(video, facts, transcript, ideas, styles.default(), cuts))
    return took


def usable(video):
    """The facts about a take, or the reason it cannot be used, in words a person can act on."""
    try: facts = media.probe(video)
    except (media.ToolError, ValueError, KeyError): raise ValueError("this file is not a video the pipeline can read")
    if not facts["width"] or not facts["height"] or facts["seconds"] < 1: raise ValueError("this file is not a video the pipeline can read")
    if not facts["has_audio"]: raise ValueError("the video has no sound, and the pipeline works from the words")
    return facts


def heard(transcript):
    if not transcript["words"]: raise ValueError("no speech was heard in this video")
    return transcript


def replan(folder):
    """Asks the AI for the montage again, for a project that already has its words. The text, the cuts and the pictures stay."""
    doc = project.load(folder); kept = set()
    for s in doc["edit"]["segments"]: kept.update(range(s["from"], s["to"] + 1))
    ideas = suggest.suggest(doc["words"], set(range(len(doc["words"]))) - kept)
    doc.update(emphasis=ideas["emphasis"], beats=ideas["beats"], needs=ideas["needs"], corrections=[c for c in doc["corrections"] if c["by"] == "user"] + ideas["corrections"])
    project.save(folder, doc); show(folder)


def new(video, name=None):
    video = Path(video); folder = ROOT / (name or video.stem)
    took = create(video, folder)
    show(folder); say({"project": str(folder), "took_seconds": took})


def show(folder):
    doc = project.load(folder); words = doc["words"]
    phrase = lambda b: " ".join(w["text"] for w in words[b["from"]:b["to"] + 1])
    say({"text": " ".join(f"[{w['id']}]{w['text']}" for w in words),
         "kept": [[s["from"], s["to"]] for s in doc["edit"]["segments"]],
         "emphasis": [words[e["word"]]["text"] for e in doc["emphasis"] if e["accepted"]],
         "corrections_to_review": [f"{words[c['word']]['text']} -> {c['text']}" for c in doc["corrections"] if not c["accepted"]],
         "beats": [f"{b['id']} {b['kind']:8} \"{phrase(b)}\"" + (f" text={b['text']}" if b.get("text") else "") + (f" needs {b['need']}" if b.get("need") else "") for b in doc["beats"]],
         "needs": [f"{n['id']} [{n['status']}] {n['what']}" + (" (optional)" if n["optional"] else "") for n in doc["needs"]]})


def fill(folder, need_id, file):
    say({"filled": project.fill(folder, need_id, file)["what"]})


def beat(folder, kind, first, last, extra=None):
    item = project.add_beat(folder, kind, first, last, file=None if kind in ("title", "zoom") else extra, text=extra if kind == "title" else None)
    doc = project.load(folder); say({"added": item["id"], "kind": kind, "over": " ".join(w["text"] for w in doc["words"][item["from"]:item["to"] + 1])})


def unbeat(folder, beat_id):
    doc = project.load(folder); doc["beats"] = [b for b in doc["beats"] if b["id"] != beat_id]; project.save(folder, doc); say({"removed": beat_id})


def drop(folder, first, last):
    say({"kept": [[s["from"], s["to"]] for s in project.drop(folder, int(first), int(last))]})


def serve(port="8787"):
    from . import server
    server.run(int(port))


if __name__ == "__main__":
    commands = {"new": new, "render": lambda folder: say(render.render(folder)), "fill": fill, "drop": drop, "beat": beat, "unbeat": unbeat, "show": show, "replan": replan, "serve": serve}
    if len(sys.argv) < 2 or sys.argv[1] not in commands or (len(sys.argv) < 3 and sys.argv[1] != "serve"): sys.exit(__doc__)
    commands[sys.argv[1]](*sys.argv[2:])
