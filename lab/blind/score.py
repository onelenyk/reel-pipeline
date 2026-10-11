"""Experiment: the pipeline's steps on takes whose right answer is known (lab/blind/samples.py), without building any video.
usage: python3 lab/blind/make.py; ./reel run lab/blind/score.py [fresh]

  heard    how much of what was said is in the transcript
  text     how close the text left after the review is to the lines that should stay; then the words wrongly left and wrongly cut
  rooms    which of the rooms walked through got a moment
  numbers  which of the figures got an overlay; then every overlay proposed
"""
import difflib, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from samples import SAMPLES, said, ideal
from engine import speech, suggest

WORK = Path(__file__).parent / "work"; fresh = "fresh" in sys.argv


def tokens(text): return re.sub(r"[^\w\s'-]", " ", text.lower().replace("’", "'").replace("ʼ", "'")).split()
def close(a, b): return sum(m.size for m in difflib.SequenceMatcher(None, a, b).get_matching_blocks()) / max(len(a), 1)
def stem(word): return re.sub(r"[^\w]", "", word.lower())[:5]


total = {"heard": [], "text": [], "rooms": [0, 0], "numbers": [0, 0], "extra": 0, "lost": 0}
for s in SAMPLES:
    kept_file = WORK / f"{s['name']}.json"
    if kept_file.exists() and not fresh: words = json.loads(kept_file.read_text())
    else: words = speech.transcribe(WORK / f"{s['name']}.mp4")["words"]; kept_file.write_text(json.dumps(words, ensure_ascii=False))
    words = speech.spelled(words, speech.vocabulary())   # a kept transcript gets today's vocabulary
    got = tokens(" ".join(w["text"] for w in words)); heard = close(tokens(said(s)), got)
    cuts = suggest.review(words, fresh=fresh); gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    left = tokens(" ".join(w["text"] for i, w in enumerate(words) if i not in gone)); want = tokens(ideal(s))
    # the right text is judged against what was heard of it, so that a misheard word is not counted twice
    ops = difflib.SequenceMatcher(None, want, left).get_opcodes()
    extra = [" ".join(left[j1:j2]) for op, i1, i2, j1, j2 in ops if op == "insert"]; lost = [" ".join(want[i1:i2]) for op, i1, i2, j1, j2 in ops if op == "delete"]
    other = [f"{' '.join(want[i1:i2])} → {' '.join(left[j1:j2])}" for op, i1, i2, j1, j2 in ops if op == "replace"]
    shown = [w if i not in gone else {**w, "text": "…"} for i, w in enumerate(words)]
    moments = [m for m in suggest.moments(shown, [(0, len(words) - 1)]) if m["from"] not in gone]
    named = [r for r in s["rooms"] if any(stem(r) in {stem(x) for x in re.split(r"[\s-]", m["name"])} or stem(m["name"]) == stem(r) for m in moments)]
    made = suggest.decorate(words, gone, [], fresh=fresh); figures = [str(o.get("value")) for o in made if o["kind"] == "number"]
    hit = [n for n in s["numbers"] if n in figures]
    print(f"\n== {s['name']}: heard {heard:.0%}, text {close(want, left):.0%}, {len(cuts)} cuts, rooms {len(named)}/{len(s['rooms'])}, numbers {len(hit)}/{len(s['numbers'])}")
    for c in cuts: print("   cut:", c.get("why"), "|", " ".join(w["text"] for w in words[c["from"]:c["to"] + 1])[:110])
    if extra: print("   LEFT BY MISTAKE:", extra)
    if lost: print("   CUT BY MISTAKE:", lost)
    if other: print("   differs:", other)
    print("   moments:", [m["name"] for m in moments], "| missed:", [r for r in s["rooms"] if r not in named])
    print("   overlays:", [(o["kind"], o.get("value") or o.get("text") or o.get("title"), o.get("unit") or o.get("icon") or "") for o in made], "| missed:", [n for n in s["numbers"] if n not in hit])
    total["heard"].append(heard); total["text"].append(close(want, left)); total["extra"] += sum(len(e.split()) for e in extra); total["lost"] += sum(len(e.split()) for e in lost)
    total["rooms"][0] += len(named); total["rooms"][1] += len(s["rooms"]); total["numbers"][0] += len(hit); total["numbers"][1] += len(s["numbers"])
n = len(SAMPLES)
print(f"\nTOTAL over {n} takes: heard {sum(total['heard']) / n:.0%}, text {sum(total['text']) / n:.0%}, words left by mistake {total['extra']}, cut by mistake {total['lost']}, "
      f"rooms {total['rooms'][0]}/{total['rooms'][1]}, numbers {total['numbers'][0]}/{total['numbers'][1]}")
