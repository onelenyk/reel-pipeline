"""Experiment: the recogniser leaves out speech it takes for repetition (retakes, stumbles) and stretches a neighbouring word
over it. Which settings bring the left-out speech back? usage: ./reel run lab/speech/verbatim.py IMG_7824 120 175"""
import subprocess, sys, time
sys.path.insert(0, "/work")
from engine import speech
name, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
wav = "/tmp/part.wav"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", f"/work/media/{name}.MOV", "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
model = speech.recogniser("large-v3-turbo"); base = dict(word_timestamps=True, beam_size=5)
ways = {
    "no vocabulary": dict(vad_filter=True),
    "vocabulary as hot words": dict(vad_filter=True, hotwords=", ".join(speech.vocabulary())),
    "vocabulary as a short list of names only": dict(vad_filter=True, initial_prompt=", ".join(t for t in speech.vocabulary() if t[:1].isupper()) + "."),
}
if len(sys.argv) > 4: ways = {"as now": dict(vad_filter=True, initial_prompt=speech.primer()), **ways}
for way, settings in ways.items():
    began = time.time(); segments, _ = model.transcribe(wav, **base, **settings); words = [w for s in segments for w in (s.words or [])]
    long = [w for w in words if w.end - w.start > 1.2]; holes = [(round(x.end + a, 1), round(y.start + a, 1)) for x, y in zip(words, words[1:]) if y.start - x.end > 1.5]
    print(f"\n== {way}: {len(words)} words, {time.time() - began:.0f} s, words longer than 1.2 s: {len(long)}, holes over 1.5 s: {holes}")
    print("   " + " ".join(w.word.strip() + (f"<{w.end - w.start:.1f}s>" if w.end - w.start > 1.2 else "") for w in words))
