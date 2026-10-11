"""Speech to words with timings."""
import difflib, os, re, tempfile, threading
from pathlib import Path
from . import HOME
from .media import ffmpeg

MODELS = Path("/work/models")
FOREIGN = re.compile("[ыэъёЫЭЪЁ]")


# Names and terms the recogniser should expect. Without them it writes "котерне містечко" and "перед покій";
# with them, the same audio comes out right, at no cost in time. The author adds their own on the page.
VOCABULARY = HOME / "vocabulary.txt"
SEED = ["котеджне містечко", "передпокій", "кухня-вітальня", "гардеробна", "санвузол", "пральня", "тераса", "навіс", "бомбосховище", "панорамні вікна"]


def lines():
    """The vocabulary as written: a term to a line, optionally with the ways it is misheard, "G-Village = Джівілич, Джі Вілідж"."""
    if not VOCABULARY.exists(): return list(SEED)
    return [line.strip() for line in VOCABULARY.read_text(encoding="utf-8").splitlines() if line.strip()][:80]


def vocabulary(): return [line.split("=")[0].strip() for line in lines() if line.split("=")[0].strip()]


def misheard():
    """What the recogniser writes instead of a term, as people have corrected it: heard (letters only) -> term."""
    return {letters(h): line.split("=")[0].strip() for line in lines() if "=" in line for h in line.split("=", 1)[1].split(",") if letters(h)}


def primer():
    """The vocabulary as an opening the recogniser continues from. Written as sentences: a bare list of words makes it drop full stops."""
    terms = vocabulary()
    return ("Розповідь про нерухомість. У ній звучать слова: " + ", ".join(terms)[:600] + ". Далі сама розповідь.") if terms else None


def set_vocabulary(terms):
    clean, seen = [], set()
    for term in terms:
        term = re.sub(r"\s+", " ", str(term)).strip(" ,.;")[:120]
        key = term.split("=")[0].strip().lower()
        if key and key not in seen: seen.add(key); clean.append(term)
    VOCABULARY.parent.mkdir(parents=True, exist_ok=True); VOCABULARY.write_text("\n".join(clean[:80]) + "\n", encoding="utf-8"); return clean[:80]


def learn(term, heard=None):
    """A corrected word that looks like a name (a capital letter or Latin letters) is remembered for the next videos,
    together with what the recogniser wrote instead of it: next time that is respelled without anyone's help."""
    term = term.strip(" ,.;!?«»\"")
    if not (len(term) >= 3 and (term[0].isupper() or re.search("[A-Za-z]", term))): return
    kept = lines(); heard = (heard or "").strip(" ,.;!?«»\"")
    for i, line in enumerate(kept):
        if line.split("=")[0].strip().lower() == term.lower():
            if heard and letters(heard) != letters(term) and letters(heard) not in misheard(): kept[i] = line + (", " if "=" in line else " = ") + heard
            break
    else: kept.append(term + (f" = {heard}" if heard and letters(heard) != letters(term) else ""))
    set_vocabulary(kept)


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
        # No vocabulary is given to the recogniser: any hint of what to expect makes it leave out what it takes for
        # repetition, and a failed attempt said again is exactly what must be seen to be cut (lab/speech/verbatim.py)
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
        if words and (text.startswith("-") or words[-1]["text"].endswith("-") or (re.match(r"[.,]\d", text) and words[-1]["text"][-1:].isdigit())):
            words[-1] = {**words[-1], "text": words[-1]["text"] + text, "end": round(w.end, 2), "confidence": round(min(words[-1]["confidence"], w.probability), 2)}
        else:
            words.append({"text": text, "start": round(w.start, 2), "end": round(w.end, 2), "confidence": round(w.probability, 2)})
    if meta.language == "uk":
        # Letters Ukrainian does not have mean the word was heard as Russian: mark it as doubtful, so the page points at it
        for word in words:
            if FOREIGN.search(word["text"]): word["confidence"] = min(word["confidence"], 0.3)
    for word in words:
        # A word stretched far beyond what its letters take hides speech the recogniser left out: the word keeps its start
        longest = LONGEST + PER_LETTER * len(re.sub(r"[^\w]", "", word["text"]))
        if word["end"] - word["start"] > longest: word["end"] = round(word["start"] + longest, 2); word["confidence"] = min(word["confidence"], 0.4)
    return {"language": meta.language, "words": spelled(words, vocabulary())}


LONGEST, PER_LETTER = 0.45, 0.11  # seconds: what a word may last, however slowly it is said
ALIKE = 0.72                      # how alike a heard name and a name of the vocabulary must be to be taken for it


def letters(text): return re.sub(r"[^\w]", "", text.lower().replace("ʼ", "").replace("'", ""))


def spelled(words, terms, known=None):
    """The vocabulary's spelling for what was heard, applied after recognition.
    Two words that together are a term become it ("перед покій", "G Village"); a capitalised word that is nearly a name
    of the vocabulary becomes that name ("Горанич" for "Гореничі"). What was heard is kept in "heard"."""
    whole = {letters(t): t for t in terms if " " not in t.strip()}; names = [t for t in terms if t[:1].isupper() and " " not in t and len(t) >= 5]
    whole.update(known if known is not None else misheard())
    out = []
    for word in words:
        tail = re.search(r"[^\w]*$", word["text"]).group(0)
        # a short preposition heard as part of the word before a term: "вперед покій" is "в передпокій"
        stuck = next((p for p in ("в", "у", "з") if out and letters(out[-1]["text"]) + letters(word["text"]) == p + letters(whole.get((letters(out[-1]["text"]) + letters(word["text"]))[1:], "\0"))), None)
        if stuck:
            term = whole[(letters(out[-1]["text"]) + letters(word["text"]))[1:]]; first = out[-1]["text"]
            out[-1] = {**out[-1], "heard": first, "text": stuck.upper() if first[:1].isupper() else stuck, "end": round(min(out[-1]["end"], out[-1]["start"] + 0.2), 2)}
            out.append({**word, "heard": word["text"], "text": term + tail}); continue
        if letters(word["text"]) in whole and whole[letters(word["text"])] != word["text"][:len(word["text"]) - len(tail)] and letters(whole[letters(word["text"])]) != letters(word["text"]):
            out.append({**word, "heard": word["text"], "text": whole[letters(word["text"])] + tail}); continue
        if out and letters(out[-1]["text"]) + letters(word["text"]) in whole and letters(word["text"]) not in whole:
            term = whole[letters(out[-1]["text"]) + letters(word["text"])]; first = out[-1]["text"]
            out[-1] = {**out[-1], "heard": out[-1].get("heard", first) + " " + word["text"], "text": (term[:1].upper() + term[1:] if first[:1].isupper() and not term[:1].isupper() else term) + tail,
                       "end": word["end"], "confidence": round(min(out[-1]["confidence"], word["confidence"]), 2)}
            continue
        bare = word["text"][:len(word["text"]) - len(tail)] if tail else word["text"]
        if bare[:1].isupper() and len(bare) >= 5 and letters(bare) not in whole:
            best = max(names, key=lambda t: difflib.SequenceMatcher(None, letters(bare), letters(t)).ratio(), default=None)
            if best and best[:1].lower() == bare[:1].lower() and difflib.SequenceMatcher(None, letters(bare), letters(best)).ratio() >= ALIKE:
                word = {**word, "heard": word["text"], "text": best + tail}
        out.append(word)
    return [{"id": i, **{k: v for k, v in w.items() if k != "id"}} for i, w in enumerate(out)] if out and "id" in out[0] else out
