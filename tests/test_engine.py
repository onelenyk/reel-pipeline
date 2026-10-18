"""Tests of the engine's logic: no video, no network. Run in the container:  ./reel test"""
import json, tempfile, unittest
from pathlib import Path
from engine import project, speech, styles, suggest


def words(*texts, step=0.5):
    return [{"text": t, "start": round(i * step, 2), "end": round(i * step + 0.4, 2), "confidence": 0.9} for i, t in enumerate(texts)]


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.folder = Path(self.tmp.name) / "p"
        text = "Це нове містечко G-Village де є 22 будинки і ще 15 у продажі".split()
        ideas = suggest.clean({"emphasis": [3, 6], "beats": [{"kind": "title", "from": 3, "to": 6, "text": "G-Village"}, {"kind": "cutaway", "from": 6, "to": 9, "need": "n1"}],
                               "needs": [{"id": "n1", "what": "вид згори", "search": "aerial view houses", "kind": "photo"}], "corrections": [{"word": 2, "text": "селище"}]}, len(text))
        facts = {"seconds": 8.0, "width": 1080, "height": 1920, "fps": 30, "hdr": False, "has_audio": True}
        project.save(self.folder, project.new("take.mov", facts, {"language": "uk", "words": words(*text)}, ideas))
        self.picture = Path(self.tmp.name) / "photo.jpg"; self.picture.write_bytes(b"\xff\xd8fake")

    def tearDown(self): self.tmp.cleanup()
    def doc(self): return project.load(self.folder)
    def timeline(self): return project.resolve(self.doc())
    def spoken(self): return [w["text"] for line in self.timeline()["lines"] for w in line["words"]]


class Review(unittest.TestCase):
    def test_cuts_are_applied_and_can_be_seen(self):
        cuts = suggest.clean_cuts({"cuts": [{"from": 2, "to": 3, "why": "retake", "note": "повтор"}, {"from": 9, "to": 4}, {"from": 1, "to": 99}, "x"]}, 8)
        self.assertEqual([(c["from"], c["to"], c["why"]) for c in cuts], [(2, 3, "retake")])
        facts = {"seconds": 8.0, "width": 1080, "height": 1920, "fps": 30, "hdr": False, "has_audio": True}
        doc = project.new("take.mov", facts, {"language": "uk", "words": words(*"a b c d e f g h".split())}, suggest.clean({}, 8), cuts=cuts)
        self.assertEqual([(s["from"], s["to"]) for s in doc["edit"]["segments"]], [(0, 1), (4, 7)])
        self.assertEqual(doc["cuts"][0]["note"], "повтор")

    def test_a_title_must_be_made_of_spoken_words(self):
        said = words("будинку", "в", "Джівілич,", "який")
        self.assertFalse(suggest.spoken("Живіличі", said)); self.assertTrue(suggest.spoken("джівілич", said))
        self.assertTrue(suggest.spoken("G-Village", words("воно", "G-Village,", "яке")))

    def test_a_review_that_would_cut_nearly_everything_is_ignored(self):
        self.assertEqual(suggest.clean_cuts({"cuts": [{"from": 0, "to": 6, "why": "aside"}]}, 8), [])


class Request(Case):
    def test_operations_proposed_for_a_request_are_carried_out(self):
        project.apply(self.folder, [{"op": "cut", "from": 10, "to": 12}, {"op": "text", "word": 1, "to": "нове!"}, {"op": "emphasis", "word": 3, "on": False},
                                    {"op": "emphasis", "word": 0, "on": True}, {"op": "zoom", "from": 0, "to": 2}])
        doc = self.doc()
        self.assertEqual([(s["from"], s["to"]) for s in doc["edit"]["segments"]], [(0, 9)])
        self.assertIn("нове!", self.spoken())
        self.assertEqual({e["word"] for e in doc["emphasis"] if e["accepted"]}, {0, 6})
        self.assertEqual(doc["beats"][-1]["kind"], "zoom")
        project.apply(self.folder, [{"op": "restore", "from": 10, "to": 12}])
        self.assertEqual([(s["from"], s["to"]) for s in self.doc()["edit"]["segments"]], [(0, 12)])


class Text(Case):
    def test_own_correction_is_used_and_ai_one_is_not(self):
        self.assertIn("містечко", self.spoken())  # the AI's "селище" is only an offer
        project.set_text(self.folder, 2, "  котеджне   містечко ")
        self.assertIn("котеджне містечко", self.spoken())
        self.assertEqual([(c["by"], c["accepted"]) for c in self.doc()["corrections"]], [("ai", False), ("user", True)])

    def test_empty_or_original_text_removes_the_correction(self):
        project.set_text(self.folder, 1, "нове!"); project.set_text(self.folder, 1, "")
        self.assertEqual([c for c in self.doc()["corrections"] if c["word"] == 1], [])
        project.set_text(self.folder, 1, "нове"); self.assertEqual([c for c in self.doc()["corrections"] if c["word"] == 1], [])

    def test_ai_offer_survives_the_authors_own_correction(self):
        doc = self.doc(); doc["corrections"][0]["accepted"] = True; project.save(self.folder, doc)
        project.set_text(self.folder, 2, "поселення")
        self.assertEqual([(c["by"], c["accepted"]) for c in self.doc()["corrections"]], [("ai", False), ("user", True)]); self.assertIn("поселення", self.spoken())
        project.set_text(self.folder, 2, "")
        self.assertEqual([(c["by"], c["accepted"]) for c in self.doc()["corrections"]], [("ai", False)])

    def test_correction_is_limited_and_needs_a_real_word(self):
        self.assertEqual(len(project.set_text(self.folder, 0, "я" * 200)), 40)
        with self.assertRaises(KeyError): project.set_text(self.folder, 999, "x")

    def test_cut_and_restore(self):
        before = self.timeline()["seconds"]
        project.drop(self.folder, 4, 7)
        self.assertEqual([[s["from"], s["to"]] for s in self.doc()["edit"]["segments"]], [[0, 3], [8, 12]])
        self.assertLess(self.timeline()["seconds"], before); self.assertNotIn("22", self.spoken())
        project.drop(self.folder, 5, 5, restore=True)
        self.assertEqual([[s["from"], s["to"]] for s in self.doc()["edit"]["segments"]], [[0, 3], [5, 5], [8, 12]])
        project.drop(self.folder, 0, 99, restore=True); self.assertEqual(self.timeline()["seconds"], before)

    def test_everything_cut_still_resolves(self):
        project.drop(self.folder, 0, 12); t = self.timeline()
        self.assertEqual((t["seconds"], t["lines"], t["beats"]), (0, [], []))

    def test_times_are_remapped_after_a_cut(self):
        project.drop(self.folder, 0, 3); first = self.timeline()["lines"][0]["words"][0]
        self.assertEqual(first["text"], "де"); self.assertLess(first["start"], 0.2)


