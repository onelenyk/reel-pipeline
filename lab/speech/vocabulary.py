"""Experiment: the whole of IMG_7824 recognised with the vocabulary. usage: ./reel run lab/speech/vocabulary.py
Result (2026-10-10): "G-Village", "передпокій", "котеджне містечко" come out right and punctuation stays; the recogniser also
smooths the speech (a repeated sentence dropped, a swear word softened). Later (lab/speech/verbatim.py) this smoothing was found to hide failed attempts, and the engine stopped
giving the recogniser a vocabulary; this script still does, to show the effect."""
import json
from engine import speech
speech.VOCABULARY.parent.mkdir(parents=True, exist_ok=True)
segments, _ = speech.recogniser("large-v3-turbo").transcribe("/work/media/IMG_7824.MOV", word_timestamps=True, vad_filter=True, beam_size=5, initial_prompt=speech.primer())
t = {"words": [{"text": w.word.strip(), "confidence": w.probability} for s in segments for w in (s.words or [])]}
text = " ".join(w["text"] for w in t["words"]); print(len(t["words"]), "words"); print(text[:1300])
