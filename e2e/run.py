"""End to end: generated takes go through the real service over HTTP, and the finished videos are measured.

  ./reel e2e                 everything
  ./reel e2e quiet pauses    only the cases whose names contain one of these words
  ./reel e2e --ai            also one take planned by the real AI (uses the key in .env; off by default so runs are repeatable and free)
  ./reel e2e --real          also a real take from her phone, when media/IMG_7821.MOV is there
  ./reel e2e --fresh         build the test takes again first

The service runs inside this process on its own data folder (e2e/work/home), so the author's projects and styles are never touched.
What is checked is what a viewer would notice: the right words, the right length, the frame the right way up, subtitles
on screen, loudness at the chosen level, and that the same take always gives the same video.
The results are printed and written to e2e/work/report.md; one frame of every finished video is kept in e2e/work/frames.
"""
import difflib, json, os, shutil, subprocess, sys, threading, time, traceback, urllib.error, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import numpy as np

sys.path[:0] = ["/work", str(Path(__file__).resolve().parent)]
import materials
from engine import HOME, project, server

PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
W, H = 1080, 1920
FRAMES, RESULTS = materials.WORK / "frames", materials.WORK / "results"
ACCENT, GREEN, MAGENTA = (255, 214, 10), (0, 230, 118), (255, 0, 255)
SUB_LOW, SUB_MIDDLE, TOP = (0.62, 0.82), (0.47, 0.65), (0.06, 0.18)

checks, heard, cases = [], {}, []
current = {"case": ""}


def check(label, ok, detail=""):
    checks.append({"case": current["case"], "check": label, "ok": bool(ok), "detail": str(detail)})
    print(f"   {'ok  ' if ok else 'FAIL'} {label}" + (f"  ({detail})" if detail and not ok else ""), flush=True)
    return bool(ok)


def case(name):
    def wrap(work): cases.append((name, work)); return work
    return wrap


# ---------- talking to the service ----------
def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    if method == "POST" and data is None: data = b""
    request = urllib.request.Request(BASE + urllib.parse.quote(path, safe="/?=&%"), data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=300) as reply: code, raw, kind = reply.status, reply.read(), reply.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error: code, raw, kind = error.code, error.read(), error.headers.get("Content-Type", "")
    return code, (json.loads(raw) if "json" in kind else raw)


def upload(path, name=None):
    code, reply = call("POST", f"/api/new/{name or Path(path).name}", Path(path).read_bytes())
    if code != 200: raise RuntimeError(f"upload answered {code}: {reply}")
    return reply["project"]


def wait(name, limit=900):
    """Polls like the page does until nothing is running for this project."""
    until = time.time() + limit
    while time.time() < until:
        code, state = call("GET", f"/api/projects/{name}")
        if code == 200 and not state["busy"] and state["steps"]: return state
        time.sleep(0.4)
    raise RuntimeError(f"{name} did not finish in {limit} s")


def edit(name, change):
    code, state = call("POST", f"/api/projects/{name}/edit", change)
    if code != 200: raise RuntimeError(f"edit {change} answered {code}: {state}")
    return state


def rerender(name):
    code, _ = call("POST", f"/api/projects/{name}/render")
    if code != 200: raise RuntimeError(f"render answered {code}")
    return wait(name)


def fetch(name):
    """Downloads the finished video the way a browser would."""
    code, raw = call("GET", f"/video/{name}/render.mp4")
    if code != 200: raise RuntimeError(f"the video answered {code}")
    RESULTS.mkdir(parents=True, exist_ok=True); out = RESULTS / f"{name}.mp4"; out.write_bytes(raw); return out


def states(state): return {s["step"]: s["state"] for s in state["steps"]}
def timeline(name): return json.loads((HOME / "projects" / name / "timeline.json").read_text(encoding="utf-8"))


