"""The AI's part: what to emphasise, what might be misheard, how to cut the picture, and what material that needs.

Everything it returns is a suggestion. Emphasis and beats are accepted by default (they are easy to see and undo);
changes to words are never applied until a person accepts them, because the model guesses names it cannot know.
"""
import json, os, re
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
- title: лише один, з назвою об'єкта (до 14 символів), на тих словах, де назву вимовляють, і ще 6-8 слів після. Текст титру бери зі слів дослівно; якщо назва звучить дивно або схожа на недочуту, не вгадуй її і титр не роби.
- zoom на 1-2 ключових фразах, по 5-8 слів.
needs: проси лише матеріал, який справді є в автора (фото об'єкта, вид згори, план, логотип), конкретно; не більше 5.

"""


REVIEW = """Ти редактор відео про нерухомість. Нижче розшифровка одного дубля; слова пронумеровані. Людина говорить у камеру, не зупиняючи запис:
коли збивається, вона починає фразу або цілий шматок заново; іноді каже щось не для глядача. Знайди все, що не має потрапити в готове відео.
Поверни один JSON: {"cuts": [{"from": номер_слова, "to": номер_слова, "why": "retake" | "aside" | "rude", "note": "коротко, що це"}]}

- retake: невдала спроба, яку далі сказано заново. Вирізай ПЕРШУ спробу цілком, від її початку до слова перед початком вдалого повтору; лишається остання повна версія.
  Якщо заново сказано кілька речень поспіль, вирізай увесь перший варіант. Обірване речення без продовження теж сюди.
- aside: слова не для глядача: коментарі про власну обмовку, пошук слова вголос, звертання до того, хто знімає, питання "я погано сказав?".
- rude: лайка.
- Після вирізання мова має лишатися зв'язною: межі вирізу ставай на межах фраз.
- Не вирізай те, що просто незграбно сказано, і не скорочуй зміст. Якщо сумніваєшся, не вирізай. Якщо вирізати нічого, поверни {"cuts": []}.

"""


def ask(prompt, think=False):
    """One question to the model, answered as JSON. Thinking costs seconds; it is for the questions where a quick answer is often wrong."""
    body = {"model": "deepseek-flash", "thinking": {"type": "enabled" if think else "disabled"}, "response_format": {"type": "json_object"}, "max_tokens": 32000 if think else 8000,
            "messages": [{"role": "user", "content": prompt}]}
    if not think: body["temperature"] = 0.3
    response = requests.post("https://api.deepseek.com/chat/completions", timeout=300, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}, json=body)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


def review(words):
    """What should not reach the viewer: failed attempts that were said again, remarks not meant for the viewer, swearing."""
    if not enabled() or not words: return []
    return clean_cuts(ask(REVIEW + " ".join(f"[{i}]{w['text']}" for i, w in enumerate(words)), think=True), len(words))


def clean_cuts(raw, count):
    cuts = []
    for c in raw.get("cuts", [])[:40] if isinstance(raw, dict) and isinstance(raw.get("cuts"), list) else []:
        if not isinstance(c, dict): continue
        first, last = c.get("from"), c.get("to")
        if not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count for i in (first, last)) or last < first: continue
        note = c.get("note").strip()[:120] if isinstance(c.get("note"), str) and c.get("note").strip() else None
        cuts.append({"id": f"c{len(cuts) + 1}", "from": first, "to": last, "why": c.get("why") if c.get("why") in ("retake", "aside", "rude") else "retake", "note": note, "by": "ai"})
    # Never the whole take: if the review would leave almost nothing, it has misunderstood
    gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    return cuts if len(gone) <= 0.7 * count else []


def enabled():
    return bool(os.environ.get("DEEPSEEK_API_KEY")) and os.environ.get("REEL_AI", "on") != "off"


def suggest(words, skip=()):
    """The montage plan for the words that stay; the words in `skip` were cut by the review and are not shown to the model."""
    if not enabled() or not words: return clean({}, len(words))  # no key or switched off: the video is made without suggestions
    skip = set(skip)
    numbered = " ".join(f"[{i}]{w['text']}" for i, w in enumerate(words) if i not in skip)
    ideas = clean(ask(PROMPT + numbered), len(words))
    ideas["beats"] = [b for b in ideas["beats"] if not any(i in skip for i in range(b["from"], b["to"] + 1)) and (b["kind"] != "title" or spoken(b["text"], words[b["from"]:b["to"] + 1]))]
    return ideas


def spoken(title, words):
    """A title must be made of what was actually said: the model likes to 'repair' a misheard name into a place that does not exist."""
    letters = lambda text: re.sub(r"[\W_]+", "", text.lower())
    return bool(letters(title)) and letters(title) in letters(" ".join(w["text"] for w in words))


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
