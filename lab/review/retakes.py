"""Experiment: what the AI review cuts from a project's words. usage: ./reel run lab/review/retakes.py IMG_7824 [more projects]
Result (2026-10-10): with thinking on it cuts the failed attempts and asides; without thinking it cut the wrong attempt.
It is not the same from run to run: once it cut a sentence that should have stayed."""
import json, sys, time
from engine import suggest
for n in sys.argv[1:]:
    w=json.load(open(f"/work/projects/{n}/project.json"))["words"]; t=time.time()
    cuts=suggest.review(w); gone={i for c in cuts for i in range(c["from"],c["to"]+1)}
    print("\n==",n,len(cuts),"cuts,",len(gone),"of",len(w),"words,",round(time.time()-t),"s")
    for c in cuts: print(" ",c["why"],c["from"],c["to"],"|"," ".join(x["text"] for x in w[c["from"]:c["to"]+1])[:160])
    print("LEFT:", " ".join(x["text"] for i,x in enumerate(w) if i not in gone))
