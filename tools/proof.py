"""The proofreading alone: what is heard in a take and what the review would cut, with no video built.
usage: ./reel run tools/proof.py media/IMG_7824.MOV [more]"""
import sys, time
sys.path.insert(0, "/work")
from engine import speech, suggest
for video in sys.argv[1:]:
    began = time.time(); words = speech.transcribe(video)["words"]; heard = time.time() - began
    began = time.time(); cuts = suggest.review(words); gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    print(f"\n== {video}: {len(words)} words heard in {heard:.0f} s, {len(gone)} cut by the review in {time.time() - began:.0f} s")
    print("respelled:", [(w["heard"], w["text"]) for w in words if w.get("heard")])
    print("doubtful:", [w["text"] for w in words if w["confidence"] < 0.5 and w["id"] not in gone] if words and "id" in words[0] else [w["text"] for i, w in enumerate(words) if w["confidence"] < 0.5 and i not in gone])
    for c in cuts: print(f"CUT {c['why']} [{c['from']}-{c['to']}]: " + " ".join(w["text"] for w in words[c["from"]:c["to"] + 1]) + (f"   ({c['note']})" if c.get("note") else ""))
    print("\nKEPT: " + " ".join(w["text"] for i, w in enumerate(words) if i not in gone))
