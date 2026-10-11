#!/usr/bin/env python3
"""Speaks the test takes with a local voice (Piper, Ukrainian, three speakers): lab/blind/work/NAME.wav and NAME.truth.json,
which says when each line is spoken. Run on the Mac itself:
  python3 -m venv lab/blind/.venv && lab/blind/.venv/bin/pip install piper-tts
  lab/blind/.venv/bin/python -m piper.download_voices uk_UA-ukrainian_tts-medium --download-dir models/piper
  lab/blind/.venv/bin/python lab/blind/make.py [fresh]
"""
import json, sys, wave
from pathlib import Path
import numpy as np
from piper import PiperVoice, SynthesisConfig
sys.path.insert(0, str(Path(__file__).parent))
from samples import SAMPLES

HERE = Path(__file__).parent; WORK = HERE / "work"; WORK.mkdir(exist_ok=True)
MODEL = HERE.parent.parent / "models" / "piper" / "uk_UA-ukrainian_tts-medium.onnx"
voice = PiperVoice.load(str(MODEL)); RATE = voice.config.sample_rate; SPEAKERS = {"lada": 0, "mykyta": 1, "tetiana": 2}

for s in SAMPLES:
    out = WORK / f"{s['name']}.wav"
    if out.exists() and "fresh" not in sys.argv: continue
    config = SynthesisConfig(speaker_id=SPEAKERS[s["voice"]], length_scale=s["pace"]); parts, times, at = [np.zeros(int(RATE * 0.4), dtype=np.float32)], [], 0.4
    for line in s["lines"]:
        # a line that breaks off is said without its dots, and the pause after it is the hesitation
        spoken = np.concatenate([chunk.audio_float_array for chunk in voice.synthesize(line["text"].lower().replace("...", ","), syn_config=config)])
        times.append({**line, "start": round(at, 2), "end": round(at + len(spoken) / RATE, 2)})
        gap = np.zeros(int(RATE * s["pause"]), dtype=np.float32); parts += [spoken, gap]; at += (len(spoken) + len(gap)) / RATE
    sound = np.concatenate(parts)
    if s["noise"]: sound = sound + np.random.default_rng(len(sound)).standard_normal(len(sound)).astype(np.float32) * s["noise"]   # the hiss of a room
    with wave.open(str(out), "wb") as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(RATE); file.writeframes((np.clip(sound, -1, 1) * 32767).astype("<i2").tobytes())
    (WORK / f"{s['name']}.truth.json").write_text(json.dumps({**s, "lines": times, "seconds": round(len(sound) / RATE, 2)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out.name, s["voice"], f"{len(sound) / RATE:.0f} s", sum(not l["keep"] for l in s["lines"]), "to cut")
