"""Experiment: how alike are the AI's montage plans from run to run, at the temperature given?
usage: ./reel run lab/review/plan_stability.py IMG_7824 [runs] [temperature]"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/work")
from engine import suggest

name = sys.argv[1]; runs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
if len(sys.argv) > 3: suggest.TEMPERATURE = float(sys.argv[3])
doc = json.load(open(f"/work/projects/{name}/project.json")); words = doc["words"]
kept = {i for s in doc["edit"]["segments"] for i in range(s["from"], s["to"] + 1)}; skip = set(range(len(words))) - kept
with ThreadPoolExecutor(runs) as pool: plans = list(pool.map(lambda _: suggest.suggest(words, skip), range(runs)))
print(name, "temperature", getattr(suggest, "TEMPERATURE", "as built"))
for p in plans:
    print(f"  {len(p['beats'])} inserts, {len(p['needs'])} requests, {len(p['emphasis'])} key words, {len(p.get('corrections', []))} word offers | " + " ".join(f"{b['kind'][:2]}{b['from']}-{b['to']}" for b in p["beats"]))
same = lambda key: len({json.dumps(sorted(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in p[key])) for p in plans})
print("  different answers among the runs: inserts", same("beats"), "| requests", same("needs"), "| key words", same("emphasis"))
