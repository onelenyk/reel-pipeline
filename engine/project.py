"""The project document: one JSON file that fully describes a video. Rendering is a pure function of it."""
import json, shutil, time
from pathlib import Path

FORMAT = 1
PAD = 0.12     # a breath kept on each side of every stretch of speech
JOIN = 0.45    # pauses shorter than this stay in
MIN_BEAT = {"title": 2.6, "cutaway": 2.5, "backdrop": 2.5, "zoom": 1.6}  # seconds: shorter than this reads as a glitch


def new(source_file, facts, transcript, suggestions):
    words = transcript["words"]
    return {
        "format": FORMAT,
        "sources": [{"id": "s1", "file": str(source_file), **facts}],
        "language": transcript["language"],
        "words": [{"id": i, "source": "s1", **w} for i, w in enumerate(words)],
        # The cut, in words: one segment keeps everything from one word to another, inclusive
        "edit": {"segments": [{"source": "s1", "from": 0, "to": len(words) - 1}] if words else []},
        **suggestions,
        "assets": [],
        "style": {"preset": "bold-yellow", "accent": "#ffd60a"},
        "audio": {"level": -15, "denoise": "off"},
        "output": {"width": 1080, "height": 1920, "fps": 30},
    }


def load(folder):
    doc = json.loads((Path(folder) / "project.json").read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT: raise ValueError(f"project format {doc.get('format')} is not supported")
    return doc


def save(folder, doc):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / "project.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def resolve(doc):
    """Turns the document (in words) into a timeline (in seconds of the finished video)."""
    words = doc["words"]; source = doc["sources"][0]
    kept, spans = [], []  # spans: [source_start, source_end] stretches that stay
    for segment in doc["edit"]["segments"]:
        for w in words[segment["from"]:segment["to"] + 1]:
            kept.append(w)
            if spans and w["start"] - spans[-1][1] <= JOIN + 2 * PAD: spans[-1][1] = min(source["seconds"], w["end"] + PAD)
            else: spans.append([max(0.0, w["start"] - PAD), min(source["seconds"], w["end"] + PAD)])
    offsets, total = [], 0.0
    for a, b in spans: offsets.append(total); total += b - a

    def at(t):  # source time → time in the finished video
        for (a, b), offset in zip(spans, offsets):
            if t <= b: return round(offset + max(0.0, t - a), 3)
        return round(total, 3)

    hot = {e["word"] for e in doc.get("emphasis", []) if e.get("accepted")}
    fixed = {c["word"]: c["text"] for c in doc.get("corrections", []) if c.get("accepted")}
    spoken = [{"id": w["id"], "text": fixed.get(w["id"], w["text"]), "start": at(w["start"]), "end": at(w["end"]), "hot": w["id"] in hot} for w in kept]
    kept_ids = {w["id"] for w in kept}

    # Phrases of up to three words or about 16 letters, never running past the end of a sentence
    phrases, current = [], []
    for w in spoken:
        current.append(w)
        if len(current) >= 3 or len(" ".join(x["text"] for x in current)) >= 16 or w["text"][-1:] in ".!?": phrases.append(current); current = []
    if current: phrases.append(current)
    lines = [{"start": p[0]["start"], "end": min(p[-1]["end"] + 0.3, phrases[i + 1][0]["start"]) if i + 1 < len(phrases) else p[-1]["end"] + 0.5, "words": p} for i, p in enumerate(phrases)]

    filled = {n["id"]: n["asset"] for n in doc.get("needs", []) if n.get("status") == "filled" and n.get("asset")}
    assets = {a["id"]: a for a in doc.get("assets", [])}
    beats = []
    for b in doc.get("beats", []):
        inside = [w for w in words[b["from"]:b["to"] + 1] if w["id"] in kept_ids]
        if not b.get("accepted") or not inside: continue  # the words it belongs to were cut
        asset = assets.get(b.get("asset")) or (assets.get(filled.get(b.get("need"))) if b.get("need") else None)
        if b["kind"] in ("cutaway", "backdrop") and not asset: continue  # waiting for material: the speaker stays
        start = at(inside[0]["start"])
        end = min(total, max(at(inside[-1]["end"]), start + MIN_BEAT[b["kind"]]))
        beats.append({"id": b["id"], "kind": b["kind"], "start": start, "end": end, "source_start": inside[0]["start"], "text": b.get("text"), "file": asset["file"] if asset else None})
    # A title and a picture share the top of the frame: the title leaves as the picture arrives
    pictures = [b for b in beats if b["kind"] in ("cutaway", "backdrop")]
    for title in (b for b in beats if b["kind"] == "title"):
        for picture in pictures:
            if title["start"] < picture["start"] < title["end"]: title["end"] = round(picture["start"] + 0.15, 3)
    beats = [b for b in beats if b["end"] - b["start"] >= 0.8]
    return {"spans": spans, "seconds": round(total, 3), "lines": lines, "beats": beats, "style": doc["style"], **doc["output"]}


# ---------- changes to a project ----------
def keep_asset(folder, doc, file, kind="photo", name=None):
    """Copies material into the project and registers it."""
    folder = Path(folder); (folder / "assets").mkdir(exist_ok=True)
    asset_id = f"a{len(doc['assets']) + 1}"
    kept = folder / "assets" / f"{asset_id}{Path(name or file).suffix.lower() or '.jpg'}"
    shutil.copyfile(file, kept)
    doc["assets"].append({"id": asset_id, "file": str(kept), "kind": kind})
    return asset_id


def fill(folder, need_id, file, name=None):
    doc = load(folder); need = next((n for n in doc["needs"] if n["id"] == need_id), None)
    if not need: raise KeyError(f"no request {need_id}")
    need["asset"] = keep_asset(folder, doc, file, need["kind"], name); need["status"] = "filled"
    save(folder, doc); return need


def drop(folder, first, last, restore=False):
    """Cuts the words first..last out of the video, or puts them back."""
    doc = load(folder); count = len(doc["words"])
    kept = [False] * count
    for s in doc["edit"]["segments"]:
        for i in range(s["from"], s["to"] + 1): kept[i] = True
    for i in range(max(0, first), min(count - 1, last) + 1): kept[i] = restore
    segments, start = [], None
    for i, on in enumerate(kept + [False]):
        if on and start is None: start = i
        if not on and start is not None: segments.append({"source": "s1", "from": start, "to": i - 1}); start = None
    doc["edit"]["segments"] = segments; save(folder, doc); return segments


def add_beat(folder, kind, first, last, file=None, text=None, name=None):
    doc = load(folder)
    if kind not in ("backdrop", "cutaway", "title", "zoom"): raise ValueError("kind must be backdrop, cutaway, title or zoom")
    item = {"id": f"b{max([int(b['id'][1:]) for b in doc['beats']] + [0]) + 1}", "kind": kind, "from": int(first), "to": int(last), "need": None,
            "text": (text or "")[:40] or None, "why": None, "by": "user", "accepted": True}
    if kind in ("backdrop", "cutaway"):
        if not file: raise ValueError("a picture is needed")
        item["asset"] = keep_asset(folder, doc, file, "photo", name)
    doc["beats"].append(item); save(folder, doc); return item


# ---------- progress, for anyone watching ----------
def progress(folder, step, state, **facts):
    """Records where the pipeline is: one line per step, rewritten as it moves from running to done or failed."""
    path = Path(folder) / "status.json"
    steps = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    steps = [s for s in steps if s["step"] != step] + [{"step": step, "state": state, "at": round(time.time(), 1), **facts}]
    Path(folder).mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(steps, ensure_ascii=False), encoding="utf-8")
