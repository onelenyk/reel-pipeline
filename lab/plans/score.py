"""How well rooms are outlined, measured on plans whose walls, doors and windows were marked by people.

The true rooms are the spaces those marks enclose. The finder sees only the picture and one point inside each room. Two finders can be scored: "engine" (engine/plan.py with
the CubiCasa5k reader) and "drawing" (lab/plans/drawing_only.py, no network). The plans in plans/cubicasa are from the
CubiCasa5k set, most of which the network was trained on: its score here flatters it.
usage: ./reel run lab/plans/score.py plans/cubicasa [how many] [engine|drawing] ; writes plans/report/"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, "/work")
import drawing_only
from engine import plan

folder = Path(sys.argv[1]); limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 6; finder = sys.argv[3] if len(sys.argv) > 3 else "engine"
report = folder.parent / "report"; report.mkdir(exist_ok=True)
scores, per_plan, began = [], [], time.time()
for picture in sorted(folder.glob("images/*.png"))[:limit]:
    colour = cv2.imread(str(picture)); h, w = colour.shape[:2]; marked = np.zeros((h, w), np.uint8)
    for line in (folder / "labels" / (picture.stem + ".txt")).read_text().splitlines():
        n = np.array(line.split()[1:], float).reshape(-1, 2) * (w, h); cv2.fillPoly(marked, [n.round().astype(np.int32)], 1)
    marked = cv2.dilate(marked, np.ones((3, 3), np.uint8))
    count, parts, stats, _ = cv2.connectedComponentsWithStats(1 - marked, connectivity=4)
    rim = set(np.unique(np.concatenate([parts[0], parts[-1], parts[:, 0], parts[:, -1]])))
    truth = [p for p in range(1, count) if p not in rim and stats[p, cv2.CC_STAT_AREA] >= 0.002 * w * h]
    if not truth: continue
    points = []
    for p in truth:
        deep = cv2.distanceTransform((parts == p).astype(np.uint8), cv2.DIST_L2, 3); y, x = np.unravel_index(deep.argmax(), deep.shape); points.append((int(x), int(y)))
    if finder == "drawing": found = drawing_only.rooms(cv2.cvtColor(colour, cv2.COLOR_BGR2GRAY), points)
    else:
        # the engine may merge or drop points: each true room is matched to the engine's room that holds its point
        answer = plan.rooms(colour, points=points); found = []
        for x, y in points:
            inside = [[[round(px * w), round(py * h)] for px, py in r["shape"]] for r in answer if not r.get("outdoors") and cv2.pointPolygonTest((np.array(r["shape"]) * (w, h)).astype(np.float32), (float(x), float(y)), False) >= 0]
            found.append(inside[0] if inside else None)
    mine = []
    for p, shape in zip(truth, found):
        guess = np.zeros((h, w), np.uint8)
        if shape: cv2.fillPoly(guess, [np.array(shape, np.int32)], 1)
        guess &= 1 - marked; real = parts == p
        mine.append(float((guess.astype(bool) & real).sum() / max(1, (guess.astype(bool) | real).sum())))
    scores += mine; per_plan.append((float(np.mean(mine)), picture.stem, len(mine)))
    shade = colour.copy()
    for i, shape in enumerate(found):
        if shape: cv2.fillPoly(shade, [np.array(shape, np.int32)], [(60, 60, 255), (255, 140, 40), (90, 180, 30), (0, 160, 240), (220, 70, 170), (190, 180, 0)][i % 6])
    seen = cv2.addWeighted(shade, 0.45, colour, 0.55, 0)
    for (x, y), s in zip(points, mine): cv2.circle(seen, (x, y), 5, (0, 0, 0), -1); cv2.putText(seen, f"{s:.2f}", (x + 6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.imwrite(str(report / f"{picture.stem}.jpg"), cv2.resize(seen, None, fx=900 / max(h, w), fy=900 / max(h, w)))
s = np.array(scores); per_plan.sort()
summary = {"finder": finder, "plans": len(per_plan), "rooms": len(s), "mean": round(float(s.mean()), 3), "median": round(float(np.median(s)), 3), "over 0.9": round(float((s >= 0.9).mean()), 3),
           "over 0.8": round(float((s >= 0.8).mean()), 3), "under 0.5": round(float((s < 0.5).mean()), 3), "seconds per plan": round((time.time() - began) / max(1, len(per_plan)), 1), "worst": per_plan[:8], "best": per_plan[-3:]}
print(json.dumps(summary, indent=1)); (report / "summary.json").write_text(json.dumps(summary, indent=1))
