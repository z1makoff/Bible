"""Механическая транслитерация эфиопского письма (геэз).

Передаётся то, что написано слогами, а не произношение. Одна таблица рядов
(ROW) задаёт и точную форму (tr), и простую (lat). Простая форма — предварительное
правило, его ещё не утвердили: ǝ→e, ā→a, без ʾ и ʿ, ḥ→h, ḫ→kh, ś→s, ṣ→ts, ḍ→ts,
ṭ→t, ṗ→p. Ряды, которых в этом правиле не было (š, č, ñ…), стоят в той же таблице
и помечены provisional.

Шестой ряд внутри слова даёт ǝ. Только шестой ряд в самом конце слова пишется
без гласного. Удвоение согласных письмо без отдельного знака не показывает:
если знака геминации в тексте нет, согласный не удваивается.
"""
import unicodedata

# (точная согласная, простая согласная, provisional).
# Простая форма берётся отсюда же, отдельного списка замен нет.
# provisional=True — ряда не было в предварительном правиле простой формы.
ROW = {
    "H": ("h", "h", False),
    "L": ("l", "l", False),
    "HH": ("ḥ", "h", False),
    "M": ("m", "m", False),
    "SZ": ("ś", "s", False),
    "R": ("r", "r", False),
    "S": ("s", "s", False),
    "SH": ("š", "sh", True),
    "Q": ("q", "q", False),
    "QH": ("q́", "q", True),
    "B": ("b", "b", False),
    "V": ("v", "v", True),
    "T": ("t", "t", False),
    "C": ("č", "ch", True),
    "X": ("ḫ", "kh", False),
    "N": ("n", "n", False),
    "NY": ("ñ", "ny", True),
    "GLOTTAL": ("ʾ", "", False),
    "K": ("k", "k", False),
    "KX": ("ḵ", "kh", True),
    "W": ("w", "w", False),
    "PHARYNGEAL": ("ʿ", "", False),
    "Z": ("z", "z", False),
    "ZH": ("ž", "zh", True),
    "Y": ("y", "y", False),
    "D": ("d", "d", False),
    "DD": ("ḏ", "d", True),
    "J": ("ǧ", "j", True),
    "G": ("g", "g", False),
    "GG": ("ǵ", "g", True),
    "TH": ("ṭ", "t", False),
    "CH": ("č̣", "ch", True),
    "PH": ("ṗ", "p", False),
    "TS": ("ṣ", "ts", False),  # ጸ
    "TZ": ("ḍ", "ts", False),  # ፀ
    "F": ("f", "f", False),
    "P": ("p", "p", False),
}

# Окончание имени Unicode → (гласная точная, гласная простая, шестой ряд).
VOWEL = {
    "A": ("a", "a", False),
    "U": ("u", "u", False),
    "I": ("i", "i", False),
    "AA": ("ā", "a", False),
    "EE": ("e", "e", False),
    "E": ("ǝ", "e", True),
    "O": ("o", "o", False),
    "WA": ("ʷa", "wa", False),
    "WI": ("ʷi", "wi", False),
    "WAA": ("ʷā", "wa", False),
    "WEE": ("ʷe", "we", False),
    "WE": ("ʷǝ", "we", True),
    "OA": ("oa", "oa", False),  # редкий слог (ሇ и др.), не шестой ряд
    "YA": ("ya", "ya", False),  # ፘ ፙ ፚ, не обычный ряд
}

# Дольше — раньше, чтобы HH не разобралось как H, TS как T.
_STEMS = sorted(ROW, key=len, reverse=True)
_VOWELS = sorted(VOWEL, key=len, reverse=True)

GEMINATION = "፟"  # U+135F, если знак реально стоит в тексте
VOWEL_LENGTH = "፞"
GEM_AND_LENGTH = "፝"

# Цифры геэза не позиционные: десятки и ፻/፼ — отдельные знаки.
NUMBER = {
    "፩": 1, "፪": 2, "፫": 3, "፬": 4, "፭": 5, "፮": 6, "፯": 7, "፰": 8, "፱": 9,
    "፲": 10, "፳": 20, "፴": 30, "፵": 40, "፶": 50, "፷": 60, "፸": 70, "፹": 80, "፺": 90,
    "፻": 100, "፼": 10000,
}

# Знаки, которые отделяют слова, а сами словом не являются.
SEPARATORS = set("፠፡።፣፤፥፦፧፨") | set(" \t\r\n")


def _parse_name(name):
    # «GLOTTAL A» пишется с пробелом, «HA» — без. Пробел к гласной не относится.
    rest = name.removeprefix("ETHIOPIC SYLLABLE ").strip()
    stem = next((s for s in _STEMS if rest.startswith(s)), None)
    if stem is None:
        raise KeyError(name)
    vow = rest[len(stem):].strip()
    if vow not in VOWEL:
        raise KeyError(name)
    return stem, vow


# char → (cons_tr, vowel_tr, cons_lat, vowel_lat, sixth, provisional)
SYLLABLE = {}
for _cp in range(0x1200, 0x135B):
    _ch = chr(_cp)
    _name = unicodedata.name(_ch, "")
    if not _name.startswith("ETHIOPIC SYLLABLE"):
        continue
    _stem, _vow = _parse_name(_name)
    _tr, _lat, _prov = ROW[_stem]
    _vtr, _vlat, _sixth = VOWEL[_vow]
    if _vow == "YA":
        # Палатальный редкий знак: согласная + ya, без отдельной гласной ряда.
        SYLLABLE[_ch] = (_tr + "y", "a", _lat + "y", "a", False, True)
    else:
        # Лабиализация ʷ входит в согласную, гласная — остаток.
        if _vtr.startswith("ʷ"):
            SYLLABLE[_ch] = (_tr + "ʷ", _vtr[1:], _lat + "w", _vlat[1:], _sixth, _prov)
        else:
            SYLLABLE[_ch] = (_tr, _vtr, _lat, _vlat, _sixth, _prov)


