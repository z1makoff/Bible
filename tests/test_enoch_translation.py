"""Сборка и проверка перевода 1 Еноха. Данные только во временной папке.

Запуск: python -X utf8 -m unittest discover -s tests
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check  # noqa: E402
import compile_chapter  # noqa: E402
import dump_chapter  # noqa: E402

HIST = [{"date": "2026-11-03", "by": "test", "change": "создано"}]
PATCH = ("GEEZ_LEXICON", "ENOCH_TRANSLATIONS", "ENOCH_CORPUS", "ENOCH_MORPH", "GEEZ_LEXEMES")

ARTICLES = {
    "Ld17": {"n": "1", "head": "አምላክ", "senses": [{"text": "deus አምላክ Jer. 7,34."}]},
    "Lb1e55": {"n": "2", "head": "ባረከ", "senses": [{"text": "benedixit ባረከ Hen. 1,1"}]},
    "L1a0d": {"n": "3", "head": "ምድር", "senses": [{"text": "terra ምድር Jer. 7,34."}]},
    "L4e1": {"n": "4", "head": "ዘ", "senses": [{"text": "qui ዘ"}]},
    "L0901": {"n": "5", "head": "እየ", "senses": [{"text": "ego እየ"}]},
    "L05ed": {"n": "6", "head": "ባዕድ", "senses": [{"text": "alius ባዕድ Jer. 8,1."}]},
    "Lba4e": {"n": "7", "head": "ባዶ", "senses": [{"text": "terra Jer. 8,8."}]},
    "L07e4": {"n": "8", "head": "ሌላ", "senses": [{"text": "alius ሌላ"}]},
}

SPEC = """@ 1
и/e10001:fn Amlak/e10001:lat благословение/e10002:blessing земли/e10003:land za/e10004:fn меня/e10004:me .
"""


def sense(sid, ru, stems, evidence):
    return {"id": sid, "ru": ru, "stems": stems, "gloss": "", "evidence": evidence}


def decision(key, kind, display, n, head, senses=None, **extra):
    data = {
        "key": key, "kind": kind, "display": display, "n": n, "head": head,
        "senses": senses or [], "status": "draft", "notes": "", "history": HIST,
    }
    data.update(extra)
    return data


class EnochTranslation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = {name: getattr(check, name) for name in PATCH}
        check.GEEZ_LEXICON = self.root / "decisions" / "geez"
        check.ENOCH_TRANSLATIONS = self.root / "translations" / "1En"
        check.ENOCH_CORPUS = self.root / "corpus" / "enoch" / "1En"
        check.ENOCH_MORPH = self.root / "morph" / "enoch"
        check.GEEZ_LEXEMES = self.root / "corpus" / "geez-lexemes.json"
        for folder in (check.GEEZ_LEXICON, check.ENOCH_TRANSLATIONS, check.ENOCH_CORPUS, check.ENOCH_MORPH):
            folder.mkdir(parents=True)
        version = check.rules_version() or "1.4"
        (self.root / "ПРАВИЛА.md").write_text(f"Версия {version}\n", encoding="utf-8")
        self.write_json(check.GEEZ_LEXEMES, ARTICLES)
        self.write_json(check.ENOCH_CORPUS / "001.json", self.corpus())
        self.write_json(check.ENOCH_MORPH / "001.json", self.morph())
        for item in self.decisions():
            self.write_json(check.GEEZ_LEXICON / f"{item['key']}.json", item)
        check.clear_enoch_caches()
        self.compile(SPEC)

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(check, name, value)
        check.clear_enoch_caches()
        self.tmp.cleanup()

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def corpus(self):
        # У e10002 в корпусе чужая лемма: проверка должна взять лемму из morph.
        return {"book": "1En", "chapter": 1, "verses": [{
            "ref": "1En.1.1", "n": 1,
            "words": [
                {"id": "e10001", "text": "ወአምላክ", "tr": "wa-amlak",
                 "segs": [{"t": "ወ", "prefix": "c"}, {"t": "አምላክ", "lemma": "Ld17"}]},
                {"id": "e10002", "text": "ባረከ", "tr": "baraka",
                 "segs": [{"t": "ባረከ", "lemma": "L07e4"}]},
                {"id": "e10003", "text": "ምድር", "tr": "medr",
                 "segs": [{"t": "ምድር", "lemma": "L1a0d"}]},
                {"id": "e10004", "text": "ዘእየ", "tr": "za-eya",
                 "segs": [{"t": "ዘ", "prefix": "s"}, {"t": "እየ", "lemma": "L0901"}]},
            ],
            "smirnov": [{"c": 1, "v": 1, "text": "Смирнов-строка"}],
            "grc": [{"edition": "flemming1901", "c": 1, "v": 1, "text": "λόγος"}],
        }]}

    def morph(self):
        return {"chapter": 1, "words": {
            "e10001": {"status": "checked", "gram": "союз и имя", "alts": [],
                       "segs": [{"t": "ወ", "prefix": "c"}, {"t": "አምላክ", "lemma": "Ld17"}]},
            "e10002": {"status": "checked", "gram": "глагол", "alts": [],
                       "segs": [{"t": "ባረከ", "lemma": "Lb1e55"}]},
            "e10003": {"status": "unsure", "gram": "существительное", "alts": ["L05ed"],
                       "segs": [{"t": "ምድር", "lemma": "L1a0d"}]},
            "e10004": {"status": "checked", "gram": "местоимение", "alts": [],
                       "segs": [{"t": "ዘ", "prefix": "s"}, {"t": "ዘ", "lemma": "L4e1"},
                                {"t": "እየ", "lemma": "L0901"}]},
        }}

    def decisions(self):
        return [
            decision("Ld17", "divine", "Amlak", "1", "አምላክ", displayForms=["Amlāk"]),
            decision("Lb1e55", "word", "baraka", "2", "ባረከ",
                     [sense("blessing", "благословение", ["благослов"], ["1En.1.1"])]),
            decision("L1a0d", "word", "medr", "3", "ምድር",
                     [sense("land", "земля", ["земл"], ["Dillmann: Jer. 7,34"])]),
            decision("L4e1", "function", "za", "4", "ዘ"),
            decision("L0901", "word", "eya", "5", "እየ",
                     [sense("me", "меня", ["мен"], ["1En.1.1"])]),
        ]

    def compile(self, text):
        spec = self.root / "spec.txt"
        spec.write_text(text, encoding="utf-8")
        return compile_chapter.compile_chapter("1En", 1, spec, root=self.root)

    def translation(self):
        return json.loads((check.ENOCH_TRANSLATIONS / "001.json").read_text(encoding="utf-8"))

    def save_translation(self, data):
        self.write_json(check.ENOCH_TRANSLATIONS / "001.json", data)

    def replace_decision(self, data):
        self.write_json(check.GEEZ_LEXICON / f"{data['key']}.json", data)

    def run_check(self):
        check.clear_enoch_caches()
        rep = check.Report()
        lex = check.load_geez_lexicon(rep)
        check.check_chapter(check.ENOCH_TRANSLATIONS / "001.json", lex, rep, check.rules_version())
        return rep

    def assertError(self, rep, fragment):
        self.assertTrue(any(fragment in e for e in rep.errors), f"нет ошибки «{fragment}»: {rep.errors}")

    def verse(self):
        return self.translation()["verses"][0]

    def span(self, **match):
        for item in self.verse()["spans"]:
            if all(item.get(k) == v for k, v in match.items()):
                return item
        self.fail(f"нет фрагмента {match}")

    def test_compile_and_check_pass(self):
        data = self.translation()
        self.assertEqual(data["book"], "1En")
        self.assertEqual(data["chapter"], 1)
        self.assertEqual(data["rules"], check.rules_version())
        self.assertEqual(self.span(w=["e10002"])["s"], "blessing")
        self.assertEqual(self.span(k="lat")["t"], "Amlak")
        self.assertNotIn("omit", data["verses"][0])
        rep = self.run_check()
        self.assertEqual(rep.errors, [])
        self.assertEqual(len(rep.warnings), 1)
        self.assertIn("e10003", rep.warnings[0])
        self.assertIn("не checked", rep.warnings[0])

    def test_display_form_is_allowed(self):
        data = self.translation()
        self.span_in(data, k="lat")["t"] = "Amlāk"
        self.save_translation(data)
        self.assertEqual(self.run_check().errors, [])

    def span_in(self, data, **match):
        for item in data["verses"][0]["spans"]:
            if all(item.get(k) == v for k, v in match.items()):
                return item
        self.fail(f"нет фрагмента {match}")

    def test_divine_name_cannot_be_translated(self):
        data = self.translation()
        lat = self.span_in(data, k="lat")
        lat.pop("k")
        lat.update(t="Бог", s="god")
        self.save_translation(data)
        self.assertError(self.run_check(), "имена и титулы не переводятся")
        lat["x"] = "всё равно имя"
        self.save_translation(data)
        self.assertError(self.run_check(), "имена и титулы не переводятся")

    def test_keep_is_not_translated(self):
        self.replace_decision(decision("Lb1e55", "keep", "baraka", "2", "ባረከ", notes="значение не выбрано",
                                       senses=[sense("blessing", "благословение", ["благослов"], ["1En.1.1"])]))
        rep = self.run_check()
        self.assertError(rep, "не переводится")
        data = self.translation()
        self.span_in(data, s="blessing")["x"] = "исключение"
        self.save_translation(data)
        self.assertError(self.run_check(), "не переводится")

    def test_other_russian_word_needs_exception(self):
        data = self.translation()
        self.span_in(data, s="blessing")["t"] = "дар"
        self.save_translation(data)
        self.assertError(self.run_check(), "ожидается «благословение»")
        self.span_in(data, s="blessing")["x"] = "здесь иначе"
        self.save_translation(data)
        self.assertEqual(self.run_check().errors, [])

    def test_missing_word_is_reported(self):
        data = self.translation()
        data["verses"][0]["spans"] = [s for s in data["verses"][0]["spans"] if s.get("s") != "land"]
        self.save_translation(data)
        self.assertError(self.run_check(), "не передано и не указано как пропущенное")

    def test_bad_latin_form(self):
        data = self.translation()
        self.span_in(data, k="lat")["t"] = "Amlaka"
        self.save_translation(data)
        self.assertError(self.run_check(), "латинская форма должна быть «Amlak»")

    def test_unknown_sense(self):
        data = self.translation()
        self.span_in(data, s="blessing")["s"] = "blessing-no"
        self.save_translation(data)
        self.assertError(self.run_check(), "значение «blessing-no» не найдено")

    def test_function_span_needs_prefix_or_function_word(self):
        data = self.translation()
        blessing = self.span_in(data, s="blessing")
        blessing["k"] = "fn"
        blessing.pop("s")
        self.save_translation(data)
        self.assertError(self.run_check(), "служебным может быть только приставка")

    def test_function_segment_does_not_cover_the_other_lemma(self):
        data = self.translation()
        data["verses"][0]["spans"] = [s for s in data["verses"][0]["spans"] if s.get("s") != "me"]
        self.save_translation(data)
        self.assertError(self.run_check(), "передано только служебной частью")

    def test_wa_is_rendered_as_i(self):
        data = self.translation()
        wa = next(s for s in data["verses"][0]["spans"] if s.get("k") == "fn" and s.get("w") == ["e10001"])
        wa["t"] = "а"
        self.save_translation(data)
        self.assertError(self.run_check(), "союз ወ")
        wa["x"] = "здесь не союз"
        self.save_translation(data)
        self.assertEqual(self.run_check().errors, [])

    def test_sense_may_belong_to_any_segment(self):
        rep = self.run_check()
        self.assertFalse(any("e10004" in e for e in rep.errors))

    def test_enoch_place_must_contain_the_lemma(self):
        self.replace_decision(decision(
            "L05ed", "word", "baed", "6", "ባዕድ",
            [sense("other", "иной", ["ин"], ["1En.1.1"])]))
        self.assertError(self.run_check(), "в 1En.1.1 этого слова нет")

    def test_missing_verse_reference(self):
        item = self.decisions()[1]
        item["senses"][0]["evidence"] = ["1En.9.9"]
        self.replace_decision(item)
        self.assertError(self.run_check(), "места 1En.9.9 нет в корпусе")

    def test_dillmann_cite_must_be_in_the_article(self):
        item = self.decisions()[1]
        item["senses"][0]["evidence"] = ["Dillmann: Jer. 9,9"]
        self.replace_decision(item)
        self.assertError(self.run_check(), "ссылки «Jer. 9,9» нет")

    def test_shorter_dillmann_number_does_not_match(self):
        item = self.decisions()[2]
        item["senses"][0]["evidence"] = ["Dillmann: Jer. 7,3"]
        self.replace_decision(item)
        self.assertError(self.run_check(), "ссылки «Jer. 7,3» нет")

    def test_dillmann_cite_needs_geez_example(self):
        self.replace_decision(decision(
            "Lba4e", "word", "bado", "7", "ባዶ",
            [sense("empty", "пустой", ["пуст"], ["Dillmann: Jer. 8,8"])]))
        self.assertError(self.run_check(), "без геэзского примера")

    def test_article_number_and_head_must_match(self):
        item = self.decisions()[1]
        item["n"] = "99"
        item["head"] = "ሌላ"
        self.replace_decision(item)
        self.assertError(self.run_check(), "не совпадают со статьёй Дильмана")

    def test_missing_article(self):
        self.replace_decision(decision("Lffff", "word", "none", "1", "አምላክ",
                                       [sense("x", "слово", ["слов"], ["1En.1.1"])]))
        self.assertError(self.run_check(), "статьи «Lffff» нет")

    def test_empty_evidence(self):
        item = self.decisions()[1]
        item["senses"][0]["evidence"] = []
        self.replace_decision(item)
        self.assertError(self.run_check(), "нет ни одного места-свидетельства")

    def test_compile_rejects_bare_word(self):
        with self.assertRaises(SystemExit):
            self.compile("@ 1\nблагословение\n")

    def test_compile_rejects_unknown_verse(self):
        with self.assertRaises(SystemExit):
            self.compile("@ 9\nи/e10001:fn\n")

    def test_compile_attaches_markers(self):
        self.compile(SPEC + "x e10002 здесь иначе\no e10003 не передаётся\n")
        data = self.translation()
        # Строка o не удаляет уже собранный фрагмент: оба остаются, проверка это увидит.
        self.assertEqual(self.span(s="blessing")["x"], "здесь иначе")
        self.assertEqual(data["verses"][0]["omit"]["e10003"], "не передаётся")

    def test_omit_line_covers_a_word(self):
        self.compile("""@ 1
