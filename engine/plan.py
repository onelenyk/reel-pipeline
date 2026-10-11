"""The rooms of a floor plan, so that a room can be lit up when it is spoken of.

A reader says where the plan's walls, doors and windows are; everything after that is the same whichever reader is used.
The spaces the walls enclose are the rooms. A gap between two ends of one wall line is bridged. Where the plan carries
room numbers, they are the seeds: two numbers in one space divide it, each growing from the widest place first, so that
they meet where the passage between them is narrowest.

The reader today is the CubiCasa5k network (models/cubicasa, fetched by `./reel plans-setup`). Its licence allows
non-commercial use only: to move to another reader, write a function like `cubicasa` below and name it in READERS.
"""
import hashlib, heapq, json, re, sys
from pathlib import Path
from . import HOME

SIDE = 1000   # plans are worked on at this size: the widths below are in these pixels
RUN = 15      # a wall line runs at least this far
GAP = 0.09    # the widest gap in a wall line that is still bridged, as a share of the plan's longer side
SMALL = 0.004 # a space smaller than this share of the plan is not a room of its own
PAPER = 252   # lighter than this is bare paper
HATCH = 13    # gaps this wide in a hatched floor or a dashed outline are closed
DASH = 31     # the gaps of a dashed line are shorter than this
YARD = 0.015  # a place outdoors is at least this share of the plan
LOOSE = 0.08 # a piece of wall smaller than this share of the main walls, and apart from them, is not a wall
OPEN = 0.3    # a room with more of its edge than this open to a neighbour is not a room of its own
_net = None
FORMAT = 7    # rises whenever rooms are found differently: answers kept under an older number are worked out again


def cubicasa(colour):
    """The plan as the CubiCasa5k network sees it. "border" is True where a room ends: that much every reader must give.
    "doors", "windows" and "things" (fixtures by name) are extras that tell rooms apart; a reader may leave them out."""
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
    things = {"closet": 3, "appliance": 4, "toilet": 5, "sink": 6, "sauna bench": 7, "fireplace": 8, "bathtub": 9}
    return {"border": (kind == 2) | (kind == 8) | (icon == 1) | (icon == 2), "doors": icon == 2, "windows": icon == 1, "things": {name: icon == n for name, n in things.items()}}


READERS = {"cubicasa": cubicasa}