class Pictures(Case):
    def test_beat_waits_for_its_picture(self):
        self.assertEqual([b["kind"] for b in self.timeline()["beats"]], ["title"])
        asset = project.add_asset(self.folder, self.picture, "Моє фото.JPG"); project.assign(self.folder, "n1", asset)
        self.assertEqual([b["kind"] for b in self.timeline()["beats"]], ["title", "cutaway"])
        self.assertTrue(Path(self.doc()["assets"][0]["file"]).exists())
        project.assign(self.folder, "n1", None)
        self.assertEqual((self.doc()["needs"][0]["status"], [b["kind"] for b in self.timeline()["beats"]]), ("open", ["title"]))

    def test_one_picture_can_serve_a_request_and_a_beat(self):
        asset = project.add_asset(self.folder, self.picture); project.assign(self.folder, "n1", asset)
        beat = project.add_beat(self.folder, "backdrop", 9, 0, asset=asset)  # the range may be given backwards
        self.assertEqual((beat["from"], beat["to"], len(self.doc()["assets"])), (0, 9, 1))

    def test_bad_requests_are_refused(self):
        with self.assertRaises(KeyError): project.assign(self.folder, "n1", "a99")
        with self.assertRaises(KeyError): project.assign(self.folder, "nope", None)
        with self.assertRaises(ValueError): project.add_beat(self.folder, "cutaway", 0, 2)
        with self.assertRaises(ValueError): project.add_beat(self.folder, "title", 0, 2, text="  ")
        with self.assertRaises(ValueError): project.add_beat(self.folder, "explode", 0, 2)
        with self.assertRaises(ValueError): project.add_beat(self.folder, "zoom", 0, 99)

    def test_title_leaves_when_a_picture_arrives(self):
        asset = project.add_asset(self.folder, self.picture); project.assign(self.folder, "n1", asset)
        title, picture = self.timeline()["beats"]
        self.assertLessEqual(title["end"], picture["start"] + 0.2)

    def test_beat_over_cut_words_disappears(self):
        project.drop(self.folder, 3, 6); self.assertEqual(self.timeline()["beats"], [])

    def test_remove_and_change_a_beat(self):
        asset = project.add_asset(self.folder, self.picture); beat = project.add_beat(self.folder, "cutaway", 0, 2, asset=asset)
        project.change_beat(self.folder, beat["id"], asset=None); self.assertIsNone(next(b for b in self.doc()["beats"] if b["id"] == beat["id"])["asset"])
        project.change_beat(self.folder, beat["id"], remove=True); self.assertNotIn(beat["id"], [b["id"] for b in self.doc()["beats"]])

    def test_the_part_of_a_photo_kept_in_view_goes_with_the_photo(self):
        asset = project.add_asset(self.folder, self.picture); project.assign(self.folder, "n1", asset)
        self.assertIsNone(self.timeline()["beats"][-1]["focus"])
        self.assertEqual(project.set_focus(self.folder, asset, [1.4, 0.25]), [1.0, 0.25])   # kept inside the photo
        self.assertEqual(self.timeline()["beats"][-1]["focus"], [1.0, 0.25])
        project.set_focus(self.folder, asset, None); self.assertIsNone(self.timeline()["beats"][-1]["focus"])
        with self.assertRaises(KeyError): project.set_focus(self.folder, "a99", [0, 0])