def ethiopic_number(chars):
    """Значение последовательности цифр геэза. ፻ и ፼ — множители."""
    total, current = 0, 0
    for ch in chars:
        value = NUMBER[ch]
        if value == 10000:
            current = (current or 1) * 10000
            total += current
            current = 0
        elif value == 100:
            current = (current or 1) * 100
        else:
            current += value
    return total + current


def _apply_mark(cons, mark):
    """Знак геминации удваивает одну записанную согласную. Без знака — не удваиваем."""
    if mark not in (GEMINATION, GEM_AND_LENGTH):
        return cons
    if len(cons) == 1:
        return cons + cons
    return cons  # ʾ, š, ts: знак есть, но удвоение неоднозначно — не выдумываем вторую букву


def transliterate(word):
    """(tr, lat) для одного слова. Цифры в начале — их значение, дальше слоги."""
    chars = list(unicodedata.normalize("NFC", word))
    i = 0
    num = []
    while i < len(chars) and chars[i] in NUMBER:
        num.append(chars[i])
        i += 1
    syllables = []  # (cons_tr, vow_tr, cons_lat, vow_lat, sixth)
    while i < len(chars):
        ch = chars[i]
        if ch in SEPARATORS or unicodedata.category(ch).startswith("M") and ch not in (
            GEMINATION, VOWEL_LENGTH, GEM_AND_LENGTH
        ):
            i += 1
            continue
        if ch not in SYLLABLE:
            if ch in NUMBER:
                # Цифра в середине слова остаётся отдельным числом в транслитерации.
                j = i
                mid = []
                while j < len(chars) and chars[j] in NUMBER:
                    mid.append(chars[j])
                    j += 1
                value = str(ethiopic_number(mid))
                syllables.append((value, "", value, "", False))
                i = j
                continue
            raise ValueError(f"нет в таблице эфиопского письма: {ch} U+{ord(ch):04X} в «{word}»")
        cons, vow, cons_lat, vow_lat, sixth, _prov = SYLLABLE[ch]
        mark = ""
        if i + 1 < len(chars) and chars[i + 1] in (GEMINATION, VOWEL_LENGTH, GEM_AND_LENGTH):
            mark = chars[i + 1]
            i += 1
        syllables.append((_apply_mark(cons, mark), vow, _apply_mark(cons_lat, mark), vow_lat, sixth))
        i += 1
    if syllables and syllables[-1][4]:
        cons, _vow, cons_lat, _vow_lat, _sixth = syllables[-1]
        syllables[-1] = (cons, "", cons_lat, "", False)
    prefix = ""
    if num:
        prefix = str(ethiopic_number(num))
    tr = prefix + "".join(c + v for c, v, _cl, _vl, _s in syllables)
    lat = prefix + "".join(c + v for _c, _v, c, v, _s in syllables)
    return tr, lat


def skeleton(word):
    """Согласные слогов, без гласных и без цифр. Для поиска корня, не для чтения."""
    out = []
    for ch in unicodedata.normalize("NFC", word):
        if ch in SYLLABLE:
            out.append(SYLLABLE[ch][0])
    return "".join(out)


# Омофоны для поиска кандидата. Точное написание в тексте не меняется.
# Совпадение только через эту свёртку — не доказательство леммы.
_FOLD_CONS = {
    "h": "h",
    "ḥ": "h",
    "ḫ": "h",
    "s": "s",
    "ś": "s",
    "ʾ": "ʾ",
    "ʿ": "ʾ",
    "ṣ": "ṣ",
    "ḍ": "ṣ",
}
# Краткие лабиовелярные (wa, wi, wǝ) в рукописях путаются: ኲሉ при заголовке ኵሉ.
# Долгие wā и we не склеиваются.
_SHORT_LABIO = {"a", "i", "ǝ"}


def _fold_parts(word):
    """Список (согласная после омофонов, гласная). Лабиовелярный краткий гласный — «ʷ»."""
    parts = []
    for ch in unicodedata.normalize("NFC", word):
        if ch not in SYLLABLE:
            continue
        cons, vow = SYLLABLE[ch][0], SYLLABLE[ch][1]
        labio = cons.endswith("ʷ")
        base = cons[:-1] if labio else cons
        base = _FOLD_CONS.get(base, base)
        if labio and vow in _SHORT_LABIO:
            vow = "ʷ"
        elif labio:
            vow = "ʷ" + vow
        parts.append((base, vow))
    return parts


def fold_form(word):
    """Форма для поиска омофона: согласные свёрнуты, гласные на месте.
    Краткие лабиовелярные одного согласного совпадают."""
    return "".join(base + vow for base, vow in _fold_parts(word))


def fold_skeleton(word):
    """Согласные после омофонов, через точку. Гласные сняты, лабиовелярность остаётся."""
    return ".".join(base + ("ʷ" if vow.startswith("ʷ") else "") for base, vow in _fold_parts(word))
