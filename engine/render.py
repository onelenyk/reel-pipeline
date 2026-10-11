"""Builds the finished video from a project document: ffmpeg cuts, colours, frames and mixes; the Node renderer draws."""
import hashlib, json, subprocess, tempfile, time
from pathlib import Path
from . import fonts, matte, media, project

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


STRIP = 48  # frames in the strip under the timeline


def strip(folder):
    """One wide picture with evenly spaced frames of the finished video."""
    folder = Path(folder); video = folder / "render.mp4"; seconds = media.probe(video)["seconds"]
    media.ffmpeg("-i", str(video), "-vf", f"fps={STRIP}/{max(seconds, 1):.3f},scale=54:96,tile={STRIP}x1", "-frames:v", "1", "-q:v", "5", str(folder / "strip.part.jpg"))
    (folder / "strip.part.jpg").replace(folder / f"strip{STRIP}.jpg")


def still(folder, t, out):
    """One frame of the video as it would be built now, at second `t` of it: for seeing a change without building.
    The speaker is shown as shot (no cut-out behind a backdrop, no zoom); everything drawn over the picture is as it will be."""
    folder = Path(folder); doc = project.load(folder); timeline = project.resolve(doc); source = doc["sources"][0]
    timeline["style"] = {**timeline["style"], **fonts.face(timeline["style"].get("font"))}
    width, height = timeline["width"], timeline["height"]; t = max(0.0, min(float(t), max(0.0, timeline["seconds"] - 0.05)))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); (tmp / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        drawn = subprocess.run(["node", str(RENDERER), str(tmp / "timeline.json"), "--stills", f"{t:.3f}", str(tmp / "layer")], capture_output=True, text=True)
        if drawn.returncode: raise RuntimeError("the graphics could not be drawn: " + drawn.stderr[-300:])
        layer = tmp / f"layer-{t:.1f}.png"
        # where this moment is in the take: the stretches that stay, laid end to end
        at, passed = 0.0, 0.0
        for a, b in timeline["spans"]:
            if t <= passed + (b - a): at = a + (t - passed); break
            passed += b - a; at = b
        covered = any(b["kind"] == "full" and b["start"] + 0.3 <= t <= b["end"] - 0.3 for b in timeline["beats"])
        if covered: media.ffmpeg("-f", "lavfi", "-i", f"color=c=black:s={width}x{height}", "-i", str(layer), "-filter_complex", "[0][1]overlay,scale=540:-2", "-frames:v", "1", "-q:v", "4", str(out))
        else:
            media.ffmpeg("-ss", f"{at:.3f}", "-i", source["file"], "-i", str(layer), "-filter_complex",
                         f"[0:v]{media.tone_filter(source['hdr'])},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}[v];[v][1]overlay,scale=540:-2", "-frames:v", "1", "-q:v", "4", str(out))
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
    level = doc["style"]["level"]
    dip = "*".join(f"clip(abs(t-{edge:.3f})/{FADE},0,1)" for a, b in timeline["spans"][:60] for edge in (a, b))
    audio = f"volume='{dip}':eval=frame,aselect='{keep}',asetpts=N/SR/TB,highpass=f=80," + ("arnndn=m=/opt/rnnoise/std.rnnn," if doc.get("audio", {}).get("denoise") == "light" else "") + f"loudnorm=I={level + 1.5}:TP=-1.5:LRA=7,aresample=48000"
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
