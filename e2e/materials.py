"""The test takes for the end-to-end run: a known Ukrainian text spoken by the Mac's voice, over a picture that can be measured.

Every take shows a dark field with one bright square (the marker). In the finished 1080x1920 video the marker must be
MARK pixels wide and sit at 45% of the height, whatever the take's size, rotation or colour was: that is how the run
knows the picture was turned, scaled and cropped correctly. Subtitles are white on the dark field, so they can be counted.
"""
import re, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"; VOICE = WORK / "voice"; TAKES = WORK / "takes"; TEXTS = HERE / "texts"
MARK, MARK_AT = 200, 0.45
FIELD, MARKER = "0x10243a", "0x00c8ff"

BASE = {"text": "flat", "size": (1080, 1920), "fps": 30, "codec": "h264", "turned": False, "uneven": False, "sound": "voice", "gain": 0, "noise": 0,
        "lead": 0, "tail": 0, "stereo": False, "rate": 48000, "ext": "mp4"}

# Different takes: each differs from the plain one in what its name says
TAKES_GOOD = [
    {"name": "plain"},
    {"name": "phone", "codec": "hlg", "turned": True, "gain": -22, "tail": 2.5, "ext": "mov", "about": "like her phone: HDR, stored sideways, quiet, a silent tail"},
    {"name": "landscape", "text": "house", "size": (1920, 1080)},
    {"name": "small-24fps", "text": "house", "size": (720, 1280), "fps": 24},
    {"name": "uhd-60fps", "text": "repair", "size": (2160, 3840), "fps": 60, "codec": "hevc"},
    {"name": "square", "text": "repair", "size": (1080, 1080)},
    {"name": "uneven-frames", "uneven": True, "about": "frames arrive at uneven intervals"},
    {"name": "quiet", "text": "house", "gain": -30},
    {"name": "loud", "text": "house", "gain": 10},
    {"name": "noisy", "text": "repair", "noise": 0.03},
    {"name": "stereo-44k", "stereo": True, "rate": 44100},
    {"name": "silent-ends", "text": "hello", "lead": 2, "tail": 6},
    {"name": "pauses", "text": "pauses"},
    {"name": "numbers", "text": "numbers"},
    {"name": "long", "text": "long"},
]
# Takes the pipeline must refuse, each with the words its refusal should contain
TAKES_BAD = [
    {"name": "no-sound", "sound": None, "refusal": "no sound"},
    {"name": "silence", "sound": "silence", "refusal": "no speech"},
    {"name": "noise-only", "sound": "noise", "refusal": "no speech"},
]


def run(*cmd):
    done = subprocess.run(cmd, text=True, errors="replace", capture_output=True)
    if done.returncode: raise RuntimeError(f"{cmd[0]} failed:\n{done.stderr[-1500:]}")
    return done.stdout


def seconds(path):
    return float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)))


def said(text):
    """The words of a text as they should be heard: no pause marks, no punctuation."""
    plain = re.sub(r"\[\[.*?\]\]", " ", (TEXTS / f"{text}.txt").read_text(encoding="utf-8"))
    return words(plain)


def words(text):
    return re.sub(r"[^\w\s'-]", " ", text.lower().replace("’", "'").replace("ʼ", "'")).split()


def build(take, fresh=False):
    take = {**BASE, **take}; out = TAKES / f"{take['name']}.{take['ext']}"
    if out.exists() and not fresh: return out
    TAKES.mkdir(parents=True, exist_ok=True)
    w, h = take["size"]; fps = take["fps"]
    side = round(MARK / max(1080 / w, 1920 / h) / 2) * 2  # the marker's size in the take, so that it is MARK wide in the result
    voice = VOICE / f"{take['text']}.aiff"
    length = take["lead"] + seconds(voice) + take["tail"] if take["sound"] == "voice" else 8.0
    picture = f"color=c={FIELD}:s={w}x{h}:r={fps}:d={length:.3f},drawbox=x=(iw-{side})/2:y=ih*{MARK_AT}-{side}/2:w={side}:h={side}:color={MARKER}:t=fill"
    if take["uneven"]: picture += ",select='not(eq(mod(n,7),3))'"
    if take["turned"]: picture += ",transpose=2"
    picture += ",format=yuv420p10le" if take["codec"] == "hlg" else ",format=yuv420p"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", picture]
    layout = "stereo" if take["stereo"] else "mono"
    if take["sound"] == "voice":
        cmd += ["-i", str(voice)]
        chain = f"[1:a]adelay={take['lead'] * 1000:.0f}:all=1,apad=pad_dur={take['tail']},volume={take['gain']}dB"
        if take["noise"]:
            cmd += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude={take['noise']}:d={length:.3f}"]; chain += "[voice];[voice][2:a]amix=inputs=2:normalize=0"
        cmd += ["-filter_complex", f"{chain},aformat=channel_layouts={layout}[a]", "-map", "0:v", "-map", "[a]"]
    elif take["sound"] == "silence": cmd += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={length}", "-map", "0:v", "-map", "1:a"]
    elif take["sound"] == "noise": cmd += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.05:d={length}", "-map", "0:v", "-map", "1:a"]
    else: cmd += ["-map", "0:v", "-an"]
    if take["sound"]: cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", str(take["rate"])]
    if take["codec"] == "h264": cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20"]
    else:
        hlg = ":colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc" if take["codec"] == "hlg" else ""
        cmd += ["-c:v", "libx265", "-preset", "ultrafast", "-crf", "24", "-x265-params", "log-level=error" + hlg, "-tag:v", "hvc1"]
    if take["uneven"]: cmd += ["-fps_mode", "vfr"]
    cmd += ["-t", f"{length:.3f}"]
    if take["turned"]:
        # A phone stores a portrait video sideways with a note to turn it when showing
        flat = TAKES / f"{take['name']}.flat.{take['ext']}"
        run(*cmd, str(flat)); run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-display_rotation:v:0", "-90", "-i", str(flat), "-c", "copy", str(out)); flat.unlink()
    else: run(*cmd, str(out))
    return out


def junk():
    """Files that are not videos at all."""
    TAKES.mkdir(parents=True, exist_ok=True)
    text = TAKES / "not-a-video.mov"; text.write_text("this is a text file with a video's name\n" * 50)
    empty = TAKES / "empty.mp4"; empty.write_bytes(b"")
    return [text, empty]


def picture(name, colour, size=(1600, 900)):
    """A plain picture of one colour, to stand in for a photo."""
    out = TAKES / name
    if not out.exists():
        TAKES.mkdir(parents=True, exist_ok=True)
        run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s={size[0]}x{size[1]}", "-frames:v", "1", str(out))
    return out