class Styles(Case):
    def test_style_is_cleaned(self):
        style = project.clean_style({"accent": "red; }", "subtitle_size": "huge", "karaoke": "yes", "level": -99, "name": "x" * 99, "evil": "<script>"})
        self.assertEqual((style["accent"], style["subtitle_size"], style["karaoke"], style["level"], len(style["name"])), ("#ffd60a", "m", True, -24, 40))
        self.assertNotIn("evil", style)
        self.assertEqual(project.clean_style(None), project.STYLE)

    def test_save_apply_default_delete(self):
        old = styles.ROOT, styles.DEFAULT; styles.ROOT = Path(self.tmp.name) / "styles"; styles.DEFAULT = styles.ROOT / "default.txt"
        try:
            project.set_style(self.folder, {"accent": "#30D158", "subtitle_size": "l", "picture": "edge"})
            key = styles.save("Зелений / великий", self.doc()["style"])
            self.assertEqual(key, "зелений-великий"); self.assertEqual([s["name"] for s in styles.listing()], ["Зелений / великий"])
            self.assertIsNone(styles.default()); styles.set_default(key)
            self.assertEqual(styles.default()["accent"], "#30d158"); self.assertTrue(styles.listing()[0]["default"])
            fresh = project.new("t.mov", {"seconds": 1, "width": 1, "height": 1, "fps": 30, "hdr": False}, {"language": "uk", "words": []}, suggest.clean({}, 0), styles.default())
            self.assertEqual((fresh["style"]["subtitle_size"], fresh["style"]["picture"]), ("l", "edge"))
            (styles.ROOT / "broken.json").write_text("{not json"); self.assertEqual(len(styles.listing()), 1)
            with self.assertRaises(KeyError): styles.get("../../etc/passwd")
            styles.remove(key); self.assertEqual((styles.listing(), styles.default()), ([], None))
        finally: styles.ROOT, styles.DEFAULT = old

    def test_a_renamed_style_stays_the_default(self):
        old = styles.ROOT, styles.DEFAULT; styles.ROOT = Path(self.tmp.name) / "styles"; styles.DEFAULT = styles.ROOT / "default.txt"
        try:
            key = styles.save("Перший", self.doc()["style"]); other = styles.save("Другий", self.doc()["style"]); styles.set_default(key)
            new = styles.rename(key, "  Новий   перший "); self.assertEqual(new, "новий-перший")
            self.assertEqual([(s["name"], s["default"]) for s in styles.listing()], [("Другий", False), ("Новий перший", True)])
            with self.assertRaises(ValueError): styles.rename(new, "Другий")   # it would replace another one
            with self.assertRaises(ValueError): styles.rename(new, "   ")
            with self.assertRaises(KeyError): styles.rename("нема", "Щось")
            self.assertEqual(styles.rename(other, "ДРУГИЙ"), other)   # the same name written otherwise keeps its file
            self.assertEqual(styles.get(other)["name"], "ДРУГИЙ")
        finally: styles.ROOT, styles.DEFAULT = old

    def test_old_project_gets_a_full_style(self):
        doc = self.doc(); doc["style"] = {"preset": "bold-yellow", "accent": "#0a84ff"}; doc.pop("assets"); project.save(self.folder, doc)
        self.assertEqual((self.doc()["style"]["accent"], self.doc()["style"]["subtitle_place"], self.doc()["assets"]), ("#0a84ff", "low", []))


class Suggestions(unittest.TestCase):
    def test_only_well_formed_suggestions_survive(self):
        out = suggest.clean({"emphasis": [1, 1, 99, "2", True], "corrections": [{"word": 0, "text": "<b>x</b>" * 30}, {"word": 50, "text": "y"}, "junk"],
                             "beats": [{"kind": "title", "from": 0, "to": 1}, {"kind": "zoom", "from": 2, "to": 1}, {"kind": "cutaway", "from": 0, "to": 2, "need": "ghost"}, {"kind": "hack", "from": 0, "to": 1}],
                             "needs": [{"id": "n1", "what": "a"}, {"id": "n1", "what": "dup"}, {"what": "no id"}, "junk"] + [{"id": f"x{i}", "what": "w"} for i in range(9)]}, 3)
        self.assertEqual([e["word"] for e in out["emphasis"]], [1])
        self.assertEqual((len(out["corrections"]), out["corrections"][0]["accepted"], len(out["corrections"][0]["text"])), (1, False, 40))
        self.assertEqual([(b["kind"], b["need"]) for b in out["beats"]], [("cutaway", None)])
        self.assertLessEqual(len(out["needs"]), 5); self.assertEqual(out["needs"][0]["status"], "open")
        self.assertEqual(suggest.clean({"emphasis": "all", "beats": None, "needs": {}}, 3), {"emphasis": [], "corrections": [], "beats": [], "needs": []})


if __name__ == "__main__":
    unittest.main()


class Rooms(unittest.TestCase):
    """Rooms of a plan, with a reader that takes the drawn black lines for walls."""

    def setUp(self):
        import numpy as np
        from engine import plan
        self.plan = plan; plan.READERS["ink"] = lambda colour: colour[:, :, 0] < 100
        # Two rooms side by side in one box, joined by a doorway in the wall between them
        sheet = np.full((400, 600, 3), 255, np.uint8); sheet[50:60, 50:550] = 0; sheet[340:350, 50:550] = 0; sheet[50:350, 50:60] = 0; sheet[50:350, 540:550] = 0
        sheet[50:150, 295:305] = 0; sheet[210:350, 295:305] = 0
        self.sheet = sheet

    def area(self, room): 
        import cv2, numpy as np
        return cv2.contourArea((np.array(room["shape"]) * (600, 400)).astype(np.float32))

    def test_a_door_the_reader_marks_parts_two_rooms(self):
        self.assertEqual(len(self.plan.rooms(self.sheet, "ink", points=[])), 1)  # an open doorway and no numbers: one space
        self.sheet[150:210, 295:305] = 0; found = self.plan.rooms(self.sheet, "ink", points=[])
        self.assertEqual(len(found), 2)
        for room in found: self.assertAlmostEqual(self.area(room), 235 * 280, delta=0.06 * 235 * 280)

    def test_two_numbers_in_one_space_divide_it(self):
        sheet = self.sheet.copy(); sheet[50:350, 295:305] = 255; sheet[50:60, 295:305] = 0; sheet[340:350, 295:305] = 0; sheet[50:120, 295:305] = 0; sheet[280:350, 295:305] = 0
        self.assertEqual(len(self.plan.rooms(sheet, "ink", points=[(150, 200)])), 1)
        halves = self.plan.rooms(sheet, "ink", points=[(150, 200), (450, 200)])
        self.assertEqual(len(halves), 2)
        for room in halves: self.assertAlmostEqual(self.area(room), 240 * 280, delta=0.12 * 240 * 280)


class Vote(unittest.TestCase):
    def test_a_cut_stays_when_most_answers_have_it(self):
        from engine.suggest import vote
        cut = lambda a, b, why="retake": {"id": "c1", "from": a, "to": b, "why": why, "note": None, "by": "ai"}
        agreed = vote([[cut(5, 9), cut(20, 22, "aside")], [cut(5, 9)], [cut(5, 10), cut(20, 22, "aside")]])
        self.assertEqual([(c["from"], c["to"], c["why"]) for c in agreed], [(5, 9, "retake"), (20, 22, "aside")])
        self.assertEqual(vote([[cut(5, 9)], [], []]), [])


