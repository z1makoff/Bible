"""Тесты механической транслитерации (tools/hebrew.py).

Запуск: python -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hebrew  # noqa: E402


class TranslitTest(unittest.TestCase):
    def test_simple_word(self):
        self.assertEqual(hebrew.translit("בְּרֵאשִׁ֖ית"), "bərēʾšît")

    def test_jerusalem_two_vowels_under_lamed(self):
        # Хирек вместе с патахом или камецом — всегда одна и та же форма,
        # а не случайная из двух (набор значков не хранит порядок).
        self.assertEqual(hebrew.translit("יְרוּשָׁלִַ֖ם"), "yərûšālayim")
        self.assertEqual(hebrew.translit("בִּירוּשָׁלִָֽם"), "bîrûšālāyim")

    def test_qamats_and_holem_on_one_letter(self):
        self.assertEqual(hebrew.vowel_of({hebrew.HOLEM, hebrew.QAMATS}), "ā")


if __name__ == "__main__":
    unittest.main()
