"""Experiment: the whole of IMG_7824 recognised with the vocabulary. usage: ./reel run lab/speech/vocabulary.py
Result (2026-10-10): "G-Village", "передпокій", "котеджне містечко" come out right and punctuation stays; the recogniser also
smooths the speech (a repeated sentence dropped, a swear word softened). Note: it overwrites vocabulary.txt with the seed list."""
import json
from engine import speech
speech.VOCABULARY.parent.mkdir(parents=True, exist_ok=True)
speech.set_vocabulary(speech.SEED + ["G-Village", "Гореничі"])
t = speech.transcribe("/work/media/IMG_7824.MOV")
text = " ".join(w["text"] for w in t["words"]); print(len(t["words"]), "words"); print(text[:1300])
