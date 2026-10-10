"""Builds the finished video from a project document: ffmpeg cuts, colours, frames and mixes; the Node renderer draws."""
import json, subprocess, time
from pathlib import Path
from . import media, project

RENDERER = Path(__file__).resolve().parent.parent / "renderer" / "render.mjs"
ZOOM = 0.12   # how much closer a zoom beat comes
RAMP = 0.35   # seconds to get there and back


def render(folder):
    folder = Path(folder); doc = project.load(folder); timeline = project.resolve(doc); source = doc["sources"][0]
    width, height, fps = timeline["width"], timeline["height"], timeline["fps"]
    (folder / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
    keep = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in timeline["spans"])
    chain = [media.tone_filter(source["hdr"]), f"select='{keep}'", "setpts=N/FRAME_RATE/TB", f"fps={fps}",
             f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}"]
    zooms = [b for b in timeline["beats"] if b["kind"] == "zoom"]
    if zooms:
        # One smooth move in and back per beat, centred a little above the middle, where the face is
        z = "1+" + "+".join(f"{ZOOM}*(clip((in_time-{b['start']:.3f})/{RAMP},0,1)-clip((in_time-{b['end']:.3f})/{RAMP},0,1))" for b in zooms)
        chain.append(f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih*0.42-(ih/zoom*0.42)':d=1:s={width}x{height}:fps={fps}")
    level = doc["audio"]["level"]
    audio = f"aselect='{keep}',asetpts=N/SR/TB,highpass=f=80," + ("arnndn=m=/opt/rnnoise/std.rnnn," if doc["audio"].get("denoise") == "light" else "") + f"loudnorm=I={level + 1.5}:TP=-1.5:LRA=7,aresample=48000"
    out = folder / "render.mp4"
    started = time.time()
    # The graphics layer arrives as raw frames with transparency on ffmpeg's standard input
    drawer = subprocess.Popen(["node", str(RENDERER), str(folder / "timeline.json")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        media.ffmpeg("-i", source["file"], "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0",
                     "-filter_complex", f"[0:v]{','.join(chain)}[base];[base][1:v]overlay=shortest=1:format=auto,format=yuv420p[v];[0:a]{audio}[a]",
                     "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out), stdin=drawer.stdout)
    finally:
        drawer.stdout.close(); errors = drawer.stderr.read().decode(errors="replace"); drawer.wait()
    if drawer.returncode not in (0, None) and "EPIPE" not in errors: raise media.ToolError(f"renderer failed:\n{errors[-1500:]}")
    return {"file": str(out), "seconds": timeline["seconds"], "took_seconds": round(time.time() - started, 1), "beats_drawn": [b["kind"] for b in timeline["beats"]],
            "waiting_for_material": [n["what"] for n in doc.get("needs", []) if n["status"] == "open"], "sound": media.loudness(out)}