# ---------- measuring a video ----------
def facts(path):
    data = json.loads(materials.run("ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)))
    video = next(s for s in data["streams"] if s["codec_type"] == "video"); audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {"seconds": float(data["format"]["duration"]), "codec": video["codec_name"], "width": video["width"], "height": video["height"], "pixels": video["pix_fmt"],
            "rate": video["r_frame_rate"], "frames": int(video.get("nb_frames", 0)), "sound": audio.get("codec_name"), "sound_rate": int(audio.get("sample_rate", 0))}


def frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    if len(raw) != W * H * 3: raise RuntimeError(f"no {W}x{H} frame at {t:.2f} s")
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(int)


def rows(image, band): return image[int(band[0] * H):int(band[1] * H)]
def white(image, band): return int((rows(image, band) > 225).all(axis=2).sum())
def coloured(image, band, colour, within=60): return int((np.abs(rows(image, band) - np.array(colour)) < within).all(axis=2).sum())


def marker(image):
    """The bright square of the test picture: its area, and where its centre is as a share of the frame."""
    top = int(0.385 * H); part = image[top:int(0.56 * H)]
    field = np.median(part.reshape(-1, 3), axis=0)
    ys, xs = np.nonzero(np.abs(part - field).sum(axis=2) > 90)
    if not len(ys): return 0, 0.0, 0.0
    return len(ys), float(xs.mean()) / W, float(ys.mean() + top) / H


def digest(path, stream):
    """A fingerprint of the decoded picture or sound, so two files can be compared by what they play."""
    return materials.run("ffmpeg", "-v", "error", "-i", str(path), "-map", f"0:{stream}", "-f", "md5", "-").strip()


def loudness(path):
    from engine import media
    return media.loudness(path)["lufs"]


def keep_frame(path, name, t):
    FRAMES.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "5", str(FRAMES / f"{name}.jpg")])


def said_at(line):
    """A moment when every word of a subtitle line has been spoken and the line has not begun to fade, so all of it is solid white."""
    return min(line["words"][-1]["start"] + 0.15, line["end"] - 0.14)


def clear_line(plan):
    """The line whose last word stays longest: the easiest one to catch whole."""
    return max(plan["lines"], key=lambda line: line["end"] - line["words"][-1]["start"])


def finished(name, state, source_seconds, level=-15):
    """The checks every finished video must pass. Returns the file and its timeline."""
    done = states(state)
    if not check("every step finished", all(done.get(s) == "done" for s in ("probe", "transcribe", "review", "suggest", "render")), done): return None, None
    video = fetch(name); f = facts(video); line_up = timeline(name)
    check("portrait 1080x1920, 30 frames a second, ordinary colour", (f["codec"], f["width"], f["height"], f["rate"], f["pixels"]) == ("h264", W, H, "30/1", "yuv420p"), f)
    check("sound is AAC at 48 kHz", (f["sound"], f["sound_rate"]) == ("aac", 48000), f)
    check("as long as the kept speech", abs(f["seconds"] - line_up["seconds"]) <= 0.15 and f["seconds"] <= source_seconds + 0.1, f"video {f['seconds']:.2f} s, planned {line_up['seconds']:.2f} s, take {source_seconds:.2f} s")
    check("picture and sound end together", abs(f["frames"] - line_up["seconds"] * 30) <= 1.5 and f["seconds"] - f["frames"] / 30 <= 0.05, f"{f['frames']} frames, {f['seconds']:.2f} s in all")
    lufs = loudness(video)
    check(f"loudness near {level} LUFS", abs(lufs - level) <= 2.5, f"{lufs} LUFS")
    head = video.read_bytes()[:4096]
    check("starts playing before it is fully downloaded", b"moov" in head, "the index is not at the front of the file")
    code, part = call("GET", f"/video/{name}/render.mp4", headers={"Range": "bytes=100-299"})
    check("the player can seek (byte ranges)", code == 206 and len(part) == 200, f"{code}, {len(part)} bytes")
    return video, line_up


