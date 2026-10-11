"""Short sounds under what appears on screen: a pop for a sticker, a chime for a figure, a whoosh for a picture or a break,
a soft thud for a title. They are made here from sine waves and noise, so nothing is borrowed from anyone."""
import wave
import numpy as np

RATE = 48000
LEVELS = {"off": 0.0, "quiet": 0.09, "normal": 0.18}   # the peak of a sound; speech peaks near 0.8


def sweep(seconds, low, high, decay):
    t = np.arange(int(RATE * seconds)) / RATE
    return np.sin(2 * np.pi * np.cumsum(low + (high - low) * t / seconds) / RATE) * np.exp(-t * decay)


def pop(): return sweep(0.11, 420, 940, 34)
def thud(): return sweep(0.22, 150, 55, 16) * 1.3


def chime():
    t = np.arange(int(RATE * 0.5)) / RATE
    return (np.sin(2 * np.pi * 1318.5 * t) + 0.45 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t * 9) * 0.6


def whoosh(seconds=0.42):
    """Noise between 400 and 6000 Hz that swells and falls away; the same every time."""
    n = int(RATE * seconds); spectrum = np.fft.rfft(np.random.default_rng(7).standard_normal(n)); hz = np.fft.rfftfreq(n, 1 / RATE)
    spectrum[(hz < 400) | (hz > 6000)] = 0; noise = np.fft.irfft(spectrum, n); t = np.arange(n) / n
    return noise / np.abs(noise).max() * np.sin(np.pi * t ** 0.7) ** 2 * 0.8


def events(timeline):
    """(second, sound) for everything that appears in the video."""
    out = []
    for o in timeline.get("overlays", []):
        if o["kind"] == "list": out += [(i["start"], "pop") for i in o.get("items", [])]
        else: out.append((o["start"] + 0.04, "pop"))
        if o["kind"] == "number": out.append((o["start"] + 0.72, "chime"))   # the figure has counted up
    for b in timeline.get("beats", []):
        if b["kind"] == "title": out.append((b["start"], "thud"))
        elif b["kind"] in ("full", "cutaway", "backdrop"): out.append((b["start"] - 0.2, "whoosh"))
    for b in timeline.get("breaks", []): out += [(b["start"] - 0.1, "whoosh"), (b["end"] - 0.3, "whoosh")]
    return sorted((max(0.0, t), name) for t, name in out)


def track(timeline, out):
    """The sounds of a video as one file as long as the video, or None when it is to have none."""
    level = LEVELS.get(timeline["style"].get("sounds"), 0.0); found = events(timeline)
    if not level or not found: return None
    made = {"pop": pop(), "chime": chime(), "thud": thud(), "whoosh": whoosh()}; mix = np.zeros(int(RATE * timeline["seconds"]) + RATE)
    for t, name in found:
        at = int(t * RATE); sound = made[name][:max(0, len(mix) - at)]; mix[at:at + len(sound)] += sound
    mix = np.clip(mix[:int(RATE * timeline["seconds"])] * level, -0.5, 0.5)
    with wave.open(str(out), "wb") as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(RATE); file.writeframes((mix * 32767).astype("<i2").tobytes())
    return out
