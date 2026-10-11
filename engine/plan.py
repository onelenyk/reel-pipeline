"""The rooms of a floor plan, so that a room can be lit up when it is spoken of.

A reader says where the plan's walls, doors and windows are; everything after that is the same whichever reader is used.
The spaces the walls enclose are the rooms. A gap between two ends of one wall line is bridged. Where the plan carries
room numbers, they are the seeds: two numbers in one space divide it, each growing from the widest place first, so that
they meet where the passage between them is narrowest.

The reader today is the CubiCasa5k network (models/cubicasa, fetched by `./reel plans-setup`). Its licence allows
non-commercial use only: to move to another reader, write a function like `cubicasa` below and name it in READERS.
"""
import heapq, json, sys
from pathlib import Path
from . import HOME

SIDE = 1000   # plans are worked on at this size: the widths below are in these pixels
RUN = 15      # a wall line runs at least this far
GAP = 0.09    # the widest gap in a wall line that is still bridged, as a share of the plan's longer side
SMALL = 0.004 # a space smaller than this share of the plan is not a room of its own
_net = None


def cubicasa(colour):
    """Walls, doors and windows as the CubiCasa5k network sees them: True where a room ends."""
    global _net
    import cv2, numpy as np, torch
    home = HOME / "models" / "cubicasa"
    if not (home / "weights.pkl").exists(): raise RuntimeError("the plan reader is not installed: run ./reel plans-setup")
    if _net is None:
        sys.path.insert(0, str(home / "repo"))
        from floortrans.models.hg_furukawa_original import hg_furukawa_original
        _net = hg_furukawa_original(n_classes=51); _net.conv4_ = torch.nn.Conv2d(256, 44, bias=True, kernel_size=1); _net.upsample = torch.nn.ConvTranspose2d(44, 44, kernel_size=4, stride=4)
        _net.load_state_dict(torch.load(home / "weights.pkl", map_location="cpu", weights_only=True)["model_state"]); _net.eval()
    h, w = colour.shape[:2]; H, W = (h + 31) // 32 * 32, (w + 31) // 32 * 32
    padded = cv2.copyMakeBorder(colour, 0, H - h, 0, W - w, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    with torch.no_grad(): answer = _net(torch.from_numpy(cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)).permute(2, 0, 1)[None].float() / 127.5 - 1)[0]
    kind = answer[21:33].argmax(0).numpy()[:h, :w]; icon = answer[33:44].argmax(0).numpy()[:h, :w]
    return (kind == 2) | (kind == 8) | (icon == 1) | (icon == 2)


READERS = {"cubicasa": cubicasa}


