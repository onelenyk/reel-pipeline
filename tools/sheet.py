"""A contact sheet of a finished video: one frame from every insert and every lit room, to review the montage at a glance.
usage: ./reel run tools/sheet.py PROJECT [more]  -> out/sheet-PROJECT.jpg"""
import subprocess, sys
sys.path.insert(0, "/work")
from engine import project
for name in sys.argv[1:]:
    folder = f"/work/projects/{name}"; plan = project.resolve(project.load(folder)); times = []
    for b in plan["beats"]:
        marks = b.get("marks") or []
        if not marks: times.append((b["start"] + min(1.2, (b["end"] - b["start"]) / 2), b["kind"]))
        if marks and marks[0]["start"] - b["start"] > 1.5: times.append((b["start"] + 0.8, b["kind"]))
        for m in marks: times.append((m["start"] + min(1.0, (m["end"] - m["start"]) / 2), "room"))
    times = sorted(times)[:24]; print(name, [(round(t, 1), k) for t, k in times])
    cmd = ["ffmpeg", "-loglevel", "error", "-y"]
    for t, _ in times: cmd += ["-ss", f"{t:.2f}", "-i", f"{folder}/render.mp4"]
    rows = (len(times) + 7) // 8; cols = min(8, len(times))
    scale = "".join(f"[{i}:v]trim=end_frame=1,scale=240:426,drawtext=text='{t:.0f}s {k}':x=6:y=6:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.6[v{i}];" for i, (t, k) in enumerate(times))
    layout = "|".join(f"{(i % 8) * 240}_{(i // 8) * 426}" for i in range(len(times)))
    cmd += ["-filter_complex", scale + "".join(f"[v{i}]" for i in range(len(times))) + f"xstack=inputs={len(times)}:layout={layout}:fill=black", "-frames:v", "1", f"/work/out/sheet-{name}.jpg"]
    subprocess.run(cmd, check=True)
