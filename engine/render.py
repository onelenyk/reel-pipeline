"""Builds the finished video from a project document: ffmpeg cuts, colours, frames and mixes; the Node renderer draws."""
import hashlib, json, subprocess, tempfile, time
from pathlib import Path
from . import fonts, matte, media, project, sounds, spaces

RENDERER = Path(__file__).resolve().parent.parent / "renderer" / "render.mjs"
ZOOM = 0.12   # how much closer a zoom beat comes
PUNCH = 0.10  # how much closer the alternate framing is
FADE = 0.012  # seconds: the sound dips to nothing at each cut, so the join does not click
RAMP = 0.35   # seconds to get there and back


def render(folder):
    """Builds render.mp4. Progress and failures are recorded for anyone watching."""
    project.progress(folder, "render", "running", note="preparing")
    try:
        result = build(folder)
    except Exception as error:
        project.progress(folder, "render", "failed", error=str(error)[-300:]); raise
    project.progress(folder, "render", "done", seconds=result["took_seconds"]); return result


# The workspace's logo: small in a corner the whole time, or large over the last seconds, or both. It lies under
# everything that is drawn, so a caption or a picture on the whole frame is never hidden by it.
CORNER = (220, 120)   # the box the small logo fits in, near the upper left corner, clear of the phone's own buttons
BIG = (620, 420)      # the box of the large one, in the middle of the darkened frame
END = 2.5             # seconds of the large one at the end


def logo_graph(index, last, look, seconds, at=None):
    """The filters that lay the logo (ffmpeg input `index`) over the stream `last`; returns (filters, new last).
    With `at`, for one still frame at that second: what is on screen then, without moving in."""
    tail = max(0.0, seconds - END); corner, end = look in ("corner", "both"), look in ("end", "both")
    if at is not None: corner, end = corner and not (end and at >= tail), end and at >= tail
    if not corner and not end: return [], last
    out, a, b = [], f"{index}:v", f"{index}:v"
    if corner and end: out.append(f"[{index}:v]split[logo_a][logo_b]"); a, b = "logo_a", "logo_b"
    if corner:
        when = f":enable='lt(t,{tail:.3f})'" if end and at is None else ""
        out += [f"[{a}]scale={CORNER[0]}:{CORNER[1]}:force_original_aspect_ratio=decrease,format=rgba,colorchannelmixer=aa=0.92[logo_small]", f"[{last}][logo_small]overlay=56:150{when}[logo_1]"]; last = "logo_1"
    if end:
        when = f":enable='gte(t,{tail:.3f})'" if at is None else ""; rise = f",fade=t=in:st={tail:.3f}:d=0.4:alpha=1" if at is None else ""
        out += [f"[{b}]scale={BIG[0]}:{BIG[1]}:force_original_aspect_ratio=decrease,format=rgba{rise}[logo_big]", f"[{last}]drawbox=c=black@0.55:t=fill{when}[logo_dark]",
                f"[logo_dark][logo_big]overlay=(W-w)/2:(H-h)/2{when}[logo_2]"]; last = "logo_2"
    return out, last


def logo_of(folder, doc):
    """The logo this project's video shows, and how; None when its workspace has none or the style leaves it out."""
    look = doc["style"].get("logo", "corner"); file = spaces.logo(spaces.space_of(Path(folder).name))
    return (file, look) if file and look != "off" else None


STRIP = 48  # frames in the strip under the timeline


def strip(folder):
    """One wide picture with evenly spaced frames of the finished video."""
    folder = Path(folder); video = folder / "render.mp4"; seconds = media.probe(video)["seconds"]
    media.ffmpeg("-i", str(video), "-vf", f"fps={STRIP}/{max(seconds, 1):.3f},scale=54:96,tile={STRIP}x1", "-frames:v", "1", "-q:v", "5", str(folder / "strip.part.jpg"))
    (folder / "strip.part.jpg").replace(folder / f"strip{STRIP}.jpg")


SAMPLES = {"number": {"kind": "number", "value": "150", "unit": "м²", "caption": "площа будинку"}, "sticker": {"kind": "sticker", "text": "Біля лісу", "icon": "🌲"},
           "list": {"kind": "list", "title": "У будинку", "items": ["Гардеробна", "Пральня", "Тераса"]}}


