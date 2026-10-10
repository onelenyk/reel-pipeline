"""Cuts the speaker out of the background for a stretch of the take: a greyscale video where white is the person."""
import subprocess, time
from pathlib import Path
from . import media

SIZE = (432, 768)  # the matte is computed small and scaled up; edges are softened afterwards


def matte(source, hdr, start, seconds, fps, frame, out):
    """`frame` is the (width, height) the footage is cropped to in the finished video, so the matte lines up with it."""
    import numpy as np, torch
    model = torch.hub.load("PeterL1n/RobustVideoMatting", "mobilenetv3", trust_repo=True, verbose=False).eval()
    w, h = SIZE; started = time.time()
    crop = f"scale={frame[0]}:{frame[1]}:force_original_aspect_ratio=increase,crop={frame[0]}:{frame[1]},scale={w}:{h}"
    reader = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(source),
                               "-vf", f"{media.tone_filter(hdr)},fps={fps},{crop}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    writer = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                               "-c:v", "ffv1", str(out)], stdin=subprocess.PIPE)
    state, count = [None] * 4, 0
    with torch.no_grad():
        while True:
            raw = reader.stdout.read(w * h * 3)
            if len(raw) < w * h * 3: break
            picture = torch.from_numpy(np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()).permute(2, 0, 1).float().div(255).unsqueeze(0)
            # The model remembers the previous frames (state), which keeps the edge steady from frame to frame
            _, alpha, *state = model(picture, *state, downsample_ratio=0.6)
            writer.stdin.write((alpha[0, 0].clamp(0, 1) * 255).byte().numpy().tobytes()); count += 1
    writer.stdin.close(); writer.wait(); reader.wait()
    return {"frames": count, "took_seconds": round(time.time() - started, 1)}
