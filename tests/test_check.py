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

    def test_stem_must_start_the_word(self):
        # «воссоздал» содержит основу «созда», но это другое слово: приставочные формы перечисляются в словаре
        rep = self.run_check(self.edited(1, t="воссоздал"))
        self.assertError(rep, "ожидается «создать»")

    def test_stem_found(self):
        self.assertTrue(check.stem_found("дел", "сделаем, делай"))
        self.assertFalse(check.stem_found("дел", "отделил"))
        self.assertTrue(check.stem_found("дал", "дала"))
        self.assertFalse(check.stem_found("дал", "предал"))
        # основа короче трёх букв — только целым словом
        self.assertTrue(check.stem_found("ел", "и ел он"))
        self.assertFalse(check.stem_found("бо", "богохульствуй"))
        self.assertFalse(check.stem_found("по", "попросила"))
        self.assertTrue(check.stem_found("в живых", "сохранили в живых"))

    def test_latin_word_needs_place_analysis(self):
        rep = self.run_check(self.edited(5, t="erets", k="lat", s=None))
        self.assertError(rep, "нет разбора места")

    def test_translation_with_several_fits(self):
        v = copy.deepcopy(GEN_1_1)
        v["places"]["01nPh"] = {"fits": ["land", "other"], "why": "подходят два"}
        rep = self.run_check(v)
        self.assertError(rep, "подходят 2 значения, а слово переведено")
        v["places"]["01nPh"]["covers"] = True  # русское слово сохраняет оба значения (правила, раздел 1)
        rep = self.run_check(v)
        self.assertFalse(any("а слово переведено" in e for e in rep.errors), rep.errors)

    def test_same_russian_word_for_different_words(self):
        def write(key, **extra):
            data = {"key": key, "status": "draft", "notes": "", "history": HIST} | LEXICON[key] | extra
            data["senses"] = [dict(s, ru="небеса") for s in data["senses"]]
            (check.LEXICON / f"{key}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        write("776")
        rep = self.run_check()
        self.assertTrue(any("«небеса» — и у" in w for w in rep.warnings), rep.warnings)
        write("776", sameRu=["8064"])
        data = json.loads((check.LEXICON / "8064.json").read_text("utf-8")) | {"sameRu": ["776"]}
        (check.LEXICON / "8064.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        rep = self.run_check()
        self.assertFalse(any("«небеса» — и у" in w for w in rep.warnings), rep.warnings)

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

    def interpretation(self, **source):
        return {"id": "test-claim", "tradition": "Автор", "claim": "утверждение", "lemmas": ["430"],
                "places": ["Gen.1.1"], "source": source,
                "support": [{"claim": "часть", "grade": "compatible", "for": ["Gen.1.1"], "against": []}]}

    def book_source(self, **changes):
        src = {"kind": "book", "book": "test-book", "quote": "короткий отрывок из книги",
               "quoteRu": "короткий отрывок из книги", "checked": "2026-10-17"}
        src.update(changes)
        return src

    def with_book(self, found, pages=False, lang="it"):
        """Подменяет каталог книг: одна книга test-book, цитата находится или нет."""
        orig = check.books.book, check.books.find_quote, check.books.file_matches
        check.books.book = lambda i: {"id": i, "title": "Тест", "pages": pages, "lang": lang} if i == "test-book" else None
        check.books.find_quote = lambda i, q: found
        check.books.file_matches = lambda b: True
        self.addCleanup(lambda: setattr(check.books, "book", orig[0]))
        self.addCleanup(lambda: setattr(check.books, "find_quote", orig[1]))
        self.addCleanup(lambda: setattr(check.books, "file_matches", orig[2]))

    def test_interpretation_needs_checked_source(self):
        rep = self.run_check(interpretation=self.interpretation(title="Книга"))
        self.assertError(rep, "нет проверенного источника")
        self.assertError(rep, "неизвестный вид источника")

    def test_book_quote_found_passes(self):
        self.with_book(found=True)
        rep = self.run_check(interpretation=self.interpretation(**self.book_source()))
        self.assertEqual(rep.errors, [])
        self.assertFalse(any("трактовка" in w for w in rep.warnings))

    def test_book_quote_not_found(self):
        self.with_book(found=False)
        rep = self.run_check(interpretation=self.interpretation(**self.book_source()))
        self.assertError(rep, "отрывок не найден")

    def test_book_unavailable_is_warning(self):
        self.with_book(found=None)
        rep = self.run_check(interpretation=self.interpretation(**self.book_source()))
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("не проверен" in w for w in rep.warnings))

    def test_book_source_rules(self):
        self.with_book(found=True)
        rep = self.run_check(interpretation=self.interpretation(**self.book_source(book="other")))
        self.assertError(rep, "нет в каталоге")
        long_quote = " ".join(["слово"] * 16)
        rep = self.run_check(interpretation=self.interpretation(**self.book_source(quote=long_quote, quoteRu="")))
        self.assertError(rep, "длиннее 15 слов")
        self.assertError(rep, "нет русского перевода")
        rep = self.run_check(interpretation=self.interpretation(**self.book_source(page="12")))
        self.assertError(rep, "нет печатных страниц")

    def test_russian_book_needs_no_translation(self):
        self.with_book(found=True, lang="ru")
        rep = self.run_check(interpretation=self.interpretation(**self.book_source(quoteRu="")))
        self.assertEqual(rep.errors, [])

    def test_letters_ignore_hyphenation_and_quotes(self):
        self.assertEqual(check.books.letters("dell’ac-\nqua «là-acque»"), check.books.letters("dell'acqua \"là acque\""))


if __name__ == "__main__":
    unittest.main()
