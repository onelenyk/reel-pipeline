"""Finds openly licensed pictures on the internet that could stand in for material the author has not supplied.

Source: Openverse (openly licensed images, mostly from Flickr and Wikimedia), limited to licences that allow
commercial use and changes. These are illustrations, not pictures of the author's own property: the page says so, and the
credit travels with the picture so it can be given where the video is posted.
"""
import os, re, tempfile
from pathlib import Path
import requests
from . import HOME

API = "https://api.openverse.org/v1/images/"
AGENT = {"User-Agent": "reel-pipeline/0.1 (local tool)"}
ID = re.compile(r"^[0-9a-f-]{36}$")
MAX_BYTES = 20_000_000
# Licences that allow both commercial use and changes: putting a picture in a video with text over it is a change,
# so "no derivatives" licences are left out
LICENSES = "cc0,pdm,by,by-sa"


def query_for(what):
    """A short English search phrase for a request written in the author's language."""
    response = requests.post("https://api.deepseek.com/chat/completions", timeout=60, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
                             json={"model": "deepseek-flash", "thinking": {"type": "disabled"}, "temperature": 0.2, "max_tokens": 40, "messages": [{"role": "user", "content":
                                   "Напиши англійською пошуковий запит із 3-5 слів для фотобанку за цим описом потрібного фото. Без назв конкретних об'єктів. Лише запит, без лапок.\n\n" + what}]})
    response.raise_for_status()
    return re.sub(r"[^\w\s-]", "", response.json()["choices"][0]["message"]["content"]).strip()[:60]


def credit(item):
    return {"title": (item.get("title") or "")[:80], "creator": (item.get("creator") or "")[:60], "license": f'CC {str(item.get("license", "")).upper()} {item.get("license_version") or ""}'.strip(),
            "source": item.get("foreign_landing_url") or "", "found_by": "internet search"}


def search(query, count=8):
    response = requests.get(API, timeout=30, headers=AGENT, params={"q": query, "page_size": count, "license": LICENSES, "mature": "false"})
    response.raise_for_status()
    return [{"id": r["id"], "thumb": r.get("thumbnail") or r.get("url"), "width": r.get("width"), "height": r.get("height"), **credit(r)} for r in response.json().get("results", []) if ID.match(r.get("id", ""))]


def fetch(image_id):
    """Downloads one search result by its id. The address comes from the search service, never from the page."""
    if not ID.match(image_id): raise ValueError("not a search result")
    record = requests.get(f"{API}{image_id}/", timeout=30, headers=AGENT); record.raise_for_status(); item = record.json()
    url = item.get("url", "")
    if not url.startswith("https://"): raise ValueError("the picture has no secure address")
    with requests.get(url, timeout=60, headers=AGENT, stream=True) as download:
        download.raise_for_status()
        kind = download.headers.get("Content-Type", "")
        if not kind.startswith("image/"): raise ValueError("that address is not a picture")
        suffix = {"image/png": ".png", "image/webp": ".webp"}.get(kind.split(";")[0], ".jpg")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=str(HOME / "out")); size = 0
        for chunk in download.iter_content(1 << 16):
            size += len(chunk)
            if size > MAX_BYTES: tmp.close(); Path(tmp.name).unlink(); raise ValueError("the picture is too large")
            tmp.write(chunk)
        tmp.close()
    return Path(tmp.name), credit(item)