# ---------- cases: different takes ----------
def good(take):
    spec = {**materials.BASE, **take}; source = materials.build(take); source_seconds = materials.seconds(source)
    name = upload(source); state = wait(name)
    video, line_up = finished(name, state, source_seconds)
    if not video: return
    check("recognised as Ukrainian", state["language"] == "uk", state["language"])
    expected = materials.said(spec["text"]); got = materials.words(" ".join(w["heard"] for w in state["words"])); heard[spec["name"]] = (spec["text"], got)
    matched = sum(b.size for b in difflib.SequenceMatcher(None, expected, got).get_matching_blocks()) / len(expected)
    # Spoken numbers are written as digits, so a text full of numbers matches the script less
    check("the words are the ones that were said", matched >= (0.5 if spec["text"] == "numbers" else 0.8), f"{matched:.0%}: {' '.join(got)}")
    foreign = [w for w in state["words"] if set(w["heard"]) & set("ыэъёЫЭЪЁ")]
    if foreign: check("a word heard with letters Ukrainian does not have is marked as doubtful", all(w["unsure"] for w in foreign), [w["heard"] for w in foreign])
    t = said_at(clear_line(line_up)); image = frame(video, t); keep_frame(video, name, t)
    check("subtitles are on screen", white(image, SUB_LOW) > 3000, f"{white(image, SUB_LOW)} white pixels at {t:.2f} s")
    check("nothing is drawn where nothing was asked for", white(image, (0.02, 0.30)) < 50, f"{white(image, (0.02, 0.30))} white pixels at the top")
    area, x, y = marker(image)
    check("the picture is the right way up, the right size and centred", abs(area / materials.MARK ** 2 - 1) < 0.15 and abs(x - 0.5) < 0.01 and abs(y - materials.MARK_AT) < 0.01,
          f"marker {area} px (expected {materials.MARK ** 2}) at {x:.3f}, {y:.3f}")
    voice = source_seconds - spec["lead"] - spec["tail"]
    if spec["lead"] or spec["tail"]: check("the silence before and after the speech is cut", line_up["seconds"] <= voice + 0.6, f"{line_up['seconds']:.2f} s from {voice:.2f} s of speech")
    if spec["name"] == "pauses": check("both long pauses are cut", len(line_up["spans"]) == 3 and line_up["seconds"] < source_seconds - 4, f"{len(line_up['spans'])} stretches, {line_up['seconds']:.2f} of {source_seconds:.2f} s")
    if spec["name"] == "long": check("a minute of speech keeps all its words", len(got) >= 0.9 * len(expected), f"{len(got)} of {len(expected)} words")


for one in materials.TAKES_GOOD: cases.append((one["name"], lambda one=one: good(one)))


@case("same-words")
def same_words():
    """The same speech in different files (other frame timing, other sound format) must read the same."""
    reference = heard.get("plain")
    if not reference: return check("the plain take was run first", False, "run without a filter, or include 'plain'")
    for other in ("uneven-frames", "stereo-44k", "phone"):
        if other not in heard: continue
        differ = [f"{a} / {b}" for a, b in zip(reference[1], heard[other][1]) if a != b]
        check(f"'{other}' reads the same as 'plain', give or take a word", len(heard[other][1]) == len(reference[1]) and len(differ) <= 1, differ)


# ---------- cases: the same take several times ----------
@case("identical")
def identical():
    source = materials.build(materials.TAKES_GOOD[0])
    first = upload(source, "twin.mp4"); wait(first)
    second = upload(source, "twin.mp4"); wait(second)
    third, fourth = upload(source, "twin.mp4"), upload(source, "twin.mp4")  # these two are worked on at the same time
    wait(third); wait(fourth); names = [first, second, third, fourth]
    check("each upload became its own project", len(set(names)) == 4, names)
    docs = [project.load(HOME / "projects" / n) for n in names]
    check("the same words with the same timings", all(d["words"] == docs[0]["words"] for d in docs), [len(d["words"]) for d in docs])
    plans = [timeline(n) for n in names]
    for plan in plans:
        for beat in plan["beats"]: beat.pop("file", None)
    check("the same plan for the video", all(p == plans[0] for p in plans))
    videos = [fetch(n) for n in names]
    check("the same picture, frame for frame", len({digest(v, "v") for v in videos}) == 1, [digest(v, "v") for v in videos])
    check("the same sound, sample for sample", len({digest(v, "a") for v in videos}) == 1, [digest(v, "a") for v in videos])


# ---------- cases: takes that must be refused ----------
def refused(file, reason):
    name = upload(file); state = wait(name); failed = [s for s in state["steps"] if s["state"] == "failed"]
    check("the pipeline stopped and said why", len(failed) == 1 and reason in failed[0].get("error", ""), failed or states(state))
    check("no video is offered", not state["has_render"] and call("GET", f"/video/{name}/render.mp4")[0] == 404)
    check("the service is still answering", call("GET", "/api/projects")[0] == 200)


