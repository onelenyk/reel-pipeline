"""Experiment: does a second, English pass hear English names better? usage: ./reel run lab/speech/two_languages.py
Result (2026-10-10): no. In English mode the recogniser translates the Ukrainian speech into English and takes up to three
times longer; `hotwords` fix the names but drop full stops. What works is a vocabulary given as an opening sentence (engine/speech.py)."""
import subprocess, time
from engine import speech
m = speech.recogniser("large-v3-turbo")
def run(wav, **kw):
    t = time.time(); segs, meta = m.transcribe(wav, word_timestamps=True, vad_filter=True, beam_size=5, **kw)
    words = [w for s in segs for w in (s.words or [])]
    return words, round(time.time() - t, 1), meta.language
for name, a, b in (("IMG_7824", 0, 32), ("IMG_7811", 0, 16), ("IMG_7821", 8, 14)):
    wav = f"/tmp/{name}.wav"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", f"/work/media/{name}.MOV", "-vn", "-ac", "1", "-ar", "16000", wav])
    print("\n==", name)
    A, ta, lang = run(wav); print("auto", lang, ta, "s:", " ".join(f"{w.word.strip()}{'?' if w.probability < 0.5 else ''}" for w in A))
    B, tb, _ = run(wav, language="uk", hotwords="G-Village, Гореничі, Шелест, котеджне містечко, передпокій"); print("uk+hotwords", tb, "s:", " ".join(w.word.strip() for w in B))
    P, tp, _ = run(wav, language="uk", initial_prompt="Огляд будинку в котеджному містечку G-Village, село Гореничі. Передпокій, кухня-вітальня, гардеробна."); print("uk+prompt", tp, "s:", " ".join(w.word.strip() for w in P))
    C, tc, _ = run(wav, language="en"); print("en", tc, "s:", " ".join(f"{w.word.strip()}({w.start:.1f},{w.probability:.2f})" for w in C)[:900])
    print("low in auto:", [(w.word.strip(), round(w.start, 1), round(w.probability, 2)) for w in A if w.probability < 0.6])
