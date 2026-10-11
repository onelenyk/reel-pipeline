"""Puts the voice of a test take over the picture of a real one, so the take can go through the whole pipeline and be watched:
media/blind-NAME.mp4. The lips do not match the words; everything else is as in a real take.
usage: ./reel run lab/blind/film.py NAME [NAME ...]"""
import json, random, sys
from pathlib import Path
from engine import media

WORK = Path(__file__).parent / "work"; MEDIA = Path("/work/media"); PICTURES = ["IMG_7821.MOV", "IMG_7824.MOV", "IMG_7811.MOV"]
for name in sys.argv[1:]:
    truth = json.loads((WORK / f"{name}.truth.json").read_text(encoding="utf-8")); rng = random.Random(name)
    source = MEDIA / rng.choice(PICTURES); facts = media.probe(source); seconds = truth["seconds"]
    start = rng.uniform(0, max(0, facts["seconds"] - seconds - 1)); out = MEDIA / f"blind-{name}.mp4"
    media.ffmpeg("-stream_loop", "-1", "-ss", f"{start:.2f}", "-i", str(source), "-i", str(WORK / f"{name}.wav"), "-map", "0:v", "-map", "1:a", "-t", f"{seconds:.2f}",
                 "-vf", f"{media.tone_filter(facts['hdr'])},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-r", "30",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-ar", "48000", str(out))
    print(out.name, f"{seconds:.0f} s, picture from {source.name} at {start:.0f} s")
