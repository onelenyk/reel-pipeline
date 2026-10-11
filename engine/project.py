"""The project document: one JSON file that fully describes a video. Rendering is a pure function of it."""
import json, os, re, shutil, tempfile, time
from pathlib import Path

FORMAT = 1
PAD = 0.12     # a breath kept on each side of every stretch of speech
JOIN = 0.45    # pauses shorter than this stay in
PUNCH_EVERY = 6.0   # seconds of one framing before the next sentence end may change it
PUNCH_TAIL = 2.5    # a change of framing this close to the end is not worth it
PICTURED = ("full", "cutaway", "backdrop")  # the kinds of insert that show a picture
MIN_BEAT = {"title": 2.6, "cutaway": 2.5, "backdrop": 2.5, "full": 2.5, "zoom": 1.6}  # seconds: shorter than this reads as a glitch


# ---------- style: how the graphics and the sound of a video are finished; saved styles are reused across videos ----------
STYLE = {"name": "Жовтий акцент", "accent": "#ffd60a", "subtitle_size": "m", "subtitle_place": "low", "karaoke": True, "title_glow": True, "picture": "card", "rhythm": True, "level": -15}
CHOICES = {"subtitle_size": ("s", "m", "l"), "subtitle_place": ("low", "middle"), "picture": ("card", "edge")}


