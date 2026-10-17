"""Тесты проверки на Бытии 1:1. Нужен собранный корпус (python tools/build_corpus.py).

Запуск: python -m unittest discover -s tests
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check  # noqa: E402

HIST = [{"date": "2026-10-17", "by": "test", "change": "создано"}]


def sense(sid, ru, stems, refs):
    return {"id": sid, "ru": ru, "stems": stems, "gloss": "", "evidence": refs}


LEXICON = {
    "7225": {"kind": "word", "display": "reshit", "senses": [sense("beginning", "начало", ["начал"], ["Gen.1.1"])]},
    "1254a": {"kind": "word", "display": "bara", "senses": [sense("create", "создать", ["созда"], ["Gen.1.1"])]},
    "430": {"kind": "divine", "display": "Elohim", "senses": []},
    "853": {"kind": "function", "display": "et", "senses": []},
    "8064": {"kind": "word", "display": "shamayim", "senses": [sense("sky", "небеса", ["небес", "небо"], ["Gen.1.1"])]},
    "776": {"kind": "word", "display": "erets", "senses": [sense("land", "земля", ["земл"], ["Gen.1.1"])]},
}

GEN_1_1 = {
    "n": 1,
    "spans": [
        {"t": "В начале", "w": ["01xeN"], "s": "beginning", "g": "два разбора конструкции"},
        {"t": "создал", "w": ["01Nvk"], "s": "create"},
        {"t": "Elohim", "w": ["01TyA"], "k": "lat"},
        {"t": "небеса", "w": ["01TSc"], "s": "sky"},
        {"t": "и", "w": ["01k5P"], "k": "fn"},
        {"t": "землю", "w": ["01nPh"], "s": "land"},
        {"t": ".", "k": "p"},
    ],
    "omit": {"01vuQ": "et"},
    "places": {"01Nvk": {"fits": ["create"], "why": "одно значение подходит"}},
}


class CheckGen11(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        check.LEXICON = root / "lexicon"
        check.TRANSLATIONS = root / "translations"
        check.INTERPRETATIONS = root / "interpretations"
        for d in (check.LEXICON, check.TRANSLATIONS / "Gen", check.INTERPRETATIONS):
            d.mkdir(parents=True)
        for key, e in LEXICON.items():
            data = {"key": key, "status": "draft", "notes": "", "history": HIST} | e
            (check.LEXICON / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, verse=None, interpretation=None):
        chapter = {"book": "Gen", "chapter": 1, "rules": check.rules_version(), "status": "draft",
                   "verses": [verse or GEN_1_1]}
        (check.TRANSLATIONS / "Gen" / "001.json").write_text(json.dumps(chapter, ensure_ascii=False), "utf-8")
        if interpretation:
            (check.INTERPRETATIONS / f"{interpretation['id']}.json").write_text(
                json.dumps(interpretation, ensure_ascii=False), "utf-8")
        rep = check.Report()
        lex = check.load_lexicon(rep)
        check.check_chapter(check.TRANSLATIONS / "Gen" / "001.json", lex, rep, check.rules_version())
        check.check_interpretations(rep)
        return rep

    def edited(self, i, **changes):
        v = copy.deepcopy(GEN_1_1)
        v["spans"][i].update(changes)
        return v

    def assertError(self, rep, fragment):
        self.assertTrue(any(fragment in e for e in rep.errors), f"нет ошибки «{fragment}»: {rep.errors}")

    def test_valid_verse_passes(self):
        rep = self.run_check()
        self.assertEqual(rep.errors, [])

    def test_divine_name_cannot_be_translated(self):
        rep = self.run_check(self.edited(2, t="Бог", k=None, s="god"))
        self.assertError(rep, "имена и титулы не переводятся")

    def test_other_russian_word_needs_exception(self):
        rep = self.run_check(self.edited(1, t="сотворил"))
        self.assertError(rep, "ожидается «создать»")
        rep = self.run_check(self.edited(1, t="сотворил", x="проверка исключения"))
        self.assertEqual(rep.errors, [])

    def test_missing_word_is_reported(self):
        v = copy.deepcopy(GEN_1_1)
        del v["spans"][5]
        rep = self.run_check(v)
        self.assertError(rep, "не передано и не указано как пропущенное")

    def test_latin_form_must_match_lexicon(self):
        rep = self.run_check(self.edited(2, t="Elohiym"))
        self.assertError(rep, "латинская форма должна быть «Elohim»")

    def test_word_without_decision(self):
        (check.LEXICON / "776.json").unlink()
        rep = self.run_check()
        self.assertError(rep, "нет решения в словаре")

    def test_conjunction_alone_does_not_render_noun(self):
        v = copy.deepcopy(GEN_1_1)
        v["spans"][3] = {"t": "и", "w": ["01TSc"], "k": "fn"}
        rep = self.run_check(v)
        self.assertError(rep, "передано только служебной частью")
        v["spans"][3] = {"t": "и", "w": ["01Nvk"], "k": "fn"}
        rep = self.run_check(v)
        self.assertError(rep, "служебным может быть только приставка, окончание")

    def test_interpretation_needs_checked_source(self):
        it = {"id": "test-claim", "tradition": "Автор", "claim": "утверждение", "lemmas": ["430"],
              "places": ["Gen.1.1"], "source": {"title": "Книга"},
              "support": [{"claim": "часть", "grade": "compatible", "for": ["Gen.1.1"], "against": []}]}
        rep = self.run_check(interpretation=it)
        self.assertError(rep, "нет проверенного источника")
        self.assertError(rep, "не указано место")


if __name__ == "__main__":
    unittest.main()
