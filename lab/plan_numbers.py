"""Experiment: finding a plan's room numbers. Frames found for certain give the frame's size; every other frame of that
size is then looked for by its outline alone, whatever it stands on. Truth is counted by eye."""
import cv2, numpy as np
TRUTH = {"154-plan": 16, "shelest-plan-1": 8, "shelest-plan-2": 7}

def frames(grey, level):
    found = []
    count, parts, stats, _ = cv2.connectedComponentsWithStats((grey < level).astype(np.uint8), connectivity=8)
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if not (11 <= bw <= 44 and 8 <= bh <= 28 and 1.15 <= bw / bh <= 2.4): continue
        own = parts[y:y + bh, x:x + bw] == i
        if min(own[:2].any(0).mean(), own[-2:].any(0).mean(), own[:, :2].any(1).mean(), own[:, -2:].any(1).mean()) < 0.8: continue
        inside = grey[y + 2:y + bh - 2, x + 2:x + bw - 2]
        if 0.04 <= (inside < level - 30).mean() <= 0.55: found.append((x + bw // 2, y + bh // 2, bw, bh))
    return found

def certain(grey):
    out = []
    for level in (170, 185, 200, 215):
        for f in frames(grey, level):
            if not any(abs(f[0] - a) < 16 and abs(f[1] - b) < 12 for a, b, *_ in out): out.append(f)
    return out

def alike(grey, sure, least=0.55):
    """Every place that looks like the certain frames: their average picture is the pattern."""
    bw = int(np.median([f[2] for f in sure])); bh = int(np.median([f[3] for f in sure])); hw, hh = bw // 2 + 1, bh // 2 + 1
    crops = [grey[y - hh:y + hh + 1, x - hw:x + hw + 1].astype(np.float32) for x, y, *_ in sure if y - hh >= 0 and x - hw >= 0]
    crops = [c for c in crops if c.shape == (2 * hh + 1, 2 * hw + 1)]; pattern = np.mean(crops, axis=0)
    score = cv2.matchTemplate(grey.astype(np.float32), pattern, cv2.TM_CCOEFF_NORMED)
    peaks = (score == cv2.dilate(score, np.ones((bh, bw), np.uint8))) & (score > least)
    return [(int(x + hw), int(y + hh)) for y, x in zip(*np.where(peaks))], bw, bh

for name, truth in TRUTH.items():
    colour = cv2.imread(f"/work/media/kit/{name}.jpg"); grey = cv2.cvtColor(colour, cv2.COLOR_BGR2GRAY)
    sure = certain(grey); found, bw, bh = alike(grey, sure) if len(sure) >= 2 else ([], 0, 0)
    print(name, "truth", truth, "certain", len(sure), "frame", (bw, bh), "alike", len(found))
    for x, y in found: cv2.rectangle(colour, (x - bw // 2 - 3, y - bh // 2 - 3), (x + bw // 2 + 3, y + bh // 2 + 3), (0, 0, 255), 2)
    for x, y, *_ in sure: cv2.circle(colour, (int(x), int(y)), 3, (0, 160, 0), -1)
    cv2.imwrite(f"/work/out/rooms/numbers-{name}.jpg", colour)
