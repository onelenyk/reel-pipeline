"""The web page: watch the pipeline work, edit the text, answer its requests for material, render.

Plain standard-library HTTP: this is a tool for one person on a trusted machine. It listens inside the container;
the launcher publishes it on 127.0.0.1 only.
"""
import json, re, tempfile, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from . import HOME, find, plan as plans, project, render, speech, styles, suggest
from .__main__ import ROOT, create, find_rooms

PAGE = Path(__file__).resolve().parent / "page.html"
INBOX = HOME / "media"
SCRATCH = HOME / "out"
changing = threading.Lock()  # one change to a project document at a time
busy = {}  # project name → what is running, so two jobs never write the same project at once
NAME = re.compile(r"^[\w.-]{1,60}$")


def background(name, what, work):
    if busy.get(name): raise RuntimeError(f"{busy[name]} is still running")
    busy[name] = what
    def run():
        try: work()
        except Exception: traceback.print_exc()
        finally: busy.pop(name, None)
    threading.Thread(target=run, daemon=True).start()


def summary(name):
    folder = ROOT / name; status = folder / "status.json"
    out = {"name": name, "busy": busy.get(name), "steps": json.loads(status.read_text(encoding="utf-8")) if status.exists() else [], "has_render": (folder / "render.mp4").exists(),
           "render_version": int((folder / "render.mp4").stat().st_mtime) if (folder / "render.mp4").exists() else 0}
    if (folder / "project.json").exists():
        doc = project.load(folder); kept = set()
        for s in doc["edit"]["segments"]: kept.update(range(s["from"], s["to"] + 1))
        hot = {e["word"] for e in doc["emphasis"] if e["accepted"]}
        fixed = {c["word"]: c["text"] for c in doc["corrections"] if c["accepted"]}
        plan = project.resolve(doc); at = {w["id"]: w["start"] for line in plan["lines"] for w in line["words"]}  # where each word is in the finished video
        assets = {a["id"]: a for a in doc["assets"]}; used = {n.get("asset") for n in doc["needs"]} | {b.get("asset") for b in doc["beats"]}
        out.update(source=doc["sources"][0], language=doc["language"],
                   words=[{"id": w["id"], "text": fixed.get(w["id"], w["text"]), "heard": w["text"], "fixed": w["id"] in fixed, "start": w["start"], "at": at.get(w["id"]), "kept": w["id"] in kept,
                           "hot": w["id"] in hot, "unsure": w["confidence"] < 0.5} for w in doc["words"]],
                   corrections=doc["corrections"], cuts=doc["cuts"], kinds={b["id"]: b["kind"] for b in plan["beats"]}, seconds=plan["seconds"], style=doc["style"],
                   beats=[{**b, "file": Path(assets[b["asset"]]["file"]).name if b.get("asset") in assets else None} for b in doc["beats"]],
                   assets=[{"id": a["id"], "file": Path(a["file"]).name, "credit": a.get("credit")} for a in doc["assets"]],
                   needs=[{**n, "file": Path(assets[n["asset"]]["file"]).name if n.get("asset") in assets else None, "credit": assets.get(n.get("asset"), {}).get("credit")} for n in doc["needs"]],
                   credits=[a["credit"] for a in doc["assets"] if a.get("credit") and a["id"] in used],
                   marks=doc["marks"], plans=[{"asset": a, "file": Path(assets[a]["file"]).name, "read": plans.stored(assets[a]["file"], lenient=True) is not None,
                                               "rooms": [{"id": r["id"], "shape": r["shape"], "at": r["at"], "name": r.get("name"), "number": r.get("number"), "guess": bool(r.get("guess")), "outdoors": bool(r.get("outdoors"))} for r in project.rooms_of(assets[a]["file"])]} for a in project.plan_assets(doc) if a in assets])
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def send(self, data, code=200, kind="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", kind); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def upload(self, suffix):
        """Streams the request body to a temporary file (videos are large) and returns its path."""
        left = int(self.headers.get("Content-Length") or 0); tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=str(SCRATCH))
        while left > 0:
            chunk = self.rfile.read(min(left, 1 << 20))
            if not chunk: break
            tmp.write(chunk); left -= len(chunk)
        tmp.close(); return Path(tmp.name)

    def file(self, path, kind):
        """Serves a file with byte ranges, which video players need for seeking."""
        if not path.exists(): return self.send({"error": "not found"}, 404)
        size = path.stat().st_size; start, end = 0, size - 1
        match = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if match and (match.group(1) or match.group(2)):
            start = int(match.group(1)) if match.group(1) else size - int(match.group(2)); end = int(match.group(2)) if match.group(1) and match.group(2) else size - 1
        self.send_response(206 if match else 200); self.send_header("Content-Type", kind); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if match: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(left, 1 << 18))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): return
                left -= len(chunk)

    def route(self):
        parts = [unquote(p) for p in self.path.split("?")[0].strip("/").split("/") if p]
        if any(not NAME.match(p) or not p.strip(".") for p in parts): return None  # no path tricks
        return parts

    def do_GET(self):
        try: self.get()
        except Exception as error:
            traceback.print_exc(); self.send({"error": str(error)[-300:]}, 500)

    def get(self):
        parts = self.route(); query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        if parts is None: return self.send({"error": "bad path"}, 400)
        if not parts: return self.send(PAGE.read_bytes(), kind="text/html; charset=utf-8")
        if parts == ["api", "projects"]:
            names = sorted((p.name for p in ROOT.iterdir() if p.is_dir()), key=lambda n: -(ROOT / n).stat().st_mtime) if ROOT.exists() else []
            return self.send([{"name": n, "busy": busy.get(n), "has_render": (ROOT / n / "render.mp4").exists()} for n in names])
        if parts == ["api", "styles"]: return self.send(styles.listing())
        if parts == ["api", "vocabulary"]: return self.send({"terms": speech.lines()})
        if len(parts) == 3 and parts[:2] == ["api", "projects"]:
            return self.send(summary(parts[2])) if (ROOT / parts[2]).is_dir() else self.send({"error": "there is no such project"}, 404)
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "search":
            # Pictures from the internet: by the author's own words, or for one of the requests
            try:
                folder = ROOT / parts[2]; text = (query.get("q") or "").strip()[:80]
                if not text and query.get("need"):
                    doc = project.load(folder); need = next(n for n in doc["needs"] if n["id"] == query["need"])
                    if not need.get("search"): need["search"] = find.query_for(need["what"]); project.save(folder, doc)
                    text = need["search"]
                elif text and re.search(r"[^\x00-\x7f]", text): text = find.query_for(text)  # the picture archive is searched in English
                return self.send({"query": text, "results": find.search(text) if text else []})
            except Exception as error:
                traceback.print_exc(); return self.send({"error": str(error)[-200:]}, 502)
        if len(parts) == 3 and parts[0] == "video": return self.file(ROOT / parts[1] / "render.mp4", "video/mp4")
        if len(parts) == 3 and parts[0] == "strip":
            folder = ROOT / parts[1]
            picture = folder / f"strip{render.STRIP}.jpg"
            if (folder / "render.mp4").exists() and (not picture.exists() or picture.stat().st_mtime < (folder / "render.mp4").stat().st_mtime): render.strip(folder)  # built before the timeline existed
            return self.file(picture, "image/jpeg")
        if len(parts) == 3 and parts[0] == "asset":
            kind = {".png": "image/png", ".webp": "image/webp"}.get(Path(parts[2]).suffix, "image/jpeg")
            return self.file(ROOT / parts[1] / "assets" / parts[2], kind)
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        parts = self.route()
        try:
            if parts is None: return self.send({"error": "bad path"}, 400)
            if parts[:2] == ["api", "new"] and len(parts) == 3:
                # A raw take arrives: keep it in the inbox and start the pipeline, ending with a first render
                stem, suffix = Path(parts[2]).stem, Path(parts[2]).suffix or ".mov"; tmp = self.upload(suffix)
                with changing:  # a take with a name already in use becomes a new project; the earlier one and its edits stay
                    name, count = stem, 1
                    while (ROOT / name).exists() or busy.get(name): count += 1; name = f"{stem}-{count}"
                    folder = ROOT / name; folder.mkdir(parents=True)
                INBOX.mkdir(parents=True, exist_ok=True); video = INBOX / f"{name}{suffix}"; tmp.replace(video)
                background(name, "pipeline", lambda: (create(video, folder), render.render(folder)))
                return self.send({"project": name})
            if parts == ["api", "vocabulary"]:
                terms = json.loads(self.body() or b"{}").get("terms"); return self.send({"terms": speech.set_vocabulary(terms if isinstance(terms, list) else [])})
            if parts[:2] == ["api", "styles"] and len(parts) == 4 and parts[3] in ("default", "delete"):
                if parts[3] == "delete": styles.remove(parts[2])
                else: styles.set_default("" if parts[2] == "built-in" else parts[2])
                return self.send(styles.listing())
            if len(parts) < 4 or parts[:2] != ["api", "projects"]: return self.send({"error": "not found"}, 404)
            name, action = parts[2], parts[3]; folder = ROOT / name
            if not (folder / "project.json").exists(): return self.send({"error": "there is no such project"}, 404)
            if busy.get(name) and action != "state": return self.send({"error": f"{busy[name]} is still running"}, 409)
            if action == "render": background(name, "render", lambda: render.render(folder)); return self.send(summary(name))
            if action == "rooms": background(name, "rooms", lambda: find_rooms(folder)); return self.send(summary(name))
            if action == "ask":
                # The author marked a stretch and said what is wrong with it; the AI answers with changes, which are applied
                asked = json.loads(self.body() or b"{}"); doc = project.load(folder); count = len(doc["words"])
                first, last = sorted((int(asked.get("from", 0)), int(asked.get("to", 0)))); request = str(asked.get("text", "")).strip()
                if not request or not 0 <= first <= last < count: return self.send({"error": "mark a stretch and say what to change"}, 400)
                kept = {i for s in doc["edit"]["segments"] for i in range(s["from"], s["to"] + 1)}
                answer = suggest.edit(doc["words"], kept, first, last, request)
                with changing: project.apply(folder, answer["ops"])
                return self.send({**summary(name), "said": answer["say"], "changed": len(answer["ops"])})
            changing.acquire(); self.held = True
            if False: pass
            elif action == "assets" and len(parts) == 5:
                # A picture from the device goes into the project's library
                suffix = Path(parts[4]).suffix.lower()
                if suffix not in (".jpg", ".jpeg", ".png", ".webp"): return self.send({"error": "only JPEG, PNG or WebP pictures"}, 415)
                if int(self.headers.get("Content-Length") or 0) > find.MAX_BYTES: return self.send({"error": "the picture is too large"}, 413)
                tmp = self.upload(suffix); added = project.add_asset(folder, tmp, parts[4]); tmp.unlink()
                return self.send({**summary(name), "added": added})
            elif action == "find" and len(parts) == 5:
                tmp, credit = find.fetch(parts[4]); added = project.add_asset(folder, tmp, tmp.name, credit); tmp.unlink()
                return self.send({**summary(name), "added": added})
            elif action == "style-save":
                wanted = json.loads(self.body() or b"{}").get("name", ""); doc = project.load(folder)
                if not str(wanted).strip(): return self.send({"error": "a style needs a name"}, 400)
                styles.save(str(wanted), doc["style"]); project.set_style(folder, {"name": str(wanted)})
            elif action == "edit":
                change = json.loads(self.body() or b"{}"); doc = project.load(folder)
                if "text" in change:
                    heard = doc["words"][int(change["text"]["word"])]; project.set_text(folder, int(change["text"]["word"]), str(change["text"].get("to", ""))); speech.learn(str(change["text"].get("to", "")), heard.get("heard", heard["text"]))
                elif "assign" in change: project.assign(folder, change["assign"]["need"], change["assign"].get("asset"))
                elif "style" in change: project.set_style(folder, change["style"])
                elif "apply_style" in change: project.set_style(folder, styles.get(change["apply_style"]))
                elif "add_beat" in change:
                    b = change["add_beat"]; project.add_beat(folder, b.get("kind"), b.get("from"), b.get("to"), text=b.get("text"), asset=b.get("asset"))
                elif "beat_picture" in change: project.change_beat(folder, change["beat_picture"]["beat"], asset=change["beat_picture"].get("asset"))
                elif "mark" in change:
                    m = change["mark"]; project.set_mark(folder, m.get("id"), m.get("asset"), m.get("room"), m.get("from"), m.get("to"), m.get("name"))
                elif "zone" in change:
                    z = change["zone"]; project.name_zone(folder, z.get("asset"), z.get("room"), z.get("name"), z.get("number"))
                elif "remove_mark" in change: project.remove_mark(folder, change["remove_mark"])
                elif "remove_beat" in change: project.change_beat(folder, change["remove_beat"], remove=True)
                elif "drop" in change: project.drop(folder, int(change["drop"][0]), int(change["drop"][1]), restore=bool(change.get("restore")))
                elif "emphasis" in change:
                    word = int(change["emphasis"]); found = next((e for e in doc["emphasis"] if e["word"] == word), None)
                    if found: found["accepted"] = not found["accepted"]; found["by"] = "user"
                    else: doc["emphasis"].append({"word": word, "by": "user", "accepted": True})
                    project.save(folder, doc)
                elif "beat" in change:
                    for b in doc["beats"]:
                        if b["id"] == change["beat"]: b["accepted"] = not b["accepted"]
                    project.save(folder, doc)
                elif "correction" in change:
                    for c in doc["corrections"]:
                        if c["word"] == int(change["correction"]): c["accepted"] = not c["accepted"]
                    project.save(folder, doc)
                elif "skip" in change:
                    for n in doc["needs"]:
                        if n["id"] == change["skip"] and n["status"] != "filled": n["status"] = "open" if n["status"] == "skipped" else "skipped"
                    project.save(folder, doc)
            else: return self.send({"error": "not found"}, 404)
            self.send(summary(name))
        except Exception as error:
            traceback.print_exc(); self.send({"error": str(error)[-300:]}, 500)
        finally:
            if getattr(self, "held", False): self.held = False; changing.release()


def run(port):
    ROOT.mkdir(parents=True, exist_ok=True); SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"reel: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
