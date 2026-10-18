"""Saved styles: a look worked out once and reused on other videos. One JSON file per style."""
import json, re
from pathlib import Path
from . import HOME, project

ROOT = HOME / "styles"
DEFAULT = ROOT / "default.txt"


def slug(name):
    """A file name for a style name; Cyrillic is kept, anything unsafe becomes a dash."""
    return re.sub(r"[^\w-]+", "-", name.strip().lower(), flags=re.UNICODE).strip("-")[:40] or "style"


def listing():
    chosen = DEFAULT.read_text(encoding="utf-8").strip() if DEFAULT.exists() else ""
    out = []
    for path in sorted(ROOT.glob("*.json")) if ROOT.exists() else []:
        try: out.append({"id": path.stem, **project.clean_style(json.loads(path.read_text(encoding="utf-8"))), "default": path.stem == chosen})
        except (ValueError, OSError): continue  # a damaged file is not a style
    return out


def save(name, style):
    style = project.clean_style({**style, "name": name}); key = slug(style["name"])
    project.write_whole(ROOT / f"{key}.json", json.dumps(style, ensure_ascii=False, indent=1)); return key


def get(key):
    path = ROOT / f"{slug(key)}.json"
    if not path.exists(): raise KeyError(f"no style {key}")
    return project.clean_style(json.loads(path.read_text(encoding="utf-8")))


def remove(key):
    path = ROOT / f"{slug(key)}.json"
    if path.exists(): path.unlink()
    if DEFAULT.exists() and DEFAULT.read_text(encoding="utf-8").strip() == slug(key): DEFAULT.unlink()


def rename(key, name):
    """A saved style under another name. Being the default for new videos goes with it; returns its new key."""
    style = get(key); name = " ".join(str(name or "").split())[:40]
    if not name: raise ValueError("a style needs a name")
    new = slug(name)
    if new != slug(key) and (ROOT / f"{new}.json").exists(): raise ValueError("another saved style has that name")
    was_default = DEFAULT.exists() and DEFAULT.read_text(encoding="utf-8").strip() == slug(key)
    save(name, style)
    if new != slug(key): (ROOT / f"{slug(key)}.json").unlink(missing_ok=True)
    if was_default: project.write_whole(DEFAULT, new)
    return new


def set_default(key):
    """New videos start with this style ("" = the built-in one)."""
    if key: get(key); project.write_whole(DEFAULT, slug(key))
    elif DEFAULT.exists(): DEFAULT.unlink()


def default():
    try: return get(DEFAULT.read_text(encoding="utf-8").strip()) if DEFAULT.exists() else None
    except (KeyError, ValueError, OSError): return None