for one in materials.TAKES_BAD: cases.append((one["name"], lambda one=one: refused(materials.build(one), one["refusal"])))


@case("not-a-video")
def not_a_video():
    for file in materials.junk(): print(f"  {file.name}"); refused(file, "not a video")


# ---------- cases: what the author does on the page ----------
@case("editing")
def editing():
    source = materials.build(materials.TAKES_GOOD[0]); name = upload(source, "edit.mp4"); state = wait(name)
    video, before = finished(name, state, materials.seconds(source))
    if not video: return
    count = len(state["words"]); base_area = marker(frame(video, 1.0))[0]; base_level = loudness(video)
    if not check("enough words to edit", count >= 15, count): return

    print("  a correction, a key word, a title, a picture and a zoom")
    state = edit(name, {"text": {"word": 2, "to": "оселя"}})
    check("the corrected word is kept next to what was heard", state["words"][2]["text"] == "оселя" and state["words"][2]["fixed"] and state["words"][2]["heard"] != "оселя", state["words"][2])
    edit(name, {"emphasis": 5}); edit(name, {"add_beat": {"kind": "title", "from": 0, "to": 3, "text": "ТЕСТ"}})
    photo = materials.picture("photo.png", "0xff00ff")
    code, reply = call("POST", f"/api/projects/{name}/assets/{photo.name}", photo.read_bytes())
    check("a picture from the device joins the library", code == 200 and reply.get("added"), reply if code != 200 else "")
    code, reply = call("POST", f"/api/projects/{name}/assets/notes.txt", b"not a picture")
    check("a file that is not a picture is refused", code == 415, code)
    middle = count // 2 - 1
    edit(name, {"add_beat": {"kind": "cutaway", "from": middle, "to": middle + 4, "asset": call("GET", f"/api/projects/{name}")[1]["assets"][0]["id"]}})
    edit(name, {"add_beat": {"kind": "zoom", "from": count - 4, "to": count - 1}})
    state = rerender(name); check("the video is built again", states(state).get("render") == "done", states(state))
    video = fetch(name); plan = timeline(name); beat = {b["kind"]: b for b in plan["beats"]}
    if check("the title, the picture and the zoom are in the plan", set(beat) == {"title", "cutaway", "zoom"}, list(beat)):
        check("the correction is in the subtitles", any(w["text"] == "оселя" for line in plan["lines"] for w in line["words"]))
        image = frame(video, beat["title"]["start"] + 1.8); keep_frame(video, f"{name}-title", beat["title"]["start"] + 1.8)
        check("the title is on screen in the accent colour", coloured(image, TOP, ACCENT) > 1500, f"{coloured(image, TOP, ACCENT)} pixels")
        image = frame(video, beat["cutaway"]["start"] + 1.2); keep_frame(video, f"{name}-picture", beat["cutaway"]["start"] + 1.2)
        check("the picture is on screen above the speaker", coloured(image, (0.12, 0.28), MAGENTA) > 100000, f"{coloured(image, (0.12, 0.28), MAGENTA)} pixels")
        grown = marker(frame(video, (beat["zoom"]["start"] + beat["zoom"]["end"]) / 2))[0] / base_area
        check("the zoom brings the frame closer", 1.15 < grown < 1.35, f"the marker is {grown:.2f} times its size")
        hot = next(w for line in plan["lines"] for w in line["words"] if w["hot"]); image = frame(video, hot["start"] + 0.25)
        check("the key word is in the accent colour", coloured(image, SUB_LOW, ACCENT) > 300, f"{coloured(image, SUB_LOW, ACCENT)} pixels")

    print("  a sentence cut out and another style")
    state = edit(name, {"drop": [count - 5, count - 1]})
    check("the cut words are marked as cut", [w["kept"] for w in state["words"][-5:]] == [False] * 5)
    state = edit(name, {"style": {"accent": "#00e676", "subtitle_size": "l", "subtitle_place": "middle", "karaoke": False, "picture": "edge", "level": -20}})
    state = rerender(name); video = fetch(name); plan = timeline(name); beat = {b["kind"]: b for b in plan["beats"]}
    check("the video is shorter by the cut sentence", plan["seconds"] < before["seconds"] - 1 and abs(facts(video)["seconds"] - plan["seconds"]) <= 0.15, f"{before['seconds']:.2f} → {plan['seconds']:.2f} s")
    check("the zoom on the cut words is gone", "zoom" not in beat, list(beat))
    hot = next(w for line in plan["lines"] for w in line["words"] if w["hot"]); image = frame(video, hot["start"] + 0.25); keep_frame(video, f"{name}-style", hot["start"] + 0.25)
    check("subtitles moved to the middle of the frame", white(image, SUB_MIDDLE) > 3000 and white(image, (0.70, 0.85)) < 50, f"{white(image, SUB_MIDDLE)} in the middle, {white(image, (0.70, 0.85))} below")
    check("the key word took the new accent colour", coloured(image, SUB_MIDDLE, GREEN) > 300, f"{coloured(image, SUB_MIDDLE, GREEN)} pixels")
    image = frame(video, beat["cutaway"]["start"] + 1.2)
    check("the picture now runs to the top edge", coloured(image, (0.0, 0.03), MAGENTA) > 50000, f"{coloured(image, (0.0, 0.03), MAGENTA)} pixels")
    level = loudness(video)
    check("the sound follows the chosen level", abs(level - -20) <= 2.5 and level < base_level - 2.5, f"{base_level} → {level} LUFS")

    print("  undoing")
    state = edit(name, {"drop": [count - 5, count - 1], "restore": True}); check("cut words come back", all(w["kept"] for w in state["words"]))
    state = edit(name, {"text": {"word": 2, "to": ""}}); check("an emptied correction returns what was heard", not state["words"][2]["fixed"] and state["words"][2]["text"] == state["words"][2]["heard"])
    title = next(b["id"] for b in state["beats"] if b["kind"] == "title")
    state = edit(name, {"remove_beat": title}); check("a removed insert is gone", all(b["id"] != title for b in state["beats"]))
    picture = next(b["id"] for b in state["beats"] if b["kind"] == "cutaway")
    state = edit(name, {"beat": picture}); check("an insert can be switched off without removing it", not next(b for b in state["beats"] if b["id"] == picture)["accepted"])

    print("  the style saved and reused")
    code, _ = call("POST", f"/api/projects/{name}/style-save", {"name": "E2E зелений"}); check("the style is saved under a name", code == 200, code)
    saved = [s for s in call("GET", "/api/styles")[1] if s["name"] == "E2E зелений"]
    if not check("it is in the list of styles", len(saved) == 1 and saved[0]["accent"] == "#00e676", saved): return
    call("POST", f"/api/styles/{saved[0]['id']}/default")
    other = upload(materials.build(next(t for t in materials.TAKES_GOOD if t["name"] == "silent-ends")), "styled.mp4"); state = wait(other)
    check("a new video starts in the default style", (state["style"]["accent"], state["style"]["subtitle_place"], state["style"]["level"]) == ("#00e676", "middle", -20), state["style"])
    edit(other, {"style": {"accent": "#ff0000", "subtitle_place": "low"}}); state = edit(other, {"apply_style": saved[0]["id"]})
    check("a saved style can be applied to another video", (state["style"]["accent"], state["style"]["subtitle_place"]) == ("#00e676", "middle"), state["style"])
    call("POST", f"/api/styles/{saved[0]['id']}/delete"); call("POST", "/api/styles/built-in/default")
    check("a deleted style leaves the list", not call("GET", "/api/styles")[1])
    third = upload(materials.build(next(t for t in materials.TAKES_GOOD if t["name"] == "silent-ends")), "styled.mp4"); state = wait(third)
    check("after that new videos use the built-in style again", state["style"]["accent"] == "#ffd60a", state["style"])


