"""Experiment: which room is the speaker talking about? Three ways of asking, scored against a truth table made by eye.
usage: ./reel run lab/plans/which_room.py [runs]
Result (2026-10-11): one or two of four checked rooms right, whichever way it is asked, and two to three minutes an answer;
asked with facts alone the model thinks until its allowance runs out. So the room is chosen by a click (engine/project.py set_mark).
The truth table below was made for the room tags of that day; check it against out/rooms/which-room.jpg before trusting a score."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, "/work")
from engine import plan, project, suggest

FOLDER, ASSET = "/work/projects/IMG_7824", "a4"
# what the speaker calls a room -> the tags that would be right (the hall and the living room are one space on this plan)
TRUTH = {"передпок": {"r6"}, "техн": {"r13"}, "пост": {"r10"}, "кухн": {"r6", "r5"}, "господар": {"r1"}, "спальн": {"r1"}}

FACTS = """A house is shown to a viewer on its floor plan. The plan's rooms have tags r1, r2, ... and this is what is known of each:
{rooms}
"share" is the room's part of the whole floor. "doors" are the rooms its doors open to; "outside" is the way out of the house.
Fixtures were recognised by a machine and may be missing or wrong; doors and sizes are more reliable.
Below is what the speaker says while the plan is on screen; every word has its number in square brackets.
The tour starts where one enters the house and goes on through doors, from a room to its neighbour.
Find the moments when the speaker talks about one particular room and say which tag it is.
Reply with JSON only: {{"marks":[{{"room":"r4","from":<number of the first word about this room>,"to":<number of the last word about it>,"name":"<the room's name as the speaker says it>"}}]}}
A room that is not among the tags (a terrace, a carport) gets no mark. If you cannot tell which room is meant, give no mark for it.
The speaker's words:
"""

doc = project.load(FOLDER); asset = next(a for a in doc["assets"] if a["id"] == ASSET); rooms = plan.outline(asset["file"])["rooms"]
kept = {w["id"] for s in doc["edit"]["segments"] for w in doc["words"][s["from"]:s["to"] + 1]}
filled = {n["id"]: n["asset"] for n in doc["needs"] if n.get("asset")}
shown = sorted({i for b in doc["beats"] if b["kind"] == "full" and (b.get("asset") or filled.get(b.get("need"))) == ASSET for i in range(b["from"], b["to"] + 1)} & kept)
said = " ".join(f"[{i}]{doc['words'][i]['text']}" for i in shown)
facts = FACTS.format(rooms="\n".join(f"{r['id']}: share {r['share']}, doors to {', '.join(r['doors']) or 'none found'}, windows {r['windows']}, fixtures: {', '.join(r['things']) or 'none found'}" for r in rooms))
tagged = Path("/work/out/rooms/which-room.jpg"); tagged.parent.mkdir(parents=True, exist_ok=True); plan.draw(asset["file"], {"rooms": rooms}, tagged)
ways = {"picture only": lambda: suggest.ask(suggest.MARK + said, think=True, picture=tagged),
        "facts only": lambda: suggest.ask(facts + said, think=True),
        "facts and picture": lambda: suggest.ask(facts.replace("A house is shown", "The picture shows the plan with its tags. A house is shown") + said, think=True, picture=tagged)}
for way, call in ways.items():
    for run in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
        began = time.time()
        try: marks = call().get("marks", [])
        except Exception as e: print(way, "failed:", e); continue
        right = wrong = 0; lines = []
        for m in marks:
            key = next((k for k in TRUTH if k in (m.get("name") or "").lower()), None)
            verdict = "" if key is None else ("ok" if m["room"] in TRUTH[key] else "WRONG"); right += verdict == "ok"; wrong += verdict == "WRONG"
            lines.append(f"{m['room']}={m.get('name')}{' ' + verdict if verdict else ''}")
        print(f"{way} #{run + 1}: {time.time() - began:.0f}s, checked rooms right {right}, wrong {wrong} | " + "; ".join(lines))
