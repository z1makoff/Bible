"""Книга Еноха: транслитерация, черновая нарезка, целостность корпуса.

Запуск из reader: python -m unittest discover -s tests
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_enoch  # noqa: E402
import check  # noqa: E402
import enoch_tag  # noqa: E402
import geez  # noqa: E402

TEI = ROOT / "sources" / "enoch-bm" / "LIT1340EnochE.xml"
CORPUS = ROOT / "corpus" / "enoch" / "1En"
MORPH = ROOT / "morph" / "enoch"
VERSES = ROOT / "corpus-input" / "enoch-verses.json"


def entry(eid, head, n="1", pos=None, forms=None, enoch=None, stem=None):
    return {
        "head": head,
        "n": str(n),
        "skeleton": geez.skeleton(head),
        "forms": forms or [],
        "enoch": enoch or [],
        "pos": pos or ["n."],
        "stem": stem,
    }


class TranslitTest(unittest.TestCase):
    def test_table_size(self):
        self.assertEqual(len(geez.SYLLABLE), 326)

    def test_teguhan(self):
        self.assertEqual(geez.transliterate("ትጉሃን"), ("tǝguhān", "teguhan"))

    def test_malaekt_keeps_inner_sixth_order(self):
        # Шестой ряд внутри слова — ǝ. Конечный шестой ряд без гласной.
        self.assertEqual(geez.transliterate("መላእክት"), ("malāʾǝkǝt", "malaeket"))

    def test_final_sixth_order_silent(self):
        self.assertEqual(geez.transliterate("ቃል"), ("qāl", "qal"))
        self.assertEqual(geez.transliterate("ብ"), ("b", "b"))

    def test_names_are_mechanical(self):
        self.assertEqual(geez.transliterate("እግዚአብሔር"), ("ʾǝgǝziʾabǝḥer", "egeziabeher"))
        self.assertEqual(geez.transliterate("አምላክ"), ("ʾamǝlāk", "amelak"))
        self.assertEqual(geez.transliterate("መንፈስ"), ("manǝfas", "manefas"))

    def test_labiovelar(self):
        self.assertEqual(geez.transliterate("ቈ"), ("qʷa", "qwa"))
        self.assertEqual(geez.transliterate("ኵሉ"), ("kʷǝlu", "kwelu"))

    def test_simple_form_is_one_table(self):
        self.assertEqual(geez.transliterate("ሥጋ"), ("śǝgā", "sega"))
        self.assertEqual(geez.transliterate("ፀሐይ")[1], "tsahay")

    def test_gemination_only_with_mark(self):
        self.assertEqual(geez.transliterate("ብ"), ("b", "b"))
        marked = "ብ" + geez.GEMINATION
        self.assertEqual(geez.transliterate(marked), ("bb", "bb"))

    def test_number_does_not_cross_wa(self):
        # ፲ и ፬ — разные числа: между ними ወ, это не 14 одной цифрой.
        self.assertEqual(geez.transliterate("፲ወ፬ዐፀው"), ("10wa4ʿaḍaw", "10wa4atsaw"))


class PrefixTest(unittest.TestCase):
    def test_wa_splits_when_stem_is_a_head(self):
        lex = enoch_tag.LexIndex({"La": entry("La", "አምላክ")})
        rec = enoch_tag.analyze("ወአምላክ", (1, 1), lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["t"], "ወ")
        self.assertEqual(rec["segs"][0]["prefix"], "c")
        self.assertEqual(rec["segs"][1]["t"], "አምላክ")
        self.assertEqual(rec["segs"][1]["lemma"], "La")

    def test_bare_wa_with_two_heads_stays_unsure(self):
        lex = enoch_tag.LexIndex({
            "L1": entry("L1", "ወ", n="1"),
            "L2": entry("L2", "ወ", n="2"),
        })
        rec = enoch_tag.analyze("ወ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(rec["segs"][0]["lemma"])
        self.assertEqual(set(rec["alts"]), {"L1", "L2"})

    def test_head_warada_is_not_stripped(self):
        lex = enoch_tag.LexIndex({
            "Lw": entry("Lw", "ወረደ", pos=["v."], stem=["I,1"]),
            "Lr": entry("Lr", "ረደ", pos=["v."], stem=["I,1"]),
        })
        rec = enoch_tag.analyze("ወረደ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(len(rec["segs"]), 1)
        self.assertEqual(rec["segs"][0]["t"], "ወረደ")
        self.assertIsNone(rec["segs"][0]["prefix"])
        self.assertEqual(rec["segs"][0]["lemma"], "Lw")

    def test_unrelated_quoted_form_is_not_auto(self):
        lex = enoch_tag.LexIndex({
            "Lbook": entry("Lbook", "መጽሐፍ", forms=["አብ", "መጽሐፍ"]),
        })
        rec = enoch_tag.analyze("አብ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(rec["segs"][0]["lemma"])
        self.assertNotIn("Lbook", rec["alts"])

    def test_ni_blocks_auto(self):
        lex = enoch_tag.LexIndex({
            "Lg": entry("Lg", "ገብረ", pos=["v."], stem=["I,1"]),
        })
        rec = enoch_tag.analyze("ገብረኒ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertTrue(all(seg["lemma"] is None for seg in rec["segs"]))
        self.assertNotIn("Enc-ni", [seg.get("morph") for seg in rec["segs"]])

    def test_ni_on_verb_is_s1cs_not_enc_ni(self):
        # ኒ при глаголе — местоимение n=4755, не энклитика. auto нет.
        lex = enoch_tag.LexIndex({
            "Lv": entry("Lv", "ገብረ", n="1", pos=["v."], stem=["I,1"]),
            "Lverb": entry("Lverb", "ኒ", n="4755", pos=["pron. suff."]),
            "Lenc": entry("Lenc", "ኒ", n="4756", pos=["part."]),
        })
        rec = enoch_tag.analyze("ገብረኒ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertEqual(rec["segs"][-1]["t"], "ኒ")
        self.assertEqual(rec["segs"][-1]["morph"], "S1cs")
        self.assertEqual(rec["segs"][-1]["lemma"], "Lverb")
        self.assertNotEqual(rec["segs"][-1]["lemma"], "Lenc")

    def test_ni_on_noun_is_enc_ni(self):
        lex = enoch_tag.LexIndex({
            "Ln": entry("Ln", "ምድር", n="1586", pos=["subst."]),
            "Lenc": entry("Lenc", "ኒ", n="4756", pos=["part."]),
        })
        rec = enoch_tag.analyze("ምድርኒ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][-1]["morph"], "Enc-ni")
        self.assertEqual(rec["segs"][-1]["lemma"], "Lenc")
        self.assertEqual(rec["segs"][0]["lemma"], "Ln")

    def test_homophone_match_is_unsure_not_auto(self):
        lex = enoch_tag.LexIndex({
            "Ls": entry("Ls", "ሰላም", n="2", pos=["subst."]),
        })
        rec = enoch_tag.analyze("ሠላም", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertEqual(rec["segs"][0]["lemma"], "Ls")
        self.assertEqual(rec["alts"], [])

    def test_paradigm_form_is_unsure_not_auto(self):
        item = entry("Lw", "ወሀበ", n="3", pos=["v."], stem=["I,1"])
        item["senses"] = [{"text": "Imperf. ይሁብ፡ Subj. የሀብ፡"}]
        lex = enoch_tag.LexIndex({"Lw": item})
        rec = enoch_tag.analyze("ትሁቡ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertEqual(rec["segs"][0]["lemma"], "Lw")
        self.assertEqual(rec["alts"], [])

    def test_two_ba_are_not_both_prefixes(self):
        # После በ вторая በ уже не приставка. በበ — отдельное слово, не цепочка b+b.
        lex = enoch_tag.LexIndex({"La": entry("La", "አምላክ")})
        rec = enoch_tag.analyze("በበአምላክ", None, lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(rec["segs"][0]["lemma"])


class Stage2Test(unittest.TestCase):
    """Окно парадигмы, корень, построенные формы. Чужой глагол из цитаты не берётся."""

    def _verb(self, eid, head, n, text):
        item = entry(eid, head, n=n, pos=["v."], stem=["I,1"])
        item["senses"] = [{"n": "1", "text": text}]
        return item

    def test_quote_words_are_not_foreign_verbs(self):
        lex = enoch_tag.LexIndex({
            "Lg": self._verb(
                "Lg", "ገብረ", "8420",
                "seq. Subj. vel ከመ፡ c. Subj. : ገብረ፡ ሎሙ፡ ይፍርህዎሙ፡",
            ),
            "Lq": self._verb("Lq", "ቄአ", "3591", "ቄአ፡ እምአፉሁ፡ ደመ፡"),
            "Lf": self._verb("Lf", "ፈርሀ", "9884", "ፈርሀ፡ ደመ፡"),
            "La": self._verb(
                "La", "አሕጸጸ", "998",
                "c.c. Acc. Infin.: አሠንዮ፡",
            ),
            "Lw": self._verb("Lw", "ወግዐ", "1", "c. Subj. ትፈቅዱ፡"),
        })
        for word in ("ሎሙ", "ደመ", "አሠንዮ", "ትፈቅዱ"):
            rec = enoch_tag.analyze(word, None, lex)
            lemmas = [seg.get("lemma") for seg in rec["segs"] if seg.get("lemma")]
            self.assertEqual(lemmas, [], word)
            self.assertFalse(set(rec["alts"]) & {"Lg", "Lq", "Lf", "La", "Lw"}, word)

    def test_lomu_is_the_preposition(self):
        la = entry("Ll", "ለ", n="144", pos=["praep."])
        la["senses"] = [{"n": "1", "text": "ሊተ፡ ለከ፡ ለኪ፡ ሎቱ፡ ላቲ፡ ለነ፡ ለክሙ፡ ለክን፡ ሎሙ፡ ሎን፡"}]
        gabra = self._verb(
            "Lg", "ገብረ", "8420",
            "seq. Subj. vel ከመ፡ c. Subj. : ገብረ፡ ሎሙ፡ ይፍርህዎሙ፡",
        )
        lex = enoch_tag.LexIndex({"Ll": la, "Lg": gabra})
        rec = enoch_tag.analyze("ሎሙ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["lemma"], "Ll")
        self.assertNotIn("Lg", rec["alts"])

    def test_wa_asenyo_is_not_ahsese(self):
        bad = self._verb("Lbad", "አሕጸጸ", "998", "c.c. Acc. Infin.: አሠንዮ፡")
        lex = enoch_tag.LexIndex({"Lbad": bad})
        rec = enoch_tag.analyze("ወአሠንዮ", None, lex)
        lemmas = [seg.get("lemma") for seg in rec["segs"] if seg.get("lemma")]
        self.assertNotIn("Lbad", lemmas)
        self.assertNotIn("Lbad", rec["alts"])
        self.assertNotIn("998", rec["note"])

    def test_wa_waradu_is_warada(self):
        item = self._verb("Lw", "ወረደ", "6556", "Subj. ይረድ፡")
        lex = enoch_tag.LexIndex({"Lw": item})
        rec = enoch_tag.analyze("ወወረዱ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["t"], "ወ")
        self.assertEqual(rec["segs"][0]["prefix"], "c")
        self.assertEqual(rec["segs"][1]["t"], "ወረዱ")
        self.assertEqual(rec["segs"][1]["lemma"], "Lw")

    def test_wa_neled_is_walada(self):
        item = self._verb("Lw", "ወለደ", "6430", "Subj. ይለድ፡")
        lex = enoch_tag.LexIndex({"Lw": item})
        rec = enoch_tag.analyze("ወንለድ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["prefix"], "c")
        self.assertEqual(rec["segs"][1]["t"], "ንለድ")
        self.assertEqual(rec["segs"][1]["lemma"], "Lw")

    def test_qatalu_is_qatala(self):
        item = self._verb("Lq", "ቀተለ", "3450", "Subj. ይቅትል፡")
        lex = enoch_tag.LexIndex({"Lq": item})
        rec = enoch_tag.analyze("ቀተሉ", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["lemma"], "Lq")
        self.assertEqual(len(rec["segs"]), 1)

    def test_sadeqan_is_sadeq(self):
        lex = enoch_tag.LexIndex({
            "Ls": entry("Ls", "ጻድቅ", n="9564", pos=["adj."]),
        })
        rec = enoch_tag.analyze("ጻድቃን", None, lex)
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(rec["segs"][0]["lemma"], "Ls")

    def test_michael_stem_is_not_a_verb(self):
        item = entry("Lm", "ሚካኤል", n="10309", pos=[], stem=["III,3"])
        item["senses"] = [{"n": "1", "text": "Michael (archangelus; de eo cf. III,3,5"}]
        self.assertFalse(enoch_tag.is_verb(item))
        self.assertEqual(enoch_tag.coarse_gram(item), "имя")

    def test_w_keeping_subj_is_not_dropped(self):
        item = self._verb("Lw", "ወሰደ", "1", "Subj. ይውስድ፡")
        lex = enoch_tag.LexIndex({"Lw": item})
        rec = enoch_tag.analyze("ይሰድ", None, lex)
        lemmas = [seg.get("lemma") for seg in rec["segs"] if seg.get("lemma")]
        self.assertNotIn("Lw", lemmas)


    def test_cited_form_does_not_beat_prefix_split(self):
        # ለእለ процитировано в статье ለለ, но это ለ + እለ.
        a = entry("La", "ለለ", n="145", pos=["praep."])
        a["forms"] = ["ለለ", "ለእለ"]
        b = entry("Lb", "እለ", n="5394", pos=["pron."])
        lex = enoch_tag.LexIndex({"La": a, "Lb": b})
        rec = enoch_tag.analyze("ለእለ", None, lex)
        self.assertEqual(rec["status"], "unsure")

    def test_vid_without_sub_is_a_pointer(self):
        a = entry("La", "ለእመ", n="345")
        a["senses"] = [{"text": "vid. እመ፡"}]
        b = entry("Lb", "እመ", n="5436", pos=["conj."])
        lex = enoch_tag.LexIndex({"La": a, "Lb": b})
        rec = enoch_tag.analyze("ለእመ", None, lex)
        self.assertEqual(rec["status"], "unsure")


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ed1, _eotc = build_enoch.load_editions(TEI)
        cls.chapters = []
        for number in range(1, 109):
            path = CORPUS / f"{number:03d}.json"
            cls.chapters.append(json.loads(path.read_text(encoding="utf-8")))

    def test_word_ids_are_gapless(self):
        ids = []
        for chapter in self.chapters:
            for verse in chapter["verses"]:
                for word in verse["words"]:
                    ids.append(word["id"])
        self.assertEqual(ids, [f"e{i:05d}" for i in range(1, len(ids) + 1)])
        self.assertEqual(ids[0], "e00001")

    def test_chapter_words_equal_ed1(self):
        self.assertEqual(len(self.ed1), 108)
        total = 0
        for edition, chapter in zip(self.ed1, self.chapters):
            words = [word for verse in chapter["verses"] for word in verse["words"]]
            self.assertEqual([word["text"] for word in words], edition["words"])
            self.assertEqual(chapter["chapter"], edition["n"])
            total += len(words)
        self.assertEqual(total, sum(len(ch["words"]) for ch in self.ed1))

    def test_no_word_lost_or_repeated_in_verses(self):
        for chapter in self.chapters:
            seen = []
            for verse in chapter["verses"]:
                self.assertTrue(verse["words"], chapter["chapter"])
                for word in verse["words"]:
                    seen.append(word["id"])
            self.assertEqual(len(seen), len(set(seen)))
            self.assertEqual(seen, sorted(seen))

    def test_every_morph_id_is_in_the_corpus(self):
        for number, chapter in enumerate(self.chapters, start=1):
            morph = json.loads((MORPH / f"{number:03d}.json").read_text(encoding="utf-8"))
            words = {word["id"]: word for verse in chapter["verses"] for word in verse["words"]}
            self.assertEqual(set(morph["words"]), set(words))
            for wid, rec in morph["words"].items():
                word = words[wid]
                self.assertEqual("".join(seg["t"] for seg in rec["segs"]), word["text"])
                self.assertEqual(word["segs"], rec["segs"])
                self.assertEqual(word.get("status"), rec["status"])

    def test_chapters_1_to_5_are_manual(self):
        for number in range(1, 6):
            morph = json.loads((MORPH / f"{number:03d}.json").read_text(encoding="utf-8"))
            for wid, rec in morph["words"].items():
                self.assertIn(rec["status"], ("checked", "unsure"), wid)
                if rec["status"] == "unsure":
                    self.assertTrue(str(rec.get("note") or "").strip(), wid)

    def test_variant_word_ids_exist(self):
        path = ROOT / "corpus-input" / "enoch-variants.json"
        variants = json.loads(path.read_text(encoding="utf-8"))
        by_ref = {}
        for chapter in self.chapters:
            for verse in chapter["verses"]:
                by_ref[verse["ref"]] = {word["id"] for word in verse["words"]}
                for block in verse.get("variants") or []:
                    for wid in block["wordIds"]:
                        self.assertIn(wid, by_ref[verse["ref"]], verse["ref"])
        self.assertTrue(variants)
        for item in variants:
            self.assertIn(item["ref"], by_ref, item["ref"])
            for wid in item["wordIds"]:
                self.assertIn(wid, by_ref[item["ref"]], item["ref"])

    def test_flemming_has_no_german_cues(self):
        cue = re.compile(
            r"(?:\b(?:der|die|das|und|den|dem|des|ein|eine|oder|nicht)\b)|(?:\bCap\.)",
            re.IGNORECASE,
        )
        seen = 0
        for chapter in self.chapters:
            for verse in chapter["verses"]:
                for block in verse.get("grc") or []:
                    if block.get("edition") != "flemming1901":
                        continue
                    seen += 1
                    self.assertIsNone(cue.search(block["text"]), verse["ref"])
        self.assertGreater(seen, 0)

    def test_verse_map_keeps_1_4(self):
        # Граница 1:4 не на ።. Карта правится вручную и выигрывает у автоматики.
        manual = json.loads(VERSES.read_text(encoding="utf-8"))
        self.assertEqual(manual["1"]["4"], "e00056")
        chapter = self.chapters[0]
        verse4 = next(verse for verse in chapter["verses"] if verse["n"] == 4)
        self.assertEqual(verse4["words"][0]["id"], "e00056")
        self.assertEqual(verse4["words"][0]["text"], "ወአምላከ")


class CheckEnochTest(unittest.TestCase):
    """check_enoch ловит порчу разметки: подменяем ROOT на копию с одной главой."""

    def errors(self, spoil):
        data = json.loads((MORPH / "001.json").read_text(encoding="utf-8"))
        spoil(data["words"][next(iter(data["words"]))])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "morph" / "enoch"
            folder.mkdir(parents=True)
            (folder / "001.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            report = check.Report()
            with mock.patch.object(check, "ROOT", Path(tmp)):
                check.check_enoch(report)
        return report.errors

    def test_clean_chapter_passes(self):
        self.assertEqual(self.errors(lambda word: None), [])

    def test_unknown_status(self):
        self.assertTrue(self.errors(lambda word: word.update(status="ok")))

    def test_unknown_lemma(self):
        self.assertTrue(self.errors(lambda word: word["segs"][0].update(lemma="L0")))

    def test_segments_must_join_to_corpus_word(self):
        self.assertTrue(self.errors(lambda word: word["segs"][0].update(t="ሀ")))

    def test_checked_word_needs_lemma(self):
        def spoil(word):
            word["status"] = "checked"
            word["gram"] = None
            for seg in word["segs"]:
                seg["lemma"] = None
        self.assertTrue(self.errors(spoil))


class Stage3Test(unittest.TestCase):
    """Чужая цитата в forms не становится auto. ያ/ይት берут свою породу.

    Примеры — реальные слова глав 17–108 и пары, которые ручная сверка
    глав 1–16 уже отнесла к другой основе. Словарь — DillmannData проекта.
    """

    @classmethod
    def setUpClass(cls):
        cls.lex = enoch_tag.LexIndex.load(enoch_tag.LEXICON)

    def _rec(self, word):
        return enoch_tag.analyze(word, (41, 1), self.lex)

    def _n(self, rec):
        for seg in rec["segs"]:
            eid = seg.get("lemma")
            if eid:
                return str(self.lex.items[eid].get("n"))
        return None

    def _alt_n(self, rec):
        return {str(self.lex.items[eid].get("n")) for eid in rec["alts"]}

    def test_balance_citation_is_not_the_participle(self):
        # 41:1 በመዳልው лежит в forms причастия ድልው n=7808.
        # Напечатанное Pl. መዳልው — у መድሎት n=7814.
        rec = self._rec("በመዳልው")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "7814")
        self.assertNotEqual(self._n(rec), "7808")

    def test_lie_citation_is_not_stem_one(self):
        # 104:9 ወኢተሐስዉ. ኢተሐስዉ процитировано у ሐሰወ n=695, корня там нет.
        rec = self._rec("ወኢተሐስዉ")
        self.assertNotEqual(rec["status"], "auto")
        self.assertNotEqual(self._n(rec), "695")
        self.assertNotIn("695", self._alt_n(rec))

    def test_people_citation_with_two_prefixes_is_not_auto(self):
        # 72:1 በበሕዘቢሆሙ целиком стоит в forms ሕዝብ. Две приставки, не форма.
        rec = self._rec("በበሕዘቢሆሙ")
        self.assertNotEqual(rec["status"], "auto")

    def test_days_plural_is_not_the_empty_stub(self):
        # መዋዕል — Pl. от ሞዐልት n=6716. Пустая статья n=12572 леммой не берётся.
        rec = self._rec("መዋዕል")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "6716")
        bare = self._rec("ወመዋዕሊሁ")
        self.assertEqual(bare["status"], "auto")
        self.assertEqual(self._n(bare), "6716")

    def test_ya_takes_stem_two_not_stem_one(self):
        # ያበርህ — II አብርሀ n=3861, не I በርሀ n=3860.
        rec = self._rec("ያበርህ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "3861")

    def test_yet_takes_stem_three_articles(self):
        # ይትነገፍኡ: две статьи III, не I ነገፈ n=5234.
        rec = self._rec("ይትነገፍኡ")
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(self._n(rec))
        self.assertEqual(self._alt_n(rec), {"5236", "5237"})

    def test_two_stem_two_articles_stay_unsure(self):
        # ወያጸንዑ: II,1 n=9393 и II,2 n=9394. I ጸንዐ n=9391 не лемма.
        rec = self._rec("ወያጸንዑ")
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(self._n(rec))
        self.assertEqual(self._alt_n(rec), {"9393", "9394"})

    def test_yet_on_t_initial_root_stays_stem_one(self):
        # ይትርፍ напечатан как Subj. у ተርፈ n=4269. Радикал t, не порода III.
        rec = self._rec("ይትርፍ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "4269")

    def test_yettefesam_sade_is_10122_not_mute(self):
        # ጸ — n=10122 ተፈጸመ. Статья печатает ዘኢይትፌጸም и Hen. 16,1.
        # ፀ — n=10142 ተፈፅመ: в forms есть ይትፌፀም, смысл obmutescere.
        for word in ("ይትፌጸም", "ወይትፌጸም", "ትትፌጸም", "ወትትፌጸም", "ይትፌጸሙ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "10122", word)
            self.assertNotIn("10142", self._alt_n(rec), word)
        mute = self._rec("ይትፌፀም")
        self.assertEqual(mute["status"], "auto")
        self.assertEqual(self._n(mute), "10142")
        self.assertNotIn("10122", self._alt_n(mute))
        plural = self._rec("ይትፌፀሙ")
        self.assertEqual(self._n(plural), "10142")
        self.assertNotIn("10122", self._alt_n(plural))

    def test_his_seed_is_noun_and_verb(self):
        # 22:7 ዘርኡ. Глагол ዘርአ n=7547 строит 3 мн., имя ዘርእ n=7550 — суффикс -u.
        # В гл. 10 то же написание оставлено именем. Здесь обе статьи, не auto.
        rec = self._rec("ዘርኡ")
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(self._n(rec))
        self.assertEqual(self._alt_n(rec), {"7547", "7550"})

    def test_ya_does_not_take_a_participle_of_another_sibilant(self):
        # 69:5 ያማስኑ. Статья n=1880 — part. II,2 መሠንይ, не эта форма.
        rec = self._rec("ያማስኑ")
        self.assertNotEqual(rec["status"], "auto")
        self.assertNotEqual(self._n(rec), "1880")

    def test_kullu_stays_its_own_article(self):
        # ኵሉ n=5982 — заголовок «ኵል с суффиксом», не форма пустого построения.
        rec = self._rec("ኵሉ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "5982")


class Stage3bClusters(unittest.TestCase):
    """Кластеры проверки этапа 3. Словарь — DillmannData проекта."""

    @classmethod
    def setUpClass(cls):
        cls.lex = enoch_tag.LexIndex.load(enoch_tag.LEXICON)

    def _rec(self, word):
        return enoch_tag.analyze(word, (41, 1), self.lex)

    def _n(self, rec):
        for seg in rec["segs"]:
            eid = seg.get("lemma")
            if eid:
                return str(self.lex.items[eid].get("n"))
        return None

    def _alt_n(self, rec):
        return {str(self.lex.items[eid].get("n")) for eid in rec["alts"]}

    def test_emne_suffix_is_emmena_not_the_particle(self):
        # n=4758 только в እስከኔ и አሐተኔ. እምኔ-+суффикс — እምነ n=1400.
        for word in ("እምኔሆሙ", "ወእምኔሆሙ", "እምኔክሙ", "እምኔሃ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "1400", word)
        rec = self._rec("እምኔሆሙ")
        self.assertEqual([seg["t"] for seg in rec["segs"]], ["እምኔ", "ሆሙ"])
        host = self._rec("እስከኔ")
        self.assertEqual(host["status"], "auto")
        self.assertEqual(self._n(host), "5573")
        particle = self._rec("አሐተኔ")
        self.assertEqual(particle["status"], "auto")
        self.assertEqual(self._n(particle), "4758")
        self.assertEqual([seg["t"] for seg in particle["segs"]], ["አሐተ", "ኔ"])

    def test_walda_is_the_accusative_not_a_letter(self):
        # ወልደ — винительный/сопряжённый ወልድ n=6436, не буква ደ n=7792.
        rec = self._rec("ወልደ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "6436")
        self.assertEqual([seg["t"] for seg in rec["segs"]], ["ወልደ"])
        self.assertNotIn("7792", self._alt_n(rec))

    def test_one_letter_article_is_not_a_lemma(self):
        rec = self._rec("ለሐ")
        self.assertNotEqual(rec["status"], "auto")
        self.assertIsNone(self._n(rec))
        self.assertNotIn("493", self._alt_n(rec))

    def test_abu_with_suffix_is_father(self):
        for word in ("አቡከ", "አቡሁ", "ለአቡሁ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "5601", word)
            self.assertNotEqual(self._n(rec), "5634", word)
        bare = self._rec("አቡ")
        self.assertEqual(bare["status"], "auto")
        self.assertEqual(self._n(bare), "5634")

    def test_bo_is_exists_and_heart_is_not_haba(self):
        for word in ("ቦ", "ወቦ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "3741", word)
            self.assertNotIn("4534", self._alt_n(rec))
        heart = self._rec("ልቦ")
        self.assertEqual(heart["status"], "auto")
        self.assertEqual(self._n(heart), "289")
        self.assertNotEqual(self._n(heart), "4534")

    def test_short_noun_beats_the_rare_long_form(self):
        for word in ("ወልቦሙ", "ወልብክሙ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "289", word)
            self.assertTrue(any(seg.get("prefix") == "c" for seg in rec["segs"]))
        self.assertEqual(self._n(self._rec("ሞትነ")), "1472")
        self.assertEqual(self._n(self._rec("ብዕልክሙ")), "4068")
        self.assertEqual(self._n(self._rec("ኮንክሙ")), "6290")
        self.assertEqual(self._n(self._rec("ነፍሶ")), "5324")
        self.assertEqual(self._n(self._rec("ርእሳ")), "2230")

    def test_both_real_readings_stay_unsure(self):
        pairs = (
            ("ሞትክሙ", {"1475", "1472"}),
            ("ነፍስነ", {"5324", "5320"}),
            ("ወልዳ", {"10211", "6436"}),
            ("ወገብሮ", {"8420", "8428"}),
            ("ወፈርሁ", {"6894", "9884"}),
            ("ገብርዋ", {"8420", "8428"}),
        )
        for word, expected in pairs:
            rec = self._rec(word)
            self.assertEqual(rec["status"], "unsure", word)
            self.assertIsNone(self._n(rec), word)
            self.assertTrue(expected <= self._alt_n(rec), word)

    def test_same_head_homonyms_are_not_chosen_silently(self):
        rec = self._rec("ወጽኡ")
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(self._n(rec))
        self.assertTrue({"6864", "6870"} <= self._alt_n(rec))
        bare = self._rec("ወጽአ")
        self.assertEqual(bare["status"], "unsure")
        self.assertTrue({"6864", "6870"} <= self._alt_n(bare))
        days = self._rec("መዋዕል")
        self.assertEqual(days["status"], "auto")
        self.assertEqual(self._n(days), "6716")
        lomu = self._rec("ሎሙ")
        self.assertEqual(lomu["status"], "auto")
        self.assertEqual(self._n(lomu), "144")

    def test_s_spelling_of_stem_three_is_unsure(self):
        # 104:13 ሠ. Статья n=7083 пишет ስ и не ссылается на этот стих.
        for word in ("ይትዐሠዩ", "ወይትዐሠዩ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "unsure", word)
            self.assertIsNone(self._n(rec), word)
            self.assertIn("7083", self._alt_n(rec), word)
        for word in ("ትትሐጐል", "ይትሐጐሉ"):
            rec = self._rec(word)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "118", word)

    def test_wayezeni_keeps_conjunction_and_enclitic(self):
        # n=7767 печатает ወይእዜኒ целиком. ወ и ኒ всё равно отдельные.
        rec = self._rec("ወይእዜኒ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual([seg["t"] for seg in rec["segs"]], ["ወ", "ይእዜ", "ኒ"])
        self.assertEqual(self._n(rec), "7767")
        ni = rec["segs"][-1].get("lemma")
        self.assertEqual(str(self.lex.items[ni].get("n")), "4756")

    def test_whose_at_22_6_is_not_silently_time(self):
        # Hen. 22,6 ዘመኑ цитирует መኑ n=1365 «чей». ዘመን n=7520 тоже пишет ዘመኑ.
        rec = enoch_tag.analyze("ዘመኑ", (22, 6), self.lex)
        self.assertEqual(rec["status"], "unsure")
        self.assertIsNone(self._n(rec))
        self.assertTrue({"1365", "7520"} <= self._alt_n(rec))

    def test_sunrise_homonym_does_not_claim_the_imperfect(self):
        # n=1777 «nectere» формы ይሠርቅ не печатает. Сонет оставил n=1768.
        rec = self._rec("ይሠርቅ")
        self.assertEqual(rec["status"], "auto")
        self.assertEqual(self._n(rec), "1768")
        self.assertNotIn("1777", self._alt_n(rec))


class MengelPrepositionTest(unittest.TestCase):
    """መንገለ — предлог n=5185, не radix inusitata n=5184 и не отсылка n=1410."""

    @classmethod
    def setUpClass(cls):
        cls.lex = enoch_tag.LexIndex.load(enoch_tag.LEXICON)

    def _n(self, rec):
        for seg in rec["segs"]:
            eid = seg.get("lemma")
            if eid:
                return str(self.lex.items[eid].get("n"))
        return None

    def _alt_n(self, rec):
        return {str(self.lex.items[eid].get("n")) for eid in rec["alts"]}

    def test_mengel_is_preposition_5185(self):
        words = (
            "መንገለ",
            "ዘመንገለ",
            "ወመንገለ",
            "በመንገለ",
            "ለመንገለ",
            "ወዘመንገለ",
            "ወኢመንገለ",
            "፫መንገለ",
            "ወ፫መንገለ",
            "፩ወ፫መንገለ",
        )
        for word in words:
            rec = enoch_tag.analyze(word, (24, 2), self.lex)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "5185", word)
            self.assertEqual(rec["segs"][-1]["t"], "መንገለ", word)
            self.assertNotIn("5184", self._alt_n(rec), word)
            self.assertNotIn("1410", self._alt_n(rec), word)
            self.assertEqual(rec["gram"], "предлог", word)
        za = enoch_tag.analyze("ዘመንገለ", (24, 2), self.lex)
        self.assertEqual([seg["t"] for seg in za["segs"]], ["ዘ", "መንገለ"])
        self.assertEqual(za["segs"][0]["prefix"], "s")
        num = enoch_tag.analyze("ወ፫መንገለ", (18, 6), self.lex)
        self.assertEqual([seg["t"] for seg in num["segs"]], ["ወ", "፫", "መንገለ"])
        self.assertEqual(num["segs"][0]["prefix"], "c")
        both = enoch_tag.analyze("፩ወ፫መንገለ", (24, 2), self.lex)
        self.assertEqual([seg["t"] for seg in both["segs"]], ["፩ወ፫", "መንገለ"])

    def test_printed_mengel_forms_stay_5185(self):
        for word in ("እመንገለ", "መነገለ", "መንገሌሁ", "መንገል"):
            rec = enoch_tag.analyze(word, (24, 2), self.lex)
            self.assertEqual(rec["status"], "auto", word)
            self.assertEqual(self._n(rec), "5185", word)

    def test_other_letter_is_not_pulled_off_an_unused_root(self):
        # አምዐ и አምዕዐ — разная огласовка и разный состав. Правило መንገለ их не склеивает.
        pointer = entry("Lp", "አምዐ", n="9001")
        pointer["senses"] = [{"text": "vid. sub መዐዐ፡"}]
        unused = entry("Lu", "መዐዐ", n="9002")
        unused["senses"] = [{"text": "rad. inus. quae non adhibetur."}]
        other = entry("Lo", "አምዕዐ", n="9003", pos=["subst."], forms=["አምዕዐ", "አምዐ"])
        other["senses"] = [{"text": "subst. alia vox."}]
        lex = enoch_tag.LexIndex({"Lp": pointer, "Lu": unused, "Lo": other})
        rec = enoch_tag.analyze("አምዐ", None, lex)
        self.assertNotEqual(self._n_of(rec, lex), "9003")

    def _n_of(self, rec, lex):
        for seg in rec["segs"]:
            eid = seg.get("lemma")
            if eid:
                return str(lex.items[eid].get("n"))
        return None

    def test_checked_word_survives_a_later_tag(self):
        old = {
            "status": "checked",
            "segs": [
                {"t": "መንገለ", "lemma": "OLD", "prefix": None, "morph": None},
            ],
            "gram": "предлог",
            "alts": [],
            "note": "Проверено по Дильману: መንገል n=5185.",
        }
        new = {
            "status": "auto",
            "segs": [
                {"t": "መንገለ", "lemma": "NEW", "prefix": None, "morph": None},
            ],
            "gram": "предлог",
            "alts": [],
            "note": "",
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "017.json"
            path.write_text(
                json.dumps({"chapter": 17, "words": {"e1": old}}, ensure_ascii=False),
                encoding="utf-8",
            )
            data, kept = enoch_tag._keep_manual_words(
                path, {"chapter": 17, "words": {"e1": new}}
            )
        self.assertEqual(kept, 1)
        self.assertEqual(data["words"]["e1"]["status"], "checked")
        self.assertEqual(data["words"]["e1"]["segs"][0]["lemma"], "OLD")


if __name__ == "__main__":
    unittest.main()
