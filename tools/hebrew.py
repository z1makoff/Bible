"""Механическая транслитерация огласованного масоретского написания.

Это передача того, что записано буквами и значками, а не реконструкция древнего
произношения. Известные ограничения: камец хатуф без отдельного знака даётся как ā;
звучащий или немой шва определяется упрощённым правилом.
"""
import re
import unicodedata

CONSONANTS = {
    "א": "ʾ", "ב": "v", "ג": "g", "ד": "d", "ה": "h", "ו": "w", "ז": "z", "ח": "ḥ",
    "ט": "ṭ", "י": "y", "כ": "kh", "ך": "kh", "ל": "l", "מ": "m", "ם": "m", "נ": "n",
    "ן": "n", "ס": "s", "ע": "ʿ", "פ": "f", "ף": "f", "צ": "ṣ", "ץ": "ṣ", "ק": "q",
    "ר": "r", "ש": "š", "ת": "t",
}
HARD = {"ב": "b", "כ": "k", "ך": "k", "פ": "p", "ף": "p"}

SHEVA, HATAF_E, HATAF_A, HATAF_O = "ְ", "ֱ", "ֲ", "ֳ"
HIRIQ, TSERE, SEGOL, PATAH, QAMATS = "ִ", "ֵ", "ֶ", "ַ", "ָ"
HOLEM, HOLEM_VAV, QUBUTS, QAMATS_QATAN = "ֹ", "ֺ", "ֻ", "ׇ"
DAGESH, SHIN_DOT, SIN_DOT = "ּ", "ׁ", "ׂ"

VOWELS = {
    HATAF_E: "ĕ", HATAF_A: "ă", HATAF_O: "ŏ", HIRIQ: "i", TSERE: "ē", SEGOL: "e",
    PATAH: "a", QAMATS: "ā", HOLEM: "ō", HOLEM_VAV: "ō", QUBUTS: "u", QAMATS_QATAN: "o",
}
LONG = {"ā", "ē", "ō", "î", "û", "ê", "ô"}
KEEP = set(VOWELS) | {SHEVA, DAGESH, SHIN_DOT, SIN_DOT}


def clusters(word):
    """Список [буква, набор значков, начало сегмента] без кантилляции."""
    out, seg_start = [], True
    for ch in unicodedata.normalize("NFC", word):
        if ch == "/":
            seg_start = True
        elif "א" <= ch <= "ת":
            out.append([ch, set(), seg_start])
            seg_start = False
        elif ch in KEEP and out:
            out[-1][1].add(ch)
    return out


def vowel_of(marks):
    found = [VOWELS[m] for m in sorted(marks) if m in VOWELS]  # sorted: набор значков без порядка
    if len(found) > 1 and "i" in found:
        # Только ירושלם: хирек рядом с патахом или камецом — огласовка чтения yərûšālayim
        # с невписанным йодом.
        return next(v for v in found if v != "i") + "yi"
    return found[0] if found else ""


def translit(word):
    cl = clusters(word)
    parts = []  # (текст, гласная) по кластерам
    for i, (ch, marks, seg_start) in enumerate(cl):
        prev = cl[i - 1] if i else None
        nxt = cl[i + 1] if i + 1 < len(cl) else None
        last = nxt is None
        prev_vowel = parts[-1][1] if parts else ""
        v = vowel_of(marks)

        # Матери чтения: буква не даёт согласного, а удлиняет предыдущую гласную.
        if ch == "י" and not v and DAGESH not in marks and SHEVA not in marks and prev_vowel in ("i", "ē", "e"):
            parts[-1] = (parts[-1][0][:-1] + {"i": "î", "ē": "ê", "e": "ê"}[prev_vowel], "î")
            continue
        if ch == "ו" and prev is not None and not prev_vowel and not seg_start:
            if HOLEM in marks and not (marks - {HOLEM}):
                parts[-1] = (parts[-1][0] + "ô", "ô")
                continue
            if DAGESH in marks and not v and SHEVA not in marks:
                parts[-1] = (parts[-1][0] + "û", "û")
                continue
        if ch == "ו" and (prev is None or seg_start) and DAGESH in marks and not v:
            parts.append(("û", "û"))
            continue
        if ch == "ה" and last and not v and DAGESH not in marks and prev_vowel:
            parts.append(("h", ""))
            continue

        if ch == "ש":
            cons = "ś" if SIN_DOT in marks else "š"
        elif DAGESH in marks and ch in HARD:
            cons = HARD[ch]
        else:
            cons = CONSONANTS[ch]

        doubled = DAGESH in marks and bool(prev_vowel) and not (ch == "ה" and last)
        if doubled:
            cons = cons + cons if len(cons) == 1 else cons[0] + cons

        if SHEVA in marks:
            vocal = (i == 0 or seg_start or doubled or prev_vowel in LONG
                     or (prev is not None and SHEVA in prev[1]))
            vocal = vocal and not last
            v = "ə" if vocal else ""

        if last and v == "a" and ch in ("ח", "ע", "ה") and prev_vowel:
            parts.append(("a" + cons, ""))  # патах вороватый: произносится перед буквой
            continue
        sep = "-" if seg_start and parts else ""
        parts.append((sep + cons + v, v))
    return "".join(p[0] for p in parts)


def strip_marks(word):
    """Только буквы без огласовки и кантилляции, для сравнения написаний."""
    return re.sub(r"[^א-ת]", "", word)
