"""The AI's part: what to emphasise, what might be misheard, how to cut the picture, and what material that needs.

Everything it returns is a suggestion. Emphasis and beats are accepted by default (they are easy to see and undo);
changes to words are never applied until a person accepts them, because the model guesses names it cannot know.
"""
import json, os
import requests

PROMPT = """Ти монтажер коротких вертикальних відео про нерухомість. Нижче розшифровка одного дубля, де людина говорить у камеру; слова пронумеровані.
Поверни один JSON:
{"emphasis": [номери слів],
 "corrections": [{"word": номер, "text": "виправлене слово"}],
 "beats": [{"kind": "backdrop" | "cutaway" | "title" | "zoom", "from": номер_слова, "to": номер_слова, "need": "id потреби або null", "text": "текст титру або null", "why": "коротко"}],
 "needs": [{"id": "n1", "what": "що саме потрібно від автора", "search": "3-5 слів англійською для пошуку схожого фото у фотобанку, без назв об'єктів", "kind": "photo" | "video" | "plan" | "logo", "optional": true | false}]}

emphasis: числа з одиницями, назви, ціни, ключові переваги; не більше одного-двох слів на речення.
corrections: лише очевидні помилки розпізнавання (закінчення, числа). Назви місць і об'єктів не вгадуй.
beats, щоб відео не було статичним:
- backdrop: мовця вирізано з фону, за ним картинка; cutaway: картинка у верхній частині кадру, мовець лишається видимим; title: напис у кадрі; zoom: крупніший план для наголосу.
- разом не більше 6 beats; між ними лишай час, де в кадрі просто мовець.
- вставка починається на слові, де про це заговорили, і охоплює 6-12 слів (2-4 секунди мовлення); не більше однієї вставки одночасно.
- title: лише один, з назвою об'єкта (до 14 символів), на тих словах, де назву вимовляють, і ще 6-8 слів після.
- zoom на 1-2 ключових фразах, по 5-8 слів.
needs: проси лише матеріал, який справді є в автора (фото об'єкта, вид згори, план, логотип), конкретно; не більше 5.

"""


def enabled():
    return bool(os.environ.get("DEEPSEEK_API_KEY")) and os.environ.get("REEL_AI", "on") != "off"


def suggest(words):
    if not enabled() or not words: return clean({}, len(words))  # no key or switched off: the video is made without suggestions
    numbered = " ".join(f"[{i}]{w['text']}" for i, w in enumerate(words))
    response = requests.post("https://api.deepseek.com/chat/completions", timeout=180, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
                             json={"model": "deepseek-flash", "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}, "temperature": 0.3,
                                   "messages": [{"role": "user", "content": PROMPT + numbered}]})
    response.raise_for_status()
    return clean(json.loads(response.json()["choices"][0]["message"]["content"]), len(words))


def clean(raw, count):
    """Only well-formed suggestions that point at real words survive."""
    ok = lambda i: isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count
    text = lambda v, limit: v.strip()[:limit] if isinstance(v, str) and v.strip() else None
    needs, seen = [], set()
    for n in raw.get("needs", [])[:5] if isinstance(raw.get("needs"), list) else []:
        if not isinstance(n, dict) or not text(n.get("id"), 12) or not text(n.get("what"), 140) or n["id"] in seen: continue
        seen.add(n["id"])
        needs.append({"id": n["id"], "what": text(n["what"], 140), "search": text(n.get("search"), 60), "kind": n.get("kind") if n.get("kind") in ("photo", "video", "plan", "logo") else "photo",
                      "optional": bool(n.get("optional")), "status": "open", "asset": None})
    beats = []
    for b in raw.get("beats", [])[:12] if isinstance(raw.get("beats"), list) else []:
        if not isinstance(b, dict) or b.get("kind") not in ("backdrop", "cutaway", "title", "zoom") or not ok(b.get("from")) or not ok(b.get("to")) or b["to"] < b["from"]: continue
        if b["kind"] == "title" and not text(b.get("text"), 40): continue
        beats.append({"id": f"b{len(beats) + 1}", "kind": b["kind"], "from": b["from"], "to": b["to"], "need": b.get("need") if b.get("need") in seen else None,
                      "text": text(b.get("text"), 40), "why": text(b.get("why"), 120), "by": "ai", "accepted": True})
    return {
        "emphasis": [{"word": i, "by": "ai", "accepted": True} for i in sorted({i for i in raw.get("emphasis", []) if ok(i)})] if isinstance(raw.get("emphasis"), list) else [],
        "corrections": [{"word": c["word"], "text": text(c["text"], 40), "by": "ai", "accepted": False} for c in raw.get("corrections", [])[:20]
                        if isinstance(c, dict) and ok(c.get("word")) and text(c.get("text"), 40)] if isinstance(raw.get("corrections"), list) else [],
        "beats": beats, "needs": needs,
    }