@case("wrong-requests")
def wrong_requests():
    check("an unknown project is 'not found'", call("GET", "/api/projects/nobody")[0] == 404)
    check("editing an unknown project is 'not found'", call("POST", "/api/projects/nobody/edit", {"emphasis": 1})[0] == 404)
    check("rendering an unknown project is 'not found'", call("POST", "/api/projects/nobody/render")[0] == 404)
    check("a video that does not exist is 'not found'", call("GET", "/video/nobody/render.mp4")[0] == 404)
    check("a path cannot climb out of the projects folder", call("GET", "/video/../render.mp4")[0] == 400 and call("GET", "/asset/twin/..%2F..%2Fproject.json")[0] == 400)
    check("the page itself is served", call("GET", "/")[0] == 200)


@case("ai")
def with_ai():
    """One take planned by the real AI: its answer differs from run to run, so only its shape is checked."""
    os.environ["REEL_AI"] = "on"
    try:
        source = materials.build(next(t for t in materials.TAKES_GOOD if t["name"] == "long")); name = upload(source, "planned.mp4"); state = wait(name)
    finally: os.environ["REEL_AI"] = "off"
    video, plan = finished(name, state, materials.seconds(source))
    if not video: return
    count = len(state["words"])
    check("the AI suggested something", state["beats"] or any(w["hot"] for w in state["words"]), "no beats and no key words")
    check("every suggestion points at real words", all(0 <= b["from"] <= b["to"] < count for b in state["beats"]), state["beats"])
    check("inserts that wait for material are not drawn", all(b["kind"] not in ("cutaway", "backdrop") for b in plan["beats"]), [b["kind"] for b in plan["beats"]])
    print(f"   {len(state['beats'])} inserts, {len(state['needs'])} requests, {sum(w['hot'] for w in state['words'])} key words")


