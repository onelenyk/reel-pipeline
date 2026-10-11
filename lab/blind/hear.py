"""Recognises every test take and keeps the words (work/NAME.words.json), so that scoring them needs only the AI.
Prints how much of what was said was heard. usage: ./reel run lab/blind/hear.py"""
import difflib, json, re
from pathlib import Path
from engine import speech

WORK = Path(__file__).parent / "work"
tokens = lambda text: re.sub(r"[^\w\s'-]", " ", text.lower().replace("’", "'").replace("ʼ", "'")).split()
for truth in sorted(WORK.glob("*.truth.json")):
    s = json.loads(truth.read_text(encoding="utf-8")); kept = WORK / f"{s['name']}.words.json"
    if not kept.exists(): kept.write_text(json.dumps(speech.transcribe(WORK / f"{s['name']}.wav")["words"], ensure_ascii=False))
    said = tokens(" ".join(l["text"] for l in s["lines"])); got = tokens(" ".join(w["text"] for w in json.loads(kept.read_text())))
    ops = difflib.SequenceMatcher(None, said, got).get_opcodes()
    print(f"{s['name']} {s['voice']} {s['pace']} noise {s['noise']}: {sum(i2 - i1 for op, i1, i2, _, _ in ops if op == 'equal') / len(said):.0%}",
          [f"{' '.join(said[i1:i2])} → {' '.join(got[j1:j2])}" for op, i1, i2, j1, j2 in ops if op == "replace"], flush=True)
