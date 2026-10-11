"""The AI's part: what to emphasise, what might be misheard, how to cut the picture, and what material that needs.

Everything it returns is a suggestion. Emphasis and beats are accepted by default (they are easy to see and undo);
changes to words are never applied until a person accepts them, because the model guesses names it cannot know.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import base64, difflib, hashlib, json, os, re, time
import requests
from . import HOME

PROMPT = """Ти монтажер коротких вертикальних відео про нерухомість. Нижче розшифровка одного дубля, де людина говорить у камеру; слова пронумеровані.
Поверни один JSON:
{"emphasis": [номери слів],
 "corrections": [{"word": номер, "text": "виправлене слово"}],
 "beats": [{"kind": "full" | "backdrop" | "cutaway" | "title" | "zoom", "from": номер_слова, "to": номер_слова, "need": "id потреби або null", "text": "текст титру або null", "why": "коротко"}],
 "needs": [{"id": "n1", "what": "що саме потрібно від автора", "search": "3-5 слів англійською для пошуку схожого фото у фотобанку, без назв об'єктів", "kind": "photo" | "video" | "plan" | "logo", "optional": true | false}]}

emphasis: числа з одиницями, назви, ціни, ключові переваги; не більше одного-двох слів на речення.
corrections: лише очевидні помилки розпізнавання (закінчення, числа). Назви місць і об'єктів не вгадуй.
beats, щоб відео не було статичним:
- full: картинка на весь кадр, мовця не видно, голос звучить далі. Це головний прийом, коли мовець веде по плану будинку ("перейдемо до планування", "заходимо в передпокій", "далі кухня"): показуй план на весь кадр на кожну кімнату чи групу кімнат по 4-8 секунд (10-20 слів), повертаючись до мовця між ними на одну-дві фрази. Усі такі beats посилаються на одну потребу kind "plan". Також full годиться для головного рендера чи фото об'єкта.
- backdrop: мовця вирізано з фону, за ним картинка; cutaway: картинка у верхній частині кадру, мовець лишається видимим; title: напис у кадрі; zoom: крупніший план для наголосу.
- разом приблизно {beats} beats (не більше), розподілених по всьому тексту, а не лише на початку; між ними лишай час, де в кадрі просто мовець.
- вставка починається на слові, де про це заговорили, і охоплює 6-12 слів (2-4 секунди мовлення); не більше однієї вставки одночасно.
- title: лише один, з назвою об'єкта (до 14 символів), на тих словах, де назву вимовляють, і ще 6-8 слів після. Текст титру бери зі слів дослівно; якщо назва звучить дивно або схожа на недочуту, не вгадуй її і титр не роби.
- zoom на 1-2 ключових фразах, по 5-8 слів.
needs: проси лише матеріал, який справді є в автора (фото об'єкта, вид згори, план, логотип), конкретно; не більше {needs}. Одне фото може служити кільком beats.

"""


REVIEW = """Ти редактор відео про нерухомість. Нижче розшифровка одного дубля; слова пронумеровані. Людина говорить у камеру, не зупиняючи запис:
коли збивається, вона починає фразу або цілий шматок заново; іноді каже щось не для глядача. Знайди все, що не має потрапити в готове відео.
Поверни один JSON: {"cuts": [{"from": номер_слова, "to": номер_слова, "why": "retake" | "aside" | "rude" | "garble", "note": "коротко, що це"}]}

- retake: невдала спроба, яку далі сказано заново. Вирізай ПЕРШУ спробу цілком, від її початку до слова перед початком вдалого повтору; лишається остання повна версія.
  Якщо заново сказано кілька речень поспіль, вирізай увесь перший варіант. Обірване речення без продовження теж сюди.
- aside: слова не для глядача: коментарі про власну обмовку, пошук слова вголос, звертання до того, хто знімає, питання "я погано сказав?".
- rude: лайка.
- garble: фраза, яка не має змісту так, як сказана: слова не складаються в речення, мовець заплутався і сам її закрив («Це і весь гардеробна кімната»),
  або слова-паразити між двома повними реченнями. Вирізай лише якщо сусідні речення без неї читаються цілісно і жодна інформація не зникає.
- Після вирізання мова має лишатися зв'язною: межі вирізу ставай на межах фраз.
- Не вирізай те, що просто незграбно сказано, і не скорочуй зміст. Якщо сумніваєшся, не вирізай. Якщо вирізати нічого, поверни {"cuts": []}.

"""


TEMPERATURE = 0  # for the quick questions; the thinking ones do not take a temperature
ANSWERS = HOME / "answers"


def ask(prompt, think=False, picture=None, sample=0, fresh=False):
    """One question to the model, answered as JSON. Thinking costs seconds; it is for the questions where a quick answer is often wrong.

    The model does not answer the same question the same way twice, so an answer is kept: the same take gives the same video
    however many times it is sent. `fresh` asks again (the author wants another answer); `sample` tells apart the several
    answers to one question that a vote is taken from."""
    mark = hashlib.sha1(json.dumps(["deepseek-flash", think, prompt, hashlib.sha1(Path(picture).read_bytes()).hexdigest() if picture else None, sample]).encode()).hexdigest()
    kept = ANSWERS / f"{mark}.json"
    if kept.exists() and not fresh: return json.loads(kept.read_text(encoding="utf-8"))
    body = {"model": "deepseek-flash", "thinking": {"type": "enabled" if think else "disabled"}, "response_format": {"type": "json_object"}, "max_tokens": 64000 if picture else 32000 if think else 8000,
            "messages": [{"role": "user", "content": prompt}]}
    if picture: body["messages"][0]["content"] = [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(Path(picture).read_bytes()).decode()}}]
    if not think: body["temperature"] = TEMPERATURE
    for attempt in range(3):
        # a connection that drops or a server that is busy is asked again; a refusal (a bad key, a bad request) is not
        try:
            response = requests.post("https://api.deepseek.com/chat/completions", timeout=300, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}, json=body)
            if response.status_code < 500 and response.status_code != 429: break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError):
            if attempt == 2: raise
        time.sleep(3 * (attempt + 1))
    if response.status_code == 402: raise RuntimeError("the AI account has no money left: top it up at platform.deepseek.com, then run this step again")
    response.raise_for_status()
    spent(response.json().get("usage") or {}, think, bool(picture))
    answer = response.json()["choices"][0]["message"]["content"]
    if not answer.strip(): raise RuntimeError("the AI thought until its allowance ran out and gave no answer")
    answer = json.loads(answer)
    ANSWERS.mkdir(parents=True, exist_ok=True); kept.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
    return answer


USAGE = HOME / "usage.jsonl"


def spent(usage, think, picture):
    """One line per paid answer: when, what kind of question, how many tokens. Answers taken from the kept ones cost nothing and are not written."""
    try:
        with USAGE.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": "picture" if picture else "thinking" if think else "quick", "in": usage.get("prompt_tokens", 0),
                                   "cached": usage.get("prompt_cache_hit_tokens", 0), "out": usage.get("completion_tokens", 0)}) + "\n")
    except OSError: pass   # a full disk must not lose the answer


def usage():
    """What was asked of the AI, by day, and the money left on the account as the service reports it."""
    days = {}
    for line in USAGE.read_text(encoding="utf-8").splitlines() if USAGE.exists() else []:
        one = json.loads(line); day = days.setdefault(one["at"][:10], {"requests": 0, "in": 0, "out": 0}); day["requests"] += 1; day["in"] += one["in"]; day["out"] += one["out"]
    try: left = requests.get("https://api.deepseek.com/user/balance", timeout=30, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}).json()["balance_infos"]
    except Exception as error: left = f"unknown: {error}"
    stamp = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "balance": left}
    with (HOME / "balance.jsonl").open("a", encoding="utf-8") as file: file.write(json.dumps(stamp) + "\n")   # two readings give what was spent between them
    return {"by day": days, "balance now": left, "readings kept in": "balance.jsonl"}


VOTERS = 3


TAKES = """Позначки ⟦запис N⟧ показують, де починається наступний окремий файл: відео знімали кількома записами. Новий запис може продовжувати розповідь,
а може бути новою спробою того, що вже сказано в попередньому записі: тоді попередню спробу вирізай цілком (retake), навіть якщо це весь попередній запис, і лишай останню.
Самі позначки не є словами і номерів не мають.

"""


def review(words, fresh=False, starts=()):
    """What should not reach the viewer: failed attempts that were said again, remarks not meant for the viewer, swearing."""
    if not words: return []
    if not enabled(): return merged([], restarts(words))
    # Three answers at once, and a word is cut when most of them cut it: one answer alone sometimes strays
    opens = {i: n for n, i in enumerate(starts, 2)}   # a video of one take is asked about exactly as before
    prompt = REVIEW + (TAKES if opens else "") + " ".join((f"⟦запис {opens[i]}⟧ " if i in opens else "") + f"[{i}]{w['text']}" for i, w in enumerate(words))
    def answer(n):
        # one answer that fails (the model thought until its allowance ran out) does not stop the review: the others vote
        try: return clean_cuts(ask(prompt, think=True, sample=n, fresh=fresh), len(words))
        except RuntimeError as error: return error
    # The slowest of the three answers takes several times longer than the others. When the first two say the same, word for
    # word and reason for reason, the third cannot change the vote and is not waited for (it still comes, and is kept).
    pool = ThreadPoolExecutor(VOTERS); asked = {pool.submit(answer, n): n for n in range(VOTERS)}; got = {}
    said = lambda cuts: sorted((i, c["why"]) for c in cuts for i in range(c["from"], c["to"] + 1))
    for done in as_completed(asked):
        got[asked[done]] = done.result(); good = [a for a in got.values() if not isinstance(a, Exception)]
        if len(good) == 2 and len(got) < VOTERS and said(good[0]) == said(good[1]): break
    pool.shutdown(wait=False); answers = [got[n] for n in sorted(got)]
    failed = [a for a in answers if isinstance(a, Exception)]; answers = [a for a in answers if not isinstance(a, Exception)]
    if len(answers) < 2: raise failed[0]
    return merged([c for c in vote(answers) if c["why"] != "garble" or empty(words, c)], restarts(words))


def bare(word): return re.sub(r"[^\w]", "", word["text"].lower())
def same(a, b): return a == b or (min(len(a), len(b)) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


def restarts(words):
    """Phrases begun and at once begun again, found without the AI: "Санвузол уже з. Санвузол уже з ремонтом" loses its first three words.
    The words must open a sentence and be followed straight away by the same words; the longest such run is taken."""
    cuts, i = [], 0
    while i < len(words):
        opens = i == 0 or re.search(r"[.!?…]$", words[i - 1]["text"])
        run = next((n for n in range(min(14, (len(words) - i) // 2), 1, -1) if all(bare(words[i + k]) and same(bare(words[i + k]), bare(words[i + n + k])) for k in range(n))), 0) if opens else 0
        if run: cuts.append({"from": i, "to": i + run - 1, "why": "retake", "note": "почато і одразу сказано заново", "by": "ai"}); i += run
        else: i += 1
    return cuts


def empty(words, cut):
    """Whether a phrase the AI calls senseless may go. A scrap of a sentence may. A whole sentence of six words or more that
    makes no sense as written is more often one that was heard wrong, and cutting it would take what was said out of the
    video: it goes only if its longer words are all said near it, so nothing new is lost."""
    whole = (cut["from"] == 0 or re.search(r"[.!?…]$", words[cut["from"] - 1]["text"])) and re.search(r"[.!?…]$", words[cut["to"]]["text"])
    if not whole or cut["to"] - cut["from"] < 5: return True
    inside = {bare(w)[:4] for w in words[cut["from"]:cut["to"] + 1] if len(bare(w)) >= 4}
    near = {bare(w)[:4] for i, w in enumerate(words) if (cut["from"] - 25 <= i < cut["from"] or cut["to"] < i <= cut["to"] + 25)}
    return len(inside - near) <= 1


def merged(first, second):
    """Two lists of cuts as one: a cut that touches one already there is left out."""
    out = list(first) + [c for c in second if not any(c["from"] <= k["to"] and k["from"] <= c["to"] for k in first)]
    return [{**c, "id": f"c{n}"} for n, c in enumerate(sorted(out, key=lambda c: c["from"]), 1)]


def vote(answers):
    """The cuts most of the answers agree on, word by word; each keeps the reason of the first answer that had it."""
    reason = {}
    for cuts in answers:
        for c in cuts:
            for i in range(c["from"], c["to"] + 1): reason.setdefault(i, (c["why"], c["note"]))
    agreed = sorted(i for i in reason if sum(any(c["from"] <= i <= c["to"] for c in cuts) for cuts in answers) * 2 > len(answers))
    cuts, start = [], None
    for i, nxt in zip(agreed, agreed[1:] + [None]):
        start = i if start is None else start
        if nxt != i + 1 or reason[nxt][0] != reason[i][0]:
            cuts.append({"id": f"c{len(cuts) + 1}", "from": start, "to": i, "why": reason[start][0], "note": reason[start][1], "by": "ai"}); start = None
    return cuts


def clean_cuts(raw, count):
    cuts = []
    for c in raw.get("cuts", [])[:40] if isinstance(raw, dict) and isinstance(raw.get("cuts"), list) else []:
        if not isinstance(c, dict): continue
        first, last = c.get("from"), c.get("to")
        if not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < count for i in (first, last)) or last < first: continue
        note = c.get("note").strip()[:120] if isinstance(c.get("note"), str) and c.get("note").strip() else None
        cuts.append({"id": f"c{len(cuts) + 1}", "from": first, "to": last, "why": c.get("why") if c.get("why") in ("retake", "aside", "rude", "garble") else "retake", "note": note, "by": "ai"})
    # Never the whole take: if the review would leave almost nothing, it has misunderstood
    gone = {i for c in cuts for i in range(c["from"], c["to"] + 1)}
    return cuts if len(gone) <= 0.7 * count else []


EDIT = """Ти редактор відео. Нижче розшифровка дубля; слова пронумеровані, слова у дужках (ось так) уже вирізані з відео.
Автор позначив слова від {first} до {last} і просить: "{request}"
Зроби саме те, що просять, і лише там, де це стосується прохання (зазвичай у позначеному місці та поруч). Поверни один JSON:
{{"say": "одне-два речення українською: що зроблено, або чому нічого не зроблено",
 "ops": [{{"op": "cut", "from": n, "to": n}} | {{"op": "restore", "from": n, "to": n}} | {{"op": "text", "word": n, "to": "нове слово"}} |
         {{"op": "emphasis", "word": n, "on": true | false}} | {{"op": "title", "from": n, "to": n, "text": "до 14 символів"}} | {{"op": "zoom", "from": n, "to": n}}]}}

- cut прибирає слова з відео разом із картинкою і звуком; після вирізання мова має лишатися зв'язною, тому ріж на межах фраз.
- Якщо щось сказано двічі, лишай останню повну версію і вирізай попередню.
- text лише виправляє написання в субтитрах; звук не змінюється. Нові слова в мовлення додати неможливо.
- Якщо прохання незрозуміле або його не можна виконати цими діями, поверни порожній ops і поясни в say.

"""


def edit(words, kept, first, last, request):
    """What to change for the author's request about the words first..last: a list of checked operations and a sentence about them."""
    if not enabled(): return {"say": "AI вимкнено: немає ключа.", "ops": []}
    lo, hi = max(0, first - 150), min(len(words), last + 151)  # the stretch with enough around it to see repeats
    text = " ".join(f"[{i}]{words[i]['text']}" if i in kept else f"([{i}]{words[i]['text']})" for i in range(lo, hi))
    raw = ask(EDIT.format(first=first, last=last, request=request.replace('"', "'")[:400]) + text, think=True, fresh=True)
    ok = lambda i: isinstance(i, int) and not isinstance(i, bool) and lo <= i < hi
    ops = []
    for o in raw.get("ops", [])[:20] if isinstance(raw.get("ops"), list) else []:
        if not isinstance(o, dict): continue
        kind = o.get("op")
        if kind in ("cut", "restore", "zoom") and ok(o.get("from")) and ok(o.get("to")) and o["from"] <= o["to"]: ops.append({"op": kind, "from": o["from"], "to": o["to"]})
        elif kind == "title" and ok(o.get("from")) and ok(o.get("to")) and o["from"] <= o["to"] and isinstance(o.get("text"), str) and o["text"].strip(): ops.append({"op": kind, "from": o["from"], "to": o["to"], "text": o["text"].strip()[:40]})
        elif kind == "text" and ok(o.get("word")) and isinstance(o.get("to"), str) and o["to"].strip(): ops.append({"op": kind, "word": o["word"], "to": o["to"].strip()[:40]})
        elif kind == "emphasis" and ok(o.get("word")): ops.append({"op": kind, "word": o["word"], "on": bool(o.get("on", True))})
    return {"say": raw.get("say").strip()[:300] if isinstance(raw.get("say"), str) and raw.get("say").strip() else ("Зроблено." if ops else "Нічого не змінено."), "ops": ops}


MARK = """The picture is the floor plan shown in a short video about a house. Each room is shaded and carries a tag: r1, r2, ...
The plan may also carry the architect's own room numbers; ignore them, answer with the r-tags only.
Below is what the speaker says while the plan is on screen. Every word has its number in square brackets.
Find the moments when the speaker talks about one particular room of this plan, and say which room it is: judge by the furniture
and fittings drawn in it, by the doors (the entrance hall has the door to the outside) and by the order of the walk: a tour starts
at the entrance and goes from room to room next door. Decide briskly; do not deliberate at length.
Reply with JSON only: {"marks":[{"room":"r4","from":<number of the first word about this room>,"to":<number of the last word about it>,"name":"<the room's name as the speaker says it>"}]}
A room that is not on the plan, or is not shaded (a terrace, a carport), gets no mark. If you cannot tell which room is meant, give no mark for it.
The speaker's words:
"""


def mark(picture, rooms, words, spans):
    """Which room of a plan the speaker talks about, and when. `spans` are the word ranges during which the plan is shown."""
    if not enabled() or not rooms: return []
    known = {r["id"] for r in rooms}; shown = {i for a, b in spans for i in range(a, b + 1)}
    raw = ask(MARK + " ".join(f"[{i}]{words[i]['text']}" for i in sorted(shown)), think=True, picture=picture)
    marks = []
    for m in raw.get("marks", []) if isinstance(raw, dict) and isinstance(raw.get("marks"), list) else []:
        if not isinstance(m, dict) or m.get("room") not in known: continue
        first, last = m.get("from"), m.get("to")
        if not all(isinstance(i, int) and not isinstance(i, bool) and i in shown for i in (first, last)) or last < first: continue
        marks.append({"room": m["room"], "from": first, "to": last, "name": m["name"].strip()[:40] if isinstance(m.get("name"), str) else None, "by": "ai"})
    return marks


MOMENTS = """A speaker walks a viewer through a house, room by room, while its floor plan is on screen.
Every word has its number in square brackets. Find each stretch in which the speaker talks about one particular room or part
of the house (a hall, a kitchen, a bedroom, a bathroom, a wardrobe, a terrace, a carport and so on).
Reply with JSON only: {"moments":[{"from":<number of the first word of the stretch>,"to":<number of its last word>,"name":"<the room's name, in the speaker's language, in the nominative>"}]}
A stretch starts where the speaker turns to the room and ends where they stop talking about it: before the next room is named,
or before they turn to something that is not a room (the settlement, the plot, the landscape, prices, an appeal to the viewer). Give no stretch for those. Stretches do not overlap.
If the same room is spoken of again later, give it again with the same name.
The speaker's words:
"""


def moments(words, spans):
    """When the speaker names a room, and what they call it. `spans` are the word ranges during which a plan is shown."""
    shown = sorted({i for a, b in spans for i in range(a, b + 1) if 0 <= i < len(words)})
    if not enabled() or not shown: return []
    raw = ask(MOMENTS + " ".join(f"[{i}]{words[i]['text']}" for i in shown)); found = []
    for m in raw.get("moments", []) if isinstance(raw, dict) and isinstance(raw.get("moments"), list) else []:
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not m["name"].strip(): continue
        first, last = m.get("from"), m.get("to")
        if not all(isinstance(i, int) and not isinstance(i, bool) and i in shown for i in (first, last)) or last < first: continue
        if any(first <= f["to"] and f["from"] <= last for f in found): continue
        found.append({"from": first, "to": last, "name": m["name"].strip()[:40]})
    return sorted(found, key=lambda m: m["from"])


DECORATE = """Ти режисер коротких вертикальних відео про нерухомість. Нижче розшифровка; слова пронумеровані. Мовець у кадрі, внизу йдуть субтитри.
Твоє завдання: оживити відео накладками, які з'являються рівно на тих словах, де про це мовиться, і підсилюють сказане, а не повторюють субтитри.
Поверни один JSON: {"overlays": [...]}. Види накладок:

- {"kind": "number", "from": N, "to": N, "value": "154", "unit": "м²", "caption": "площа будинку"}
  Велике число, що набігає. Для цифр, які продають: площа, кількість будинків, сотки, висота стелі, відстань, ціна. value бери зі слів дослівно.
- {"kind": "sticker", "from": N, "to": N, "text": "Бомбосховище", "icon": "🛡️"}
  Наліпка з коротким підписом (1-3 слова, до 22 знаків) і одним емодзі. Для переваг і особливостей: «Біля лісу» 🌲, «Закрита територія» 🔒, «Панорамні вікна» 🪟.
  Підпис складай лише з того, що мовець сказав у цьому місці; не вигадуй фактів.
- {"kind": "list", "from": N, "to": N, "title": "У будинку", "items": [{"at": N, "text": "Гардеробна"}, {"at": N, "text": "Пральня"}]}
  Список, пункти якого з'являються по черзі, коли мовець їх називає (2-4 пункти, кожен 1-2 слова). Лише там, де мовець справді перелічує.
- {"kind": "break", "from": N, "text": "Планування"}
  Перебивка: на секунду кадр перекриває заставка з назвою наступної частини розповіді (1-2 слова: «Локація», «Будинок», «Планування», «Ділянка», «Ціна»).
  Став її на перше слово речення, з якого мовець переходить до нової теми. Якщо у відео понад 80 слів, дай обов'язково 2-3 перебивки: не на самому початку, між ними щонайменше 30 слів.
  Перебивки не входять у кількість накладок нижче.

Правила:
- приблизно {count} накладок на все відео (не більше), розподілених рівномірно від початку до кінця; між сусідніми щонайменше 8 слів.
- from - слово, на якому накладка з'являється (саме там, де звучить число чи ключове слово), to - останнє слово думки (3-10 слів далі).
- не став накладки на слова з номерами: {busy} - там кадр уже зайнятий іншою картинкою.
- різноманітність: чергуй види. Числа лише для справді важливих цифр; щонайменше половина накладок - наліпки про переваги, місце, особливості
  (локація 📍, ліс 🌲, закрита територія 🔒, один поверх 🏠, тераса ☀️, паркінг 🚗, гардеробна 👗, санвузол 🚿, спальня 🛏️, кухня 🍳, запрошення написати ✉️).
- емодзі лише одне й очевидне за змістом; якщо доречного немає, дай "icon": null.
- якщо в якомусь місці нічого цікавого не сказано, нічого туди не став. Краще менше, але влучно.

Розшифровка:
"""

ICONS = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")


def decorate(words, skip=(), busy=(), fresh=False):
    """Overlays that make the video livelier: a number counting up, a sticker, a list. Every one is checked against the words:
    a number must be one that was said, a caption must be made of what was said near it."""
    if not enabled() or not words: return []
    skip = set(skip); kept = [i for i in range(len(words)) if i not in skip]; count = max(4, min(16, round(len(kept) / 18)))
    taken = ", ".join(f"{a}-{b}" for a, b in busy) or "немає"
    raw = ask(DECORATE.replace("{count}", str(count)).replace("{busy}", taken) + " ".join(f"[{i}]{words[i]['text']}" for i in kept), fresh=fresh)
    stem = lambda text: {w[:4] for w in re.findall(r"\w+", text.lower()) if len(w) >= 3}
    def said(text, first, last):   # the words of a caption were spoken near the place it stands
        near = stem(" ".join(words[i]["text"] for i in range(max(0, first - 12), min(len(words), last + 13)) if i not in skip))
        return bool(stem(text)) and len(stem(text) & near) >= max(1, len(stem(text)) - 1)
    def icon(value): found = ICONS.findall(value) if isinstance(value, str) else []; return value.strip()[:8] if found and len(value.strip()) <= 8 else None
    out, breaks, blocked = [], [], {i for a, b in busy for i in range(a, b + 1)}
    for o in raw.get("overlays", []) if isinstance(raw, dict) and isinstance(raw.get("overlays"), list) else []:
        if not isinstance(o, dict): continue
        first = o.get("from"); last = first if o.get("kind") == "break" else o.get("to")
        if not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(words) and i not in skip for i in (first, last)) or not first <= last <= first + 40: continue
        if o.get("kind") == "break":
            # a break stands where a sentence starts, not at the very beginning, and not close to another
            text = " ".join(str(o.get("text") or "").split()[:2])[:18]; before = next((words[i]["text"] for i in range(first - 1, -1, -1) if i not in skip), "")
            if text and len(breaks) < 3 and first not in blocked and (re.search(r"[.!?…]$", before) or words[first]["text"][:1].isupper()) and kept.index(first) >= 10 and all(abs(first - b["from"]) >= 25 for b in breaks):
                breaks.append({"from": first, "to": first, "kind": "break", "text": text, "by": "ai", "accepted": True})
            continue
        if len(out) >= count: continue
        if any(i in blocked for i in range(first, last + 1)) or any(first <= k["to"] + 1 and k["from"] <= last + 1 for k in out): continue
        if o.get("kind") == "number":
            # a range ("7-8 метрів") is a number too, and is kept as a range
            only = lambda text: re.sub(r"[^\d,.\-]", "", text.replace("–", "-")).strip(".,-")
            value = str(o.get("value", "")).strip(); digits = only(value)
            if not re.search(r"\d", digits) or not any(only(words[i]["text"]) == digits for i in range(first, min(len(words), last + 1))): continue
            item = {"kind": "number", "value": digits, "unit": str(o.get("unit") or "").strip()[:8], "caption": str(o.get("caption") or "").strip()[:28] or None}
        elif o.get("kind") == "sticker":
            text = str(o.get("text", "")).strip()[:22]
            if not text or not said(text, first, last): continue
            item = {"kind": "sticker", "text": text, "icon": icon(o.get("icon"))}
        elif o.get("kind") == "list":
            items = [{"at": i["at"], "text": str(i["text"]).strip()[:20]} for i in o.get("items", []) if isinstance(i, dict) and isinstance(i.get("at"), int) and first <= i["at"] <= last + 4 and isinstance(i.get("text"), str) and said(i["text"], i["at"], i["at"])][:4]
            if len(items) < 2: continue
            item = {"kind": "list", "title": str(o.get("title") or "").strip()[:20] or None, "items": sorted(items, key=lambda i: i["at"])}; last = max(last, items[-1]["at"])
        else: continue
        out.append({"from": first, "to": last, **item, "by": "ai", "accepted": True})
    return [{"id": f"o{i}", **o} for i, o in enumerate(sorted(out + breaks, key=lambda o: o["from"]), 1)]