def numbers(grey):
    """Where the plan's room numbers are. A number sits in a small frame of its own: a thin rectangle, empty but for a few glyphs."""
    import cv2, numpy as np
    found = []
    for level in (170, 185, 200, 215):  # the frame's line is fainter on some plans than on others
        count, parts, stats, _ = cv2.connectedComponentsWithStats((grey < level).astype(np.uint8), connectivity=8)
        for i in range(1, count):
            x, y, bw, bh, area = stats[i]
            if not (11 <= bw <= 44 and 8 <= bh <= 28 and 1.15 <= bw / bh <= 2.4): continue
            own = parts[y:y + bh, x:x + bw] == i
            # a frame: ink along all four sides of its box, and a few glyphs inside
            if min(own[:2].any(0).mean(), own[-2:].any(0).mean(), own[:, :2].any(1).mean(), own[:, -2:].any(1).mean()) < 0.8: continue
            inside = grey[y + 2:y + bh - 2, x + 2:x + bw - 2]
            if 0.04 <= (inside < level - 30).mean() <= 0.55 and not any(abs(x + bw // 2 - a) < 16 and abs(y + bh // 2 - b) < 12 for a, b in found): found.append((int(x + bw // 2), int(y + bh // 2)))
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


def outdoors(grey, wall, owner):
    """Places drawn beside the house that no wall encloses: a terrace, a carport. Each is whatever is drawn in one piece
    next to the house's walls, with the gaps of a dashed outline or a boarded floor closed."""
    import cv2, numpy as np
    h, w = grey.shape
    house = np.zeros((h, w), np.uint8)
    outlines, _ = cv2.findContours((wall | (owner > 0)).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); cv2.drawContours(house, outlines, -1, 1, -1)
    house = cv2.dilate(house, np.ones((7, 7), np.uint8))
    drawn = ((grey < PAPER) & (house == 0)).astype(np.uint8)
    # a dashed line is a line: its dashes are joined along their own direction, further than gaps are closed elsewhere
    dashes = cv2.morphologyEx(drawn, cv2.MORPH_CLOSE, np.ones((1, DASH), np.uint8)) | cv2.morphologyEx(drawn, cv2.MORPH_CLOSE, np.ones((DASH, 1), np.uint8))
    drawn = cv2.morphologyEx(drawn, cv2.MORPH_CLOSE, np.ones((HATCH, HATCH), np.uint8)) | cv2.morphologyEx(dashes, cv2.MORPH_OPEN, np.ones((1, 3 * DASH), np.uint8)) | cv2.morphologyEx(dashes, cv2.MORPH_OPEN, np.ones((3 * DASH, 1), np.uint8))
    whole = np.zeros((h, w), np.uint8)
    outlines, _ = cv2.findContours(drawn, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); cv2.drawContours(whole, outlines, -1, 1, -1)
    whole = cv2.morphologyEx(whole, cv2.MORPH_OPEN, np.ones((HATCH, HATCH), np.uint8))  # a lone line is not a place
    # A carport is often only a thin outline, dashed and not quite closed: lines that frame a large box stand for the box
    for outline in outlines:
        x, y, bw, bh = cv2.boundingRect(outline)
        if YARD * h * w <= bw * bh <= 0.3 * h * w and min(bw, bh) >= 0.1 * max(h, w) and whole[y:y + bh, x:x + bw].mean() < 0.5:
            sides = [drawn[y:y + 6, x:x + bw].any(0).mean(), drawn[y + bh - 6:y + bh, x:x + bw].any(0).mean(), drawn[y:y + bh, x:x + 6].any(1).mean(), drawn[y:y + bh, x + bw - 6:x + bw].any(1).mean()]
            if sum(side > 0.6 for side in sides) >= 3: whole[y:y + bh, x:x + bw] = 1
    whole[house > 0] = 0
    count, parts, stats, _ = cv2.connectedComponentsWithStats(whole, connectivity=4); beside = cv2.dilate(house, np.ones((25, 25), np.uint8)); found = []
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area < YARD * h * w or not (beside[parts == i]).any(): continue
        shape = cv2.approxPolyDP(max(cv2.findContours((parts == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea), 0.006 * SIDE, True).reshape(-1, 2)
        if len(shape) < 3: continue
        deep = cv2.distanceTransform((parts == i).astype(np.uint8), cv2.DIST_L2, 3); cy, cx = np.unravel_index(deep.argmax(), deep.shape)
        found.append({"n": -1, "at": [round(cx / w, 4), round(cy / h, 4)], "shape": [[round(px / w, 4), round(py / h, 4)] for px, py in shape], "share": 0, "doors": [], "windows": 0, "things": [], "outdoors": True})
    return found


def rooms(colour, reader="cubicasa", points=None):
    """The plan's rooms: [{"at": [x, y], "shape": [[x, y], ...], "share", "doors", "windows", "things"}], places in shares of the
    picture's width and height. "doors" names the rooms a door leads to (or "outside"), "share" is the room's part of the floor.
    `points` are places known to be inside rooms (pixels of the picture); without them the plan's own numbers are looked for."""
    import cv2, numpy as np
    scale = min(1.0, SIDE / max(colour.shape[:2])); small = cv2.resize(colour, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else colour
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY); h, w = grey.shape
    seen = READERS[reader](small); seen = seen if isinstance(seen, dict) else {"border": seen}
    wall = cv2.morphologyEx(seen["border"].astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # A streak of "wall" that stands apart from the house's walls is the edge of a rug or a shadow, not a wall
    count, pieces, stats, _ = cv2.connectedComponentsWithStats(wall, connectivity=8)
    if count > 2:
        largest = max(stats[1:, cv2.CC_STAT_AREA])
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] < LOOSE * largest: wall[pieces == i] = 0
    gap = round(GAP * max(h, w)); bridge = np.zeros_like(wall)
    for along, across in (((1, RUN), (1, gap)), ((RUN, 1), (gap, 1))):
        bridge |= cv2.morphologyEx(cv2.morphologyEx(wall, cv2.MORPH_OPEN, np.ones(along, np.uint8)), cv2.MORPH_CLOSE, np.ones(across, np.uint8))
    wall = wall.astype(bool); bridge = bridge.astype(bool) & ~wall
    seeds = [(round(x * scale), round(y * scale)) for x, y in points] if points is not None else numbers(grey)
    # A number printed across a bridge says the space is one room there: that bridge goes
    _, spans = cv2.connectedComponents(bridge.astype(np.uint8), connectivity=8)
    for x, y in seeds:
        if 0 <= y < h and 0 <= x < w:
            for crossed in np.unique(spans[max(0, y - 6):y + 7, max(0, x - 9):x + 10]):
                if crossed: bridge[spans == crossed] = False
    free = ~wall & ~bridge
    depth = cv2.distanceTransform((~wall).astype(np.uint8), cv2.DIST_L2, 3)
    # Spaces as the walls alone enclose them, and the pieces the bridges cut them into
    _, whole = cv2.connectedComponents((~wall).astype(np.uint8), connectivity=4)
    count, parts, stats, _ = cv2.connectedComponentsWithStats(free.astype(np.uint8), connectivity=4)
    edge = lambda grid: set(np.unique(np.concatenate([grid[0], grid[-1], grid[:, 0], grid[:, -1]]))) - {0}
    open_air, rim = edge(whole), edge(parts)
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
    # A division is kept only where walls bear it out: a part whose edge is mostly open to its neighbour was cut on a guess
    # (two numbers in one space with no wall line between them), and goes back to that neighbour
    while True:
        for i in range(1, len(at) + 1):
            mine = owner == i
            if not mine.any(): continue
            edge = cv2.dilate(mine.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~mine
            beyond = cv2.dilate((edge & ~wall).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~mine & (owner > 0)
            sides, sizes = np.unique(owner[beyond], return_counts=True)
            if len(sides) and (edge & ~wall).sum() > OPEN * edge.sum(): owner[mine] = int(sides[sizes.argmax()]); break
        else: break
    # What tells the rooms apart: which rooms a door joins, where the windows are, what stands inside
    joined = {i: set() for i in range(1, len(at) + 1)}; windows = dict.fromkeys(joined, 0)
    for what in ("doors", "windows"):
        if what not in seen: continue
        count, spots = cv2.connectedComponents(seen[what].astype(np.uint8), connectivity=8)
        for d in range(1, count):
            around = cv2.dilate((spots == d).astype(np.uint8), np.ones((13, 13), np.uint8)).astype(bool)
            sides, sizes = np.unique(owner[around & (owner != 0)], return_counts=True); sides = [int(v) for v, n in zip(sides, sizes) if n >= 6]
            for a in sides:
                if a < 0: continue
                if what == "windows": windows[a] += 1; continue
                for b in sides:
                    if b != a: joined[a].add(b)
    total = sum(int((owner == i).sum()) for i in joined) or 1; found = []
    for i, (x, y) in enumerate(at, 1):
        mine = owner == i; mask = cv2.morphologyEx(mine.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        if not mine.any(): continue
        outlines, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not outlines: continue
        shape = cv2.approxPolyDP(max(outlines, key=cv2.contourArea), 0.004 * SIDE, True).reshape(-1, 2)
        if len(shape) < 3: continue
        things = [name for name, where in seen.get("things", {}).items() if (where & mask.astype(bool)).sum() >= 40]
        found.append({"n": i, "at": [round(x / w, 4), round(y / h, 4)], "shape": [[round(px / w, 4), round(py / h, 4)] for px, py in shape], "share": round(int(mine.sum()) / total, 3),
                      "doors": sorted(joined[i]), "windows": windows[i], "things": things})
    found += outdoors(grey, wall, owner)
    # doors are kept by the rooms' final names
    name = {r["n"]: f"r{k}" for k, r in enumerate(found, 1) if r["n"] > 0}
    for r in found: r["doors"] = sorted({"outside" if d < 0 else name[d] for d in r["doors"] if d < 0 or d in name}); del r["n"]
    return found


def place(picture):
    """Where what is known of a picture is kept: by its content, so that the same plan in another video is known at once."""
    return HOME / "rooms" / (hashlib.sha1(Path(picture).read_bytes()).hexdigest()[:20] + ".json")


def stored(picture, lenient=False):
    """What is already known of a picture, without reading it again; None if it has not been read. An answer found by an
    earlier way of finding is given only to the `lenient`: a video already tied to its rooms must still build."""
    kept = place(picture)
    if not kept.exists(): return None
    known = json.loads(kept.read_text(encoding="utf-8"))
    return known if known.get("format") == FORMAT or lenient else None


def outline(picture, reader="cubicasa"):
    """The rooms of a picture, worked out once and remembered."""
    import cv2
    known = stored(picture)
    if known: return known
    colour = cv2.imread(str(picture))
    if colour is None: raise RuntimeError("this file is not a picture the pipeline can read")
    found = [{"id": f"r{i}", **r} for i, r in enumerate(rooms(colour, reader), 1)]
    describe(colour, found)
    result = {"format": FORMAT, "reader": reader, "rooms": found, "names": {}}
    kept = place(picture); kept.parent.mkdir(parents=True, exist_ok=True); kept.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8"); return result


def read_numbers(grey):
    """The plan's room numbers as text, each with the place of its frame: [((x, y), "07"), ...]. Read on this machine by Tesseract;
    a number it cannot read is left out rather than guessed."""
    import cv2, shutil, subprocess, tempfile
    if not shutil.which("tesseract"): return []
    read = []
    with tempfile.TemporaryDirectory() as tmp:
        for x, y in numbers(grey):
            crop = grey[max(0, y - 9):y + 10, max(0, x - 14):x + 15]
            if crop.shape[0] < 12 or crop.shape[1] < 16: continue
            big = cv2.resize(crop, None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(f"{tmp}/n.png", cv2.copyMakeBorder(big[14:-14, 14:-14], 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255))
            text = subprocess.run(["tesseract", f"{tmp}/n.png", "-", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789"], capture_output=True, text=True).stdout.strip()
            if re.fullmatch(r"\d{2}", text): read.append(((x, y), text))
    return read


def describe(colour, found):
    """What each room probably is, said before anyone is asked: its number as printed on the plan, and a name guessed from
    what stands in it, its size, its windows and where its doors lead. A guess is marked as one ("guess": true) and a
    person's word replaces it; a room nothing can be said of stays unnamed."""
    import cv2, numpy as np
    grey = cv2.cvtColor(colour, cv2.COLOR_BGR2GRAY); h, w = grey.shape
    inside = lambda room, x, y: cv2.pointPolygonTest((np.array(room["shape"]) * (w, h)).astype(np.float32), (float(x), float(y)), False) >= 0
    for (x, y), number in read_numbers(grey):
        homes = [r for r in found if inside(r, x, y)]
        if homes and "number" not in homes[0]: homes[0]["number"] = number
    indoors = [r for r in found if not r.get("outdoors")]; by_id = {r["id"]: r for r in found}
    largest = max(indoors, key=lambda r: r["share"], default=None)
    wet = lambda r: any(t in r["things"] for t in ("toilet", "bathtub"))
    small = lambda r: r["share"] < 0.07
    kinds = {}
    for r in found:
        if r.get("outdoors"):
            # cars are drawn in black ink, a boarded terrace in faint lines
            mask = np.zeros((h, w), np.uint8); cv2.fillPoly(mask, [(np.array(r["shape"]) * (w, h)).astype(np.int32)], 1)
            kinds[r["id"]] = "carport" if (grey[mask > 0] < 110).mean() > 0.02 else "terrace"
        elif wet(r): kinds[r["id"]] = "bathroom" if "bathtub" in r["things"] else "toilet"
        elif r is largest and (r["share"] >= 0.3 or any(t in r["things"] for t in ("appliance", "sink"))): kinds[r["id"]] = "living"
        elif small(r) and r["windows"] == 0 and "closet" in r["things"]: kinds[r["id"]] = "wardrobe"
        elif "outside" in r["doors"] and r["share"] < 0.2: kinds[r["id"]] = "hall"
        elif 0.07 <= r["share"] < 0.28 and r["windows"] >= 1: kinds[r["id"]] = "bedroom"
    for r in found:
        if kinds.get(r["id"]) == "bedroom":
            own = [kinds.get(d) for d in r["doors"] if d in by_id and by_id[d]["doors"] == [r["id"]]]  # rooms reached only through this one
            if "bathroom" in own or "toilet" in own: kinds[r["id"]] = "master"
    for r in found:
        r["kind"] = kinds.get(r["id"]); r["name"] = NAMES.get(r["kind"]); r["guess"] = r["name"] is not None


NAMES = {"carport": "Навіс", "terrace": "Тераса", "bathroom": "Ванна кімната", "toilet": "Санвузол", "living": "Кухня-вітальня", "wardrobe": "Гардеробна", "hall": "Передпокій",
         "bedroom": "Спальня", "master": "Спальня господарів"}
# Words that mean one room in a tour of a house: a zone named by one answers to the others
SAME = [("навіс", "паркінг", "гараж", "паркомісце"), ("тераса", "дворик", "патіо"), ("ванна", "санвузол", "туалет", "вбиральня", "душова"), ("кухня", "вітальня", "зал", "їдальня", "кухня-вітальня"),
        ("гардеробна", "гардероб"), ("передпокій", "прихожа", "покій", "тамбур"), ("спальня", "спальний", "дитяча", "блок"), ("пральня", "постірочна"),
        ("технічне", "котельня", "бойлерна", "техприміщення"), ("комора", "кладова", "інвентарна")]


GENERIC = {"кімна", "примі", "зона", "власн", "велик", "малий", "наша", "окрем"}  # words that say nothing of which room it is


def stems(name):
    """A name cut to what is compared: word stems, with the words of one meaning brought to one."""
    out = set()
    for word in re.findall(r"[\w-]+", (name or "").lower()):
        for piece in [word] + word.split("-"):
            group = next((g for g in SAME if any(piece[:5] == other[:5] for other in g)), None)
            out.add(group[0][:5] if group else piece[:5])
    return out - GENERIC if out - GENERIC else out


def match(picture, name, taken=(), near=None):
    """The room of a plan that a spoken name means: what a person tied before, else the room whose name says the same.
    Among several rooms of one name: one not yet `taken`, and of those the nearest to `near`, where the walk has just been."""
    remembered = recall(picture, name)
    if remembered: return remembered
    known = stored(picture, lenient=True) or {}; said = stems(name); best = []
    for room in known.get("rooms", []):
        own = stems(room.get("name")); common = said & own
        if not common: continue
        # a guessed name is trusted less than a person's: it must say the whole of what was spoken
        if room.get("guess") and not said <= own and not own <= said: continue
        # the name that says exactly what was spoken first; then a room not yet spoken of; then the one closest to where
        # the walk has just been (`near`), since a tour goes from a room to its neighbour
        away = ((room["at"][0] - near[0]) ** 2 + (room["at"][1] - near[1]) ** 2) ** 0.5 if near else 0
        best.append((-len(common), own != said, room["id"] in taken, round(away, 3), known["rooms"].index(room), room["id"]))
    return sorted(best)[0][-1] if best else None


def name_room(picture, room, name=None, number=None):
    """A person says what a room is. Their word stands until they change it."""
    known = stored(picture, lenient=True)
    if not known: raise ValueError("this plan has not been read")
    target = next((r for r in known["rooms"] if r["id"] == room), None)
    if not target: raise ValueError("there is no such room on this plan")
    if name is not None: target["name"] = str(name).strip()[:40] or None; target["guess"] = False
    if number is not None: target["number"] = re.sub(r"[^\w-]", "", str(number))[:4] or None
    place(picture).write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8"); return target


def add_room(picture, shape, name=None):
    """A person draws a room the finder did not see as one: a hall that shares its space with the living room, say.
    Where the drawing lies on rooms already found, the new room is the part of them it covers, so its sides along the walls
    are the walls themselves and only the open side is where the person drew it; those rooms give that part up.
    Drawn where no room was found, it is taken as drawn."""
    import cv2, numpy as np
    known = stored(picture, lenient=True)
    if not known: raise ValueError("this plan has not been read")
    colour = cv2.imread(str(picture)); h, w = colour.shape[:2]
    points = [(min(1.0, max(0.0, float(x))), min(1.0, max(0.0, float(y)))) for x, y in shape][:60]
    if len(points) < 3: raise ValueError("a room needs at least three corners")
    def mask(outline): m = np.zeros((h, w), np.uint8); cv2.fillPoly(m, [(np.array(outline) * (w, h)).astype(np.int32)], 1); return m
    def trace(m):
        outlines, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not outlines: return None
        best = max(outlines, key=cv2.contourArea); corners = cv2.approxPolyDP(best, 0.004 * max(h, w), True).reshape(-1, 2)
        if len(corners) < 3 or cv2.contourArea(best) < 0.0008 * h * w: return None
        only = np.zeros((h, w), np.uint8); cv2.drawContours(only, [best], -1, 1, -1); deep = cv2.distanceTransform(only, cv2.DIST_L2, 3); y, x = np.unravel_index(deep.argmax(), deep.shape)
        return {"shape": [[round(px / w, 4), round(py / h, 4)] for px, py in corners], "at": [round(x / w, 4), round(y / h, 4)]}
    drawn = mask(points)
    if drawn.sum() < 0.0008 * h * w: raise ValueError("the room drawn is too small")
    under = [(r, mask(r["shape"])) for r in known["rooms"]]; under = [(r, m) for r, m in under if (m & drawn).sum() >= 0.03 * drawn.sum()]
    covered = np.zeros((h, w), np.uint8)
    for _, m in under: covered |= m
    new = (drawn & covered) if (drawn & covered).sum() >= 0.4 * drawn.sum() else drawn
    new = cv2.morphologyEx(new, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)); made = trace(new)
    if not made: raise ValueError("the room drawn is too small")
    for room, m in under:
        rest = cv2.morphologyEx(m & (1 - new), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8)); left = trace(rest)
        if left is None or rest.sum() < 0.12 * m.sum(): known["rooms"].remove(room)   # the new room took all of it
        else: room.update(left)
    number = max([int(r["id"][1:]) for r in known["rooms"]] + [0]) + 1
    while any(room == f"r{number}" for room in known.get("names", {}).values()): number += 1
    room = {"id": f"r{number}", **made, "share": 0, "doors": [], "windows": 0, "things": [], "kind": None, "name": (str(name).strip()[:40] or None) if name else None, "guess": False, "by": "user",
            **({"outdoors": True} if not under else {})}
    known["rooms"].append(room); place(picture).write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8"); return room


def remove_room(picture, room):
    known = stored(picture, lenient=True)
    if not known: raise ValueError("this plan has not been read")
    known["rooms"] = [r for r in known["rooms"] if r["id"] != room]; known["names"] = {k: v for k, v in known.get("names", {}).items() if v != room}
    place(picture).write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")


def plain(name):
    """A room's name as it is compared: "гардеробну кімнату" and "Гардеробна кімната" are one name."""
    return " ".join(w[:5] for w in re.findall(r"\w+", (name or "").lower()))


def remember(picture, name, room):
    """A person said which room a name means on this plan; the next video with the plan starts from that."""
    known = stored(picture)
    if not known or not plain(name): return
    known.setdefault("names", {})[plain(name)] = room; place(picture).write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")


def recall(picture, name):
    known = stored(picture) or {}; room = known.get("names", {}).get(plain(name))
    return room if any(r["id"] == room for r in known.get("rooms", [])) else None


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
