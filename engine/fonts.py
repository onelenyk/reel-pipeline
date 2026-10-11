"""Fonts for the words drawn over the video. Inter comes with the engine; any family of Google Fonts is fetched once,
by name, and kept in HOME/fonts, so a video builds the same with no network afterwards."""
import re
from pathlib import Path
import requests
from . import HOME

FOLDER = HOME / "fonts"
BUILT_IN = "Inter"
# Families that have Cyrillic and read well as large words over a picture: the ones the page offers. Any other family
# of Google Fonts can be typed in by name.
OFFERED = ["Inter", "Montserrat", "Unbounded", "Rubik", "Manrope", "Golos Text", "Nunito", "Jost", "Exo 2", "Oswald", "Roboto Condensed", "Russo One", "Play", "Comfortaa",
           "Playfair Display", "PT Serif", "Lobster", "Pacifico", "Caveat"]
WEIGHTS = (800, 700, 900, 600, 400)  # the heaviest a family has, as near to extra bold as it comes


def clean(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    return name if re.fullmatch(r"[A-Za-z0-9 ]{2,40}", name) else BUILT_IN


def face(name):
    """What the renderer needs to draw in a family: {"font_file", "font_weight"}, or {} for the built-in one.
    A family that cannot be fetched (no network, no such name) falls back to the built-in font and says so in "font_note"."""
    name = clean(name)
    if name == BUILT_IN: return {}
    slug = name.lower().replace(" ", "-")
    for kept in sorted(FOLDER.glob(f"{slug}-*.ttf")):
        return {"font_file": str(kept), "font_weight": int(kept.stem.rsplit("-", 1)[1])}
    for weight in WEIGHTS:
        try:
            # asked without a browser's name, the service answers with one TrueType file for all alphabets
            sheet = requests.get("https://fonts.googleapis.com/css2", params={"family": f"{name}:wght@{weight}"}, headers={"User-Agent": "reel"}, timeout=15)
            found = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", sheet.text) if sheet.ok else None
            if not found: continue
            data = requests.get(found.group(1), timeout=30); data.raise_for_status()
            FOLDER.mkdir(parents=True, exist_ok=True); kept = FOLDER / f"{slug}-{weight}.ttf"; kept.write_bytes(data.content)
            return {"font_file": str(kept), "font_weight": weight}
        except requests.RequestException as error:
            return {"font_note": f"the font {name} could not be fetched ({str(error)[:80]}); the built-in one is used"}
    return {"font_note": f"there is no font called {name} on Google Fonts with a bold weight; the built-in one is used"}
