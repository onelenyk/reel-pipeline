"""Single frames of the graphics layer (plans, titles, subtitles), to judge a design without building the video.
On frames where the speaker shows through, the background is left grey. usage: ./reel run tools/stills.py PROJECT 28.9,35,43 -> out/still-PROJECT.jpg"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "/work")
from engine import project, render
name, times = sys.argv[1], sys.argv[2]; folder = Path(f"/work/projects/{name}")
timeline = project.resolve(project.load(folder)); (folder / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
Path("/work/out/stills").mkdir(parents=True, exist_ok=True)
subprocess.run(["node", str(render.RENDERER), str(folder / "timeline.json"), "--stills", times, f"/work/out/stills/{name}"], check=True)
files = [f"/work/out/stills/{name}-{float(t):.1f}.png" for t in times.split(",")]
cmd = ["ffmpeg", "-loglevel", "error", "-y"] + [x for f in files for x in ("-i", f)]
chain = "".join(f"color=c=0x808080:s=1080x1920[g{i}];[g{i}][{i}:v]overlay,scale=405:720[v{i}];" for i in range(len(files)))
subprocess.run(cmd + ["-filter_complex", chain + "".join(f"[v{i}]" for i in range(len(files))) + f"hstack=inputs={len(files)}" if len(files) > 1 else chain + "[v0]null", "-frames:v", "1", f"/work/out/still-{name}.jpg"], check=True)
print(f"out/still-{name}.jpg")