@case("real")
def real_take():
    """A take from her phone, if one is in media/: the real format (Dolby Vision HDR, stored sideways, drifting frame rate)."""
    source = Path("/work/media/IMG_7821.MOV")
    if not source.exists(): return print("   skipped: media/IMG_7821.MOV is not here")
    name = upload(source, "real.mov"); state = wait(name)
    video, plan = finished(name, state, materials.seconds(source))
    if not video: return
    check("recognised as Ukrainian", state["language"] == "uk", state["language"])
    check("the speech is all there", len(state["words"]) >= 80 and "G-Village" in " ".join(w["heard"] for w in state["words"]), len(state["words"]))
    check("the silent tail is cut", plan["seconds"] < 38.5, plan["seconds"])
    keep_frame(video, name, said_at(clear_line(plan)))


# ---------- the run ----------
def main(args):
    flags = {a for a in args if a.startswith("--")}; wanted = [a for a in args if not a.startswith("--")]
    if "e2e/work" not in str(HOME): sys.exit("the end-to-end run must have its own data folder (REEL_HOME)")
    for folder in (HOME, RESULTS, FRAMES): shutil.rmtree(folder, ignore_errors=True)
    if "--fresh" in flags: shutil.rmtree(materials.TAKES, ignore_errors=True)
    HOME.mkdir(parents=True); (HOME / "projects").mkdir(); (HOME / "out").mkdir()
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler).serve_forever, daemon=True).start()
    started = time.time(); took = {}
    for name, work in cases:
        if name in ("ai", "real") and f"--{name}" not in flags: continue
        if wanted and not any(word in name for word in wanted): continue
        current["case"] = name; print(f"\n{name}", flush=True); began = time.time()
        try: work()
        except Exception as error:
            traceback.print_exc(); check("ran to the end", False, f"{type(error).__name__}: {str(error)[-300:]}")
        took[name] = round(time.time() - began, 1)
    failed = [c for c in checks if not c["ok"]]; total = round(time.time() - started)
    lines = ["# End-to-end run", "", f"{len(took)} cases, {len(checks)} checks, {len(failed)} failed, {total} s.", "", "| Case | Checks | Failed | Seconds |", "|---|---|---|---|"]
    for name in took:
        mine = [c for c in checks if c["case"] == name]
        lines.append(f"| {name} | {len(mine)} | {sum(not c['ok'] for c in mine)} | {took[name]} |")
    if failed: lines += ["", "## Failed", ""] + [f"- **{c['case']}**: {c['check']} ({c['detail']})" for c in failed]
    (materials.WORK / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (materials.WORK / "report.json").write_text(json.dumps({"seconds": total, "took": took, "checks": checks}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + "\n".join(lines[2:]))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
