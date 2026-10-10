"""Builds the finished video from a project document: ffmpeg cuts, colours, frames and mixes; the Node renderer draws."""
import json, subprocess, time
from pathlib import Path
from . import matte, media, project

RENDERER = Path(__file__).resolve().parent.parent / "renderer" / "render.mjs"
ZOOM = 0.12   # how much closer a zoom beat comes
RAMP = 0.35   # seconds to get there and back


def render(folder):
    """Builds render.mp4. Progress and failures are recorded for anyone watching."""
    project.progress(folder, "render", "running", note="preparing")
    try:
        result = build(folder)
    except Exception as error:
        project.progress(folder, "render", "failed", error=str(error)[-300:]); raise
    project.progress(folder, "render", "done", seconds=result["took_seconds"]); return result


def build(folder):
    folder = Path(folder); doc = project.load(folder); timeline = project.resolve(doc); source = doc["sources"][0]
    width, height, fps = timeline["width"], timeline["height"], timeline["fps"]
    (folder / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    keep = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in timeline["spans"])
    # Even frames first: a phone's frames do not arrive evenly, and cutting by counting them would let the picture run ahead of the sound
    chain = [f"fps={fps}", f"select='{keep}'", "setpts=N/FRAME_RATE/TB", f"fps={fps}", media.tone_filter(source["hdr"]),
             f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}"]
    # Backdrops: the speaker, cut out, over a picture. Each needs a matte of that stretch of the take.
    inputs, graph, last, mattes = ["-i", source["file"]], [f"[0:v]{','.join(chain)}[v0]"], "v0", {}
    for index, b in enumerate(x for x in timeline["beats"] if x["kind"] == "backdrop"):
        seconds = b["end"] - b["start"]; file = folder / f"matte-{b['id']}.mkv"
        project.progress(folder, "render", "running", note=f"cutting the speaker out for an insert ({index + 1})")
        mattes[b["id"]] = matte.matte(source["file"], source["hdr"], b["source_start"], seconds, fps, (width, height), file)
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
    if zooms:
        # One smooth move in and back per beat, centred a little above the middle, where the face is
        z = "1+" + "+".join(f"{ZOOM}*(clip((in_time-{b['start']:.3f})/{RAMP},0,1)-clip((in_time-{b['end']:.3f})/{RAMP},0,1))" for b in zooms)
        graph.append(f"[{last}]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih*0.42-(ih/zoom*0.42)':d=1:s={width}x{height}:fps={fps}[zoomed]"); last = "zoomed"
    level = doc["style"]["level"]
    audio = f"aselect='{keep}',asetpts=N/SR/TB,highpass=f=80," + ("arnndn=m=/opt/rnnoise/std.rnnn," if doc.get("audio", {}).get("denoise") == "light" else "") + f"loudnorm=I={level + 1.5}:TP=-1.5:LRA=7,aresample=48000"
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
    return {"file": str(out), "seconds": timeline["seconds"], "took_seconds": round(time.time() - started, 1), "beats_drawn": [b["kind"] for b in timeline["beats"]], "mattes": mattes,
            "waiting_for_material": [n["what"] for n in doc.get("needs", []) if n["status"] == "open"], "sound": media.loudness(out)}
