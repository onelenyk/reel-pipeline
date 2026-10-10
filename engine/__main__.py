"""Command line of the engine.

  new VIDEO [NAME]            a project from a raw take: probe, transcribe, ask the AI
  render PROJECT              build the video from the project document
  fill PROJECT NEED FILE      give the project the material one of its requests asks for
  drop PROJECT FROM TO        cut the words FROM..TO (numbers) out of the video
  show PROJECT                what the project holds: the text, the beats and the open requests
"""
import json, shutil, sys, time
from pathlib import Path
from . import media, project, render, speech, suggest

ROOT = Path("/work/projects")


def say(data): print(json.dumps(data, ensure_ascii=False, indent=2))


def new(video, name=None):
    video = Path(video); folder = ROOT / (name or video.stem); took = {}
    t = time.time(); facts = media.probe(video); took["probe"] = round(time.time() - t, 1)
    t = time.time(); transcript = speech.transcribe(video); took["transcribe"] = round(time.time() - t, 1)
    t = time.time(); ideas = suggest.suggest(transcript["words"]); took["suggest"] = round(time.time() - t, 1)
    project.save(folder, project.new(video, facts, transcript, ideas))
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
    folder = Path(folder); doc = project.load(folder); need = next((n for n in doc["needs"] if n["id"] == need_id), None)
    if not need: sys.exit(f"no request {need_id}")
    (folder / "assets").mkdir(exist_ok=True)
    asset_id = f"a{len(doc['assets']) + 1}"; kept = folder / "assets" / f"{asset_id}{Path(file).suffix.lower()}"
    shutil.copyfile(file, kept)
    doc["assets"].append({"id": asset_id, "file": str(kept), "kind": need["kind"]}); need["status"] = "filled"; need["asset"] = asset_id
    project.save(folder, doc); say({"filled": need["what"], "with": str(kept)})


def drop(folder, first, last):
    doc = project.load(folder); first, last = int(first), int(last); segments = []
    for s in doc["edit"]["segments"]:
        if last < s["from"] or first > s["to"]: segments.append(s); continue
        if s["from"] < first: segments.append({**s, "to": first - 1})
        if s["to"] > last: segments.append({**s, "from": last + 1})
    doc["edit"]["segments"] = segments; project.save(folder, doc)
    say({"dropped": " ".join(w["text"] for w in doc["words"][first:last + 1]), "kept": [[s["from"], s["to"]] for s in segments]})


if __name__ == "__main__":
    commands = {"new": new, "render": lambda folder: say(render.render(folder)), "fill": fill, "drop": drop, "show": show}
    if len(sys.argv) < 3 or sys.argv[1] not in commands: sys.exit(__doc__)
    commands[sys.argv[1]](*sys.argv[2:])
