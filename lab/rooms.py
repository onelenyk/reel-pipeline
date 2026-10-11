"""The rooms of a floor plan, found from the drawing itself, with no model and no fee.

A point inside each room is given (the room's number on the plan, or a tap). The thick ink is the walls; a gap between two
ends of one wall line is a door or a window and is bridged. Each point then takes the space its walls enclose. Space that
no point reached, and space two points share, is divided by a flood that grows from the widest places first, so that
neighbours meet where the passage between them is narrowest.
"""
import heapq
import cv2, numpy as np

SIDE = 1000   # plans are worked on at this size: line widths below are in these pixels
INK = 128     # darker than this is drawn
THIN = 3      # ink thinner than this is furniture, not a wall
JOIN = 9      # two outlines this close are the two faces of one wall
RUN = 15      # a wall line runs at least this far
GAP = 0.12    # the widest door or window, as a share of the plan's longer side


def walls(grey):
    """The walls as drawn, and the bridges across their doors and windows."""
    ink = (grey < INK).astype(np.uint8)
    solid = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((JOIN, JOIN), np.uint8))
    solid = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((THIN, THIN), np.uint8))
    gap = round(GAP * max(grey.shape)); bridged = np.zeros_like(solid)
    for along, across in (((1, RUN), (1, gap)), ((RUN, 1), (gap, 1))):
        line = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones(along, np.uint8))
        bridged |= cv2.morphologyEx(line, cv2.MORPH_CLOSE, np.ones(across, np.uint8))
    return solid.astype(bool), bridged.astype(bool) & ~solid.astype(bool)


def spread(owner, open_, depth):
    """Grow every owned region into the open space, the widest places first."""
    h, w = owner.shape; heap = []
    edge = (owner > 0) & (cv2.dilate((open_ & (owner == 0)).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    for y, x in zip(*np.where(edge)): heap.append((-float(depth[y, x]), int(y), int(x)))
    heapq.heapify(heap)
    while heap:
        level, y, x = heapq.heappop(heap); mine = owner[y, x]
        for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= yy < h and 0 <= xx < w and owner[yy, xx] == 0 and open_[yy, xx]:
                owner[yy, xx] = mine; heapq.heappush(heap, (max(level, -float(depth[yy, xx])), yy, xx))


def rooms(grey, points):
    """One outline per point: [[x, y], ...] in the picture's own pixels, or None where the point sits in no room."""
    scale = SIDE / max(grey.shape); small = cv2.resize(grey, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else grey
    scale = min(scale, 1.0); h, w = small.shape
    wall, bridge = walls(small); free = ~wall & ~bridge
    depth = cv2.distanceTransform((~wall).astype(np.uint8), cv2.DIST_L2, 3)
    outside = len(points) + 1; owner = np.zeros((h, w), np.int32)
    count, parts = cv2.connectedComponents(free.astype(np.uint8), connectivity=4)
    rim = set(np.unique(np.concatenate([parts[0], parts[-1], parts[:, 0], parts[:, -1]]))) - {0}
    for p in rim: owner[parts == p] = outside
    seeds = {}
    for i, (x, y) in enumerate(points, 1):
        x, y = min(w - 1, round(x * scale)), min(h - 1, round(y * scale))
        if not free[y, x]:  # the point is on ink: step to the nearest open place
            ys, xs = np.where(free[max(0, y - 12):y + 13, max(0, x - 12):x + 13])
            if not len(ys): continue
            near = np.argmin((ys - min(y, 12)) ** 2 + (xs - min(x, 12)) ** 2); y, x = max(0, y - 12) + ys[near], max(0, x - 12) + xs[near]
        seeds.setdefault(int(parts[y, x]), []).append((i, y, x))
    for part, inside in seeds.items():
        if part in rim: inside = [s for s in inside]  # a point outside the walls (a terrace): it contends with the outside
        if len(inside) == 1 and part not in rim: owner[parts == part] = inside[0][0]
        else:
            if part in rim: owner[parts == part] = 0; owner[0, :][parts[0, :] == part] = outside; owner[-1, :][parts[-1, :] == part] = outside; owner[:, 0][parts[:, 0] == part] = outside; owner[:, -1][parts[:, -1] == part] = outside
            for i, y, x in inside: owner[max(0, y - 2):y + 3, max(0, x - 2):x + 3][parts[max(0, y - 2):y + 3, max(0, x - 2):x + 3] == part] = i
    spread(owner, free, depth)    # points that share a space divide it
    spread(owner, ~wall, depth)   # what no point reached goes to a neighbour, through the bridges
    found = []; back = 1 / scale; pad = np.ones((JOIN, JOIN), np.uint8)
    for i in range(1, len(points) + 1):
        mask = cv2.morphologyEx((owner == i).astype(np.uint8), cv2.MORPH_CLOSE, pad)
        outlines, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not outlines: found.append(None); continue
        shape = cv2.approxPolyDP(max(outlines, key=cv2.contourArea), 0.004 * SIDE, True)
        found.append([[round(x * back), round(y * back)] for x, y in shape.reshape(-1, 2)] if len(shape) >= 3 else None)
    return found