class Spaces(unittest.TestCase):
    """A workspace is a client: its projects share a vocabulary, a logo and the style new videos start with."""

    def setUp(self):
        from engine import spaces
        self.home = Path(tempfile.mkdtemp()); was = (spaces.HOME, spaces.SPACES, spaces.TRASH, styles.ROOT, styles.DEFAULT, speech.VOCABULARY)
        spaces.HOME, spaces.SPACES, spaces.TRASH = self.home, self.home / "workspaces.json", self.home / "trash"
        styles.ROOT, styles.DEFAULT, speech.VOCABULARY = self.home / "styles", self.home / "styles" / "default.txt", self.home / "vocabulary.txt"
        def back(): spaces.HOME, spaces.SPACES, spaces.TRASH, styles.ROOT, styles.DEFAULT, speech.VOCABULARY = was
        self.addCleanup(back); self.spaces, self.styles = spaces, styles

    def test_each_workspace_has_its_own_vocabulary_style_and_logo_and_they_follow_a_new_name(self):
        sp = self.spaces; sp.set_space("p1", "Замовник"); speech.set_vocabulary(["Тестовий Двір"], sp.book("Замовник"))
        self.assertEqual(speech.vocabulary(sp.book(sp.space_of("p1")))[0], "Тестовий Двір"); self.assertNotIn("Тестовий Двір", speech.vocabulary())
        key = self.styles.save("Свій", {"accent": "#ff0000"}); sp.set_style("Замовник", key)
        self.assertEqual(sp.style_for("p1")["accent"], "#ff0000"); self.assertIsNone(sp.style_for("p2"))   # a project elsewhere gets the common default
        logo = self.home / "in.png"; logo.write_bytes(b"png"); sp.set_logo("Замовник", logo, ".png"); self.assertTrue(sp.logo("Замовник").exists())
        sp.set_ending("Замовник", "  Пишіть   у дірект "); self.assertEqual(sp.ending("Замовник"), "Пишіть у дірект"); self.assertIsNone(sp.ending(sp.HOME_SPACE))
        sp.rename("Замовник", "Новий замовник")
        self.assertEqual(sp.space_of("p1"), "Новий замовник"); self.assertEqual(sp.style_for("p1")["accent"], "#ff0000")
        self.assertEqual(speech.vocabulary(sp.book("Новий замовник"))[0], "Тестовий Двір"); self.assertIsNotNone(sp.logo("Новий замовник")); self.assertEqual(sp.ending("Новий замовник"), "Пишіть у дірект")

    def test_a_workspace_taken_away_gives_its_projects_back_to_the_first(self):
        sp = self.spaces; sp.set_space("p1", "Замовник"); sp.remove("Замовник")
        self.assertEqual(sp.space_of("p1"), sp.HOME_SPACE); self.assertEqual(sp.spaces()["spaces"], [sp.HOME_SPACE])
        with self.assertRaises(ValueError): sp.remove(sp.HOME_SPACE)
        with self.assertRaises(ValueError): sp.rename(sp.HOME_SPACE, "Інша назва")


