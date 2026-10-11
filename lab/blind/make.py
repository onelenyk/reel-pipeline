#!/usr/bin/env python3
"""Speaks the test takes with the Mac's Ukrainian voice: lab/blind/work/NAME.mp4. Run on the Mac itself: python3 lab/blind/make.py"""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from samples import SAMPLES

WORK = Path(__file__).parent / "work"; WORK.mkdir(exist_ok=True)
for s in SAMPLES:
    # a pause between the lines, as between attempts; "..." inside a failed attempt is a hesitation
    text = " [[slnc 900]] ".join(line[2:].replace("...", " [[slnc 500]] ") for line in s["lines"])
    voice = WORK / f"{s['name']}.aiff"; out = WORK / f"{s['name']}.mp4"
    subprocess.run(["say", "-v", "Lesya (Enhanced)", "-r", "175", "-o", str(voice), text], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x10243a:s=720x1280:r=30", "-i", str(voice),
                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-ar", "48000", str(out)], check=True)
    voice.unlink(); print(out)
