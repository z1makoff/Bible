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


if __name__ == "__main__":
    unittest.main()