class Takes(unittest.TestCase):
    """A video shot as several files: where the file changes there is always a join, and the review is told where."""

    def test_one_take_never_runs_into_the_next(self):
        said = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35, "confidence": 0.9, "take": "t1" if i < 3 else "t2"} for i, t in enumerate("Це перший запис. А це другий.".split())]
        parts = [{"id": "t1", "name": "a.mov", "start": 0, "seconds": 1.2, "from": 0, "to": 2}, {"id": "t2", "name": "b.mov", "start": 1.2, "seconds": 1.4, "from": 3, "to": 5}]
        doc = project.new("x.mp4", {"seconds": 2.6, "width": 1080, "height": 1920, "fps": 30, "hdr": False, "has_audio": True}, {"language": "uk", "words": said}, {"beats": [], "needs": [], "emphasis": [], "corrections": []}, takes=parts)
        line = project.resolve(doc)
        self.assertEqual(len(line["spans"]), 2); self.assertLessEqual(line["spans"][0][1], 1.2); self.assertGreaterEqual(line["spans"][1][0], 1.2)
        del doc["takes"]; self.assertEqual(len(project.resolve(doc)["spans"]), 1)   # the same words as one take run on

    def two(self):
        said = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35, "confidence": 0.9, "take": "t1" if i < 3 else "t2"} for i, t in enumerate("Це перший запис. А це другий.".split())]
        parts = [{"id": "t1", "name": "a.mov", "file": "a.mov", "start": 0, "seconds": 1.2, "from": 0, "to": 2}, {"id": "t2", "name": "b.mov", "file": "b.mov", "start": 1.2, "seconds": 1.4, "from": 3, "to": 5}]
        doc = project.new("x.mp4", self.FACTS, {"language": "uk", "words": said}, {"beats": [{"id": "b1", "kind": "title", "from": 1, "to": 2, "need": None, "text": "Перший", "accepted": True}], "needs": [], "emphasis": [{"word": 5, "by": "ai", "accepted": True}], "corrections": []},
                          cuts=[{"id": "c1", "from": 3, "to": 3, "why": "aside", "note": "", "by": "ai"}], takes=parts)
        doc["overlays"] = [{"id": "o1", "from": 2, "to": 4, "kind": "sticker", "text": "через межу", "accepted": True}]; doc["marks"] = []
        return doc

    FACTS = {"seconds": 2.6, "width": 1080, "height": 1920, "fps": 30, "hdr": False, "has_audio": True}

    def test_takes_put_in_another_order_carry_their_words_and_everything_done_to_them(self):
        doc = project.retake(self.two(), ["t2", "t1"], [{"start": 0, "seconds": 1.4}, {"start": 1.4, "seconds": 1.2}], "joined.mp4", self.FACTS)
        self.assertEqual([w["text"] for w in doc["words"]], "А це другий. Це перший запис.".split()); self.assertEqual([w["id"] for w in doc["words"]], list(range(6)))
        self.assertEqual(doc["words"][0]["start"], 0.0); self.assertEqual(doc["words"][3]["start"], 1.4)        # each word keeps its place within its take
        self.assertEqual([(t["id"], t["from"], t["to"]) for t in doc["takes"]], [("t2", 0, 2), ("t1", 3, 5)])
        self.assertEqual([(c["from"], c["to"]) for c in doc["cuts"]], [(0, 0)]); self.assertEqual(doc["edit"]["segments"], [{"source": "s1", "from": 1, "to": 5}])
        self.assertEqual([(b["from"], b["to"]) for b in doc["beats"]], [(4, 5)]); self.assertEqual(doc["emphasis"][0]["word"], 2)
        self.assertEqual([(o["from"], o["to"]) for o in doc["overlays"]], [(5, 5)])                                  # a stretch over two takes stays with the one it began in
        self.assertEqual(doc["sources"][0]["file"], "joined.mp4"); project.resolve(doc)

    def test_a_take_taken_out_takes_its_words_and_what_was_done_to_them(self):
        doc = project.retake(self.two(), ["t2"], [{"start": 0, "seconds": 1.4}], "joined.mp4", self.FACTS)
        self.assertEqual([w["text"] for w in doc["words"]], "А це другий.".split()); self.assertEqual(doc["beats"], []); self.assertEqual(doc["overlays"], [])
        self.assertEqual([(c["from"], c["to"]) for c in doc["cuts"]], [(0, 0)]); self.assertEqual(doc["emphasis"][0]["word"], 2)

    def test_one_more_take_goes_to_the_end_and_moves_nothing(self):
        was = self.two(); new = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35, "confidence": 0.9} for i, t in enumerate("Ой. І третій.".split())]
        doc = project.append(was, new, [{"id": "c1", "from": 0, "to": 0, "why": "aside", "note": "", "by": "ai"}], "c.mov", "c.mov", 1.3)
        self.assertEqual(doc["words"][:6], was["words"]); self.assertEqual([w["id"] for w in doc["words"]], list(range(9))); self.assertEqual(doc["words"][6]["start"], 2.6)
        self.assertEqual([(t["id"], t["from"], t["to"]) for t in doc["takes"]][-1], ("t3", 6, 8)); self.assertEqual([c["id"] for c in doc["cuts"]], ["c1", "c2"])
        self.assertEqual(doc["edit"]["segments"], [{"source": "s1", "from": 0, "to": 2}, {"source": "s1", "from": 4, "to": 5}, {"source": "s1", "from": 7, "to": 8}])

    def test_a_project_shot_as_one_file_is_one_take(self):
        doc = self.two(); del doc["takes"]
        self.assertEqual([(t["id"], t["from"], t["to"], t["file"]) for t in project.as_takes(doc)], [("t1", 0, 5, "x.mp4")])

    def test_the_review_is_told_where_each_file_starts_and_one_take_is_asked_about_as_before(self):
        asked = []; was = (suggest.ask, suggest.enabled); self.addCleanup(lambda: (setattr(suggest, "ask", was[0]), setattr(suggest, "enabled", was[1])))
        suggest.enabled = lambda: True; suggest.ask = lambda prompt, **k: asked.append(prompt) or {"cuts": []}
        words = [{"text": t} for t in "Це перший запис. А це другий.".split()]
        suggest.review(words); suggest.review(words, starts=[3])
        self.assertNotIn("⟦", asked[0]); self.assertIn("[2]запис. ⟦запис 2⟧ [3]А", asked[-1])


class Presets(unittest.TestCase):
    def test_every_ready_made_style_is_a_whole_valid_style_with_a_font_on_offer(self):
        from engine import fonts
        names = [p["name"] for p in project.PRESETS]; self.assertEqual(len(names), len(set(names)))
        for preset in project.PRESETS:
            made = project.clean_style(preset)
            self.assertEqual({k: made[k] for k in preset}, preset); self.assertIn(preset["font"], fonts.OFFERED)


class Walk(unittest.TestCase):
    def test_the_way_between_two_rooms_goes_through_the_door_and_turns_only_at_right_angles(self):
        import numpy as np, tempfile, cv2
        from engine import plan
        with tempfile.TemporaryDirectory() as tmp:
            was = plan.HOME; plan.HOME = Path(tmp); self.addCleanup(lambda: setattr(plan, "HOME", was)); plan._ways.clear()
            picture = Path(tmp) / "plan.png"; cv2.imwrite(str(picture), np.full((200, 400, 3), 255, np.uint8))
            square = lambda x, y: [[x, y], [x + 0.45, y], [x + 0.45, y + 0.9], [x, y + 0.9]]
            known = {"format": plan.FORMAT, "rooms": [{"id": "r1", "shape": square(0.03, 0.05), "at": [0.2, 0.2]}, {"id": "r2", "shape": square(0.52, 0.05), "at": [0.8, 0.2]}], "names": {}}
            plan.place(picture).parent.mkdir(parents=True); plan.place(picture).write_text(json.dumps(known))
            walls = np.zeros((90, 180), np.uint8); walls[:, 88:92] = 1   # a wall between the two rooms from top to bottom
            np.savez_compressed(plan.place(picture).with_suffix(".floor.npz"), doors=np.array([[0.5, 0.8, 0.02]], np.float32), walls=walls)   # and one door, low down
            way = plan.way(picture, "r1", "r2")
            self.assertTrue(all(a[0] == b[0] or a[1] == b[1] for a, b in zip(way, way[1:])))   # no step goes aslant
            crossing = next(a for a, b in zip(way, way[1:]) if (a[0] - 0.5) * (b[0] - 0.5) < 0)
            self.assertAlmostEqual(crossing[1], 0.8, delta=0.06)   # the wall is crossed where the door is


