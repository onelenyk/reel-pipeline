"""Several takes as one: a video shot as separate files becomes one source the rest of the pipeline works on.

Each take is brought to the same picture and sound (upright 1080x1920, 30 frames a second, ordinary colour, the same loudness),
kept as its own file, and the files are joined without encoding again. So a phone's HDR take, a landscape one and a small one
stand in one row, and changing the order later means joining again, not preparing again."""
import hashlib, json
from pathlib import Path
from . import media

WIDTH, HEIGHT, FPS = 1080, 1920, 30


def order(videos, facts):
    """The takes in the order they were shot, when every file says when that was; otherwise in the order given."""
    if not all(f.get("shot") for f in facts): return list(range(len(videos)))
    return sorted(range(len(videos)), key=lambda i: (facts[i]["shot"], i))


def prepared(video, facts, folder):
    """One take in the common form; made once and found again by the file it came from."""
    video = Path(video); stat = video.stat(); mark = hashlib.sha1(json.dumps([video.name, stat.st_size, stat.st_mtime_ns, WIDTH, HEIGHT, FPS]).encode()).hexdigest()[:12]
    out = Path(folder) / "takes" / f"{mark}.mp4"
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True); part = out.with_suffix(".part.mp4")
    media.ffmpeg("-i", str(video), "-vf", f"fps={FPS},{media.tone_filter(facts['hdr'])},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},setsar=1",
                 "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad", "-ac", "1", "-t", f"{facts['seconds']:.3f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-g", str(FPS), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-video_track_timescale", "15360", str(part))
    part.replace(out); return out


def join(videos, facts, folder):
    """The takes joined into folder/source.mp4. Returns the file and, for each take, the second of the joined video it starts at and how long it is."""
    folder = Path(folder); parts = [prepared(v, f, folder) for v, f in zip(videos, facts)]; lengths = [media.probe(p)["seconds"] for p in parts]
    listing = folder / "takes" / "order.txt"; listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    out = folder / "source.mp4"; media.ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(out))
    starts = [round(sum(lengths[:i]), 3) for i in range(len(parts))]
    return out, [{"start": s, "seconds": n} for s, n in zip(starts, lengths)]
