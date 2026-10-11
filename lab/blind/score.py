"""Experiment: the pipeline's steps on takes whose right answer is known (lab/blind/samples.py), without building any video.
usage: lab/blind/.venv/bin/python lab/blind/make.py; ./reel run lab/blind/score.py [fresh] [NAME ...]

For every take: how much of what was said was heard; which failed attempts and asides the review cut, by kind, and which
lines that should stay it damaged; which rooms got a moment; which figures got an overlay. The table goes to out/blind.md.
A line's words are found by when it was spoken, so the result does not depend on how the words were heard.
"""
import difflib, json, re, sys, time
from pathlib import Path
from engine import project, speech, suggest

WORK = Path(__file__).parent / "work"; fresh = "fresh" in sys.argv; only = [a for a in sys.argv[1:] if a != "fresh"]


def tokens(text): return re.sub(r"[^\w\s'-]", " ", text.lower().replace("’", "'").replace("ʼ", "'")).split()
def close(a, b): return sum(m.size for m in difflib.SequenceMatcher(None, a, b).get_matching_blocks()) / max(len(a), 1)
def stem(word): return re.sub(r"[^\w]", "", word.lower())[:5]


sound, audible, clipped = [0, 0, 0, 0], [], []
unheard, kinds, damaged, rows, heard_all, rooms_all, numbers_all, mistakes = [], {}, [], [], [], [0, 0], [0, 0], []
for truth_file in sorted(WORK.glob("*.truth.json")):
    s = json.loads(truth_file.read_text(encoding="utf-8"))
    if only and s["name"] not in only: continue
    kept_file = WORK / f"{s['name']}.words.json"; began = time.time()
    if kept_file.exists() and not fresh: words = json.loads(kept_file.read_text())
    else: words = speech.transcribe(WORK / f"{s['name']}.wav")["words"]; kept_file.write_text(json.dumps(words, ensure_ascii=False))
    words = speech.spelled(words, speech.vocabulary())   # a kept transcript gets today's vocabulary
    heard = close(tokens(" ".join(l["text"] for l in s["lines"])), tokens(" ".join(w["text"] for w in words)))
    cuts = suggest.review(words, fresh=fresh); gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    # which line each heard word belongs to: the heard words are laid along the spoken ones in order, and a word that
    # matches nothing goes with the word before it. (By time it goes wrong: the recogniser's times drift by a second.)
    lines = s["lines"]; spoken = [(n, t) for n, line in enumerate(lines) for t in tokens(line["text"])]; got = [(tokens(w["text"]) or [""])[0] for w in words]
    owner = [None] * len(words)
    for block in difflib.SequenceMatcher(None, [t for _, t in spoken], got, autojunk=False).get_matching_blocks():
        for k in range(block.size): owner[block.b + k] = spoken[block.a + k][0]
    for i in range(len(owner)):
        if owner[i] is not None: continue
        ahead = next((o for o in owner[i:] if o is not None), None); behind = owner[i - 1] if i else None
        # a word after a full stop opens the next line; any other goes on with the line before it
        owner[i] = ahead if behind is None or (ahead is not None and re.search(r"[.!?…]$", words[i - 1]["text"])) else behind
        if owner[i] is None: owner[i] = 0
    share = []
    for n in range(len(lines)):
        mine = [i for i, o in enumerate(owner) if o == n]; share.append((sum(i in gone for i in mine) / len(mine)) if mine else None)
    # what the viewer would hear: the stretches of the take that stay, laid against when each line was spoken
    facts = {"seconds": s["seconds"], "width": 1080, "height": 1920, "fps": 30, "hdr": False, "has_audio": True}
    spans = project.resolve(project.new("take.wav", facts, {"language": "uk", "words": words}, {"beats": [], "needs": [], "emphasis": [], "corrections": []}, cuts=cuts))["spans"]
    for line in lines:
        stays = sum(max(0.0, min(b, line["end"]) - max(a, line["start"])) for a, b in spans) / max(0.01, line["end"] - line["start"])
        if not line["keep"]: sound[1] += 1; sound[0] += stays < 0.3; audible.extend([(s["name"], line["kind"], f"{stays:.0%}", line["text"])] if stays >= 0.3 else [])
        else: sound[3] += 1; sound[2] += stays > 0.7; clipped.extend([(s["name"], f"{stays:.0%}", line["text"])] if stays <= 0.7 else [])
    caught = missed = 0; notes = []
    for n, line in enumerate(lines):
        show = lambda k: " ".join(w["text"] for i, w in enumerate(words) if owner[i] == k)
        if share[n] is None:
            # the recogniser left the whole line out; a failed attempt left out is still in the sound
            if not line["keep"]: unheard.append((s["name"], line["kind"], line["text"]))
            continue
        twin_after = not line["keep"] and n + 1 < len(lines) and tokens(lines[n + 1]["text"]) == tokens(line["text"])
        if line["keep"]:
            # said twice, either telling may be the one that goes
            twin = n and not lines[n - 1]["keep"] and tokens(lines[n - 1]["text"]) == tokens(line["text"])
            if share[n] > 0.2 and not (twin and (share[n - 1] or 0) < 0.2): damaged.append((s["name"], f"{share[n]:.0%}", show(n))); notes.append(f"damaged: {show(n)[:60]}")
            continue
        ok = share[n] >= 0.8 or (twin_after and (share[n + 1] or 0) >= 0.8 and share[n] <= 0.2)
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
report += ["", f"Failed attempts the recogniser left out of the text (they stay in the sound): {len(unheard)}.", ""] + [f"- {n}, {kind}: {text}" for n, kind, text in unheard]
report += ["", "## What the viewer hears", "", f"Of {sound[1]} failed attempts and asides, {sound[0]} are gone from the sound; of {sound[3]} lines that should stay, {sound[2]} are whole.", "", "Still heard:", ""]
report += [f"- {n}, {kind}, {part} of it: {text}" for n, kind, part, text in audible] + ["", "Lost or clipped:", ""] + [f"- {n}, {part} left: {text}" for n, part, text in clipped]
report += ["", "## Left by mistake", ""] + [f"- {n}, {kind}: {text}" for n, kind, text in mistakes] + ["", "## Damaged", ""] + [f"- {n}, {part} cut: {text}" for n, part, text in damaged]
Path("/work/out/blind.md").write_text("\n".join(report) + "\n", encoding="utf-8"); print("\n".join(report[:9 + len(kinds)]))
