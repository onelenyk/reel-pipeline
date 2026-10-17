"""Workspaces: the projects of one client under one name, with what they share — a logo, the style new videos start
with, and the vocabulary of names the recogniser is taught.

Which project is in which workspace, the names the author gave projects and the workspaces' choices are kept in
workspaces.json; a workspace's own files (its logo, its vocabulary) in spaces/<name>/. The projects stay where they are."""
import json, re, shutil, threading, time
from pathlib import Path
from . import HOME, speech, styles

SPACES = HOME / "workspaces.json"; HOME_SPACE = "Мої відео"   # the workspace of a project that was put in none
TRASH = HOME / "trash"  # deleted projects are moved here, never erased: a mistake can be taken back by hand
PROJECTS = HOME / "projects"
LOGOS = (".png", ".jpg", ".jpeg", ".webp")
lock = threading.RLock()


def spaces():
    """{"spaces": [names], "of": {project: name}, "titles": {project: title}, "settings": {name: {"style": key}}}."""
    try: kept = json.loads(SPACES.read_text(encoding="utf-8"))
    except (OSError, ValueError): kept = {}
    names = [n for n in kept.get("spaces", []) if isinstance(n, str) and n.strip()]; names = [HOME_SPACE] + [n for n in names if n != HOME_SPACE]
    of = {p: s for p, s in kept.get("of", {}).items() if s in names}
    titles = {p: t for p, t in kept.get("titles", {}).items() if isinstance(t, str) and t.strip()}
    settings = {s: v for s, v in kept.get("settings", {}).items() if s in names and isinstance(v, dict)}
    return {"spaces": names, "of": of, "titles": titles, "settings": settings}


def keep(kept):
    SPACES.write_text(json.dumps({k: kept[k] for k in ("spaces", "of", "titles", "settings")}, ensure_ascii=False, indent=1), encoding="utf-8")


def clean(name): return " ".join(str(name or "").split())[:40]


def space_of(project): return spaces()["of"].get(project, HOME_SPACE)


def folder(space):
    """Where a workspace keeps its own files. The first workspace keeps them where they were before workspaces existed."""
    return HOME if space == HOME_SPACE else HOME / "spaces" / (re.sub(r"[^\w-]+", "-", space.lower(), flags=re.UNICODE).strip("-") or "space")


def book(space):
    """The workspace's vocabulary file."""
    return speech.VOCABULARY if space == HOME_SPACE else folder(space) / "vocabulary.txt"


def logo(space):
    """The workspace's logo, or None."""
    return next((folder(space) / f"logo{s}" for s in LOGOS if (folder(space) / f"logo{s}").exists()), None)


def set_logo(space, file, suffix):
    """A new logo for the workspace (None takes it away)."""
    with lock:
        for s in LOGOS: (folder(space) / f"logo{s}").unlink(missing_ok=True)
        if file: folder(space).mkdir(parents=True, exist_ok=True); shutil.move(str(file), str(folder(space) / f"logo{suffix}"))


def style_for(project):
    """The style a new video starts with: its workspace's own, else the one chosen for all new videos."""
    key = spaces()["settings"].get(space_of(project), {}).get("style")
    if key:
        try: return styles.get(key)
        except (KeyError, ValueError, OSError): pass  # the style was deleted since
    return styles.default()


def set_style(space, key):
    with lock:
        kept = spaces()
        if space not in kept["spaces"]: raise KeyError("there is no such workspace")
        if key: styles.get(key)
        kept["settings"].setdefault(space, {})["style"] = key or None; keep(kept)


def ending(space):
    """The words the workspace's videos end with ("Пишіть у дірект @agency"), or None."""
    return spaces()["settings"].get(space, {}).get("ending") or None


def set_ending(space, text):
    text = " ".join(str(text or "").split())[:48]
    with lock:
        kept = spaces()
        if space not in kept["spaces"]: raise KeyError("there is no such workspace")
        kept["settings"].setdefault(space, {})["ending"] = text or None; keep(kept)


def set_space(project_name=None, space=None):
    """Makes a workspace, and puts a project into it when one is named."""
    space = clean(space)
    if not space: raise ValueError("a workspace needs a name")
    with lock:
        kept = spaces()
        if space not in kept["spaces"]: kept["spaces"].append(space)
        if project_name: kept["of"][project_name] = space
        keep(kept)
    return spaces()


def rename(old, new):
    """A workspace under another name: its projects, its choices and its files go with it."""
    new = clean(new)
    with lock:
        kept = spaces()
        if old == HOME_SPACE: raise ValueError("the first workspace keeps its name")
        if old not in kept["spaces"]: raise KeyError("there is no such workspace")
        if not new or new in kept["spaces"]: raise ValueError("a workspace needs a name no other one has")
        if folder(new).exists(): raise ValueError("a workspace needs a name no other one has")
        if folder(old).exists(): shutil.move(str(folder(old)), str(folder(new)))
        kept["spaces"] = [new if s == old else s for s in kept["spaces"]]; kept["of"] = {p: new if s == old else s for p, s in kept["of"].items()}
        if old in kept["settings"]: kept["settings"][new] = kept["settings"].pop(old)
        keep(kept)
    return new


def remove(space):
    """Takes a workspace away. Its projects are not deleted: they go back to the first workspace. Its own files go to the trash."""
    with lock:
        kept = spaces()
        if space == HOME_SPACE: raise ValueError("the first workspace cannot be taken away")
        if space not in kept["spaces"]: raise KeyError("there is no such workspace")
        if folder(space).exists(): TRASH.mkdir(parents=True, exist_ok=True); shutil.move(str(folder(space)), str(TRASH / f"space-{folder(space).name}-{int(time.time())}"))
        kept["spaces"].remove(space); kept["of"] = {p: s for p, s in kept["of"].items() if s != space}; kept["settings"].pop(space, None); keep(kept)


def set_title(name, title):
    """The name a project is shown under. An empty one brings back the name of its folder."""
    title = " ".join(str(title or "").split())[:60]
    with lock:
        kept = spaces(); kept["titles"].pop(name, None)
        if title and title != name: kept["titles"][name] = title
        keep(kept)
    return title or name


def trash(name):
    """Takes a project off the shelf: its folder goes to the trash folder, whole. The raw take stays in the inbox."""
    with lock:
        TRASH.mkdir(parents=True, exist_ok=True); shutil.move(str(PROJECTS / name), str(TRASH / f"{name}-{int(time.time())}"))
        kept = spaces(); kept["of"].pop(name, None); kept["titles"].pop(name, None); keep(kept)
