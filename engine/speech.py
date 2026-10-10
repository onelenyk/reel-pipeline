"""Speech to words with timings."""
import os, re, tempfile, threading
from pathlib import Path
from .media import ffmpeg

MODELS = Path("/work/models")
FOREIGN = re.compile("[ыэъёЫЭЪЁ]")


_models, _loading = {}, threading.Lock()


def recogniser(name):
    with _loading:
        if name not in _models:
            from faster_whisper import WhisperModel
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8", download_root=str(MODELS), cpu_threads=os.cpu_count() or 8)
        return _models[name]


def last_voiced(wav):
    """The moment the last sound ends: the last 20 ms frame within 35 dB of the loud parts."""
    import numpy as np, soundfile as sf
    audio, rate = sf.read(str(wav), dtype="float32")
    frame = int(rate * 0.02); count = len(audio) // frame
    if not count: return 0.0
    level = 20 * np.log10(np.sqrt((audio[:count * frame].reshape(count, frame) ** 2).mean(axis=1)) + 1e-9)
    loud = np.nonzero(level > np.percentile(level, 95) - 35)[0]
    return float((loud[-1] + 1) * 0.02) if len(loud) else 0.0


def transcribe(video, model_name="large-v3-turbo"):
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav))
        segments, meta = recogniser(model_name).transcribe(str(wav), word_timestamps=True, vad_filter=True, beam_size=5)
        raw = [w for s in segments for w in (s.words or [])]
        voiced_until = last_voiced(wav)
    # The recogniser invents a polite sign-off in the silence after the speech ("Дякую за перегляд!"), squeezed
    # into no time at all. Words with no duration, and words that begin where the sound has already stopped, are not speech.
    raw = [w for w in raw if w.end - w.start > 0.02 and w.start < voiced_until - 0.03]
    words = []
    for w in raw:
        text = w.word.strip()
        if not text: continue
        # The recogniser splits "G-Village" into "G" and "-Village": put such pieces back together
        if words and (text.startswith("-") or words[-1]["text"].endswith("-")):
            words[-1] = {**words[-1], "text": words[-1]["text"] + text, "end": round(w.end, 2), "confidence": round(min(words[-1]["confidence"], w.probability), 2)}
        else:
            words.append({"text": text, "start": round(w.start, 2), "end": round(w.end, 2), "confidence": round(w.probability, 2)})
    if meta.language == "uk":
        # Letters Ukrainian does not have mean the word was heard as Russian: mark it as doubtful, so the page points at it
        for word in words:
            if FOREIGN.search(word["text"]): word["confidence"] = min(word["confidence"], 0.3)
    return {"language": meta.language, "words": words}
