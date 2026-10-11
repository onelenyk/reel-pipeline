"""Experiment: how alike are the AI review's answers from run to run, and does a vote of several runs steady it?
Also tried: finding restarts with no AI at all, by a run of words said twice.
usage: ./reel run lab/review/stability.py IMG_7824 [runs]"""
import json, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/work")
from engine import suggest

name = sys.argv[1]; runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
words = json.load(open(f"/work/projects/{name}/project.json"))["words"]
plain = [re.sub(r"[^\w]", "", w["text"].lower()) for w in words]


def restarts(least=4, reach=70):
    """Word ranges said again a little later: [i, j) where the words from i repeat from j."""
    found, i = [], 0
    while i < len(plain):
        best = None
        for j in range(i + least, min(len(plain), i + reach)):
            n = 0
            while j + n < len(plain) and i + n < j and plain[i + n] == plain[j + n]: n += 1
            if n >= least and (best is None or n > best[1]): best = (j, n)
        if best: found.append((i, best[0] - 1, best[1])); i = best[0]
        else: i += 1
    return found


def gone(cuts): return {i for c in cuts for i in range(c["from"], c["to"] + 1)}

with ThreadPoolExecutor(runs) as pool: answers = list(pool.map(lambda _: gone(suggest.clean_cuts(suggest.ask(suggest.REVIEW + " ".join(f"[{i}]{w['text']}" for i, w in enumerate(words)), think=True), len(words))), range(runs)))
print(name, len(words), "words; cut by each run:", [len(a) for a in answers])
always = set.intersection(*answers); ever = set.union(*answers)
print("cut by all runs:", len(always), "| by some but not all:", len(ever - always))
for k in (3, 5):
    if k <= runs:
        votes = [{i for i in ever if sum(i in a for a in answers[s:s + k]) * 2 > k} for s in range(0, runs - k + 1)]
        print(f"vote of {k}: sizes {[len(v) for v in votes]}, words that differ between votes: {len(set.union(*votes) - set.intersection(*votes))}")
def show(ids):
    ids = sorted(ids); out = []; start = None
    for a, b in zip(ids, ids[1:] + [None]):
        start = a if start is None else start
        if b != a + 1: out.append(f"[{start}-{a}] " + " ".join(w["text"] for w in words[start:a + 1])[:90]); start = None
    return out
print("\nunsteady stretches:"); [print("  ", s) for s in show(ever - always)]
print("\nrestarts found without AI:"); [print(f"   [{a}-{b}] ({n} words repeat) " + " ".join(w["text"] for w in words[a:b + 1])[:90]) for a, b, n in restarts()]