def numbers(grey):
    """Where the plan's room numbers are. A number sits in a small frame of its own: a thin rectangle, empty but for a few glyphs."""
    import cv2, numpy as np
    found = []
    count, parts, stats, _ = cv2.connectedComponentsWithStats((grey < 200).astype(np.uint8), connectivity=8)
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if not (11 <= bw <= 44 and 8 <= bh <= 28 and 1.15 <= bw / bh <= 2.4): continue
        own = parts[y:y + bh, x:x + bw] == i
        # a frame: ink along all four sides of its box, and little of it inside
        sides = min(own[:2].any(0).mean(), own[-2:].any(0).mean(), own[:, :2].any(1).mean(), own[:, -2:].any(1).mean())
        if sides < 0.8: continue
        inside = grey[y + 2:y + bh - 2, x + 2:x + bw - 2]; ink = (inside < 170).mean()
        if 0.04 <= ink <= 0.55 and (inside > 215).mean() >= 0.3: found.append((int(x + bw // 2), int(y + bh // 2)))
    return found


def spread(owner, open_, depth):
    """Grow every owned region into the open space, the widest places first."""
    import cv2, numpy as np
    h, w = owner.shape
    edge = (owner > 0) & (cv2.dilate((open_ & (owner == 0)).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    heap = [(-float(depth[y, x]), int(y), int(x)) for y, x in zip(*np.where(edge))]; heapq.heapify(heap)
    while heap:
        level, y, x = heapq.heappop(heap); mine = owner[y, x]
        for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= yy < h and 0 <= xx < w and owner[yy, xx] == 0 and open_[yy, xx]:
                owner[yy, xx] = mine; heapq.heappush(heap, (max(level, -float(depth[yy, xx])), yy, xx))


def rooms(colour, reader="cubicasa", points=None):
    """The plan's rooms: [{"at": [x, y], "shape": [[x, y], ...]}], everything in shares of the picture's width and height.
    `points` are places known to be inside rooms (pixels of the picture); without them the plan's own numbers are looked for."""
    import cv2, numpy as np
    scale = min(1.0, SIDE / max(colour.shape[:2])); small = cv2.resize(colour, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else colour
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY); h, w = grey.shape
    wall = cv2.morphologyEx(READERS[reader](small).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    gap = round(GAP * max(h, w)); bridge = np.zeros_like(wall)
    for along, across in (((1, RUN), (1, gap)), ((RUN, 1), (gap, 1))):
        bridge |= cv2.morphologyEx(cv2.morphologyEx(wall, cv2.MORPH_OPEN, np.ones(along, np.uint8)), cv2.MORPH_CLOSE, np.ones(across, np.uint8))
    wall = wall.astype(bool); bridge = bridge.astype(bool) & ~wall; free = ~wall & ~bridge
    depth = cv2.distanceTransform((~wall).astype(np.uint8), cv2.DIST_L2, 3)
    # Spaces as the walls alone enclose them, and the pieces the bridges cut them into
    _, whole = cv2.connectedComponents((~wall).astype(np.uint8), connectivity=4)
    count, parts, stats, _ = cv2.connectedComponentsWithStats(free.astype(np.uint8), connectivity=4)
    edge = lambda grid: set(np.unique(np.concatenate([grid[0], grid[-1], grid[:, 0], grid[:, -1]]))) - {0}
    open_air, rim = edge(whole), edge(parts)
    seeds = [(round(x * scale), round(y * scale)) for x, y in points] if points is not None else numbers(grey)
    def stand(x, y):
        """A number printed across a bridge or a wall line stands in the nearest open place."""
        if not (0 <= y < h and 0 <= x < w): return None
        ys, xs = np.where(free[max(0, y - 15):y + 16, max(0, x - 15):x + 16])
        if not len(ys): return None
        near = np.argmin((ys + max(0, y - 15) - y) ** 2 + (xs + max(0, x - 15) - x) ** 2); return int(xs[near] + max(0, x - 15)), int(ys[near] + max(0, y - 15))
    seeds = [s for s in (stand(x, y) for x, y in seeds) if s and parts[s[1], s[0]] not in rim]
    owner = np.zeros((h, w), np.int32); at = []; owner[np.isin(parts, list(rim))] = -1
    def claim(mask, inside):
        """One space: a room of its own, or shared between the numbers that stand in it."""
        if len(inside) <= 1:
            if not inside: deep = np.where(mask, depth, 0); y, x = np.unravel_index(deep.argmax(), deep.shape); inside = [(int(x), int(y))]
            at.append(inside[0]); owner[mask] = len(at)
        else:
            for x, y in inside: at.append((x, y)); owner[max(0, y - 2):y + 3, max(0, x - 2):x + 3][mask[max(0, y - 2):y + 3, max(0, x - 2):x + 3]] = len(at)
    for space in np.unique(whole[whole > 0]):
        mask = whole == space; inside = [(x, y) for x, y in seeds if mask[y, x]]
        if space not in open_air and len(inside) <= 1:
            # an enclosed space with one number or none is one room, whatever the bridges say
            if mask.sum() >= SMALL * h * w / 2: claim(mask, inside)
            continue
        for piece in np.unique(parts[mask & (parts > 0)]):
            if piece in rim: continue
            part = parts == piece; here = [(x, y) for x, y in inside if part[y, x]]
            # a piece cut off by a bridge is a room if it carries a number, or if only the bridge keeps the outside out of it
            if here or (space in open_air and stats[piece, cv2.CC_STAT_AREA] >= SMALL * h * w): claim(part, here)
    spread(owner, free, depth)    # numbers that share a space divide it
    spread(owner, ~wall, depth)   # small leftovers go to a neighbour, through the bridges
    found = []
    for i, (x, y) in enumerate(at, 1):
        mask = cv2.morphologyEx((owner == i).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        outlines, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not outlines: continue
        shape = cv2.approxPolyDP(max(outlines, key=cv2.contourArea), 0.004 * SIDE, True).reshape(-1, 2)
        if len(shape) >= 3: found.append({"at": [round(x / w, 4), round(y / h, 4)], "shape": [[round(px / w, 4), round(py / h, 4)] for px, py in shape]})
    return found


def outline(picture, reader="cubicasa"):
    """The rooms of a picture, worked out once and kept beside it."""
    import cv2
    picture = Path(picture); kept = picture.with_suffix(".rooms.json")
    if kept.exists() and kept.stat().st_mtime >= picture.stat().st_mtime: return json.loads(kept.read_text())
    colour = cv2.imread(str(picture))
    if colour is None: raise RuntimeError("this file is not a picture the pipeline can read")
    result = {"format": 1, "reader": reader, "rooms": [{"id": f"r{i}", "name": None, **r} for i, r in enumerate(rooms(colour, reader), 1)]}
    kept.write_text(json.dumps(result, ensure_ascii=False)); return result


def draw(picture, result, out):
    """The picture with its rooms shaded, to look at."""
    import cv2, numpy as np
    colour = cv2.imread(str(picture)); h, w = colour.shape[:2]; shade = colour.copy()
    tints = [(60, 60, 255), (255, 140, 40), (90, 180, 30), (0, 160, 240), (220, 70, 170), (190, 180, 0), (150, 100, 60), (120, 60, 200)]
    for i, r in enumerate(result["rooms"]): cv2.fillPoly(shade, [(np.array(r["shape"]) * (w, h)).astype(np.int32)], tints[i % 8])
    seen = cv2.addWeighted(shade, 0.22, colour, 0.78, 0)
    for i, r in enumerate(result["rooms"]):
        cv2.polylines(seen, [(np.array(r["shape"]) * (w, h)).astype(np.int32)], True, tints[i % 8], 2)
        # the tag stands at the room's widest place, on a white plate, so that it reads on any plan
        mask = np.zeros((h, w), np.uint8); cv2.fillPoly(mask, [(np.array(r["shape"]) * (w, h)).astype(np.int32)], 1); deep = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
        y, x = np.unravel_index(deep.argmax(), deep.shape); size = max(0.5, w / 1500); (tw, th), _ = cv2.getTextSize(r["id"], cv2.FONT_HERSHEY_SIMPLEX, size, 2)
        cv2.rectangle(seen, (x - tw // 2 - 4, y - th // 2 - 5), (x + tw // 2 + 4, y + th // 2 + 5), (255, 255, 255), -1)
        cv2.putText(seen, r["id"], (x - tw // 2, y + th // 2), cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 200), 2)
    cv2.imwrite(str(out), seen)
