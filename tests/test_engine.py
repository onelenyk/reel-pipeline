"""Tests of the engine's logic: no video, no network. Run in the container:  ./reel test"""
import json, tempfile, unittest
from pathlib import Path
from engine import project, styles, suggest


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
