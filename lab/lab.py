"""Draft experiments for the reel pipeline. One command per hypothesis; results go to /work/out.

  probe FILE                 H0  what the phone recorded (codec, HDR, frame rate, rotation, loudness)
  normalize FILE             H0  re-encode to a plain, editable file
  denoise FILE [START DUR]   H1  the same excerpt cleaned in several ways, with measurements
  stabilize FILE [START DUR] H2  two-pass stabilisation, side by side with the source
  transcribe FILE [MODEL]    H3  speech to text with word timings (json + srt)
  cut FILE                   H4  remove pauses, by the word timings from `transcribe`
  highlight FILE             H5  ask the AI which words to emphasise and what to correct
  subs FILE                  H5  burn subtitles in the reference style
  needs FILE                 H9  the AI plans the edit from the words: inserts, titles, zooms, and what material it needs for them
  all FILE                   H6  the whole chain on one file, with timings
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

OUT = Path("/work/out"); OUT.mkdir(exist_ok=True)
LEVEL = "loudnorm=I=-14.5:TP=-1.5:LRA=7,aresample=48000"  # one pass lands about 1.5 LU under its target; social platforms expect about -16..-14


def run(cmd, capture=False):
    started = time.time()
    result = subprocess.run(cmd, text=True, errors="replace", stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        sys.exit(f"FAILED: {' '.join(cmd[:6])} ...\n{result.stderr[-1500:]}")
    return (result.stdout or "") + (result.stderr or "") if capture else round(time.time() - started, 1)


def ffmpeg(*args, capture=False):
    return run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], capture)


def rate(text):
    if not text or "/" not in text or text.endswith("/0"): return None
    a, b = text.split("/"); return round(int(a) / int(b), 3)


def info(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture=True))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    side = video.get("side_data_list", [])
    return {
        "seconds": round(float(data["format"].get("duration", 0)), 2),
        "megabytes": round(int(data["format"].get("size", 0)) / 1e6, 1),
        "video": f'{video.get("codec_name")} {video.get("width")}x{video.get("height")} {video.get("pix_fmt")}',
        "fps": rate(video.get("r_frame_rate")),
        "variable_frame_rate": rate(video.get("r_frame_rate")) != rate(video.get("avg_frame_rate")),
        "hdr": video.get("color_transfer") in ("smpte2084", "arib-std-b67"),
        "dolby_vision": any("DOVI" in d.get("side_data_type", "") for d in side),
        "rotation": next((d.get("rotation") for d in side if "rotation" in d), 0),
        "audio": f'{audio.get("codec_name")} {audio.get("sample_rate")} Hz {audio.get("channels")} ch' if audio else None,
    }


def loudness(path, extra=None):
    """Integrated loudness, range and true peak; plus how quiet the quietest tenth of the track is (the noise floor)."""
    log = ffmpeg(*(extra or []), "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-", capture=True)
    tail = log[log.rfind("Summary"):]
    grab = lambda label: float(re.search(label + r":\s+(-?[\d.]+)", tail).group(1))
    out = {"lufs": grab("I"), "range": grab("LRA"), "peak": grab("Peak")}
    # Momentary loudness readings, 10 per second; their 10th percentile approximates the room noise between words
    moments = sorted(float(x) for x in re.findall(r" M:\s*(-?[\d.]+)", log) if float(x) > -100)
    if moments:
        out["noise_floor"] = round(moments[len(moments) // 10], 1)
        out["speech_level"] = round(moments[len(moments) * 9 // 10], 1)
        out["speech_over_noise"] = round(out["speech_level"] - out["noise_floor"], 1)
    return out


def tone_filter(meta):
    # HDR phone footage is mapped to ordinary colour so it looks the same on every screen
    if not meta["hdr"]: return "format=yuv420p"
    return "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"


def excerpt(args, default=30):
    return ["-ss", args[1] if len(args) > 1 else "0", "-t", args[2] if len(args) > 2 else str(default)]


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return data


# ---------- H0 ----------
def probe(args):
    return show({**info(args[0]), "sound": loudness(args[0])})


def normalize(args):
    src = Path(args[0]); before = info(src); dst = OUT / f"{src.stem}.normal.mp4"
    took = ffmpeg("-i", str(src), "-vf", f"{tone_filter(before)},fps={round(before['fps'] or 30)}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst))
    after = info(dst)
    return show({"file": dst.name, "source": before, "result": after, "took_seconds": took, "speed": f'{round(before["seconds"] / took, 2)}x real time',
                 "length_drift_seconds": round(abs(after["seconds"] - before["seconds"]), 3)})


# ---------- H1 ----------
def denoise(args):
    src = Path(args[0]); cut = excerpt(args); base = OUT / f"{src.stem}.voice"
    raw = f"{base}.0-source.wav"
    ffmpeg(*cut, "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", raw)
    took = {"1-level-only": ffmpeg("-i", raw, "-af", f"highpass=f=80,{LEVEL}", f"{base}.1-level-only.wav"),
            "2-spectral": ffmpeg("-i", raw, "-af", f"highpass=f=80,afftdn=nr=14:nf=-30:tn=1,{LEVEL}", f"{base}.2-spectral.wav"),
            "3-rnnoise": ffmpeg("-i", raw, "-af", f"highpass=f=80,arnndn=m=/opt/rnnoise/std.rnnn,{LEVEL}", f"{base}.3-rnnoise.wav")}
    try:
        started = time.time()
        from df.enhance import enhance, init_df, load_audio, save_audio
        model, state, _ = init_df()
        audio, _ = load_audio(raw, sr=state.sr())
        save_audio(f"{base}.tmp.wav", enhance(model, state, audio), state.sr())
        ffmpeg("-i", f"{base}.tmp.wav", "-af", LEVEL, f"{base}.4-deepfilter.wav"); Path(f"{base}.tmp.wav").unlink()
        took["4-deepfilter"] = round(time.time() - started, 1)
    except Exception as error:  # the lab keeps going without the neural denoiser
        took["4-deepfilter"] = f"failed: {type(error).__name__}: {error}"
    measured = {p.name.split(".voice.")[1][:-4]: loudness(p) for p in sorted(OUT.glob(f"{src.stem}.voice.*.wav"))}
    return show({"seconds_per_variant": took, "measured": measured})


# ---------- H2 ----------
def stabilize(args):
    src = Path(args[0]); cut = excerpt(args, 15); trf = OUT / f"{src.stem}.trf"; dst = OUT / f"{src.stem}.stable.mp4"; meta = info(src)
    tone = tone_filter(meta)
    detect = ffmpeg(*cut, "-i", str(src), "-vf", f"{tone},vidstabdetect=shakiness=6:accuracy=12:result={trf}", "-f", "null", "-")
    # Left: source. Right: stabilised (smoothed over about a second, zoomed just enough to hide the moving borders)
    apply = ffmpeg(*cut, "-i", str(src), "-filter_complex", f"[0:v]{tone},split[a][b];[b]vidstabtransform=input={trf}:smoothing=30:optzoom=1:interpol=bicubic,unsharp=5:5:0.6:3:3:0.3[s];[a][s]hstack,scale=1920:-2",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(dst))
    return show({"file": dst.name, "detect_seconds": detect, "apply_seconds": apply, "excerpt_seconds": float(cut[3])})


# ---------- H3 ----------
def transcribe(args):
    from faster_whisper import WhisperModel
    src = Path(args[0]); name = args[1] if len(args) > 1 else "large-v3-turbo"
    wav = OUT / f"{src.stem}.16k.wav"; ffmpeg("-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(wav))
    started = time.time()
    model = WhisperModel(name, device="cpu", compute_type="int8", download_root="/work/models", cpu_threads=os.cpu_count() or 8)
    loaded = round(time.time() - started, 1); started = time.time()
    segments, meta = model.transcribe(str(wav), word_timestamps=True, vad_filter=True, beam_size=5)
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
             "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2), "p": round(w.probability, 2)} for w in s.words or []]} for s in segments]
    took = round(time.time() - started, 1); wav.unlink()
    stamp = lambda t: f"{int(t // 3600):02}:{int(t % 3600 // 60):02}:{int(t % 60):02},{int(t * 1000 % 1000):03}"
    tag = "" if name == "large-v3-turbo" else f".{name}"
    (OUT / f"{src.stem}{tag}.srt").write_text("\n".join(f"{i + 1}\n{stamp(r['start'])} --> {stamp(r['end'])}\n{r['text']}\n" for i, r in enumerate(rows)), encoding="utf-8")
    (OUT / f"{src.stem}{tag}.words.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    words = [w for r in rows for w in r["words"]]
    return show({"model": name, "language": f"{meta.language} ({round(meta.language_probability, 2)})", "audio_seconds": round(meta.duration, 1), "load_seconds": loaded,
                 "transcribe_seconds": took, "speed": f"{round(meta.duration / max(took, 0.1), 1)}x real time", "words": len(words),
                 "unsure_words": [w["w"] for w in words if w["p"] < 0.5][:40], "text": " ".join(r["text"] for r in rows)})


def words_of(src):
    path = OUT / f"{Path(src).stem}.words.json"
    if not path.exists(): sys.exit("run `transcribe` first")
    words = []
    for w in (w for r in json.loads(path.read_text(encoding="utf-8")) for w in r["words"]):
        # The recogniser splits "G-Village" into "G" and "-Village": put such pieces back together
        if words and (w["w"].startswith("-") or words[-1]["w"].endswith("-")): words[-1] = {**words[-1], "w": words[-1]["w"] + w["w"], "e": w["e"], "p": min(words[-1]["p"], w["p"])}
        else: words.append(dict(w))
    return words


# ---------- H4 ----------
def keep_spans(words, total, gap=0.45, pad=0.12):
    """Stretches of speech to keep: words closer together than `gap` stay joined, with a short breath on each side."""
    spans = []
    for w in words:
        if spans and w["s"] - spans[-1][1] <= gap: spans[-1][1] = w["e"]
        else: spans.append([w["s"], w["e"]])
    return [(max(0, a - pad), min(total, b + pad)) for a, b in spans]


def cut(args):
    src = Path(args[0]); meta = info(src); words = words_of(src)
    spans = keep_spans(words, meta["seconds"])
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in spans)
    dst = OUT / f"{src.stem}.tight.mp4"
    took = ffmpeg("-i", str(src), "-vf", f"{tone_filter(meta)},select='{expr}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{expr}',asetpts=N/SR/TB",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(dst))
    return show({"file": dst.name, "cuts": len(spans) - 1, "before_seconds": meta["seconds"], "after_seconds": info(dst)["seconds"],
                 "removed_seconds": round(meta["seconds"] - sum(b - a for a, b in spans), 2), "took_seconds": took})


# ---------- H5 ----------
def highlight(args):
    """The AI reads the transcript, fixes obvious recognition mistakes and picks what to emphasise (numbers, names, key claims)."""
    import requests
    src = Path(args[0]); words = words_of(src)
    numbered = " ".join(f"[{i}]{w['w']}" for i, w in enumerate(words))
    prompt = ("Це розшифровка короткого відео про нерухомість, слова пронумеровані. Поверни JSON: "
              '{"fixes": [{"i": номер, "to": "виправлене слово"}], "emphasis": [номери слів], "title": "коротка назва об\'єкта або теми, до 3 слів"}. '
              "fixes: лише очевидні помилки розпізнавання (назви, числа, закінчення); не переписуй стиль мовця. "
              "emphasis: числа з одиницями, назви, ціни, ключові переваги; не більше одного-двох слів на речення.\n\n" + numbered)
    started = time.time()
    response = requests.post("https://api.deepseek.com/chat/completions", timeout=120, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
                             json={"model": "deepseek-flash", "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}, "temperature": 0.2,
                                   "messages": [{"role": "user", "content": prompt}]})
    response.raise_for_status()
    body = response.json(); plan = json.loads(body["choices"][0]["message"]["content"])
    fixes = [f for f in plan.get("fixes", []) if isinstance(f.get("i"), int) and 0 <= f["i"] < len(words) and isinstance(f.get("to"), str)]
    emphasis = sorted({i for i in plan.get("emphasis", []) if isinstance(i, int) and 0 <= i < len(words)})
    (OUT / f"{src.stem}.plan.json").write_text(json.dumps({"fixes": fixes, "emphasis": emphasis, "title": str(plan.get("title", ""))[:40]}, ensure_ascii=False, indent=1), encoding="utf-8")
    return show({"seconds": round(time.time() - started, 1), "tokens": body.get("usage", {}).get("total_tokens"), "title": plan.get("title"),
                 "fixes": [f"{words[f['i']]['w']} -> {f['to']}" for f in fixes], "emphasis": [words[i]["w"] for i in emphasis]})


def needs(args):
    """The AI reads what is said and plans the montage: where a picture should cover or sit behind the speaker, where a title
    or a closer framing belongs, and which material it needs from the author for that (a REQUIRE list)."""
    import requests
    src = Path(args[0]); words = words_of(src)
    numbered = " ".join(f"[{i}]{w['w']}" for i, w in enumerate(words))
    prompt = ("Ти монтажер коротких вертикальних відео про нерухомість. Нижче розшифровка одного дубля, де людина говорить у камеру; слова пронумеровані. "
              "Сплануй монтаж так, щоб відео не було статичним. Поверни JSON:\n"
              '{"beats": [{"kind": "backdrop" | "cutaway" | "title" | "zoom", "from": номер_слова, "to": номер_слова, "need": id_потреби_або_null, "text": "текст титру або null", "why": "коротко"}],\n'
              ' "needs": [{"id": "n1", "what": "що саме потрібно від автора: конкретне фото чи відео", "kind": "photo" | "video" | "plan" | "logo", "optional": true | false}]}\n'
              "Види: backdrop - мовця вирізано з фону, за ним картинка; cutaway - картинка на весь кадр, голос триває; title - напис у кадрі; zoom - крупніший план для наголосу.\n"
              "Правила: вставка починається на слові, де про це заговорили, і триває 2-4 секунди мовлення; не більше однієї вставки одночасно; перші 2 секунди лишаються з мовцем; "
              "титр з назвою з'являється тоді, коли назву вимовляють; zoom - на 1-2 ключових фразах; проси лише матеріал, який справді є в автора (фото об'єкта, план, вид згори, логотип), не більше 5 потреб.\n\n" + numbered)
    started = time.time()
    response = requests.post("https://api.deepseek.com/chat/completions", timeout=180, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
                             json={"model": "deepseek-flash", "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}, "temperature": 0.3,
                                   "messages": [{"role": "user", "content": prompt}]})
    response.raise_for_status()
    plan = json.loads(response.json()["choices"][0]["message"]["content"])
    ok = lambda i: isinstance(i, int) and 0 <= i < len(words)
    beats = [b for b in plan.get("beats", []) if ok(b.get("from")) and ok(b.get("to")) and b["to"] >= b["from"]]
    (OUT / f"{src.stem}.needs.json").write_text(json.dumps({"beats": beats, "needs": plan.get("needs", [])}, ensure_ascii=False, indent=1), encoding="utf-8")
    return show({"seconds": round(time.time() - started, 1), "needs": plan.get("needs", []),
                 "beats": [f"{b['kind']:8} {words[b['from']]['s']:5.1f}-{words[b['to']]['e']:5.1f}s  \"{' '.join(w['w'] for w in words[b['from']:b['to'] + 1])}\"  need={b.get('need')} text={b.get('text')}  ({b.get('why')})" for b in beats]})


def subs(args, spans=None, source=None, name="subs"):
    """Subtitles in the reference style: two or three words at a time, bold white with a soft shadow, emphasised words in yellow."""
    src = Path(args[0]); words = [dict(w) for w in words_of(src)]; meta = info(source or src)
    plan_path = OUT / f"{src.stem}.plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {"fixes": [], "emphasis": [], "title": ""}
    for fix in plan["fixes"]: words[fix["i"]]["w"] = fix["to"]
    for i in plan["emphasis"]: words[i]["hot"] = True
    if spans:  # the video was tightened: move every word to its new time
        shifted = []
        for w in words:
            offset = 0.0
            for a, b in spans:
                if a <= w["s"] <= b: shifted.append({**w, "s": offset + w["s"] - a, "e": offset + min(w["e"], b) - a}); break
                offset += b - a
        words = shifted
    # Phrases of up to three words or about 18 letters, never running past a sentence end
    chunks, current = [], []
    for w in words:
        current.append(w)
        text = " ".join(x["w"] for x in current)
        if len(current) >= 3 or len(text) >= 16 or re.search(r"[.!?]$", w["w"]): chunks.append(current); current = []
    if current: chunks.append(current)
    stamp = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02}:{t % 60:05.2f}"
    width, height = (1080, 1920) if abs(meta["rotation"] or 0) == 90 or "1080x1920" in meta["video"] else (1920, 1080)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
             f"Style: Sub,Inter,{round(height * 0.05)},&H00FFFFFF,&H50000000,&H78000000,-1,1,2,3,2,110,110,{round(height * 0.24)}",
             f"Style: Title,Inter,{round(height * 0.052)},&H000AD6FF,&H50000000,&H78000000,-1,1,2,3,8,60,60,{round(height * 0.09)}", "", "[Events]",
             "Format: Layer, Start, End, Style, Text"]
    for index, chunk in enumerate(chunks):
        end = min(chunk[-1]["e"] + 0.25, chunks[index + 1][0]["s"]) if index + 1 < len(chunks) else chunk[-1]["e"] + 0.4
        text = " ".join(("{\\c&H0AD6FF&}" + w["w"] + "{\\c&HFFFFFF&}") if w.get("hot") else w["w"] for w in chunk)
        lines.append(f"Dialogue: 0,{stamp(chunk[0]['s'])},{stamp(max(end, chunk[0]['s'] + 0.3))},Sub,{{\\fad(80,60)}}{text}")
    if plan.get("title"): lines.append(f"Dialogue: 1,{stamp(0.4)},{stamp(max(5, words[-1]['e'] if words else 5))},Title,{{\\fad(250,250)\\blur3}}{plan['title']}")
    ass = OUT / f"{src.stem}.ass"; ass.write_text("\n".join(lines), encoding="utf-8")
    if source is None:
        dst = OUT / f"{src.stem}.{name}.mp4"
        took = ffmpeg("-i", str(src), "-vf", f"{tone_filter(meta)},ass={ass}", "-af", f"highpass=f=80,{LEVEL}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(dst))
        return show({"file": dst.name, "phrases": len(chunks), "took_seconds": took})
    return ass, len(chunks)


# ---------- H6 ----------
def everything(args):
    """The whole chain in the order the product would run it; one encode at the end."""
    src = Path(args[0]); meta = info(src); steps = {}; started = time.time()
    mark = lambda name, since: steps.__setitem__(name, round(time.time() - since, 1))
    t = time.time(); transcribe([str(src)]); mark("transcribe", t)
    t = time.time(); highlight([str(src)]); mark("ai_highlight", t)
    words = words_of(src); spans = keep_spans(words, meta["seconds"])
    ass, phrases = subs([str(src)], spans=spans, source=src)
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in spans)
    dst = OUT / f"{src.stem}.final.mp4"
    t = time.time()
    ffmpeg("-i", str(src), "-vf", f"{tone_filter(meta)},select='{expr}',setpts=N/FRAME_RATE/TB,fps={round(meta['fps'] or 30)},ass={ass}",
           "-af", f"aselect='{expr}',asetpts=N/SR/TB,highpass=f=80,arnndn=m=/opt/rnnoise/std.rnnn,{LEVEL}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst))
    mark("render", t)
    total = round(time.time() - started, 1)
    return show({"file": dst.name, "steps_seconds": steps, "total_seconds": total, "source_seconds": meta["seconds"], "result": info(dst), "result_sound": loudness(dst),
                 "ratio": f"{round(total / meta['seconds'], 2)}x the length of the video", "cuts": len(spans) - 1, "phrases": phrases})


if __name__ == "__main__":
    commands = {"probe": probe, "normalize": normalize, "denoise": denoise, "stabilize": stabilize, "transcribe": transcribe, "cut": cut, "highlight": highlight, "needs": needs, "subs": subs, "all": everything}
    if len(sys.argv) < 3 or sys.argv[1] not in commands: sys.exit(__doc__)
    commands[sys.argv[1]](sys.argv[2:])