def sample(timeline, what):
    """A moment of the video that shows one kind of decoration, for the gallery: a made-up number, sticker, list or break
    laid over a moment where the speaker is alone in the frame, or a real moment of the project's own plan or picture.
    Returns the second to look at; None when the project has nothing of that kind."""
    taken = [(b["start"], b["end"]) for b in timeline["beats"] if b["kind"] in ("full", "cutaway", "title")]
    alone = next((l["start"] + 0.7 for l in timeline["lines"] if l["end"] - l["start"] > 1.0 and not any(a - 1.2 < l["start"] + 0.7 < b + 0.5 for a, b in taken)), None)
    if what == "plan":
        walked = [m for b in timeline["beats"] for m in b.get("marks", []) if m.get("route")]; return walked[0]["start"] + 0.55 if walked else None
    if what == "picture":
        shown = [b for b in timeline["beats"] if b["kind"] == "cutaway" and b.get("file")]; return shown[0]["start"] + 1.0 if shown else None
    if alone is None: return None
    timeline["overlays"] = []; timeline["breaks"] = []
    if what == "break": timeline["breaks"] = [{"id": "demo", "text": "Планування", "start": round(alone - 0.5, 3), "end": round(alone + 0.5, 3)}]
    elif what in SAMPLES:
        made = {**SAMPLES[what], "id": "demo", "start": round(alone - 1.2, 3), "end": round(alone + 2.0, 3), "side": "left"}
        if what == "list": made["items"] = [{"text": text, "start": round(alone - 1.1 + 0.2 * n, 3)} for n, text in enumerate(made["items"])]
        timeline["overlays"] = [made]
    return alone


