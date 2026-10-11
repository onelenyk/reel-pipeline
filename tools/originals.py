#!/usr/bin/env python3
"""The three original takes from nothing to finished videos, through the running service: the pictures cut from her own
videos answer the requests, and the rooms are tied as a person would tie them. For seeing a change to the pipeline on real takes.
usage: tools/originals.py [IMG_7821 IMG_7824 IMG_7811]"""
import re, sys
from flow import add_picture, call, edit, show, wait

KIT = "media/kit/"
PLAN = {
    "IMG_7821": {"pictures": [(r"будинк|містечк|згори|загальн|рендер", "gvillage-aerial.jpg")], "rooms": []},
    "IMG_7824": {"pictures": [(r"план", "154-plan.jpg")],
                 "rooms": [(r"навіс|паркінг", "r15"), (r"техніч", "r13"), (r"постіроч|пральн", "r10"), (r"гардеробна кімната", "r11"), (r"кухн", "r5"), (r"терас", "r14"), (r"дитяч", "r4"), (r"господар", "r1")]},
    "IMG_7811": {"pictures": [(r"план", "shelest-plan-1.jpg"), (r"ліс|краєвид|локац", "shelest-site.jpg"), (r"вітрин|скля", "shelest-hall.jpg"), (r"кухонн|острів|кухн", "shelest-living.jpg")],
                 "first_full": "shelest-house.jpg", "rooms": [(r"навіс", "r8"), (r"передпок", "r2"), (r"вітальн|кухн", "r1")]},
}
for take in sys.argv[1:] or list(PLAN):
    name = call(f"/api/new/{take}.MOV", raw=open(f"media/{take}.MOV", "rb").read())["project"]; state, took = wait(name); print(f"\n{name}: pipeline {took} s")
    plan, used = PLAN[take], set()
    for need in state["needs"]:
        file = next((f for pattern, f in plan["pictures"] if f not in used and re.search(pattern, need["what"].lower())), None)
        if file: used.add(file); edit(name, {"assign": {"need": need["id"], "asset": add_picture(name, KIT + file)}})
    state = call(f"/api/projects/{name}")
    if plan.get("first_full"):
        first = next((b for b in sorted(state["beats"], key=lambda b: b["from"]) if b["kind"] == "full"), None)
        if first: edit(name, {"beat_picture": {"beat": first["id"], "asset": add_picture(name, KIT + plan["first_full"])}})
    if plan["rooms"]:
        call(f"/api/projects/{name}/rooms", post=True); state, _ = wait(name)
        for m in state["marks"]:
            room = next((r for pattern, r in plan["rooms"] if re.search(pattern, (m["name"] or "").lower())), None)
            edit(name, {"mark": {"id": m["id"], "room": room}} if room else {"remove_mark": m["id"]})
    call(f"/api/projects/{name}/render", post=True); state, took = wait(name); print(f"{name}: built in {took} s"); show(state)