class Restarts(unittest.TestCase):
    words = staticmethod(lambda text: [{"text": t} for t in text.split()])

    def test_a_phrase_begun_and_at_once_begun_again_loses_its_first_telling(self):
        from engine.suggest import restarts
        words = self.words("Це будинок. Санвузол уже з. Санвузол уже з ремонтом. Пальня на другому поверсі. Спальня на другому поверсі. Дуже дуже гарно, і це і те.")
        self.assertEqual([" ".join(w["text"] for w in words[c["from"]:c["to"] + 1]) for c in restarts(words)], ["Санвузол уже з.", "Пальня на другому поверсі."])

    def test_a_senseless_phrase_is_cut_only_when_it_says_nothing_new(self):
        from engine.suggest import empty
        words = self.words("Далі гардеробна кімната з вікном. Це і весь гардеробна кімната. Біля кухні, якому роди запасів і техніки. Далі тераса.")
        self.assertTrue(empty(words, {"from": 5, "to": 9})); self.assertFalse(empty(words, {"from": 10, "to": 16}))


class Spelling(unittest.TestCase):
    def test_the_vocabulary_spells_what_was_heard(self):
        from engine.speech import spelled
        heard = [{"text": t, "start": i, "end": i + 0.5, "confidence": 0.9} for i, t in enumerate("в G Village, біля села Горанич. Заходимо перед покій, а там Перемога".split())]
        words = spelled(heard, ["G-Village", "Гореничі", "передпокій", "тераса"])
        self.assertEqual(" ".join(w["text"] for w in words), "в G-Village, біля села Гореничі. Заходимо передпокій, а там Перемога")
        self.assertEqual(words[1]["heard"], "G Village,"); self.assertEqual((words[1]["start"], words[1]["end"]), (1, 2.5))

    def test_a_long_term_heard_with_one_letter_wrong_is_respelled(self):
        from engine.speech import spelled
        heard = [{"text": t, "start": i, "end": i + 0.5, "confidence": 0.9} for i, t in enumerate("Заходимо в перепокій, далі гардеробну і терасу. Панорама.".split())]
        words = spelled(heard, ["передпокій", "гардеробна", "тераса", "панорамні"])
        self.assertEqual(" ".join(w["text"] for w in words), "Заходимо в передпокій, далі гардеробну і терасу. Панорама.")
        self.assertEqual(words[2]["heard"], "перепокій,")

    def test_a_word_heard_in_pieces_is_put_together(self):
        from engine.speech import spelled
        heard = [{"text": t, "start": i, "end": i + 0.5, "confidence": 0.9} for i, t in enumerate("Обов 'язково починаємо з перед покою, а Вперед покої дев 'ять шаф. Перед покоєм не стій, вперед іди.".split())]
        words = spelled(heard, ["передпокій", "тераса"])
        self.assertEqual(" ".join(w["text"] for w in words), "Обов'язково починаємо з передпокою, а В передпокої дев'ять шаф. Передпокоєм не стій, вперед іди.")

    def test_what_was_heard_right_is_left_alone(self):
        from engine.speech import spelled
        said = "Таунхаус у Гореничах, тут кухня, вітальня і тераса."
        heard = [{"text": t, "start": i, "end": i + 0.5, "confidence": 0.9} for i, t in enumerate(said.split())]
        self.assertEqual(" ".join(w["text"] for w in spelled(heard, ["Гореничі", "кухня-вітальня"])), said)

    def test_a_name_heard_quite_differently_is_respelled_once_someone_has_said_how(self):
        from engine.speech import letters, spelled
        heard = [{"text": t, "start": i, "end": i + 0.5, "confidence": 0.9} for i, t in enumerate("будинку в Джівілич, ми попадаємо вперед покій.".split())]
        words = spelled(heard, ["G-Village", "передпокій"], known={letters("Джівілич"): "G-Village"})
        self.assertEqual(" ".join(w["text"] for w in words), "будинку в G-Village, ми попадаємо в передпокій.")

    def test_a_correction_is_remembered_when_it_is_a_name_or_when_asked(self):
        from engine.speech import learn, lines, misheard, letters
        with tempfile.TemporaryDirectory() as tmp:
            book = Path(tmp) / "vocabulary.txt"; book.write_text("тераса\n", encoding="utf-8")
            self.assertTrue(learn("Гореничі,", "Горанич,", book)); self.assertEqual(misheard(book)[letters("Горанич")], "Гореничі")
            self.assertFalse(learn("балькон", "балкон.", book)); self.assertNotIn("балькон", " ".join(lines(book)))
            self.assertTrue(learn("балькон", "балкон.", book, always=True)); self.assertIn("балькон = балкон", lines(book))
            book.write_text("\n".join(f"слово{i}" for i in range(80)) + "\n", encoding="utf-8")
            self.assertFalse(learn("Новий", None, book, always=True)); self.assertEqual(len(lines(book)), 80)


class Names(unittest.TestCase):
    def test_words_of_one_meaning_are_one_name(self):
        from engine.plan import stems
        self.assertEqual(stems("постірочна"), stems("Пральня"))
        self.assertEqual(stems("гардеробну кімнату") & stems("Гардеробна"), {"гарде"})
        self.assertTrue(stems("паркінг на два автомобілі") & stems("Навіс"))
        self.assertFalse(stems("технічне приміщення") & stems("Пральня"))
        self.assertFalse(stems("дитячі кімнати") & stems("Ванна кімната"))
        self.assertTrue(stems("дитячі кімнати") <= stems("Спальня") and stems("блок господарів") <= stems("Спальня господарів"))


