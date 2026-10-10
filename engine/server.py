"""The web page: watch the pipeline work, edit the text, answer its requests for material, render.

Plain standard-library HTTP: this is a tool for one person on a trusted machine. It listens inside the container;
the launcher publishes it on 127.0.0.1 only.
"""
import json, re, tempfile, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from . import project, render
from .__main__ import ROOT, create

PAGE = Path(__file__).resolve().parent / "page.html"
INBOX = Path("/work/media")
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
        out.update(source=doc["sources"][0], language=doc["language"],
                   words=[{"id": w["id"], "text": w["text"], "start": w["start"], "kept": w["id"] in kept, "hot": w["id"] in hot, "unsure": w["confidence"] < 0.5} for w in doc["words"]],
                   corrections=doc["corrections"], beats=doc["beats"], needs=doc["needs"], seconds=project.resolve(doc)["seconds"])
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
        left = int(self.headers.get("Content-Length") or 0); tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/work/out")
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
        if any(not NAME.match(p) for p in parts): return None  # no path tricks
        return parts

    def do_GET(self):
        parts = self.route()
        if parts is None: return self.send({"error": "bad path"}, 400)
        if not parts: return self.send(PAGE.read_bytes(), kind="text/html; charset=utf-8")
        if parts == ["api", "projects"]:
            names = sorted((p.name for p in ROOT.iterdir() if p.is_dir()), key=lambda n: -(ROOT / n).stat().st_mtime) if ROOT.exists() else []
            return self.send([{"name": n, "busy": busy.get(n), "has_render": (ROOT / n / "render.mp4").exists()} for n in names])
        if len(parts) == 3 and parts[:2] == ["api", "projects"]: return self.send(summary(parts[2]))
        if len(parts) == 3 and parts[0] == "video": return self.file(ROOT / parts[1] / "render.mp4", "video/mp4")
        if len(parts) == 3 and parts[0] == "asset": return self.file(ROOT / parts[1] / "assets" / parts[2], "image/jpeg")
        self.send({"error": "not found"}, 404)

    def do_POST(self):
        parts = self.route()
        try:
            if parts is None: return self.send({"error": "bad path"}, 400)
            if parts[:2] == ["api", "new"] and len(parts) == 3:
                # A raw take arrives: keep it in the inbox and start the pipeline, ending with a first render
                name = Path(parts[2]).stem; tmp = self.upload(Path(parts[2]).suffix or ".mov")
                INBOX.mkdir(exist_ok=True); video = INBOX / parts[2]; tmp.replace(video); folder = ROOT / name
                if (folder / "status.json").exists(): (folder / "status.json").unlink()
                background(name, "pipeline", lambda: (create(video, folder), render.render(folder)))
                return self.send({"project": name})
            if len(parts) < 4 or parts[:2] != ["api", "projects"]: return self.send({"error": "not found"}, 404)
            name, action = parts[2], parts[3]; folder = ROOT / name
            if busy.get(name) and action != "state": return self.send({"error": f"{busy[name]} is still running"}, 409)
            if action == "render": background(name, "render", lambda: render.render(folder))
            elif action == "needs" and len(parts) == 6:
                tmp = self.upload(Path(parts[5]).suffix or ".jpg"); project.fill(folder, parts[4], tmp, parts[5]); tmp.unlink()
            elif action == "edit":
                change = json.loads(self.body() or b"{}"); doc = project.load(folder)
                if "drop" in change: project.drop(folder, int(change["drop"][0]), int(change["drop"][1]), restore=bool(change.get("restore")))
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


def run(port):
    ROOT.mkdir(exist_ok=True); Path("/work/out").mkdir(exist_ok=True)
    print(f"reel: http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