def clean_style(raw):
    """A style rebuilt from untrusted data: unknown fields are dropped, bad values fall back to the defaults."""
    raw = raw if isinstance(raw, dict) else {}; out = dict(STYLE)
    if isinstance(raw.get("name"), str) and raw["name"].strip(): out["name"] = raw["name"].strip()[:40]
    if isinstance(raw.get("accent"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", raw["accent"]): out["accent"] = raw["accent"].lower()
    for key, allowed in CHOICES.items():
        if raw.get(key) in allowed: out[key] = raw[key]
    for key in ("karaoke", "title_glow", "rhythm"):
        if isinstance(raw.get(key), bool): out[key] = raw[key]
    if isinstance(raw.get("level"), (int, float)) and not isinstance(raw.get("level"), bool): out["level"] = max(-24, min(-10, round(raw["level"])))
    return out


def segments_of(kept):
    """Runs of kept words as segments."""
    segments, start = [], None
    for i, on in enumerate(list(kept) + [False]):
        if on and start is None: start = i
        if not on and start is not None: segments.append({"source": "s1", "from": start, "to": i - 1}); start = None
    return segments


def new(source_file, facts, transcript, suggestions, style=None, cuts=()):
    words = transcript["words"]; gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    return {
        "format": FORMAT,
        "sources": [{"id": "s1", "file": str(source_file), **facts}],
        "language": transcript["language"],
        "words": [{"id": i, "source": "s1", **w} for i, w in enumerate(words)],
        # The cut, in words: one segment keeps everything from one word to another, inclusive
        "edit": {"segments": segments_of(i not in gone for i in range(len(words)))},
        # What the review took out and why; each is undone by putting its words back
        "cuts": list(cuts),
        **suggestions,
        "assets": [],
        "style": clean_style(style),
        "audio": {"denoise": "off"},
        "output": {"width": 1080, "height": 1920, "fps": 30},
    }


def write_whole(path, text):
    """Replaces a file in one step, so a reader never sees it half written (the page polls while the engine writes)."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(handle, "w", encoding="utf-8") as f: f.write(text)
    os.replace(tmp, path)


def load(folder):
    doc = json.loads((Path(folder) / "project.json").read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT: raise ValueError(f"project format {doc.get('format')} is not supported")
    doc["style"] = clean_style(doc.get("style"))  # also upgrades projects made before styles existed
    for key in ("emphasis", "corrections", "beats", "needs", "assets", "cuts", "marks"): doc.setdefault(key, [])
    return doc


KEPT = 40  # earlier versions of a document kept in its history folder


def save(folder, doc):
    """Writes the document. What it replaces goes to the project's history, so that a change made by mistake can be taken back."""
    file = Path(folder) / "project.json"; text = json.dumps(doc, ensure_ascii=False, indent=1)
    if file.exists() and file.read_text(encoding="utf-8") != text:
        history = Path(folder) / "history"; history.mkdir(exist_ok=True)
        shutil.copy2(file, history / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1000000:06d}.json")
        for old in sorted(history.glob("*.json"))[:-KEPT]: old.unlink()
    write_whole(file, text)


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
        if b["kind"] in PICTURED and not asset: continue  # waiting for material: the speaker stays
        start = at(inside[0]["start"])
        end = min(total, max(at(inside[-1]["end"]), start + MIN_BEAT[b["kind"]]))
        beats.append({"id": b["id"], "kind": b["kind"], "start": start, "end": end, "source_start": inside[0]["start"], "text": b.get("text"), "file": asset["file"] if asset else None})
        if b["kind"] == "full":
            beats[-1]["marks"] = lit(doc, asset, kept_ids, at, start, end); beats[-1]["plan"] = len(rooms_of(asset["file"])) >= 3
            points = [p for r in rooms_of(asset["file"]) for p in r["shape"]]
            if beats[-1]["plan"]: beats[-1]["extent"] = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]  # where the drawing itself is on the sheet
    # A title and a picture share the top of the frame: the title leaves as the picture arrives
    pictures = [b for b in beats if b["kind"] in PICTURED]
    for title in (b for b in beats if b["kind"] == "title"):
        for picture in pictures:
            if title["start"] < picture["start"] < title["end"]: title["end"] = round(picture["start"] + 0.15, 3)
    beats = [b for b in beats if b["end"] - b["start"] >= 0.8]
    # Rhythm: the framing alternates between wide and closer. It changes at every cut, which turns the jump left by a removed
    # stretch into a deliberate change of shot, and at a sentence end when one framing has lasted long enough.
    punches = []
    if doc["style"].get("rhythm", True) and total > 0:
        switches = set(round(o, 3) for o in offsets[1:])
        last = 0.0
        for moment in sorted(switches | {w["end"] + 0.1 for w in spoken if w["text"][-1:] in ".!?"}):
            forced = moment in switches
            if (forced and moment - last >= 0.6) or (not forced and moment - last >= PUNCH_EVERY and not any(0 < s - moment < 2.0 for s in switches)):
                if total - moment >= (0.6 if forced else PUNCH_TAIL): punches.append(round(moment, 3)); last = moment
        edges = [0.0] + punches + [round(total, 3)]
        punches = [[edges[i], edges[i + 1]] for i in range(1, len(edges) - 1, 2)]  # every second stretch is the closer one
    return {"spans": spans, "seconds": round(total, 3), "lines": lines, "beats": beats, "punches": punches, "style": doc["style"], **doc["output"]}


# ---------- changes to a project ----------
def lit(doc, asset, kept_ids, at, start, end):
    """The rooms of a plan lit while it is on screen: each from the first word about it until the next room, or until the plan leaves."""
    rooms = {r["id"]: r for r in rooms_of(asset["file"])}; marks = []
    for m in sorted(doc.get("marks", []), key=lambda m: m["from"]):
        said = [w for w in doc["words"][m["from"]:m["to"] + 1] if w["id"] in kept_ids]
        if m.get("asset") != asset["id"] or m.get("room") not in rooms or not said: continue
        begin = at(said[0]["start"])
        if not start - 0.05 <= begin < end - 0.4: continue
        if marks: marks[-1]["end"] = min(marks[-1]["end"], begin)
        marks.append({"id": m["id"], "start": max(start, begin), "end": end, "shape": rooms[m["room"]]["shape"], "name": m.get("name")})
    return marks


def rooms_of(file):
    """The rooms found on a picture, if it is a plan that has been read."""
    from . import plan
    return (plan.stored(file, lenient=True) or {}).get("rooms", []) if Path(file).exists() else []


def plan_assets(doc):
    """The pictures shown over the whole frame, with the word ranges during which each is shown."""
    filled = {n["id"]: n["asset"] for n in doc["needs"] if n.get("status") == "filled" and n.get("asset")}; shown = {}
    for b in doc["beats"]:
        asset = b.get("asset") or filled.get(b.get("need"))
        if b["kind"] == "full" and b.get("accepted") and asset: shown.setdefault(asset, []).append((b["from"], b["to"]))
    return shown


def place_marks(folder, asset_id, moments):
    """The moments the AI found become marks. A name a person has already tied to a room on this plan is tied again;
    the rest wait for a click. Marks a person made or tied are kept as they are."""
    from . import plan
    doc = load(folder); asset = next(a for a in doc["assets"] if a["id"] == asset_id)
    doc["marks"] = [m for m in doc["marks"] if m["asset"] != asset_id or m.get("by") == "user"]
    for m in moments:
        if any(m["from"] <= k["to"] and k["from"] <= m["to"] for k in doc["marks"] if k["asset"] == asset_id): continue
        doc["marks"].append({"id": f"m{max([int(x['id'][1:]) for x in doc['marks']] + [0]) + 1}", "asset": asset_id, "room": None, "from": m["from"], "to": m["to"], "name": m["name"], "by": "ai"})
    tie(doc); save(folder, doc); return doc


def tie(doc):
    """Moments nobody tied take the room whose name says what was spoken. A person's own ties are not touched."""
    from . import plan
    files = {a["id"]: a["file"] for a in doc["assets"]}
    for asset_id in {m["asset"] for m in doc["marks"]}:
        taken = [m["room"] for m in doc["marks"] if m["asset"] == asset_id and m.get("by") == "user" and m["room"]]
        for m in sorted((m for m in doc["marks"] if m["asset"] == asset_id and m.get("by") != "user"), key=lambda m: m["from"]):
            m["room"] = plan.match(files[asset_id], m["name"], taken) if asset_id in files and m.get("name") else None
            if m["room"]: taken.append(m["room"])


def name_zone(folder, asset_id, room, name=None, number=None):
    """A person names a room of a plan; the moments that were waiting for that name are tied at once."""
    from . import plan
    doc = load(folder); asset = next((a for a in doc["assets"] if a["id"] == asset_id), None)
    if not asset: raise ValueError("there is no such picture")
    plan.name_room(asset["file"], room, name, number); tie(doc); save(folder, doc)


def set_mark(folder, mark_id=None, asset=None, room=None, first=None, last=None, name=None):
    """A person ties a stretch of words to a room of a plan, or makes a new mark over the words they chose."""
    from . import plan
    doc = load(folder)
    if mark_id:
        mark = next((m for m in doc["marks"] if m["id"] == mark_id), None)
        if not mark: raise ValueError("there is no such mark")
    else:
        if not any(a["id"] == asset for a in doc["assets"]): raise ValueError("there is no such picture")
        if not (isinstance(first, int) and isinstance(last, int) and 0 <= first <= last < len(doc["words"])): raise ValueError("a mark needs a stretch of words")
        doc["marks"] = [m for m in doc["marks"] if m["asset"] != asset or m["to"] < first or m["from"] > last]  # the new mark replaces what it covers
        mark = {"id": f"m{max([int(x['id'][1:]) for x in doc['marks']] + [0]) + 1}", "asset": asset, "room": None, "from": first, "to": last, "name": None, "by": "user"}; doc["marks"].append(mark)
    file = next(a["file"] for a in doc["assets"] if a["id"] == mark["asset"])
    if room is not None and not any(r["id"] == room for r in rooms_of(file)): raise ValueError("there is no such room on this plan")
    if name is not None: mark["name"] = str(name).strip()[:40] or None
    mark["room"] = room; mark["by"] = "user"
    if room and mark.get("name"): plan.remember(file, mark["name"], room)
    save(folder, doc); return mark


def remove_mark(folder, mark_id):
    doc = load(folder); doc["marks"] = [m for m in doc["marks"] if m["id"] != mark_id]; save(folder, doc)


def keep_asset(folder, doc, file, kind="photo", name=None, credit=None):
    """Copies material into the project and registers it."""
    folder = Path(folder); (folder / "assets").mkdir(exist_ok=True)
    asset_id = f"a{len(doc['assets']) + 1}"
    kept = folder / "assets" / f"{asset_id}{Path(name or file).suffix.lower() or '.jpg'}"
    shutil.copyfile(file, kept)
    doc["assets"].append({"id": asset_id, "file": str(kept), "kind": kind, **({"credit": credit} if credit else {})})
    return asset_id


def add_asset(folder, file, name=None, credit=None):
    """Puts a picture into the project's library and returns its id."""
    doc = load(folder); asset_id = keep_asset(folder, doc, file, "photo", name, credit); save(folder, doc); return asset_id


def assign(folder, need_id, asset_id):
    """Answers a request with a picture from the library, or (with None) takes the picture away again."""
    doc = load(folder); need = next((n for n in doc["needs"] if n["id"] == need_id), None)
    if not need: raise KeyError(f"no request {need_id}")
    if asset_id is not None and not any(a["id"] == asset_id for a in doc["assets"]): raise KeyError(f"no picture {asset_id}")
    need["asset"] = asset_id; need["status"] = "filled" if asset_id else "open"
    save(folder, doc); return need


def fill(folder, need_id, file, name=None, credit=None):
    asset_id = add_asset(folder, file, name, credit); return assign(folder, need_id, asset_id)


def set_text(folder, word, text):
    """The author's own correction of a recognised word. An empty text, or the original one, removes the correction."""
    doc = load(folder)
    if not 0 <= word < len(doc["words"]): raise KeyError(f"no word {word}")
    text = re.sub(r"\s+", " ", text or "").strip()[:40]
    # The AI's offer for this word is kept (switched off), so it is still there if the author changes their mind
    doc["corrections"] = [c for c in doc["corrections"] if not (c["word"] == word and c["by"] == "user")]
    if text and text != doc["words"][word]["text"]:
        for c in doc["corrections"]:
            if c["word"] == word: c["accepted"] = False
        doc["corrections"].append({"word": word, "text": text, "by": "user", "accepted": True})
    save(folder, doc); return text


def set_style(folder, patch):
    doc = load(folder); doc["style"] = clean_style({**doc["style"], **(patch if isinstance(patch, dict) else {})}); save(folder, doc); return doc["style"]


def change_beat(folder, beat_id, asset=..., text=..., remove=False):
    doc = load(folder); beat = next((b for b in doc["beats"] if b["id"] == beat_id), None)
    if not beat: raise KeyError(f"no beat {beat_id}")
    if remove: doc["beats"] = [b for b in doc["beats"] if b["id"] != beat_id]
    if asset is not ...:
        if asset is not None and not any(a["id"] == asset for a in doc["assets"]): raise KeyError(f"no picture {asset}")
        beat["asset"] = asset
    if text is not ...: beat["text"] = re.sub(r"\s+", " ", text or "").strip()[:40] or None
    save(folder, doc); return beat


def drop(folder, first, last, restore=False):
    """Cuts the words first..last out of the video, or puts them back."""
    doc = load(folder); count = len(doc["words"])
    kept = [False] * count
    for s in doc["edit"]["segments"]:
        for i in range(s["from"], s["to"] + 1): kept[i] = True
    for i in range(max(0, first), min(count - 1, last) + 1): kept[i] = restore
    segments = segments_of(kept)
    doc["edit"]["segments"] = segments; save(folder, doc); return segments


def add_beat(folder, kind, first, last, file=None, text=None, name=None, asset=None):
    """The author's own beat over the words first..last, with a picture (a file, or one already in the library) or a text."""
    doc = load(folder); first, last = sorted((int(first), int(last)))
    if kind not in MIN_BEAT: raise ValueError("kind must be full, backdrop, cutaway, title or zoom")
    if not 0 <= first <= last < len(doc["words"]): raise ValueError("no such words")
    text = re.sub(r"\s+", " ", text or "").strip()[:40] or None
    if kind == "title" and not text: raise ValueError("a title needs a text")
    item = {"id": f"b{max([int(b['id'][1:]) for b in doc['beats']] + [0]) + 1}", "kind": kind, "from": first, "to": last, "need": None, "text": text, "why": None, "by": "user", "accepted": True}
    if kind in PICTURED:
        if file: item["asset"] = keep_asset(folder, doc, file, "photo", name)
        elif asset and any(a["id"] == asset for a in doc["assets"]): item["asset"] = asset
        else: raise ValueError("a picture is needed")
    doc["beats"].append(item); save(folder, doc); return item


# ---------- progress, for anyone watching ----------
def apply(folder, ops):
    """Carries out operations proposed for the author's request (see suggest.edit)."""
    for o in ops:
        if o["op"] in ("cut", "restore"): drop(folder, o["from"], o["to"], restore=o["op"] == "restore")
        elif o["op"] == "text": set_text(folder, o["word"], o["to"])
        elif o["op"] in ("title", "zoom"): add_beat(folder, o["op"], o["from"], o["to"], text=o.get("text"))
        elif o["op"] == "emphasis":
            doc = load(folder); found = next((e for e in doc["emphasis"] if e["word"] == o["word"]), None)
            if found: found["accepted"] = o["on"]; found["by"] = "user"
            elif o["on"]: doc["emphasis"].append({"word": o["word"], "by": "user", "accepted": True})
            save(folder, doc)


def progress(folder, step, state, **facts):
    """Records where the pipeline is: one line per step, rewritten as it moves from running to done or failed."""
    path = Path(folder) / "status.json"
    steps = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    steps = [s for s in steps if s["step"] != step] + [{"step": step, "state": state, "at": round(time.time(), 1), **facts}]
    write_whole(path, json.dumps(steps, ensure_ascii=False))
