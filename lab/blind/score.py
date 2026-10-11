"""Experiment: the pipeline's steps on takes whose right answer is known (lab/blind/samples.py), without building any video.
usage: lab/blind/.venv/bin/python lab/blind/make.py; ./reel run lab/blind/score.py [fresh] [NAME ...]

For every take: how much of what was said was heard; which failed attempts and asides the review cut, by kind, and which
lines that should stay it damaged; which rooms got a moment; which figures got an overlay. The table goes to out/blind.md.
A line's words are found by when it was spoken, so the result does not depend on how the words were heard.
"""
import difflib, json, re, sys, time
from pathlib import Path
from engine import speech, suggest

WORK = Path(__file__).parent / "work"; fresh = "fresh" in sys.argv; only = [a for a in sys.argv[1:] if a != "fresh"]


def tokens(text): return re.sub(r"[^\w\s'-]", " ", text.lower().replace("’", "'").replace("ʼ", "'")).split()
def close(a, b): return sum(m.size for m in difflib.SequenceMatcher(None, a, b).get_matching_blocks()) / max(len(a), 1)
def stem(word): return re.sub(r"[^\w]", "", word.lower())[:5]


kinds, damaged, rows, heard_all, rooms_all, numbers_all, mistakes = {}, [], [], [], [0, 0], [0, 0], []
for truth_file in sorted(WORK.glob("*.truth.json")):
    s = json.loads(truth_file.read_text(encoding="utf-8"))
    if only and s["name"] not in only: continue
    kept_file = WORK / f"{s['name']}.words.json"; began = time.time()
    if kept_file.exists() and not fresh: words = json.loads(kept_file.read_text())
    else: words = speech.transcribe(WORK / f"{s['name']}.wav")["words"]; kept_file.write_text(json.dumps(words, ensure_ascii=False))
    words = speech.spelled(words, speech.vocabulary())   # a kept transcript gets today's vocabulary
    heard = close(tokens(" ".join(l["text"] for l in s["lines"])), tokens(" ".join(w["text"] for w in words)))
    cuts = suggest.review(words, fresh=fresh); gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    # the share of each line's words that was cut
    lines = s["lines"]; share = []
    for n, line in enumerate(lines):
        low = (lines[n - 1]["end"] + line["start"]) / 2 if n else 0; high = (line["end"] + lines[n + 1]["start"]) / 2 if n + 1 < len(lines) else 1e9
        mine = [i for i, w in enumerate(words) if low <= (w["start"] + w["end"]) / 2 < high]
        share.append((sum(i in gone for i in mine) / len(mine)) if mine else None)
    caught = missed = 0; notes = []
    for n, line in enumerate(lines):
        if share[n] is None: continue
        show = lambda k: " ".join(w["text"] for w in words if lines[k]["start"] - 0.3 <= (w["start"] + w["end"]) / 2 <= lines[k]["end"] + 0.4)
        if line["keep"]:
            # said twice, either telling may be the one that goes
            twin = n and lines[n - 1]["kind"] == "repeat"
            if share[n] > 0.2 and not (twin and (share[n - 1] or 0) < 0.2): damaged.append((s["name"], f"{share[n]:.0%}", show(n))); notes.append(f"damaged: {show(n)[:60]}")
            continue
        ok = share[n] >= 0.8 or (line["kind"] == "repeat" and n + 1 < len(lines) and (share[n + 1] or 0) >= 0.8 and share[n] <= 0.2)
        tally = kinds.setdefault(line["kind"], [0, 0]); tally[1] += 1; tally[0] += ok; caught += ok; missed += not ok
        if not ok: mistakes.append((s["name"], line["kind"], show(n))); notes.append(f"left {line['kind']}: {show(n)[:50]}")
    shown = [w if i not in gone else {**w, "text": "…"} for i, w in enumerate(words)]
    moments = [m for m in suggest.moments(shown, [(0, len(words) - 1)]) if m["from"] not in gone]
    named = [r for r in s["rooms"] if any(stem(r) in {stem(x) for x in re.split(r"[\s-]", m["name"])} | {stem(m["name"])} for m in moments)]
    made = suggest.decorate(words, gone, [], fresh=fresh); figures = [str(o.get("value")) for o in made if o["kind"] == "number"]
    hit = [n for n in s["numbers"] if n in figures]
    heard_all.append(heard); rooms_all[0] += len(named); rooms_all[1] += len(s["rooms"]); numbers_all[0] += len(hit); numbers_all[1] += len(s["numbers"])
    rows.append(f"| {s['name']} | {s['voice']} {s['pace']} | {s['seconds']:.0f} | {heard:.0%} | {caught}/{caught + missed} | {len(named)}/{len(s['rooms'])} | {len(hit)}/{len(s['numbers'])} | {'; '.join(notes) or ''} |")
    print(rows[-1], f"({time.time() - began:.0f} s)", flush=True)
    if set(s["rooms"]) - set(named): print("   rooms missed:", sorted(set(s["rooms"]) - set(named)), "| moments:", [m["name"] for m in moments], flush=True)

report = ["# Takes with a known right answer", "", f"{len(rows)} takes, heard {sum(heard_all) / max(len(rows), 1):.0%} on average, rooms {rooms_all[0]}/{rooms_all[1]}, figures {numbers_all[0]}/{numbers_all[1]}, "
          f"lines that should stay and were damaged: {len(damaged)}.", "", "| What should be cut | Cut | Of |", "|---|---|---|"]
report += [f"| {kind} | {a} | {b} |" for kind, (a, b) in sorted(kinds.items())]
report += ["", "| Take | Voice | Seconds | Heard | Cut right | Rooms | Figures | Notes |", "|---|---|---|---|---|---|---|---|"] + rows
report += ["", "## Left by mistake", ""] + [f"- {n}, {kind}: {text}" for n, kind, text in mistakes] + ["", "## Damaged", ""] + [f"- {n}, {part} cut: {text}" for n, part, text in damaged]
Path("/work/out/blind.md").write_text("\n".join(report) + "\n", encoding="utf-8"); print("\n".join(report[:9 + len(kinds)]))
