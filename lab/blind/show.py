#!/usr/bin/env python3
"""Sends every test take, voiced over the picture of a real one, through the whole pipeline of the running service, into the
workspace "Тестові дублі", one after another. Make the films first: ./reel run lab/blind/film.py NAME ...
usage: python3 lab/blind/show.py [NAME ...]"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"; HERE = Path(__file__).parent; MEDIA = HERE.parent.parent / "media"; SPACE = "Тестові дублі"
call = lambda path, data=None: json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, data=data), timeout=900).read())
names = sys.argv[1:] or sorted(p.name[:-len(".truth.json")] for p in (HERE / "work").glob("*.truth.json"))
for name in names:
    film = MEDIA / f"blind-{name}.mp4"
    if not film.exists(): print(name, "has no film"); continue
    began = time.time(); made = call(f"/api/new/{urllib.parse.quote(film.name)}?space={urllib.parse.quote(SPACE)}", film.read_bytes())["project"]
    while call(f"/api/projects/{made}").get("busy"): time.sleep(4)
    state = call(f"/api/projects/{made}"); failed = [s["step"] for s in state["steps"] if s["state"] == "failed"]
    print(made, f"{time.time() - began:.0f} s", "FAILED at " + failed[0] if failed else "ready", flush=True)