def enabled():
    return bool(os.environ.get("DEEPSEEK_API_KEY")) and os.environ.get("REEL_AI", "on") != "off"


def suggest(words, skip=(), fresh=False):
    """The montage plan for the words that stay; the words in `skip` were cut by the review and are not shown to the model."""
    if not enabled() or not words: return clean({}, len(words))  # no key or switched off: the video is made without suggestions
    skip = set(skip)
    numbered = " ".join(f"[{i}]{w['text']}" for i, w in enumerate(words) if i not in skip)
    kept = len(words) - len(skip); beats = max(5, min(16, round(kept / 25)))  # about one insert for every ten seconds of speech
    ideas = clean(ask(PROMPT.replace("{beats}", str(beats)).replace("{needs}", str(max(4, min(8, beats // 2)))) + numbered, fresh=fresh), len(words))
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
    for n in raw.get("needs", [])[:8] if isinstance(raw.get("needs"), list) else []:
        if not isinstance(n, dict) or not text(n.get("id"), 12) or not text(n.get("what"), 140) or n["id"] in seen: continue
        seen.add(n["id"])
        needs.append({"id": n["id"], "what": text(n["what"], 140), "search": text(n.get("search"), 60), "kind": n.get("kind") if n.get("kind") in ("photo", "video", "plan", "logo") else "photo",
                      "optional": bool(n.get("optional")), "status": "open", "asset": None})
    beats = []
    for b in raw.get("beats", [])[:16] if isinstance(raw.get("beats"), list) else []:
        if not isinstance(b, dict) or b.get("kind") not in ("full", "backdrop", "cutaway", "title", "zoom") or not ok(b.get("from")) or not ok(b.get("to")) or b["to"] < b["from"]: continue
        if b["kind"] == "title" and not text(b.get("text"), 40): continue
        beats.append({"id": f"b{len(beats) + 1}", "kind": b["kind"], "from": b["from"], "to": b["to"], "need": b.get("need") if b.get("need") in seen else None,
                      "text": text(b.get("text"), 40), "why": text(b.get("why"), 120), "by": "ai", "accepted": True})
    return {
        "emphasis": [{"word": i, "by": "ai", "accepted": True} for i in sorted({i for i in raw.get("emphasis", []) if ok(i)})] if isinstance(raw.get("emphasis"), list) else [],
        "corrections": [{"word": c["word"], "text": text(c["text"], 40), "by": "ai", "accepted": False} for c in raw.get("corrections", [])[:20]
                        if isinstance(c, dict) and ok(c.get("word")) and text(c.get("text"), 40)] if isinstance(raw.get("corrections"), list) else [],
        "beats": beats, "needs": needs,
    }
