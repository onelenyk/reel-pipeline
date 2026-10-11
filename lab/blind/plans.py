"""Chooses a floor plan for each test take: the plan whose rooms, as the reader and the naming rules see them, cover most of
the rooms the take speaks of. Writes work/plans.json: {take: {"plan": file, "covers": [rooms], "misses": [rooms]}}.
usage: ./reel run lab/blind/plans.py [HOW_MANY_PLANS]"""
import json, sys
from pathlib import Path
from engine import plan

WORK = Path(__file__).parent / "work"; count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
pictures = sorted(Path("/work/plans/cubicasa/images").glob("*.png"))[:count] + sorted(Path("/work/media/kit").glob("*plan*.jpg"))
names = {}
for picture in pictures:
    try: found = plan.outline(picture); names[str(picture)] = sorted({r.get("name") for r in found["rooms"] if r.get("name")})
    except Exception as error: print(picture.name, "not read:", str(error)[:80]); continue
    print(picture.name, len(found["rooms"]), "rooms:", names[str(picture)], flush=True)
chosen = {}
for truth in sorted(WORK.glob("*.truth.json")):
    s = json.loads(truth.read_text(encoding="utf-8"))
    if not s["rooms"]: continue
    cover = lambda p: [r for r in s["rooms"] if plan.match(p, r)]
    best = max(names, key=lambda p: (len(cover(p)), -len(names[p])))
    chosen[s["name"]] = {"plan": best, "covers": cover(best), "misses": [r for r in s["rooms"] if r not in cover(best)]}
    print(s["name"], Path(best).name, f"{len(cover(best))}/{len(s['rooms'])}", "misses", chosen[s["name"]]["misses"], flush=True)
(WORK / "plans.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=1), encoding="utf-8")