и/e10001:fn Amlak/e10001:lat благословение/e10002:blessing za/e10004:fn меня/e10004:me .
o e10003 не передаётся
""")
        rep = self.run_check()
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("e10003" in w and "не checked" in w for w in rep.warnings))

    def test_ready_chapter_needs_every_verse(self):
        corpus = self.corpus()
        corpus["verses"].append({"ref": "1En.1.2", "n": 2, "words": [
            {"id": "e10005", "text": "ምድር", "tr": "medr", "segs": [{"t": "ምድር", "lemma": "L1a0d"}]}]})
        self.write_json(check.ENOCH_CORPUS / "001.json", corpus)
        data = self.translation()
        data["status"] = "draft"
        self.save_translation(data)
        rep = self.run_check()
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("не подготовлены стихи" in w for w in rep.warnings))
        data["status"] = "ready"
        self.save_translation(data)
        self.assertError(self.run_check(), "глава отмечена готовой")

    def test_ot_compile_still_omits_et(self):
        folder = self.root / "corpus" / "ot" / "Gen"
        folder.mkdir(parents=True)
        self.write_json(folder / "001.json", {"verses": [{"n": 1, "words": [
            {"id": "w1", "segs": [{"lemma": "776", "t": "א"}]},
            {"id": "w853", "segs": [{"lemma": "853", "t": "את"}]},
        ]}]})
        spec = self.root / "gen.txt"
        spec.write_text("@ 1\nземлю/w1:land .\n", encoding="utf-8")
        path = compile_chapter.compile_chapter("Gen", 1, spec, root=self.root)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(path, self.root / "translations" / "ot" / "Gen" / "001.json")
        self.assertEqual(data["book"], "Gen")
        self.assertEqual(data["verses"][0]["omit"], {"w853": "et"})
        self.assertFalse((self.root / "translations" / "1En" / "Gen").exists())

    def test_dump_prints_sources_and_lemmas(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            dump_chapter.dump_chapter("1En", 1, root=self.root)
        text = buf.getvalue()
        self.assertIn("Смирнов 1:1: Смирнов-строка", text)
        self.assertIn("Греческий flemming1901 1:1: λόγος", text)
        self.assertIn("e10002 ባረከ baraka", text)
        self.assertIn("status=checked", text)
        self.assertIn("gram=глагол", text)
        self.assertIn("Lb1e55 n=2 head=ባረከ", text)
        self.assertIn("word:baraka", text)
        self.assertNotIn("L07e4", text)
        self.assertIn("alts:", text)
        self.assertIn("L05ed n=6 head=ባዕድ", text)


if __name__ == "__main__":
    unittest.main()
