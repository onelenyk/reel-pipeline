"""Thin, strict wrappers around ffmpeg and ffprobe."""
import json, re, subprocess, time


class ToolError(RuntimeError):
    pass


def run(cmd, capture=False, stdin=None):
    started = time.time()
    result = subprocess.run(cmd, text=True, errors="replace", stdin=stdin, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        raise ToolError(f"{cmd[0]} failed:\n{result.stderr[-2000:]}")
    return (result.stdout or "") + (result.stderr or "") if capture else round(time.time() - started, 1)


def ffmpeg(*args, capture=False, stdin=None):
    return run(["ffmpeg", "-hide_banner", "-nostats", "-y", *args], capture, stdin)


def _rate(text):
    if not text or "/" not in text or text.endswith("/0"): return None
    a, b = text.split("/"); return round(int(a) / int(b), 3)


def probe(path):
    """What a file is, in the terms the pipeline cares about."""
    data = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture=True))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    side = video.get("side_data_list", [])
    rotation = next((d.get("rotation") for d in side if "rotation" in d), 0) or 0
    width, height = video.get("width", 0), video.get("height", 0)
    if abs(rotation) == 90: width, height = height, width  # as it is displayed, not as it is stored
    return {"seconds": round(float(data["format"].get("duration", 0)), 3), "width": width, "height": height, "fps": round(_rate(video.get("r_frame_rate")) or 30),
            "hdr": video.get("color_transfer") in ("smpte2084", "arib-std-b67"), "has_audio": any(s["codec_type"] == "audio" for s in data["streams"])}


def loudness(path):
    log = ffmpeg("-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-", capture=True)
    tail = log[log.rfind("Summary"):]
    grab = lambda label: float(re.search(label + r":\s+(-?[\d.]+)", tail).group(1))
    return {"lufs": grab("I"), "range": grab("LRA"), "peak": grab("Peak")}


def tone_filter(hdr):
    """HDR phone footage mapped to ordinary colour, so it looks the same on every screen."""
    if not hdr: return "format=yuv420p"
    return "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
