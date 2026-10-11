"""Command line of the engine.

  new VIDEO [NAME]            a project from a raw take: probe, transcribe, ask the AI
  render PROJECT              build the video from the project document
  fill PROJECT NEED FILE      give the project the material one of its requests asks for
  drop PROJECT FROM TO        cut the words FROM..TO (numbers) out of the video
  beat PROJECT KIND FROM TO [FILE|TEXT]   add your own beat over the words FROM..TO: backdrop, cutaway (with a picture), title (with a text), zoom
  unbeat PROJECT ID           remove a beat
  replan PROJECT              ask the AI for the montage again, keeping the words and the cuts
  mark PROJECT                find the rooms on the project's plans and ask the AI which one is spoken of, and when
  rooms PICTURE               find the rooms of a floor plan; writes PICTURE.rooms.json and a picture to look at in out/
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


def rooms(picture):
    from . import plan
    picture = Path(picture); found = plan.outline(picture); seen = HOME / "out" / f"{picture.stem}.rooms.jpg"
    seen.parent.mkdir(exist_ok=True); plan.draw(picture, found, seen); say(f"{len(found['rooms'])} rooms; look at {seen}")


def mark(folder):
    """Rooms lit on the plans: the outlines come from the plan reader, the moments from the AI."""
    from . import plan
    doc = project.load(folder); kept = project.kept_ids(doc) if hasattr(project, "kept_ids") else {w["id"] for s in doc["edit"]["segments"] for w in doc["words"][s["from"]:s["to"] + 1]}
    filled = {n["id"]: n["asset"] for n in doc["needs"] if n.get("status") == "filled" and n.get("asset")}; shown = {}
    for b in doc["beats"]:
        asset = b.get("asset") or filled.get(b.get("need"))
        if b["kind"] == "full" and b.get("accepted") and asset: shown.setdefault(asset, []).append((b["from"], b["to"]))
    report = []
    for asset in (a for a in doc["assets"] if a["id"] in shown):
        found = plan.outline(asset["file"])["rooms"]
        if len(found) < 3: report.append({"picture": asset["id"], "rooms": len(found), "note": "not a plan"}); continue
        tagged = HOME / "out" / f"{Path(folder).name}.{asset['id']}.rooms.jpg"; tagged.parent.mkdir(exist_ok=True); plan.draw(asset["file"], {"rooms": found}, tagged)
        spans = [(a, b) for a, b in shown[asset["id"]]]; words = [{**w, "text": w["text"] if w["id"] in kept else "…"} for w in doc["words"]]
        marks = [m for m in suggest.mark(tagged, found, words, spans) if m["from"] in kept]
        doc["marks"] = [m for m in doc["marks"] if m.get("asset") != asset["id"] or m.get("by") != "ai"]
        for m in marks: doc["marks"].append({"id": f"m{max([int(x['id'][1:]) for x in doc['marks']] + [0]) + 1}", "asset": asset["id"], **m})
        report.append({"picture": asset["id"], "rooms": len(found), "look": str(tagged), "marks": [f"{m['room']} {m['name']}: " + " ".join(w["text"] for w in doc["words"][m["from"]:m["to"] + 1])[:60] for m in marks]})
    project.save(folder, doc); say(report)


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
    commands = {"new": new, "render": lambda folder: say(render.render(folder)), "fill": fill, "drop": drop, "beat": beat, "unbeat": unbeat, "show": show, "replan": replan, "rooms": rooms, "mark": mark, "serve": serve}
    if len(sys.argv) < 2 or sys.argv[1] not in commands or (len(sys.argv) < 3 and sys.argv[1] != "serve"): sys.exit(__doc__)
    commands[sys.argv[1]](*sys.argv[2:])