def still(folder, t, out, style=None, demo=None):
    """One frame of the video as it would be built now, at second `t` of it: for seeing a change without building.
    The speaker is shown as shot (no cut-out behind a backdrop, no zoom); everything drawn over the picture is as it will be.
    `style` tries other choices on without keeping them; `demo` picks the moment itself, one that shows that kind of decoration."""
    folder = Path(folder); doc = project.load(folder)
    if style: doc["style"] = project.clean_style({**doc["style"], **style})
    timeline = project.resolve(doc); source = doc["sources"][0]
    if demo:
        t = sample(timeline, demo)
        if t is None: raise LookupError(f"this project has nothing to show a {demo} on")
    timeline["style"] = {**timeline["style"], **fonts.face(timeline["style"].get("font"))}
    width, height = timeline["width"], timeline["height"]; t = max(0.0, min(float(t), max(0.0, timeline["seconds"] - 0.05)))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); (tmp / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        drawn = subprocess.run(["node", str(RENDERER), str(tmp / "timeline.json"), "--stills", f"{t:.3f}", str(tmp / "layer")], capture_output=True, text=True)
        if drawn.returncode: raise RuntimeError("the graphics could not be drawn: " + drawn.stderr[-300:])
        layer = next(tmp.glob("layer-*.png"))   # the renderer names it by the time, rounded its own way
        # where this moment is in the take: the stretches that stay, laid end to end
        at, passed = 0.0, 0.0
        for a, b in timeline["spans"]:
            if t <= passed + (b - a): at = a + (t - passed); break
            passed += b - a; at = b
        covered = any(b["kind"] == "full" and b["start"] + 0.3 <= t <= b["end"] - 0.3 for b in timeline["beats"])
        if covered: media.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s={width}x{height}", "-i", str(layer), "-filter_complex", "[0][1]overlay,scale=540:-2", "-frames:v", "1", "-q:v", "4", str(out))
        else:
            shown = logo_of(folder, doc); extra, under = (logo_graph(2, "v", shown[1], timeline["seconds"], at=t)) if shown else ([], "v")
            media.ffmpeg("-ss", f"{at:.3f}", "-i", source["file"], "-i", str(layer), *(["-i", str(shown[0])] if extra else []), "-filter_complex",
                         ";".join([f"[0:v]{media.tone_filter(source['hdr'])},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[v]", *extra, f"[{under}][1]overlay,scale=540:-2"]), "-frames:v", "1", "-q:v", "4", str(out))
    return out


def build(folder):
    folder = Path(folder); doc = project.load(folder); timeline = project.resolve(doc); source = doc["sources"][0]
    width, height, fps = timeline["width"], timeline["height"], timeline["fps"]
    timeline["style"] = {**timeline["style"], **fonts.face(timeline["style"].get("font"))}
    (folder / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    keep = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in timeline["spans"])
    # Even frames first: a phone's frames do not arrive evenly, and cutting by counting them would let the picture run ahead of the sound
    chain = [f"fps={fps}", f"select='{keep}'", "setpts=N/FRAME_RATE/TB", f"fps={fps}", media.tone_filter(source["hdr"]),
             f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}"]
    # Backdrops: the speaker, cut out, over a picture. Each needs a matte of that stretch of the take.
    inputs, graph, last, mattes, wanted = ["-i", source["file"]], [f"[0:v]{','.join(chain)}[v0]"], "v0", {}, set()
    for index, b in enumerate(x for x in timeline["beats"] if x["kind"] == "backdrop"):
        seconds = b["end"] - b["start"]
        # Cutting the speaker out is slow and depends only on which stretch of the take it is: a cut-out made before is used again
        mark = hashlib.sha1(json.dumps([source["file"], Path(source["file"]).stat().st_mtime_ns, round(b["source_start"], 3), round(seconds, 3), fps, width, height]).encode()).hexdigest()[:16]
        file = folder / f"matte-{mark}.mkv"; wanted.add(file.name)
        if file.exists(): mattes[b["id"]] = {"reused": True}
        else:
            project.progress(folder, "render", "running", note=f"cutting the speaker out for an insert ({index + 1})")
            part = folder / f"matte-{mark}.part.mkv"; mattes[b["id"]] = matte.matte(source["file"], source["hdr"], b["source_start"], seconds, fps, (width, height), part); part.replace(file)
        n = inputs.count("-i")
        inputs += ["-loop", "1", "-t", f"{seconds:.3f}", "-i", b["file"], "-i", str(file)]
        fade = f"fade=in:st=0:d=0.3:alpha=1,fade=out:st={seconds - 0.3:.3f}:d=0.3:alpha=1"
        graph += [f"[{last}]split[keep{index}][cut{index}]",
                  f"[cut{index}]trim={b['start']:.3f}:{b['end']:.3f},setpts=PTS-STARTPTS,format=rgba[person{index}]",
                  f"[{n + 1}:v]scale={width}:{height},gblur=sigma=3,format=gray[alpha{index}]",
                  f"[person{index}][alpha{index}]alphamerge[front{index}]",
                  # The picture fills the frame, slightly darkened so the speaker stands out
                  f"[{n}:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},eq=brightness=-0.06,fps={fps}[back{index}]",
                  f"[back{index}][front{index}]overlay=shortest=1,format=yuva420p,{fade},setpts=PTS+{b['start']:.3f}/TB[scene{index}]",
                  f"[keep{index}][scene{index}]overlay=enable='between(t,{b['start']:.3f},{b['end']:.3f})':eof_action=pass[v{index + 1}]"]
        last = f"v{index + 1}"
    chain = []
    zooms = [b for b in timeline["beats"] if b["kind"] == "zoom"]
    punches = timeline.get("punches", [])
    if zooms or punches:
        # One smooth move in and back per zoom beat; the alternate framing switches at once, like a change of shot.
        # Both are centred a little above the middle, where the face is.
        z = "1+" + "+".join([f"{ZOOM}*(clip((in_time-{b['start']:.3f})/{RAMP},0,1)-clip((in_time-{b['end']:.3f})/{RAMP},0,1))" for b in zooms] +
                            [f"{PUNCH}*gte(in_time,{a - 0.001:.3f})*lt(in_time,{b - 0.001:.3f})" for a, b in punches])
        graph.append(f"[{last}]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih*0.42-(ih/zoom*0.42)':d=1:s={width}x{height}:fps={fps}[zoomed]"); last = "zoomed"
    shown = logo_of(folder, doc)
    if shown:
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{timeline['seconds']:.3f}", "-i", str(shown[0])]
        extra, last = logo_graph(inputs.count("-i") - 1, last, shown[1], timeline["seconds"]); graph += extra
    level = doc["style"]["level"]
    dip = "*".join(f"clip(abs(t-{edge:.3f})/{FADE},0,1)" for a, b in timeline["spans"][:60] for edge in (a, b))
    audio = f"volume='{dip}':eval=frame,aselect='{keep}',asetpts=N/SR/TB,highpass=f=80," + ("arnndn=m=/opt/rnnoise/std.rnnn," if doc.get("audio", {}).get("denoise") == "light" else "") + f"loudnorm=I={level + 1.5}:TP=-1.5:LRA=7,aresample=48000"
    # The sounds of what appears on screen go under the voice after it is levelled, so they do not change how loud it is
    effects = sounds.track(timeline, folder / "sounds.wav")
    if effects: inputs += ["-i", str(effects)]; audio += f"[voice];[voice][{inputs.count('-i') - 1}:a]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.89:level=disabled"
    out = folder / "render.mp4"; draft = folder / "render.part.mp4"
    started = time.time()
    project.progress(folder, "render", "running", note="building the video")
    # The graphics layer arrives as raw frames with transparency on ffmpeg's standard input
    drawer = subprocess.Popen(["node", str(RENDERER), str(folder / "timeline.json")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        layer = inputs.count("-i")
        media.ffmpeg(*inputs, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
                     "-filter_complex", ";".join(graph) + f";[{last}][{layer}:v]overlay=shortest=1:format=auto,format=yuv420p[v];[0:a]{audio}[a]",
                     "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-t", f"{timeline['seconds']:.3f}", "-movflags", "+faststart", str(draft), stdin=drawer.stdout)
    finally:
        drawer.stdout.close(); errors = drawer.stderr.read().decode(errors="replace"); drawer.wait()
    if drawer.returncode not in (0, None) and "EPIPE" not in errors: raise media.ToolError(f"renderer failed:\n{errors[-1500:]}")
    draft.replace(out)  # the previous render stays playable until the new one is whole
    for old in folder.glob("matte-*.mkv"):
        if old.name not in wanted: old.unlink()  # cut-outs of inserts that are no longer there
    project.progress(folder, "render", "running", note="strip"); strip(folder)
    return {"file": str(out), "seconds": timeline["seconds"], "took_seconds": round(time.time() - started, 1), "beats_drawn": [b["kind"] for b in timeline["beats"]], "mattes": mattes,
            "waiting_for_material": [n["what"] for n in doc.get("needs", []) if n["status"] == "open"], "sound": media.loudness(out)}
