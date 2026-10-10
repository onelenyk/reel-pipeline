"""Speech to words with timings."""
import os, re, tempfile, threading
from pathlib import Path
from . import HOME
from .media import ffmpeg

MODELS = Path("/work/models")
FOREIGN = re.compile("[ыэъёЫЭЪЁ]")


# Names and terms the recogniser should expect. Without them it writes "котерне містечко" and "перед покій";
# with them, the same audio comes out right, at no cost in time. The author adds their own on the page.
VOCABULARY = HOME / "vocabulary.txt"
SEED = ["котеджне містечко", "передпокій", "кухня-вітальня", "гардеробна", "санвузол", "пральня", "тераса", "навіс", "бомбосховище", "панорамні вікна"]


def vocabulary():
    if not VOCABULARY.exists(): return list(SEED)
    return [line.strip() for line in VOCABULARY.read_text(encoding="utf-8").splitlines() if line.strip()][:60]


def primer():
    """The vocabulary as an opening the recogniser continues from. Written as sentences: a bare list of words makes it drop full stops."""
    terms = vocabulary()
    return ("Розповідь про нерухомість. У ній звучать слова: " + ", ".join(terms)[:600] + ". Далі сама розповідь.") if terms else None


def set_vocabulary(terms):
    clean, seen = [], set()
    for term in terms:
        term = re.sub(r"\s+", " ", str(term)).strip(" ,.;")[:40]
        if term and term.lower() not in seen: seen.add(term.lower()); clean.append(term)
    VOCABULARY.parent.mkdir(parents=True, exist_ok=True); VOCABULARY.write_text("\n".join(clean[:60]) + "\n", encoding="utf-8"); return clean[:60]


def learn(term):
    """A corrected word that looks like a name (a capital letter or Latin letters) is remembered for the next videos."""
    term = term.strip(" ,.;!?«»\"")
    if len(term) >= 3 and (term[0].isupper() or re.search("[A-Za-z]", term)) and term.lower() not in {t.lower() for t in vocabulary()}: set_vocabulary(vocabulary() + [term])


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
        segments, meta = recogniser(model_name).transcribe(str(wav), word_timestamps=True, vad_filter=True, beam_size=5, initial_prompt=primer())
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
        if words and (text.startswith("-") or words[-1]["text"].endswith("-") or (re.match(r"[.,]\d", text) and words[-1]["text"][-1:].isdigit())):
            words[-1] = {**words[-1], "text": words[-1]["text"] + text, "end": round(w.end, 2), "confidence": round(min(words[-1]["confidence"], w.probability), 2)}
        else:
            words.append({"text": text, "start": round(w.start, 2), "end": round(w.end, 2), "confidence": round(w.probability, 2)})
    if meta.language == "uk":
        # Letters Ukrainian does not have mean the word was heard as Russian: mark it as doubtful, so the page points at it
        for word in words:
            if FOREIGN.search(word["text"]): word["confidence"] = min(word["confidence"], 0.3)
    return {"language": meta.language, "words": words}
