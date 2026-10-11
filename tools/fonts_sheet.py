"""One frame of a project in each of several fonts, side by side: to choose a font, or to check that a family has Cyrillic.
usage: ./reel run tools/fonts_sheet.py IMG_7824 12 Montserrat Unbounded "Russo One"  -> out/fonts.jpg"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, "/work")
from engine import fonts, project, render
name, t, families = sys.argv[1], sys.argv[2], sys.argv[3:]; folder = Path(f"/work/projects/{name}"); Path("/work/out/stills").mkdir(parents=True, exist_ok=True); files = []
for family in families:
    timeline = project.resolve(project.load(folder)); face = fonts.face(family); timeline["style"] = {**timeline["style"], "font": family, **face}
    if face.get("font_note"): print(face["font_note"])
    Path("/tmp/t.json").write_text(json.dumps(timeline, ensure_ascii=False)); slug = family.replace(" ", "-")
    subprocess.run(["node", str(render.RENDERER), "/tmp/t.json", "--stills", t, f"/work/out/stills/font-{slug}"], check=True); files.append((family, f"/work/out/stills/font-{slug}-{float(t):.1f}.png"))
cmd = ["ffmpeg", "-loglevel", "error", "-y"] + [x for _, f in files for x in ("-i", f)]
chain = "".join(f"color=c=0x6b7785:s=1080x1920[g{i}];[g{i}][{i}:v]overlay,crop=1080:760:0:1000,scale=540:-1,drawtext=text='{family}':x=8:y=8:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6[v{i}];" for i, (family, _) in enumerate(files))
rows = "".join(f"[v{i}]" for i in range(len(files))) + f"xstack=inputs={len(files)}:layout=" + "|".join(f"{(i % 4) * 540}_{(i // 4) * 380}" for i in range(len(files))) + ":fill=black"
subprocess.run(cmd + ["-filter_complex", chain + rows, "-frames:v", "1", "/work/out/fonts.jpg"], check=True); print("out/fonts.jpg")
