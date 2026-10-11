"""Experiment: where does the time of a build go? usage: ./reel run lab/build_time.py IMG_7824"""
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, "/work")
from engine import media, project
name = sys.argv[1]; folder = Path("/work/projects") / name; doc = project.load(folder); t = project.resolve(doc); src = doc["sources"][0]
Path("/tmp/t.json").write_text(json.dumps(t, ensure_ascii=False)); w, h, fps = t["width"], t["height"], t["fps"]
def timed(work): began = time.time(); work(); return time.time() - began
keep = "+".join(f"between(t,{x:.3f},{y:.3f})" for x, y in t["spans"])
chain = ",".join([f"fps={fps}", f"select='{keep}'", "setpts=N/FRAME_RATE/TB", f"fps={fps}", media.tone_filter(src["hdr"]), f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}"])
graphics = timed(lambda: subprocess.run("node /work/renderer/render.mjs /tmp/t.json | cat > /dev/null", shell=True, check=True))
prepared = timed(lambda: media.ffmpeg("-i", src["file"], "-vf", chain, "-an", "-f", "null", "-"))
base = timed(lambda: media.ffmpeg("-i", src["file"], "-vf", chain, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-t", str(t["seconds"]), "/tmp/base.mp4"))
again = timed(lambda: media.ffmpeg("-i", "/tmp/base.mp4", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-an", "/tmp/again.mp4"))
print(f"{name}: video {t['seconds']} s | graphics alone {graphics:.0f} s | take decoded, cut and toned {prepared:.0f} s | the same, encoded {base:.0f} s | the ready base encoded again {again:.0f} s")