class DrawnRoom(unittest.TestCase):
    """A room a person draws on a plan that has been read."""

    def setUp(self):
        import cv2, numpy as np, tempfile
        from engine import plan
        self.plan = plan; self.was = plan.HOME; self.addCleanup(lambda: setattr(plan, "HOME", self.was))
        self.home = Path(tempfile.mkdtemp()); plan.HOME = self.home; self.picture = self.home / "plan.png"
        cv2.imwrite(str(self.picture), np.full((400, 600, 3), 255, np.uint8))
        # one room found: a box from (60,60) to (540,340)
        box = [[0.1, 0.15], [0.9, 0.15], [0.9, 0.85], [0.1, 0.85]]
        kept = plan.place(self.picture); kept.parent.mkdir(parents=True); kept.write_text(json.dumps({"format": plan.FORMAT, "rooms": [{"id": "r1", "shape": box, "at": [0.5, 0.5], "name": "Кухня-вітальня", "guess": True}], "names": {}}))

    def area(self, room):
        import cv2, numpy as np
        return cv2.contourArea((np.array(room["shape"]) * (600, 400)).astype(np.float32))

    def test_a_room_drawn_over_another_takes_its_part_and_keeps_to_the_walls(self):
        # drawn carelessly past the left and bottom walls: the hall is still only what lies inside the found room
        made = self.plan.add_room(self.picture, [[0.02, 0.6], [0.4, 0.6], [0.4, 0.98], [0.02, 0.98]], "Передпокій")
        rooms = {r["id"]: r for r in self.plan.stored(self.picture)["rooms"]}
        self.assertEqual(made["name"], "Передпокій"); self.assertEqual(len(rooms), 2)
        self.assertAlmostEqual(self.area(made), 180 * 100, delta=0.08 * 180 * 100)
        self.assertAlmostEqual(self.area(rooms["r1"]), 480 * 280 - 180 * 100, delta=0.05 * 480 * 280)

    def test_a_room_drawn_on_empty_paper_is_taken_as_drawn_and_can_be_removed(self):
        made = self.plan.add_room(self.picture, [[0.92, 0.1], [0.99, 0.1], [0.99, 0.5], [0.92, 0.5]])
        self.assertTrue(made.get("outdoors")); self.assertAlmostEqual(self.area(made), 42 * 160, delta=0.15 * 42 * 160)
        self.plan.remove_room(self.picture, made["id"]); self.assertEqual([r["id"] for r in self.plan.stored(self.picture)["rooms"]], ["r1"])

    def test_corners_moved_by_hand_are_kept_as_given(self):
        shape = [[0.1, 0.15], [0.5, 0.15], [0.5, 0.5], [0.9, 0.5], [0.9, 0.85], [0.1, 0.85]]
        room = self.plan.reshape_room(self.picture, "r1", shape)
        self.assertEqual(room["shape"], shape); self.assertEqual(self.plan.stored(self.picture)["rooms"][0]["shape"], shape)
        self.assertRaises(ValueError, self.plan.reshape_room, self.picture, "r1", [[0.1, 0.1], [0.2, 0.2]])


    def test_a_removed_room_gives_its_area_back(self):
        made = self.plan.add_room(self.picture, [[0.1, 0.6], [0.4, 0.6], [0.4, 0.85], [0.1, 0.85]], "Передпокій")
        self.assertLess(self.area(self.plan.stored(self.picture)["rooms"][0]), 0.9 * 480 * 280)
        self.plan.remove_room(self.picture, made["id"]); rooms = self.plan.stored(self.picture)["rooms"]
        self.assertEqual(len(rooms), 1); self.assertAlmostEqual(self.area(rooms[0]), 480 * 280, delta=0.03 * 480 * 280)

    def test_a_persons_work_is_carried_to_rooms_found_anew(self):
        import cv2
        old = [{"id": "r1", "shape": [[0.1, 0.15], [0.9, 0.15], [0.9, 0.85], [0.1, 0.85]], "at": [0.5, 0.5], "name": "Зала", "guess": False},
               {"id": "r7", "shape": [[0.92, 0.1], [0.99, 0.1], [0.99, 0.5], [0.92, 0.5]], "at": [0.95, 0.3], "name": "Ґанок", "guess": False, "by": "user"}]
        new = [{"id": "r1", "shape": [[0.11, 0.16], [0.89, 0.16], [0.89, 0.84], [0.11, 0.84]], "at": [0.5, 0.5], "name": "Кухня-вітальня", "guess": True}]
        self.plan.carry(cv2.imread(str(self.picture)), old, new)
        self.assertEqual([(r["name"], r.get("guess"), r.get("by")) for r in new], [("Зала", False, None), ("Ґанок", False, "user")])

    def test_a_phrase_may_speak_of_several_rooms(self):
        self.assertEqual(self.plan.several("В нас є дві дитячі кімнати"), 2); self.assertEqual(self.plan.several("дитяча кімната"), 1)


class Tour(unittest.TestCase):
    def test_the_plan_is_laid_over_each_walk_through_its_rooms(self):
        folder = Path(tempfile.mkdtemp()); words = [{"id": i, "source": "s1", "text": f"w{i}.", "start": i * 0.4, "end": i * 0.4 + 0.3, "confidence": 1} for i in range(120)]
        doc = {"format": project.FORMAT, "sources": [{"id": "s1", "seconds": 60}], "language": "uk", "words": words, "edit": {"segments": [{"source": "s1", "from": 0, "to": 119}]},
               "assets": [{"id": "a1", "file": "/nowhere/plan.jpg", "kind": "photo"}], "needs": [], "cuts": [], "emphasis": [], "corrections": [], "style": {},
               "beats": [{"id": "b1", "kind": "cutaway", "from": 12, "to": 18, "need": None, "asset": "a1", "text": None, "why": "", "by": "ai", "accepted": True}],
               "marks": [{"id": "m1", "asset": "a1", "room": "r1", "from": 10, "to": 14, "name": "хол", "by": "ai"}, {"id": "m2", "asset": "a1", "room": "r2", "from": 30, "to": 33, "name": "кухня", "by": "ai"},
                         {"id": "m3", "asset": "a1", "room": None, "from": 50, "to": 52, "name": "?", "by": "ai"}, {"id": "m4", "asset": "a1", "room": "r3", "from": 100, "to": 105, "name": "спальня", "by": "ai"}]}
        project.save(folder, doc); laid = project.lay_plans(folder); doc = project.load(folder)
        self.assertEqual(laid, {"a1": [[10, 33], [100, 105]]})   # two walks; the moment with no room does not hold the plan on screen
        self.assertFalse(next(b for b in doc["beats"] if b["id"] == "b1")["accepted"])   # the AI's insert of the same plan gives way
        project.lay_plans(folder); self.assertEqual(len([b for b in project.load(folder)["beats"] if b.get("by") == "plan"]), 2)   # remade, not added twice



