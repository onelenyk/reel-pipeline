#!/usr/bin/env python3
"""Gives the test projects the ready-made styles in turn and builds each again, so the workspace shows the looks side by side.
usage: python3 lab/blind/dress.py"""
import json, time, urllib.parse, urllib.request

BASE = "http://127.0.0.1:8787"
call = lambda path, data=None: json.loads(urllib.request.urlopen(urllib.request.Request(BASE + urllib.parse.quote(path), data=data), timeout=900).read())
names = sorted(p["name"] for p in call("/api/projects") if p["name"].startswith("blind-")); presets = call(f"/api/projects/{names[0]}")["presets"]
for n, name in enumerate(names):
    look = presets[n % len(presets)]; call(f"/api/projects/{name}/edit", json.dumps({"style": look}).encode()); call(f"/api/projects/{name}/render", b"")
    while call(f"/api/projects/{name}").get("busy"): time.sleep(3)
    failed = [s for s in call(f"/api/projects/{name}")["steps"] if s["state"] == "failed"]
    print(name, look["name"], "FAILED " + failed[0].get("error", "")[:80] if failed else "built", flush=True)
