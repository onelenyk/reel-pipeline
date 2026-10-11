#!/usr/bin/env python3
"""Sends every test take, voiced over the picture of a real one, through the whole pipeline of the running service, into the
workspace "Тестові дублі", one after another. Make the films first: ./reel run lab/blind/film.py NAME ...
usage: python3 lab/blind/show.py [NAME ...]"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"; HERE = Path(__file__).parent; MEDIA = HERE.parent.parent / "media"; SPACE = "Тестові дублі"
def call(path, data=None):
    for attempt in range(5):   # the service may be busy for a moment
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, data=data), timeout=900).read())
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 4: raise
            time.sleep(2)
def with_plan(project, take):
    """Gives a test project the floor plan chosen for its take (work/plans.json), finds the rooms spoken of and builds again."""
    chosen = json.loads((HERE / "work" / "plans.json").read_text(encoding="utf-8")).get(take)
    if not chosen: return "no plan fits"
    state = call(f"/api/projects/{urllib.parse.quote(project)}")
    if state.get("plans"): return "has a plan already"
    plan = HERE.parent.parent / Path(chosen["plan"]).relative_to("/work")
    added = call(f"/api/projects/{urllib.parse.quote(project)}/assets/{plan.name}", plan.read_bytes())["added"]
    need = next((n for n in state["needs"] if n["status"] == "open" and "план" in n["what"].lower()), None)
    if need: call(f"/api/projects/{urllib.parse.quote(project)}/edit", json.dumps({"assign": {"need": need["id"], "asset": added}}).encode())
    for action in ("rooms", "render"):
        call(f"/api/projects/{urllib.parse.quote(project)}/{action}", b"")
        while call(f"/api/projects/{urllib.parse.quote(project)}").get("busy"): time.sleep(3)
    state = call(f"/api/projects/{urllib.parse.quote(project)}"); marks = state.get("marks", [])
    return f"plan {plan.name}: {sum(1 for m in marks if m.get('room'))} of {len(marks)} moments tied to a room; the plan lacks {chosen['misses'] or 'nothing'}"


if sys.argv[1:2] == ["plans"]:
    # the projects already made get their plans
    for one in call("/api/projects"):
        if one["name"].startswith("blind-") and not one["busy"]: print(one["name"], with_plan(one["name"], one["name"][len("blind-"):].split("-")[0]), flush=True)
    sys.exit()
names = sys.argv[1:] or sorted(p.name[:-len(".truth.json")] for p in (HERE / "work").glob("*.truth.json"))
for name in names:
    film = MEDIA / f"blind-{name}.mp4"
    if not film.exists(): print(name, "has no film"); continue
    if any(p["name"] == f"blind-{name}" for p in call("/api/projects")): continue   # shown before
    began = time.time(); made = call(f"/api/new/{urllib.parse.quote(film.name)}?space={urllib.parse.quote(SPACE)}", film.read_bytes())["project"]
    while call(f"/api/projects/{made}").get("busy"): time.sleep(4)
    state = call(f"/api/projects/{made}"); failed = [s["step"] for s in state["steps"] if s["state"] == "failed"]
    print(made, f"{time.time() - began:.0f} s", "FAILED at " + failed[0] if failed else "ready, " + with_plan(made, name), flush=True)
