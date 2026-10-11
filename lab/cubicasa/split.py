"""Rooms from the network's answer: its walls, doors and windows are the borders, the spaces they enclose are the rooms.
usage: split.py <picture> <answer.npy> <out.png> ..."""
import sys
import cv2, numpy as np
ROOMS = ["", "outdoor", "", "kitchen", "living", "bedroom", "bath", "entry", "", "storage", "garage", ""]
COLOURS = [(60, 60, 255), (255, 140, 40), (90, 180, 30), (0, 160, 240), (220, 70, 170), (190, 180, 0), (150, 100, 60), (120, 60, 200)]
for path, answer, out in zip(sys.argv[1::3], sys.argv[2::3], sys.argv[3::3]):
    colour = cv2.imread(path); h, w = colour.shape[:2]; kind, icon = np.load(answer)
    border = ((kind == 2) | (kind == 8) | (icon == 1) | (icon == 2)).astype(np.uint8)
    border = cv2.morphologyEx(border, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, parts, stats, _ = cv2.connectedComponentsWithStats(1 - border, connectivity=4)
    rim = set(np.unique(np.concatenate([parts[0], parts[-1], parts[:, 0], parts[:, -1]])))
    shade = colour.copy(); shapes = []
    for p in range(1, count):
        if p in rim or stats[p, cv2.CC_STAT_AREA] < 0.0015 * w * h: continue
        mask = cv2.dilate((parts == p).astype(np.uint8), np.ones((5, 5), np.uint8))
        outline = cv2.approxPolyDP(max(cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea), 0.004 * max(w, h), True)
        votes = np.bincount(kind[parts == p], minlength=12); votes[[0, 1, 2, 8, 11]] = 0
        name = ROOMS[votes.argmax()] if votes.max() > 0.15 * stats[p, cv2.CC_STAT_AREA] else "?"
        shapes.append((outline, name)); cv2.fillPoly(shade, [outline], COLOURS[len(shapes) % 8])
    seen = cv2.addWeighted(shade, 0.45, colour, 0.55, 0)
    for i, (outline, name) in enumerate(shapes, 1):
        cv2.polylines(seen, [outline], True, COLOURS[i % 8], 2); x, y = outline.reshape(-1, 2).mean(0).astype(int); cv2.putText(seen, name, (x - 25, y - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    cv2.imwrite(out, seen); print(path, len(shapes), "rooms:", [n for _, n in shapes])
