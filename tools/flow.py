#!/usr/bin/env python3
"""The author's path through the running service, one step at a time, from the command line: the same requests the page sends.

  tools/flow.py upload media/IMG_7824.MOV        send a take, wait for the pipeline, show what came out
  tools/flow.py show IMG_7824                    the text as kept, the cuts, the inserts, the requests for material
  tools/flow.py give IMG_7824 n1 media/kit/x.jpg answer a request with a picture
  tools/flow.py beat IMG_7824 b3 media/kit/x.jpg give one insert its own picture
  tools/flow.py rooms IMG_7824                   read the plans and list the moments rooms are spoken of
  tools/flow.py tie IMG_7824 m3 r13              say which room a moment means (use - to untie)
  tools/flow.py unmark IMG_7824 m7               remove a moment
  tools/flow.py render IMG_7824                  build the video and wait for it
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"


def call(path, body=None, raw=None, post=False):
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else (b"" if post else None)
    with urllib.request.urlopen(urllib.request.Request(BASE + urllib.parse.quote(path, safe="/?=&"), data=data), timeout=600) as r: return json.loads(r.read())


def wait(name):
    began = time.time()
    while True:
        state = call(f"/api/projects/{name}")
        if not state["busy"] and state["steps"]: return state, round(time.time() - began)
        time.sleep(3)


def edit(name, change): return call(f"/api/projects/{name}/edit", change)


def show(state):
    words = state["words"]; kept = [w for w in words if w["kept"]]
    print(f"\n{state['name']}: {len(words)} words heard, {len(kept)} kept, video {state.get('seconds')} s")
    print("steps:", ", ".join(f"{s['step']} {s['state']} {s.get('seconds', '')}s" + (f" ({s['error']})" if s.get("error") else "") for s in state["steps"]))
    print("\ntext as kept:\n  " + " ".join(("*" + w["text"] + "*") if w["hot"] else w["text"] for w in kept))
    for c in state["cuts"]: print(f"cut [{c['from']}-{c['to']}] {c['why']}: " + " ".join(w["text"] for w in words[c["from"]:c["to"] + 1])[:110])
    print()
    for b in sorted(state["beats"], key=lambda b: b["from"]):
        said = " ".join(w["text"] for w in words[b["from"]:b["to"] + 1] if w["kept"])[:60]
        print(f"insert {b['id']} {b['kind']:8} [{b['from']}-{b['to']}] need {b.get('need') or '-'} picture {b.get('file') or '-'} {'' if b['accepted'] else '(off) '}| {b.get('text') or b.get('why') or ''} | {said}")
    for n in state["needs"]: print(f"request {n['id']} {n['status']:7} picture {n.get('file') or '-'} | {n['what']}")
    for p in state.get("plans", []): print(f"plan {p['asset']} {p['file']}: " + (f"{len(p['rooms'])} rooms" if p["read"] else "not read yet"))
    for m in sorted(state.get("marks", []), key=lambda m: m["from"]):
        print(f"moment {m['id']} [{m['from']}-{m['to']}] {m['asset']} room {m['room'] or '?':4} | {m['name']} | " + " ".join(w["text"] for w in words[m["from"]:m["to"] + 1] if w["kept"])[:70])


def add_picture(name, file):
    file = Path(file); return call(f"/api/projects/{name}/assets/{file.name}", raw=file.read_bytes())["added"]


if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(__doc__)
    what, name, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if what == "upload":
        file = Path(name); name = call(f"/api/new/{file.name}", raw=file.read_bytes())["project"]; state, took = wait(name); print(f"{name}: pipeline finished in {took} s"); show(state)
    elif what == "show": show(call(f"/api/projects/{name}"))
    elif what == "give": edit(name, {"assign": {"need": rest[0], "asset": add_picture(name, rest[1])}}); show(call(f"/api/projects/{name}"))
    elif what == "beat": edit(name, {"beat_picture": {"beat": rest[0], "asset": add_picture(name, rest[1])}}); show(call(f"/api/projects/{name}"))
    elif what == "rooms": call(f"/api/projects/{name}/rooms", post=True); state, took = wait(name); print(f"rooms and moments found in {took} s"); show(state)
    elif what == "tie": edit(name, {"mark": {"id": rest[0], "room": None if rest[1] == "-" else rest[1]}})
    elif what == "unmark": edit(name, {"remove_mark": rest[0]})
    elif what == "render": call(f"/api/projects/{name}/render", post=True); state, took = wait(name); print(f"{name}: built in {took} s, video {state['seconds']} s")
    else: sys.exit(__doc__)
