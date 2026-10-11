"""Answers every open request of every project with the first suitable picture found on the internet."""
import json, sys, urllib.request, urllib.parse
B = "http://127.0.0.1:8787"
def call(path, body=None, post=False):
    data = json.dumps(body).encode() if body is not None else (b"" if post else None)
    with urllib.request.urlopen(urllib.request.Request(B + urllib.parse.quote(path, safe="/?=&"), data=data), timeout=180) as r: return json.loads(r.read())
for name in sys.argv[1:]:
    state = call(f"/api/projects/{name}")
    for need in state["needs"]:
        if need["status"] != "open": continue
        found = call(f"/api/projects/{name}/search?need={need['id']}")
        picked = None
        for item in found.get("results", [])[:5]:
            try: picked = call(f"/api/projects/{name}/find/{item['id']}", post=True)["added"]; break
            except Exception as error: print("   could not fetch", item["id"], error)
        if picked: call(f"/api/projects/{name}/edit", {"assign": {"need": need["id"], "asset": picked}})
        print(name, need["id"], "|", need["what"], "|", found.get("query"), "|", len(found.get("results", [])), "found →", picked)
    call(f"/api/projects/{name}/render", post=True)