class Fonts(unittest.TestCase):
    def test_a_style_keeps_a_font_name_and_refuses_anything_else(self):
        self.assertEqual(project.clean_style({"font": " Russo  One ", "caps": True})["font"], "Russo One")
        self.assertTrue(project.clean_style({"caps": True})["caps"])
        self.assertEqual(project.clean_style({"font": "../../etc/passwd"})["font"], "Inter")
        self.assertEqual(project.clean_style({})["font"], "Inter")


class Sounds(unittest.TestCase):
    def test_everything_that_appears_has_its_sound_and_a_style_can_have_none(self):
        import tempfile, wave
        from engine import sounds
        line = {"seconds": 12, "style": {"sounds": "quiet"}, "beats": [{"kind": "title", "start": 1.0}, {"kind": "full", "start": 6.0}, {"kind": "zoom", "start": 3.0}],
                "overlays": [{"kind": "number", "start": 2.0}, {"kind": "sticker", "start": 4.0}], "breaks": [{"start": 9.0, "end": 10.0}]}
        self.assertEqual([name for _, name in sounds.events(line)], ["thud", "pop", "chime", "pop", "whoosh", "whoosh", "whoosh"])
        with tempfile.TemporaryDirectory() as tmp:
            out = sounds.track(line, Path(tmp) / "s.wav")
            with wave.open(str(out)) as file: self.assertEqual((file.getframerate(), file.getnframes()), (48000, 12 * 48000))
            self.assertEqual(Path(out).read_bytes(), Path(sounds.track(line, Path(tmp) / "again.wav")).read_bytes())   # the same every time
            self.assertIsNone(sounds.track({**line, "style": {"sounds": "off"}}, Path(tmp) / "none.wav"))


class Overlays(unittest.TestCase):
    """What the AI proposes to lay over the speaker is checked against the words before it is kept."""

    def setUp(self):
        self.words = [{"text": t} for t in "Будинок має 154 метри квадратних і перепад рельєфу 7-8 метрів, він біля лісу в Бірках і дуже затишний".split()]
        self.was = (suggest.ask, suggest.enabled); self.addCleanup(lambda: (setattr(suggest, "ask", self.was[0]), setattr(suggest, "enabled", self.was[1]))); suggest.enabled = lambda: True

    def kept(self, proposed, busy=()):
        suggest.ask = lambda *a, **k: {"overlays": proposed}
        return suggest.decorate(self.words, busy=busy)

    def test_a_price_must_be_said_and_a_name_plate_made_of_what_was_said(self):
        self.words = [{"text": t} for t in "Мене звати Олена Коваль. Будинок у Бірках коштує 85 000 доларів, а ділянка ще 20 тисяч".split()]
        made = self.kept([{"kind": "lower", "from": 0, "to": 3, "title": "Олена Коваль", "caption": "ріелторка"}, {"kind": "lower", "from": 4, "to": 6, "title": "Марія Петренко"},
                          {"kind": "price", "from": 7, "to": 10, "value": "85 000", "unit": "$", "caption": "ціна будинку"}, {"kind": "price", "from": 12, "to": 15, "value": "30 000", "unit": "$"}])
        self.assertEqual([(o["kind"], o.get("title") or o.get("value")) for o in made], [("lower", "Олена Коваль"), ("price", "85 000")])   # an invented name and an unsaid price are dropped

    def test_a_number_must_be_one_that_was_said(self):
        made = self.kept([{"kind": "number", "from": 2, "to": 4, "value": "154", "unit": "м²"}, {"kind": "number", "from": 8, "to": 9, "value": "7-8", "unit": "м"}, {"kind": "number", "from": 12, "to": 14, "value": "200", "unit": "м"}])
        self.assertEqual([(o["value"], o["unit"]) for o in made], [("154", "м²"), ("7-8", "м")])

    def test_a_break_stands_where_a_sentence_starts_and_not_at_the_very_beginning(self):
        self.words = [{"text": t} for t in ("Привіт, це будинок біля лісу. " + "Тут тихо і зелено навколо, є річка. " * 2 + "Тепер про планування будинку і кімнати.").split()]
        made = self.kept([{"kind": "break", "from": 0, "text": "Початок"}, {"kind": "break", "from": 19, "text": "Планування будинку докладно"}, {"kind": "break", "from": 21, "text": "Посеред речення"}])
        self.assertEqual([(o["kind"], o["from"], o["text"]) for o in made], [("break", 19, "Планування будинку")])

    def test_a_sticker_is_made_of_what_was_said_and_not_laid_over_a_picture(self):
        made = self.kept([{"kind": "sticker", "from": 11, "to": 15, "text": "Біля лісу", "icon": "🌲"}, {"kind": "sticker", "from": 2, "to": 4, "text": "Басейн і сауна", "icon": "🏊"}])
        self.assertEqual([(o["text"], o["icon"]) for o in made], [("Біля лісу", "🌲")])
        self.assertEqual(self.kept([{"kind": "sticker", "from": 11, "to": 15, "text": "Біля лісу", "icon": "🌲"}], busy=[(10, 16)]), [])
