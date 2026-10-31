"""Черновик разметки 1 Еноха по словарю Дильмана.

auto — одна нарезка и одна статья. Сюда входит точное написание заголовка,
напечатанная форма и форма, построенная от заголовка (сильный перфект, класс
субъюнктива, имя). Омофон и напечатанная парадигма (Imperf./Subj. и их лица)
остаются unsure. Совпадение только через омофон — тоже unsure. Ссылка Дильмана
на стих сама по себе лемму не выбирает. Отсылка «vid. sub» не становится леммой.

Файл morph/enoch/NNN.json, в котором есть status кроме auto, не перезаписывается
без --force. Ручная разметка глав 1–11 этим прогоном не затирается.
"""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import geez

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "enoch" / "1En"
LEXICON = ROOT / "corpus" / "geez-lexemes.json"
MORPH = ROOT / "morph" / "enoch"

# Длиннее — раньше. Цепочка: wa-, затем предлог, kama- или отрицание, затем za-.
# ከመ и ኢ снимаются только если остаток есть в словаре (см. exact_hits).
PREFS = (
    ("ከመ", "k"),
    ("እመ", "m"),
    ("እም", "m"),
    ("ወ", "c"),
    ("በ", "b"),
    ("ብ", "b"),
    ("ለ", "l"),
    ("ል", "l"),
    ("ዘ", "s"),
    ("ኢ", "i"),
    ("እ", "i"),
)
# (поверхность, morph, двусмысленно). Двусмысленное не даёт auto.
# ሳ и ሰ — одна частица n=2428, код Enc-ssa. Оба написания не дают auto:
# ሳ ещё сверять, ሰ легко принять за часть основы.
SUFFIXES = (
    ("ክሙ", "S2mp", False),
    ("ሆሙ", "S3mp", False),
    ("ኦሙ", "S3mp", False),
    ("ክን", "S2fp", False),
    ("ሆን", "S3fp", False),
    ("ኦን", "S3fp", False),
    ("ከ", "S2ms", False),
    ("ኪ", "S2fs", False),
    ("ሁ", "S3ms", False),
    ("ሃ", "S3fs", False),
    ("ነ", "S1cp", False),
    ("ኒ", "S1cs", True),
    ("የ", "S1cs", True),
    ("ሂ", "Enc-hi", False),
    ("ሳ", "Enc-ssa", True),
    ("ሣ", "Enc-ssa", False),
    ("ሰ", "Enc-ssa", True),
)
# Эти окончания режутся только в запасном поиске и только если основа уже известна.
# Морф ታ и ሎ не назван: роль окончания не установлена.
EXTRA_SUFFIXES = (
    ("ሙ", "S3mp", True),
    ("ዋ", "S3fs", True),
    ("ዎ", "S3ms", True),
    ("ታ", None, True),
    ("ሎ", None, True),
)
AFTER = {
    None: {"c", "b", "l", "m", "k", "s", "i"},
    "c": {"b", "l", "m", "k", "s", "i"},
    "b": {"s"},
    "l": {"s"},
    "m": {"s"},
    "k": {"s"},
    "s": {"i"},
    "i": {"b", "l", "m", "s"},
}
PERSON_TOKENS = {"y", "t", "ʾ", "n"}
SKEL_CAP = 8
SKEL_SLACK = 4

REF_RE = re.compile(r"1En\.(\d+)\.(\d+)")
LABEL_RE = re.compile(r"(?:Imperf|Subj|Imperat|Infin|Perf)\.")
GEEZ_RE = re.compile(r"[\u1200-\u137F]+")
VID_RE = re.compile(r"vid\.\s+(?:sub\s+)?([\u1200-\u135F]+)")
CITE_RE = re.compile(
    r"\b(?:Hen|Gen|Ex|Lev|Num|Deut|Jos|Jud|Reg|Ps|Matth|Marc|Luc|Joh|Act|"
    r"Rom|Sir|Job|Jes|Hez|Dan|Kuf|Cant|Apoc|Eph|Cor|Gal|Petr|Tim|Jac|Hebr|"
    r"Tob|Ruth|Esth|Par|Esdr|Esr|Chrys|Clem|Herm|Plat|Platt|Sx|Prov|Jsp|"
    r"Sam|Jer|Thren|Bar|Mac|Sap)\b|§|caet\."
)

# (согласная, гласная) → слог. Первое совпадение.
BY_CV = {}
for _ch, _info in geez.SYLLABLE.items():
    BY_CV.setdefault((_info[0], _info[1]), _ch)


def syllables(text):
    return sum(1 for ch in text if ch in geez.SYLLABLE)


def is_single(text):
    if not text:
        return False
    if any(ch in text for ch in "፡።፣፤፥ ") or any(ch.isspace() for ch in text):
        return False
    return any("\u1200" <= ch <= "\u137F" for ch in text)


def is_number(text):
    return bool(text) and all(ch in geez.NUMBER for ch in text)


def ordered_subset(needle, hay):
    pos = 0
    for ch in needle:
        found = hay.find(ch, pos)
        if found < 0:
            return False
        pos = found + 1
    return True


def _syllable_chars(word):
    return [ch for ch in word if ch in geez.SYLLABLE]


def _with_vowel(ch, vow):
    cons = geez.SYLLABLE[ch][0]
    return BY_CV.get((cons, vow))


def _with_cons(ch, cons):
    vow = geez.SYLLABLE[ch][1]
    return BY_CV.get((cons, vow))


# «III,3» в поле stem само по себе не глагол: у ሚካኤል n=10309 это номер
# списка святых «III,3,5», а разбор положил в stem кусок «III,3».
_CLASS_TOKEN = re.compile(r"(?<![A-Za-z])(?:I{1,3}|IV),\d+(?!\s*,\s*\d)")
_PARADIGM_HEAD = re.compile(r"(?:Imperf|Subj|Imperat)\.\s*[\u1200-\u137F]")


def is_verb(item):
    """Глагол — по пометке или по заголовку класса в тексте статьи.

    Поле stem вида III,3 само глагола не доказывает.
    """
    pos = [label.lower() for label in (item.get("pos") or [])]
    if any(label.startswith("v.") or label == "v" or "verb" in label for label in pos):
        return True
    senses = item.get("senses") or []
    blob = " ".join((sense.get("text") or "") for sense in senses[:2])
    if not _CLASS_TOKEN.search(blob[:500]):
        return False
    joined = " ".join(pos)
    nominal = any(
        key in joined
        for key in ("subst", "adj", "praep", "conj", "adv", "pron", "n. pr", "n. ag", "n. act")
    )
    verbal_label = any(label.startswith(("subj", "imperf", "imperat", "infin")) for label in pos)
    has_paradigm = bool(_PARADIGM_HEAD.search(blob[:800]))
    if re.search(r"(?:n\.\s*ag|n\.\s*act|part\.)\s*\(", blob[:240]) and not has_paradigm:
        return False
    if nominal and not verbal_label and not has_paradigm:
        return False
    return True


def coarse_gram(item):
    labels = []
    if is_verb(item):
        labels.append("глагол")
    head = item.get("head") or ""
    if head.endswith("ኤል") or head.endswith("ያል"):
        if "имя" not in labels and not is_verb(item):
            labels.append("имя")
    for label in item.get("pos") or []:
        low = label.lower()
        if "n. pr" in low or "n.pr" in low:
            labels.append("имя собственное")
        elif "subst" in low or low.startswith("n.") or low.startswith("n "):
            labels.append("имя")
        elif "adj" in low:
            labels.append("прилагательное")
        elif "praep" in low or "prep" in low:
            labels.append("предлог")
        elif "conj" in low:
            labels.append("союз")
        elif "adv" in low:
            labels.append("наречие")
        elif "pron" in low:
            labels.append("местоимение")
        elif low.startswith("partic"):
            labels.append("частица")
        elif low.startswith("part"):
            labels.append("причастие")
        elif low.startswith("v.") or low == "v" or "verb" in low:
            labels.append("глагол")
        elif "num" in low:
            labels.append("числительное")
        elif "interj" in low:
            labels.append("междометие")
    out = []
    for label in labels:
        if label not in out:
            out.append(label)
    if len(out) == 1:
        return out[0]
    return None


def _related(item, stem):
    """Корень статьи читается в согласных остатка. Иначе это чужое слово в статье."""
    head_skel = item.get("skeleton") or geez.skeleton(item.get("head") or "")
    stem_skel = geez.skeleton(stem)
    if len(head_skel) < 2 or not stem_skel:
        return False
    if not ordered_subset(head_skel, stem_skel):
        return False
    return len(stem_skel) - len(head_skel) <= SKEL_SLACK


# Между двумя формами Дильман ставит et / vel / raro. Это не глосса и не отсылка.
_FORM_CONNECTOR = {
    "et", "vel", "aut", "sive", "seu", "raro", "rarius", "item", "etiam",
    "quoque", "saepe", "nonnisi", "interdum", "passim", "aliter", "alias", "atque",
}
# c. Subj., c.c. Acc. Infin., seq. Subj. — управление, не форма.
_GOV_BEFORE = re.compile(r"(?:(?:c\.c\.|c\.|seq\.|Acc\.)\s*)+(?:Acc\.\s*)?$")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


def _window_tokens(window):
    """Слова геэза из окна, пока не началась отсылка. Для vice Perfecti и т.п."""
    cut = CITE_RE.split(window, maxsplit=1)[0]
    out = []
    for raw in GEEZ_RE.findall(cut):
        tok = raw.strip("፡።፣፤፥፦፧፨፠ ")
        if syllables(tok) >= 2 and is_single(tok):
            out.append(tok)
    return out


def _forms_after_label(window):
    """Геэз сразу за меткой, до двоеточия, отсылки или латинского слова.

    Скобки, в которых сразу стоит геэз, ещё форма (ይኩን፡ (ይኵን፡ passim)).
    Латинский союз между двумя формами (et, vel, raro) глоссой не считается.
    """
    forms = []
    i = 0
    n = len(window)
    while i < n:
        ch = window[i]
        if ch in " \t\r\n፡።፣፤፥፦፧፨፠,;":
            i += 1
            continue
        if ch == ":":
            break
        if ch == "(":
            rest = window[i + 1:]
            if re.match(r"\s*[\u1200-\u135F]", rest):
                i += 1
                continue
            break
        if "\u1200" <= ch <= "\u135F":
            j = i + 1
            while j < n and "\u1200" <= window[j] <= "\u135F":
                j += 1
            tok = window[i:j]
            if syllables(tok) >= 2 and is_single(tok):
                forms.append(tok)
            i = j
            continue
        match = _LATIN_WORD.match(window, i)
        if match:
            if match.group(0).lower() in _FORM_CONNECTOR:
                i = match.end()
                continue
            break
        break
    return forms


def _labeled_forms(text):
    """Формы, напечатанные сразу за Imperf./Subj./Imperat./Infin./Perf.

    Метка управления (c. Subj., seq. Subj., c.c. Acc. Infin.) формы не даёт.
    Дальше цитаты в окно не входят: их отсекает двоеточие, отсылка или латынь.
    """
    found = []
    for match in LABEL_RE.finditer(text):
        prev = text[max(0, match.start() - 48):match.start()]
        if _GOV_BEFORE.search(prev):
            continue
        label = match.group(0)[:-1]
        for tok in _forms_after_label(text[match.end():match.end() + 160]):
            found.append((tok, label))
    return found


def _clause_tokens(text, anchor):
    match = re.search(anchor, text)
    if not match:
        return []
    chunk = text[match.end():]
    semi = chunk.find(";")
    if semi >= 0:
        chunk = chunk[:semi]
    return _window_tokens(chunk[:240])


def expand_imperfect(form):
    """Лица от напечатанного 3 л. ед. муж. имперфекта или субъюнктива.

    Приставка ይ/የ меняется на ት, እ, ን с тем же гласным. Множественное -u и
    2 л. жен. -i только если последний слог шестого ряда. Форма на гласный
    (ይሬኢ) множественного не получает. Окончание -ā не порождается.
    """
    chars = _syllable_chars(form)
    if not chars or chars[0] not in ("ይ", "የ"):
        return []
    if geez.SYLLABLE[chars[0]][0] != "y":
        return []
    out = []
    for cons in ("t", "ʾ", "n"):
        first = _with_cons(chars[0], cons)
        if first:
            out.append(first + "".join(chars[1:]))
    last = chars[-1]
    if not geez.SYLLABLE[last][4]:
        return out
    for cons, vow in (("y", "u"), ("t", "u"), ("t", "i")):
        first = _with_cons(chars[0], cons)
        end = _with_vowel(last, vow)
        if first and end:
            out.append(first + "".join(chars[1:-1]) + end)
    return out


def expand_imperative(form):
    """Множественное императива от формы шестого ряда: ሀብ → ሀቡ."""
    chars = _syllable_chars(form)
    if not chars or not geez.SYLLABLE[chars[-1]][4]:
        return []
    end = _with_vowel(chars[-1], "u")
    if not end:
        return []
    return ["".join(chars[:-1]) + end]


def expand_iii_y(head):
    """Слабый перфект на -የ: ርእየት, ርእዩ, ርኢኩ и остальные лица с ኢ перед окончанием."""
    chars = _syllable_chars(head)
    if len(chars) < 2 or chars[-1] != "የ":
        return []
    out = []
    fem = head + "ት"
    if is_single(fem):
        out.append(fem)
    plural = "".join(chars[:-1]) + "ዩ"
    if is_single(plural):
        out.append(plural)
    prev = _with_vowel(chars[-2], "i")
    if not prev:
        return out
    stem = "".join(chars[:-2]) + prev
    for suf in ("ከ", "ኪ", "ኩ", "ክሙ", "ክን", "ነ"):
        form = stem + suf
        if is_single(form):
            out.append(form)
    return out


def _ends_with_suffix(word):
    for surf, _morph, _amb in SUFFIXES + EXTRA_SUFFIXES:
        if word.endswith(surf) and len(word) > len(surf):
            return True
    return False


# Согласные после омофонов. w/y и гортанные в корне могут выпасть.
_CONS_FOLD = {
    "h": "h", "ḥ": "h", "ḫ": "h",
    "s": "s", "ś": "s",
    "ʾ": "ʾ", "ʿ": "ʾ",
    "ṣ": "ṣ", "ḍ": "ṣ",
}
_OPTIONAL_CONS = {"w", "y", "ʾ", "h"}
_GUTTURAL = {"ʾ", "ʿ", "h", "ḥ", "ḫ"}
# Приставки лица и породные, которые снимаются до сравнения с корнем.
_ROOT_PREFIXES = ("አስተ", "ያ", "የ", "ይ", "ት", "እ", "ን", "ተ")
# Окончания сильного перфекта. -a — это сам заголовок 3 л. ед. муж.
_PERF_CONSONANT = ("ኩ", "ከ", "ኪ", "ክሙ", "ክን", "ነ")
# Суффиксы объекта. -o/-ā меняют гласный последнего слога, -wo/-wā пишутся ዎ/ዋ.
_OBJECT_VOWEL = (("o", ""), ("ā", ""), ("o", "ሙ"), ("o", "ን"))
_OBJECT_W = ("ዎ", "ዋ", "ዎሙ", "ዎን")


def _cons_of(word):
    out = []
    for ch in word:
        if ch not in geez.SYLLABLE:
            continue
        cons = geez.SYLLABLE[ch][0]
        if cons.endswith("ʷ"):
            cons = cons[:-1]
        out.append(_CONS_FOLD.get(cons, cons))
    return out


def _strip_root_prefix(word):
    """Снимает цепочку ይ ት እ ን ያ የ አስተ ተ с начала формы."""
    changed = True
    while changed and syllables(word) >= 2:
        changed = False
        for pref in _ROOT_PREFIXES:
            if word.startswith(pref) and len(word) > len(pref):
                word = word[len(pref):]
                changed = True
                break
    return word


def _form_has_root(head, form):
    """В форме есть согласные корня заголовка.

    Слабые w/y и гортанные могут отсутствовать. Лишние согласные окончания
    не мешают. Чужое слово из цитаты сюда не проходит.
    """
    head_cons = _cons_of(head)
    if not head_cons:
        return False
    form_cons = _cons_of(_strip_root_prefix(form))
    if not form_cons:
        return False
    pos = 0
    for cons in head_cons:
        start = pos
        found = False
        while pos < len(form_cons):
            if form_cons[pos] == cons:
                pos += 1
                found = True
                break
            pos += 1
        if found:
            continue
        if cons not in _OPTIONAL_CONS:
            return False
        # Слабой согласной в форме нет. Уже прочитанные слоты не съедаем.
        pos = start
    return True


def _syls(word):
    return [ch for ch in word if ch in geez.SYLLABLE]


def _swap_last(word, vow, extra=""):
    chars = _syls(word)
    if not chars:
        return None
    last = _with_vowel(chars[-1], vow)
    if not last:
        return None
    return "".join(chars[:-1]) + last + extra


def _as_sixth(ch):
    return _with_vowel(ch, "ǝ")


def _join(chars):
    return "".join(chars)


def _perfect_bases(head):
    """Сильный перфект от заголовка: тип ቀተለ и тип ገብረ.

    Перед согласным окончанием у ገብረ второй гласный становится a: ገበርኩ.
    У ቀተለ второй гласный остаётся, последний слог — шестой ряд: ቀተልኩ.
    """
    chars = _syls(head)
    if len(chars) < 2 or geez.SYLLABLE[chars[-1]][1] != "a":
        return []
    out = []
    last_u = _with_vowel(chars[-1], "u")
    if last_u:
        out.append(_join(chars[:-1]) + last_u)
    out.append(head + "ት")
    pen = chars[-2]
    pen_sixth = geez.SYLLABLE[pen][4]
    last_sixth = _as_sixth(chars[-1])
    if not last_sixth:
        return out
    if pen_sixth:
        pen_a = _with_vowel(pen, "a")
        if not pen_a:
            return out
        base = _join(chars[:-2]) + pen_a + last_sixth
    else:
        base = _join(chars[:-1]) + last_sixth
    for suf in _PERF_CONSONANT:
        out.append(base + suf)
    return out


def _object_forms(form):
    """Суффиксы объекта -o -wo -ā -wā -omu -womu -on -won на готовой форме."""
    chars = _syls(form)
    if not chars:
        return []
    vow = geez.SYLLABLE[chars[-1]][1]
    out = []
    if vow == "a":
        for new_vow, extra in _OBJECT_VOWEL:
            built = _swap_last(form, new_vow, extra)
            if built:
                out.append(built)
        sixth = _as_sixth(chars[-1])
        if sixth:
            stem = _join(chars[:-1]) + sixth
            for suf in _OBJECT_W:
                out.append(stem + suf)
    elif vow == "u":
        sixth = _as_sixth(chars[-1])
        if sixth:
            stem = _join(chars[:-1]) + sixth
            for suf in _OBJECT_W:
                out.append(stem + suf)
    elif geez.SYLLABLE[chars[-1]][4]:
        for new_vow, extra in _OBJECT_VOWEL:
            built = _swap_last(form, new_vow, extra)
            if built:
                out.append(built)
        for suf in _OBJECT_W:
            out.append(form + suf)
    return out


def _subj_third(chars):
    """3 л. ед. муж. субъюнктива от слогов заголовка. None, если класса нет.

    Правила сняты с напечатанных Subj. статей Дильмана, не с памяти:
    сильный ቀተለ → ይቅትል, ገብረ → ይግበር; первая w выпадает (ወለደ → ይለድ);
    полый o → ይቁም, полый o с конечной гортанной (ቦአ) → ይባእ, полый e → ይሂድ;
    конечная гортанная при шестом ряде второго → ይብላዕ; конечное y типа a-a → ይስሚ.
    """
    if len(chars) < 2:
        return None
    cons = []
    for ch in chars:
        raw = geez.SYLLABLE[ch][0]
        if raw.endswith("ʷ"):
            raw = raw[:-1]
        cons.append(_CONS_FOLD.get(raw, raw))
    person = "ይ"

    def syl(ch, vow):
        return _with_vowel(ch, vow)

    if len(chars) == 2:
        first_vow = geez.SYLLABLE[chars[0]][1]
        final_gutt = cons[-1] in {"ʾ", "h"}
        if first_vow == "o":
            if final_gutt:
                a_long = syl(chars[0], "ā")
                last = _as_sixth(chars[1])
                if a_long and last:
                    return person + a_long + last
            mid = syl(chars[0], "u")
            last = _as_sixth(chars[1])
            if mid and last:
                return person + mid + last
        if first_vow == "e":
            mid = syl(chars[0], "i")
            last = _as_sixth(chars[1])
            if mid and last:
                return person + mid + last
        return None
    if len(chars) != 3:
        return None
    first_w = cons[0] == "w"
    final_y = cons[-1] == "y"
    final_gutt = cons[-1] in {"ʾ", "h"}
    pen_sixth = geez.SYLLABLE[chars[1]][4]
    if first_w and not final_y:
        # Выпадение первой w. Глаголы, которые её держат, отсекаются снаружи.
        mid = syl(chars[1], "a")
        last = _as_sixth(chars[2])
        if mid and last:
            return person + mid + last
        return None
    if final_y and not pen_sixth and not first_w:
        first = _as_sixth(chars[0])
        mid = syl(chars[1], "i")
        if first and mid:
            return person + first + mid
        return None
    if final_gutt and pen_sixth and not first_w:
        first = _as_sixth(chars[0])
        mid = syl(chars[1], "ā")
        last = _as_sixth(chars[2])
        if first and mid and last:
            return person + first + mid + last
        return None
    if pen_sixth:
        first = _as_sixth(chars[0])
        mid = syl(chars[1], "a")
        last = _as_sixth(chars[2])
        if first and mid and last:
            return person + first + mid + last
        return None
    first = _as_sixth(chars[0])
    mid = _as_sixth(chars[1])
    last = _as_sixth(chars[2])
    if first and mid and last:
        return person + first + mid + last
    return None


def _printed_subj_keeps_w(labeled):
    for form, label in labeled:
        if label not in ("Subj", "Imperf"):
            continue
        core = _strip_root_prefix(form)
        folded = _cons_of(core)
        if folded and folded[0] == "w":
            return True
    return False


def build_verb_forms(item, labeled):
    """Формы, построенные от заголовка. Точное совпадение может быть auto.

    Объектные суффиксы только у 3 л. ед. муж., 3 л. мн. (-u), 1 л. ед. (-ኩ)
    и у 3 л. ед. муж. субъюнктива. Напечатанный субъюнктив, который держит
    первую w, запрещает выпадение: у ወሰደ статья печатает ይውስድ, и ይሰድ отсюда
    не строится.
    """
    if not is_verb(item):
        return []
    head = item.get("head") or ""
    chars = _syls(head)
    out = []
    u_form = ""
    ku_form = ""
    u_mark = ""
    if chars:
        last_u = _with_vowel(chars[-1], "u")
        if last_u:
            u_mark = _join(chars[:-1]) + last_u
    for form in _perfect_bases(head):
        out.append(form)
        if u_mark and form == u_mark:
            u_form = form
        if form.endswith("ኩ") and not ku_form:
            ku_form = form
    out.extend(_object_forms(head))
    if u_form:
        out.extend(_object_forms(u_form))
    if ku_form:
        out.extend(_object_forms(ku_form))
    subj = _subj_third(chars)
    if not subj:
        return out
    dropped = _cons_of(_strip_root_prefix(subj))
    head_cons = _cons_of(head)
    dropped_w = bool(head_cons and head_cons[0] == "w" and (not dropped or dropped[0] != "w"))
    if _printed_subj_keeps_w(labeled) and dropped_w:
        return out
    out.extend([subj] + expand_imperfect(subj))
    out.extend(_object_forms(subj))
    return out


# Служебные слова. Точный список — то, что статья печатает отдельным словом.
# «per ê … caet.» достраивает остальные лица, но ненапечатанное лицо — unsure.
_FUNCTION_HEADS = {
    "ለ", "በ", "ላዕለ", "ምስለ", "ኀበ", "እምነ", "ውስተ", "መንገለ", "መንገል",
    "ታሕተ", "ቅድመ", "ዲበ", "ድኅረ", "ማእከለ",
}
# Для ለ и በ парадигма напечатана списком, а не через ê. Чужие цитаты не собираем.
_FUNCTION_LIST = {
    "ለ": ("ሊተ", "ለከ", "ለኪ", "ሎቱ", "ላቲ", "ለነ", "ለክሙ", "ለክን", "ሎሙ", "ሎን", "ሎንቱ", "ሎንቶን", "ሎቶን"),
    "በ": ("ብየ", "ቢየ", "ብነ", "ብከ", "ብኪ", "ብክሙ", "ብክን", "ቦ", "ቦቱ", "ባ", "ባቲ", "ቦሙ", "ቦን", "ቦቶን", "ቦንቱ"),
}
_FUNCTION_E = {
    "ላዕለ": ("ላዕሌ",),
    "ምስለ": ("ምስሌ",),
    "ኀበ": ("ኀቤ",),
    "እምነ": ("እምኔ", "እምኖ"),
    "ቅድመ": ("ቅድሜ",),
    "ዲበ": ("ዲቤ",),
    "ድኅረ": ("ድኅሬ",),
    "መንገል": ("መንገሌ",),
    "መንገለ": ("መንገሌ",),
    "ታሕተ": ("ታሕቴ",),
    "ውስተ": ("ውስቴት",),
    "ማእከለ": ("ማእከሌ", "ማእከሎ", "ማእከላ"),
}
_FUNCTION_PRON = ("የ", "ከ", "ኪ", "ሁ", "ሃ", "ነ", "ክሙ", "ክን", "ሆሙ", "ሆን")
_FUNCTION_STRIP = ("እም", "ወ", "በ", "ለ")


def _article_text(item):
    return "\n".join((sense.get("text") or "") for sense in (item.get("senses") or []))


def _geez_words(text):
    """Слова геэза. ፡ внутри пробега regex не склеивает их в одно слово."""
    words = []
    for raw in GEEZ_RE.findall(text or ""):
        for part in re.split(r"[፡።፣፤፥፦፧፨፠]+", raw):
            tok = part.strip()
            if tok and is_single(tok):
                words.append(tok)
    return words


def _article_tokens(item):
    tokens = _geez_words(_article_text(item))
    for form in item.get("forms") or []:
        tokens.extend(_geez_words(form))
    return tokens


def _strip_function_prefix(token, bases):
    """Снимает እም/ወ/በ/ለ только если остаток всё ещё начинается с основы служебного."""
    rest = token
    changed = True
    while changed and len(rest) > 2:
        changed = False
        for pref in _FUNCTION_STRIP:
            if not rest.startswith(pref) or len(rest) <= len(pref) + 1:
                continue
            nxt = rest[len(pref):]
            if any(nxt.startswith(base) for base in bases):
                rest = nxt
                changed = True
                break
    return rest


def _pointer_item(item):
    """Статья-отсылка «vid. sub». Ей не принадлежат формы цели."""
    senses = item.get("senses") or []
    if not senses:
        return False
    for sense in senses:
        text = (sense.get("text") or "").strip()
        if not text or len(text) > 120 or not VID_RE.search(text):
            return False
    return True


def function_forms(item):
    """(напечатанные формы, формы по правилу ê, которых в статье нет)."""
    head = item.get("head") or ""
    if head not in _FUNCTION_HEADS or _pointer_item(item):
        return [], []
    tokens = set(_article_tokens(item))
    exact = []
    unsure = []
    for form in _FUNCTION_LIST.get(head, ()):
        if form in tokens:
            exact.append(form)
    bases = _FUNCTION_E.get(head, ())
    if not bases:
        return exact, unsure
    seen_exact = set(exact)
    for tok in tokens:
        core = _strip_function_prefix(tok, bases)
        if any(core.startswith(base) and len(core) > len(base) for base in bases):
            if core not in seen_exact and syllables(core) >= 2:
                seen_exact.add(core)
                exact.append(core)
    if head == "ውስተ":
        # Статья даёт ውስቴት и примеры, но не таблицу всех лиц. Недописанное не строим.
        return exact, unsure
    blob = _article_text(item)
    # Парадигму ê достраиваем только у статьи, которая про местоименные суффиксы.
    if not exact and not re.search(r"suff|pron\.|per ê|vocalis ê", blob, re.I):
        return exact, unsure
    for base in bases:
        if head == "እምነ" and base == "እምኖ":
            continue
        for suf in _FUNCTION_PRON:
            form = base + suf
            if form in seen_exact or form in tokens:
                continue
            unsure.append(form)
    return exact, unsure


def _plural_tokens(item):
    found = []
    for match in re.finditer(r"Pl\.\s*([\u1200-\u137F]+)", _article_text(item)):
        tok = match.group(1).strip("፡")
        if is_single(tok) and syllables(tok) >= 2 and tok not in found:
            found.append(tok)
    return found


def _nominal_article(item):
    if is_verb(item):
        return False
    head = item.get("head") or ""
    if head in _FUNCTION_HEADS:
        return False
    for label in item.get("pos") or []:
        low = label.lower()
        if low.startswith("pron") or "praep" in low or "prep" in low:
            continue
        if low.startswith("conj") or low.startswith("adv") or low.startswith("v."):
            continue
        if "subst" in low or "adj" in low or "part." in low or "n. pr" in low:
            return True
        if low.startswith("n.") or low == "n":
            return True
    return bool(_plural_tokens(item))


def build_noun_forms(item):
    """Множественное -ān -āt -t, сопряжённая и винительный -a, суффиксы.

    Ломаное множественное берётся только из напечатанного Pl. Обычное
    окончание строится от заголовка, он и есть основа в статье.
    """
    if not _nominal_article(item):
        return []
    head = item.get("head") or ""
    if not head or not is_single(head):
        return []
    bases = [head]
    for plural in _plural_tokens(item):
        if plural not in bases:
            bases.append(plural)
    out = []
    for base in bases:
        chars = _syls(base)
        if not chars:
            continue
        if geez.SYLLABLE[chars[-1]][1] != "a":
            built = _swap_last(base, "a")
            if built:
                out.append(built)
        if base == head:
            an = _swap_last(head, "ā", "ን")
            at = _swap_last(head, "ā", "ት")
            if an:
                out.append(an)
            if at:
                out.append(at)
            if not head.endswith("ት"):
                out.append(head + "ት")
        omu = _swap_last(base, "o", "ሙ")
        ihomu = _swap_last(base, "i", "ሆሙ")
        ihu = _swap_last(base, "i", "ሁ")
        for form in (omu, ihomu, ihu):
            if form:
                out.append(form)
    return out


def collect_paradigm(item):
    """Формы парадигмы одной статьи. Не каждая цитата геэза внутри статьи."""
    if not is_verb(item):
        return []
    forms = []  # (surface, how)
    seen = set()
    head = item.get("head") or ""

    def add(form, how):
        if not form or form in seen or not is_single(form) or syllables(form) < 2:
            return
        if head and not _form_has_root(head, form):
            return
        seen.add(form)
        forms.append((form, how))

    texts = [sense.get("text") or "" for sense in (item.get("senses") or [])]
    for text in texts:
        for form, label in _labeled_forms(text):
            add(form, label)
            if label in ("Imperf", "Subj"):
                for extra in expand_imperfect(form):
                    add(extra, label)
            elif label == "Imperat":
                for extra in expand_imperative(form):
                    add(extra, label)
        for form in _clause_tokens(text, r"vice Perfecti"):
            add(form, "vice")
        for form in _clause_tokens(text, r"resumitur:"):
            add(form, "resum")
    head = item.get("head") or ""
    if head.endswith("የ"):
        for form in expand_iii_y(head):
            add(form, "iii-y")
    for form in item.get("forms") or []:
        if not is_single(form) or syllables(form) < 2 or syllables(form) > 5:
            continue
        if not form.startswith(("ይ", "የ")) or _ends_with_suffix(form):
            continue
        if not _related(item, form):
            continue
        add(form, "listed")
        for extra in expand_imperfect(form):
            add(extra, "listed")
    return forms


def pointer_targets(lex, eid):
    """Заголовок статьи-отсылки «vid. sub …». None, если это настоящая статья."""
    item = lex.items.get(eid) or {}
    senses = item.get("senses") or []
    if not senses:
        return None
    heads = []
    for sense in senses:
        text = (sense.get("text") or "").strip()
        if not text:
            continue
        if len(text) > 120:
            return None
        match = VID_RE.search(text)
        if not match:
            return None
        heads.append(match.group(1).strip("፡"))
    if not heads:
        return None
    ids = []
    for head in heads:
        for tid in lex.by_head.get(head, []):
            if tid not in ids:
                ids.append(tid)
    return ids


class LexIndex:
    def __init__(self, items):
        self.items = items
        self.by_head = {}
        self.by_form = {}
        self.by_skel = {}
        self.by_fold_head = {}
        self.by_fold_form = {}
        self.by_fold_skel = {}
        self.paradigm = {}
        self.built = {}
        self.built_fold = {}
        self.func_unsure = {}
        self.cite = {}
        self.verbal = set()
        self.by_n = {}
        for eid, item in items.items():
            number = str(item.get("n") or "")
            if number and number not in self.by_n:
                self.by_n[number] = eid
            elif number:
                self.by_n[number] = None
            head = item.get("head") or ""
            if is_single(head):
                self.by_head.setdefault(head, []).append(eid)
                skel = item.get("skeleton") or geez.skeleton(head)
                if skel:
                    self.by_skel.setdefault(skel, []).append(eid)
                folded = geez.fold_form(head)
                if folded:
                    self.by_fold_head.setdefault(folded, []).append(eid)
                fskel = geez.fold_skeleton(head)
                if fskel:
                    self.by_fold_skel.setdefault(fskel, []).append(eid)
            for form in item.get("forms") or []:
                if is_single(form) and _related(item, form):
                    bucket = self.by_form.setdefault(form, [])
                    if eid not in bucket:
                        bucket.append(eid)
                    folded = geez.fold_form(form)
                    fold_bucket = self.by_fold_form.setdefault(folded, [])
                    if eid not in fold_bucket:
                        fold_bucket.append(eid)
            for form, _how in collect_paradigm(item):
                bucket = self.paradigm.setdefault(form, [])
                if eid not in bucket:
                    bucket.append(eid)
            labeled = []
            for sense in item.get("senses") or []:
                labeled.extend(_labeled_forms(sense.get("text") or ""))
            for form in build_verb_forms(item, labeled):
                self._add_built(eid, form)
            for form in build_noun_forms(item):
                self._add_built(eid, form)
            exact_fn, unsure_fn = function_forms(item)
            for form in exact_fn:
                self._add_listed(eid, form)
            for form in unsure_fn:
                if is_single(form) and syllables(form) >= 2:
                    bucket = self.func_unsure.setdefault(form, [])
                    if eid not in bucket:
                        bucket.append(eid)
            for ref in item.get("enoch") or []:
                match = REF_RE.fullmatch(ref)
                if match:
                    key = (int(match.group(1)), int(match.group(2)))
                    self.cite.setdefault(key, set()).add(eid)
            if is_verb(item):
                self.verbal.add(eid)
        for bucket in (
            self.by_head, self.by_form, self.by_skel, self.by_fold_head,
            self.by_fold_form, self.by_fold_skel, self.paradigm, self.built,
            self.built_fold, self.func_unsure,
        ):
            for key in bucket:
                bucket[key] = sorted(set(bucket[key]))

    def _add_built(self, eid, form):
        if not form or not is_single(form) or syllables(form) < 2:
            return
        head = (self.items.get(eid) or {}).get("head") or ""
        if form == head:
            return
        bucket = self.built.setdefault(form, [])
        if eid not in bucket:
            bucket.append(eid)
        folded = geez.fold_form(form)
        if not folded:
            return
        fold_bucket = self.built_fold.setdefault(folded, [])
        if eid not in fold_bucket:
            fold_bucket.append(eid)

    def _add_listed(self, eid, form):
        if not form or not is_single(form) or syllables(form) < 2:
            return
        bucket = self.by_form.setdefault(form, [])
        if eid not in bucket:
            bucket.append(eid)
        folded = geez.fold_form(form)
        if not folded:
            return
        fold_bucket = self.by_fold_form.setdefault(folded, [])
        if eid not in fold_bucket:
            fold_bucket.append(eid)

    @classmethod
    def load(cls, path):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(raw)


def chains(text, allow_k):
    found = []

    def walk(pieces, rest, prev):
        found.append((pieces, rest))
        for surf, code in PREFS:
            if code not in AFTER[prev]:
                continue
            if code == "k" and not allow_k:
                continue
            if rest.startswith(surf) and len(rest) > len(surf):
                nxt = rest[len(surf):]
                # እ- как отрицание только в написании እይ-.
                if surf == "እ" and not nxt.startswith("ይ"):
                    continue
                walk(pieces + ((surf, code),), nxt, code)

    walk((), text, None)
    return found


def _hit(pieces, stem, suf, lemmas, kind, ambiguous, suf_lemma=None):
    return {
        "pieces": pieces,
        "stem": stem,
        "suf": suf,
        "lemmas": list(lemmas),
        "kind": kind,
        "ambiguous": ambiguous,
        "sufLemma": suf_lemma,
    }


def form_related(eid, stem, lex):
    return _related(lex.items.get(eid) or {}, stem)


def _needs_known_stem(pieces):
    for surf, code in pieces:
        if code == "k" or (code == "i" and surf == "ኢ"):
            return True
    return False


def _stem_options(rest, suffixes):
    options = [(rest, None, False)]
    for surf, morph, ambiguous in suffixes:
        if not rest.endswith(surf) or len(rest) <= len(surf):
            continue
        stem = rest[: -len(surf)]
        if len(surf) == 1 and syllables(stem) < 2:
            continue
        if syllables(stem) < 1:
            continue
        options.append((stem, (surf, morph), ambiguous))
    return options


def _positively_nominal(lex, eid):
    """Имя или частица, а не глагол и не статья без части речи."""
    if eid in lex.verbal:
        return False
    targets = pointer_targets(lex, eid)
    if targets is not None:
        if any(tid in lex.verbal for tid in targets):
            return False
        if not targets:
            return False
    item = lex.items.get(eid) or {}
    if is_verb(item):
        return False
    labels = item.get("pos") or []
    if not labels:
        return False
    for label in labels:
        low = label.lower()
        if low.startswith("v.") or low == "v" or "verb" in low:
            return False
        if low.startswith("subj") or low.startswith("imperf") or low.startswith("imperat"):
            return False
    return True


def _ni_fields(lex, lemmas):
    """ኒ: на глаголе S1cs и n=4755; на имени Enc-ni и n=4756. Иначе не решаю."""
    if not lemmas:
        return None
    if all(_positively_nominal(lex, eid) for eid in lemmas):
        return ("Enc-ni", False, lex.by_n.get("4756"))
    verbal = any(eid in lex.verbal for eid in lemmas)
    if not verbal:
        for eid in lemmas:
            targets = pointer_targets(lex, eid)
            if targets and any(tid in lex.verbal for tid in targets):
                verbal = True
                break
    if verbal:
        return ("S1cs", True, lex.by_n.get("4755"))
    return ("S1cs", True, None)


def _apply_particle(hit, lex):
    if not hit["suf"]:
        return hit
    surf, morph = hit["suf"]
    if surf == "ኒ":
        fields = _ni_fields(lex, hit["lemmas"])
        if fields is None:
            return None
        code, ambiguous, suf_lemma = fields
        hit["suf"] = (surf, code)
        # Решение рецензента сильнее пометки «ኒ двусмысленно» в общем списке.
        hit["ambiguous"] = ambiguous
        hit["sufLemma"] = suf_lemma
    elif morph == "Enc-ssa":
        hit["ambiguous"] = True
        hit["sufLemma"] = lex.by_n.get("2428")
    return hit


def _form_lemmas(lex, stem):
    """Статьи, у которых эта поверхность — напечатанная форма, а не чужая цитата."""
    lemmas = []
    for eid in lex.by_form.get(stem, []):
        item = lex.items.get(eid) or {}
        head = item.get("head") or ""
        if head in _FUNCTION_HEADS or form_related(eid, stem, lex):
            if eid not in lemmas:
                lemmas.append(eid)
    return lemmas


def _stem_known(lex, stem):
    return stem in lex.by_head or stem in lex.by_form or stem in lex.built


def exact_hits(text, lex):
    """Точные написания. Заглавное слово важнее процитированной формы.

    Построенная форма, которая совпала с чужим заголовком, auto не даёт.
    """
    if text in lex.by_head:
        heads = lex.by_head[text]
        extra = [eid for eid in lex.built.get(text, []) if eid not in heads]
        if extra:
            return [
                _hit((), text, None, heads, "head", True),
                _hit((), text, None, extra, "built", True),
            ]
        return [_hit((), text, None, heads, "head", False)]
    found = []
    for pieces, rest in chains(text, allow_k=True):
        for stem, suf, ambiguous in _stem_options(rest, SUFFIXES):
            if _needs_known_stem(pieces) and not _stem_known(lex, stem):
                continue
            hits = []
            if stem in lex.by_head:
                hit = _hit(pieces, stem, suf, lex.by_head[stem], "head", ambiguous)
                extra = [eid for eid in lex.built.get(stem, []) if eid not in lex.by_head[stem]]
                if extra:
                    hit["ambiguous"] = True
                    hits.append(hit)
                    hits.append(_hit(pieces, stem, suf, extra, "built", True))
                else:
                    hits.append(hit)
            else:
                built = [eid for eid in lex.built.get(stem, [])]
                listed = _form_lemmas(lex, stem)
                if built:
                    amb = ambiguous or len(built) != 1
                    hits.append(_hit(pieces, stem, suf, built, "built", amb))
                extra = [eid for eid in listed if eid not in built]
                if extra:
                    hits.append(_hit(pieces, stem, suf, extra, "form", ambiguous or len(extra) != 1))
                elif listed and not built:
                    hits.append(_hit(pieces, stem, suf, listed, "form", ambiguous))
            for hit in hits:
                hit = _apply_particle(hit, lex)
                if hit is not None:
                    found.append(hit)
    # Процитированная форма в статье («forms») без приставок не бьёт нарезку на приставку
    # и известное заглавное слово: ለእለ — ለ + እለ, а не ለለ.
    split_known = any(
        pieces and rest in lex.by_head
        for pieces, rest in chains(text, allow_k=True)
    )
    if split_known:
        for hit in found:
            if hit["kind"] == "form" and not hit["pieces"]:
                hit["ambiguous"] = True
    return _merge_same_cut(found)


def _known_loose(lex, stem):
    """Основа известна не по точному написанию: парадигма, ê или омофон."""
    if stem in lex.paradigm:
        return lex.paradigm[stem], "paradigm"
    if stem in lex.func_unsure:
        return lex.func_unsure[stem], "func"
    folded = geez.fold_form(stem)
    if stem not in lex.by_head and stem not in lex.built and folded in lex.by_fold_head:
        return lex.by_fold_head[folded], "homophone"
    if stem not in lex.by_form and stem not in lex.built and folded in lex.by_fold_form:
        lemmas = []
        for eid in lex.by_fold_form[folded]:
            if eid not in lemmas:
                lemmas.append(eid)
        if lemmas:
            return lemmas, "homophone"
    if stem not in lex.built and folded in getattr(lex, "built_fold", {}):
        lemmas = []
        for eid in lex.built_fold[folded]:
            if eid not in lemmas:
                lemmas.append(eid)
        if lemmas:
            return lemmas, "homophone"
    return None


def loose_hits(text, lex):
    """Омофон, парадигма и редкое окончание. Сюда попадаем, только если точного нет."""
    found = []
    for pieces, rest in chains(text, allow_k=True):
        options = _stem_options(rest, SUFFIXES)
        for stem, suf, _amb in _stem_options(rest, EXTRA_SUFFIXES):
            if suf is not None:
                options.append((stem, suf, True))
        for stem, suf, ambiguous in options:
            known = _known_loose(lex, stem)
            if known is None and suf is not None and stem in lex.by_head:
                # Окончание -ሙ/-ዋ/-ዎ/-ታ/-ሎ только при уже известной основе.
                if suf[0] in {item[0] for item in EXTRA_SUFFIXES}:
                    known = (lex.by_head[stem], "suffix")
            if known is None and suf is not None and stem in lex.by_form:
                if suf[0] in {item[0] for item in EXTRA_SUFFIXES}:
                    lemmas = _form_lemmas(lex, stem)
                    if lemmas:
                        known = (lemmas, "suffix")
            if known is None:
                continue
            if _needs_known_stem(pieces) and known is None:
                continue
            lemmas, kind = known
            hit = _hit(pieces, stem, suf, lemmas, kind, True)
            hit = _apply_particle(hit, lex)
            if hit is not None:
                hit["ambiguous"] = True
                found.append(hit)
    return found


def _merge_same_cut(hits):
    """Одна нарезка и один набор лемм — один hit. Список форм и построенная форма не спорят."""
    order = {"head": 0, "built": 1, "form": 2}
    grouped = {}
    out = []
    for hit in hits:
        key = (hit["pieces"], hit["stem"], hit["suf"], tuple(hit["lemmas"]))
        prev = grouped.get(key)
        if prev is None:
            grouped[key] = hit
            out.append(hit)
            continue
        if order.get(hit["kind"], 9) < order.get(prev["kind"], 9):
            prev["kind"] = hit["kind"]
        prev["ambiguous"] = prev["ambiguous"] or hit["ambiguous"]
        if hit.get("sufLemma") and not prev.get("sufLemma"):
            prev["sufLemma"] = hit["sufLemma"]
    return out


def _prefer_confident(hits):
    """Короткая приставка выигрывает у лишней. Заголовок выигрывает у построенной формы.

    Две статьи на одной глубине не прячутся: иначе auto взял бы одну из них молча.
    Более глубокая нарезка отбрасывается, только если на малой глубине статья одна.
    """
    confident = [hit for hit in hits if not hit["ambiguous"]]
    if len(confident) <= 1:
        return hits
    heads = [hit for hit in confident if hit["kind"] == "head"]
    pool = heads or confident
    best_depth = min(len(hit["pieces"]) for hit in pool)
    shallow = [hit for hit in pool if len(hit["pieces"]) == best_depth]
    deeper = any(len(hit["pieces"]) > best_depth for hit in confident)
    hidden = len(pool) != len(confident)
    if len(shallow) == 1 and len(shallow[0]["lemmas"]) == 1 and (deeper or hidden):
        weak = [hit for hit in hits if hit["ambiguous"]]
        return shallow + weak
    return hits


def _blocks_auto(chosen, weak):
    """Слабый hit на той же или меньшей глубине не даёт auto. Более глубокий — нет."""
    depth = len(chosen["pieces"])
    return any(len(hit["pieces"]) <= depth for hit in weak)


def _dedupe(hits):
    seen = set()
    out = []
    for hit in hits:
        key = (
            hit["pieces"],
            hit["stem"],
            hit["suf"],
            tuple(hit["lemmas"]),
            hit["kind"],
            hit["ambiguous"],
            hit.get("sufLemma"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


def _fold_tokens(word):
    skel = geez.fold_skeleton(word)
    return [part for part in skel.split(".") if part]


def _token_subset(needle, hay):
    pos = 0
    for tok in needle:
        if pos >= len(hay):
            return False
        try:
            found = hay.index(tok, pos)
        except ValueError:
            return False
        pos = found + 1
    return True


def skeleton_alts(text, verse, lex):
    """Согласные после омофонов. Не для auto и не как выбранная лемма.

    Возвращает ещё нарезку приставок: леммы нет, но ወ/ለ/በ уже отделены.
    Берётся самая короткая цепочка, у которой остаток совпал по согласным.
    Если совпадения нет, остаётся одна первая приставка, не самая длинная.
    """
    equal = []
    weaker = []
    best = None
    for pieces, rest in chains(text, allow_k=True):
        stems = [rest]
        for surf, _morph, _amb in SUFFIXES:
            if rest.endswith(surf) and len(rest) > len(surf):
                stem = rest[: -len(surf)]
                if syllables(stem) >= 1 and not (len(surf) == 1 and syllables(stem) < 2):
                    stems.append(stem)
        matched_equal = False
        matched_weak = False
        for stem in stems:
            parts = _fold_tokens(stem)
            if not parts:
                continue
            here = lex.by_fold_skel.get(".".join(parts), [])
            if here:
                matched_equal = True
                equal.extend(here)
            elif parts[0] in PERSON_TOKENS and len(parts) >= 3:
                key = ".".join(parts[1:])
                for eid in lex.by_fold_skel.get(key, []):
                    if eid in lex.verbal:
                        matched_weak = True
                        weaker.append(eid)
        if matched_equal:
            rank = 0
        elif matched_weak:
            rank = 1
        elif pieces and syllables(rest) >= 2:
            rank = 2
        else:
            continue
        cand = (rank, len(pieces))
        if best is None or cand < best[0]:
            best = (cand, pieces, rest)
    pool = equal or weaker
    word_parts = _fold_tokens(text)
    cited_ok = []
    for eid in sorted(lex.cite.get(verse, ())):
        head = (lex.items.get(eid) or {}).get("head") or ""
        head_parts = _fold_tokens(head)
        if len(head_parts) < 2 or not word_parts:
            continue
        if not _token_subset(head_parts, word_parts):
            continue
        if len(word_parts) - len(head_parts) > SKEL_SLACK:
            continue
        cited_ok.append(eid)
    non = sorted(set(pool) - set(cited_ok))
    alts = []
    for eid in cited_ok + non[:SKEL_CAP]:
        if eid not in alts:
            alts.append(eid)
    if best and best[1]:
        return alts, len(non), bool(equal), cited_ok, best[1], best[2]
    return alts, len(non), bool(equal), cited_ok, (), ""


def _segs(text, hit, lemma):
    if hit is None:
        return [{"t": text, "lemma": None, "prefix": None, "morph": None}]
    segs = []
    for surf, code in hit["pieces"]:
        segs.append({"t": surf, "lemma": None, "prefix": code, "morph": None})
    segs.append({"t": hit["stem"], "lemma": lemma, "prefix": None, "morph": None})
    if hit["suf"]:
        segs.append({
            "t": hit["suf"][0],
            "lemma": hit.get("sufLemma"),
            "prefix": None,
            "morph": hit["suf"][1],
        })
    if "".join(seg["t"] for seg in segs) != text:
        return [{"t": text, "lemma": None, "prefix": None, "morph": None}]
    return segs


def _names(lex, ids):
    parts = []
    for eid in ids:
        item = lex.items.get(eid) or {}
        head = item.get("head") or "?"
        number = item.get("n")
        parts.append(f"{head} n={number}" if number else head)
    return ", ".join(parts)


def _cited(lex, verse, ids):
    bag = lex.cite.get(verse, set())
    return [eid for eid in ids if eid in bag]


def _unwrap(lex, ids):
    """Отсылка «vid. sub» уходит в alts, леммой берётся цель, если она одна."""
    real = []
    pointers = []
    for eid in ids:
        targets = pointer_targets(lex, eid)
        if targets is None:
            if eid not in real:
                real.append(eid)
            continue
        pointers.append(eid)
        for tid in targets:
            if tid not in real:
                real.append(tid)
    return real, pointers


def _note_cuts(hits):
    cuts = []
    for hit in hits:
        parts = [surf for surf, _code in hit["pieces"]]
        parts.append(hit["stem"])
        if hit["suf"]:
            parts.append(hit["suf"][0])
        cuts.append("+".join(parts))
    return "нарезки: " + " | ".join(cuts[:6])


def analyze(text, verse, lex):
    """verse — (глава, стих) или None. Возвращает запись morph для одного слова."""
    text = unicodedata.normalize("NFC", text)
    if is_number(text):
        return {
            "status": "unsure",
            "segs": [{"t": text, "lemma": None, "prefix": None, "morph": None}],
            "gram": "число",
            "alts": [],
            "note": "эфиопское число; нет в словаре Дильмана",
        }
    hits = _prefer_confident(_dedupe(exact_hits(text, lex)))
    confident = [hit for hit in hits if not hit["ambiguous"]]
    weak = [hit for hit in hits if hit["ambiguous"]]
    note = []
    gram = None
    alts = []
    status = "unsure"
    chosen = None
    lemma = None
    if len(confident) == 1 and len(confident[0]["lemmas"]) == 1 and not _blocks_auto(confident[0], weak):
        chosen = confident[0]
        raw_lemma = chosen["lemmas"][0]
        real, pointers = _unwrap(lex, [raw_lemma])
        if pointers:
            status = "unsure"
            lemma = real[0] if len(real) == 1 else None
            alts = pointers + [eid for eid in real if eid != lemma]
            note.append("отсылка Дильмана «vid. sub»: заголовок отсылки не беру леммой")
            if lemma:
                note.append("кандидат по отсылке: " + _names(lex, [lemma]))
            else:
                note.append("кандидаты: " + _names(lex, real[:8] or pointers[:8]))
        else:
            status = "auto"
            lemma = raw_lemma
            gram = coarse_gram(lex.items[lemma])
            if chosen["kind"] == "built":
                note.append("форма построена от заголовка статьи")
            cited = _cited(lex, verse, [lemma])
            if cited:
                note.append("Дильман ссылается на этот стих")
    elif hits:
        chosen = confident[0] if len(confident) == 1 else (weak[0] if len(weak) == 1 and not confident else None)
        if len(confident) + len(weak) > 1:
            note.append("несколько нарезок")
            chosen = None
        seen = []
        for hit in confident + weak:
            real, pointers = _unwrap(lex, hit["lemmas"])
            for eid in real + pointers:
                if eid not in seen:
                    seen.append(eid)
        alts = seen
        if len(alts) > 1 or not confident:
            note.append("несколько статей" if len(alts) > 1 else "окончание двусмысленно")
        if any(hit["suf"] and hit["suf"][0] == "ሰ" for hit in hits):
            note.append("ሰ — частица n=2428, но может быть и частью основы, поэтому не auto")
        if any(hit["suf"] and hit["suf"][0] == "ሳ" for hit in hits):
            note.append("ሳ пишу как Enc-ssa, ту же частицу n=2428; написание ещё сверять")
        if any(hit["suf"] and hit["suf"][1] == "S1cs" for hit in hits):
            note.append("ኒ или የ не отделяю уверенно: на глаголе ኒ — n=4755, энклитика тоже возможна")
        if any(hit["suf"] and hit["suf"][1] == "Enc-ni" for hit in hits):
            note.append("ኒ на имени — энклитика n=4756, не местоимение")
        cited = _cited(lex, verse, alts)
        if cited:
            note.append("Дильман ссылается на этот стих")
        if len(confident) + len(weak) > 1:
            note.append(_note_cuts(confident + weak))
        note.append("кандидаты: " + _names(lex, alts[:8]))
    else:
        loose = _dedupe(loose_hits(text, lex))
        if loose:
            kinds = {hit["kind"] for hit in loose}
            if kinds == {"paradigm"}:
                note.append("форма из парадигмы статьи Дильмана, не заглавное написание; не auto")
            elif kinds == {"func"}:
                note.append("форма служебного слова по правилу ê, в статье этого лица нет; не auto")
            elif kinds <= {"homophone", "suffix"}:
                note.append("совпадение через омофон или известную основу с окончанием, не по точному написанию; не auto")
            else:
                note.append("кандидат по парадигме или омофону, не по точному написанию; не auto")
            if len(loose) > 1:
                note.append("несколько нарезок")
                note.append(_note_cuts(loose))
                chosen = None
            else:
                chosen = loose[0]
            seen = []
            for hit in loose:
                real, pointers = _unwrap(lex, hit["lemmas"])
                for eid in real + pointers:
                    if eid not in seen:
                        seen.append(eid)
            if chosen is not None and len(seen) == 1:
                lemma = seen[0]
                alts = []
            else:
                lemma = None
                alts = seen
            if any(hit["suf"] and hit["suf"][0] in {item[0] for item in EXTRA_SUFFIXES} for hit in loose):
                note.append("окончание отделено, потому что основа известна; роль окончания не auto")
            note.append("кандидаты: " + _names(lex, (alts or ([lemma] if lemma else []))[:8]))
        else:
            alts, total, equal, cited_ids, pieces, rest = skeleton_alts(text, verse, lex)
            if pieces and rest:
                chosen = _hit(pieces, rest, None, [], "skel", True)
            if not alts:
                note.append("нет в словаре Дильмана")
            else:
                how = "совпадение по согласным после омофонов, не по гласным"
                if not equal:
                    how = "согласные без глагольной приставки лица, после омофонов, не по написанию"
                note.append(how)
                if total > SKEL_CAP:
                    note.append(f"статей по скелету {total}, показаны {SKEL_CAP}")
                if cited_ids:
                    note.append("Дильман ссылается на этот стих")
                note.append("кандидаты: " + _names(lex, alts[:8]))
    return {
        "status": status,
        "segs": _segs(text, chosen, lemma),
        "gram": gram,
        "alts": alts,
        "note": "; ".join(note),
    }


def _manual(path):
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    for word in (data.get("words") or {}).values():
        if word.get("status") != "auto":
            return True
    return False


# Имя без статьи Дильмана. Только явный знак: -ኤል/-ያል в списке имён или эта помета.
# አርዲስ в 6:6 рецензент этапа 1 отметил как имя места и вариант чтения.
MANUAL_NAMES = {
    (6, 6, "አርዲስ"): "имя, в словаре нет",
}
_NAME_PREFIX = {"ወ": "c", "ለ": "l", "በ": "b"}


def _name_core(text):
    for pref in _NAME_PREFIX:
        if text.startswith(pref) and len(text) > len(pref) + 1:
            core = text[len(pref):]
            if core.endswith(("ኤል", "ያል")) and syllables(core) >= 2:
                return pref, core
    return None, text


def _unlisted_name(text):
    pref, core = _name_core(text)
    if pref and core.endswith(("ኤል", "ያል")):
        segs = [
            {"t": pref, "lemma": None, "prefix": _NAME_PREFIX[pref], "morph": None},
            {"t": core, "lemma": None, "prefix": None, "morph": None},
        ]
    else:
        segs = [{"t": text, "lemma": None, "prefix": None, "morph": None}]
    return {
        "status": "unsure",
        "segs": segs,
        "gram": "имя",
        "alts": [],
        "note": "имя, в словаре нет",
    }


def _has_lemma(rec):
    return any(seg.get("lemma") for seg in (rec.get("segs") or []))


def is_unlisted_name(word):
    """Имя, которого нет в словаре. В «без леммы» не входит."""
    note = word.get("note") or ""
    if word.get("gram") != "имя" or "в словаре нет" not in note:
        return False
    return not _has_lemma(word)


def _mark_names(chapter, words):
    """Список имён: в стихе не меньше двух слов на -ኤል/-ያል, считая одну приставку."""
    for verse in chapter["verses"]:
        group = []
        for word in verse["words"]:
            text = unicodedata.normalize("NFC", word["text"])
            _pref, core = _name_core(text)
            if core.endswith(("ኤል", "ያል")) and syllables(core) >= 2:
                group.append(word["id"])
        listed = set(group) if len(group) >= 2 else set()
        for word in verse["words"]:
            text = unicodedata.normalize("NFC", word["text"])
            manual = (chapter["chapter"], verse["n"], text) in MANUAL_NAMES
            if word["id"] not in listed and not manual:
                continue
            if _has_lemma(words[word["id"]]):
                continue
            words[word["id"]] = _unlisted_name(text)


def tag_chapter(chapter, lex):
    words = {}
    for verse in chapter["verses"]:
        for word in verse["words"]:
            words[word["id"]] = analyze(word["text"], (chapter["chapter"], verse["n"]), lex)
    _mark_names(chapter, words)
    ordered = {key: words[key] for key in sorted(words)}
    return {"chapter": chapter["chapter"], "words": ordered}


def coverage(chapters):
    one = several = none = names = 0
    forms = Counter()
    status = Counter()
    for chapter in chapters:
        for word in chapter["words"].values():
            text = "".join(seg["t"] for seg in word["segs"])
            status[word["status"]] += 1
            lemmas = [seg.get("lemma") for seg in word["segs"] if seg.get("lemma")]
            alts = word.get("alts") or []
            if is_unlisted_name(word):
                names += 1
            elif len(lemmas) == 1 and not alts:
                one += 1
            elif lemmas or alts:
                several += 1
            else:
                none += 1
                forms[text] += 1
    total = one + several + none + names
    return {
        "words": total,
        "one": one,
        "several": several,
        "none": none,
        "names": names,
        "status": dict(status),
        "topUnanalyzed": forms.most_common(100),
    }


def load_corpus():
    chapters = []
    for number in range(1, 109):
        path = CORPUS / f"{number:03d}.json"
        chapters.append(json.loads(path.read_text(encoding="utf-8")))
    return chapters


def write_morph(data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    force = "--force" in sys.argv
    only = None
    if "--chapter" in sys.argv:
        only = int(sys.argv[sys.argv.index("--chapter") + 1])
    print("словарь")
    lex = LexIndex.load(LEXICON)
    print(
        "статей", len(lex.items), "заглавных", len(lex.by_head),
        "форм", len(lex.by_form), "парадигм", len(lex.paradigm),
        "построенных", len(lex.built),
    )
    if "--probe" in sys.argv:
        word = sys.argv[sys.argv.index("--probe") + 1]
        verse = (1, 1)
        if "--verse" in sys.argv:
            raw = sys.argv[sys.argv.index("--verse") + 1]
            chapter, verse_n = raw.split(":")
            verse = (int(chapter), int(verse_n))
        print(json.dumps(analyze(word, verse, lex), ensure_ascii=False, indent=2))
        return
    chapters = load_corpus()
    written = []
    for chapter in chapters:
        number = chapter["chapter"]
        if only is not None and number != only:
            continue
        path = MORPH / f"{number:03d}.json"
        if _manual(path) and not force:
            print(f"глава {number}: оставлен ручной файл")
            continue
        data = tag_chapter(chapter, lex)
        write_morph(data, path)
        written.append(number)
    print("записаны", written[0] if written else "—", "…", written[-1] if written else "—", "файлов", len(written))
    loaded = []
    for number in range(1, 109):
        path = MORPH / f"{number:03d}.json"
        if path.exists():
            loaded.append(json.loads(path.read_text(encoding="utf-8")))
    report = coverage(loaded)
    print(
        f"слов {report['words']}, одна лемма {report['one']}, "
        f"несколько {report['several']}, без леммы {report['none']}, "
        f"имён нет в словаре {report['names']}, status {report['status']}"
    )
    if "--sheet" in sys.argv:
        raw = sys.argv[sys.argv.index("--sheet") + 1]
        if "-" in raw:
            start, end = raw.split("-")
            wanted = range(int(start), int(end) + 1)
        else:
            wanted = [int(raw)]
        by_morph = {item["chapter"]: item for item in loaded}
        by_chapter = {item["chapter"]: item for item in chapters}
        lines = []
        for number in wanted:
            lines.append(f"## {number}")
            morph = by_morph[number]["words"]
            for verse in by_chapter[number]["verses"]:
                lines.append(f"# {verse['ref']}")
                sm = " ".join(piece["text"] for piece in verse.get("smirnov") or [])
                if sm:
                    lines.append("Смирнов: " + sm)
                for edition in verse.get("grc") or []:
                    lines.append(f"{edition['edition']}: {edition['text']}")
                for word in verse["words"]:
                    tag = morph[word["id"]]
                    lemmas = [seg.get("lemma") for seg in tag["segs"] if seg.get("lemma")]
                    head = ""
                    sense = ""
                    if lemmas:
                        item = lex.items.get(lemmas[0]) or {}
                        head = item.get("head") or ""
                        senses = item.get("senses") or []
                        sense = senses[0]["text"][:160] if senses else ""
                    lines.append(
                        f"{word['id']}\t{word['text']}\t{word['tr']}\t{tag['status']}\t"
                        f"{tag.get('gram')}\t{head}\t{sense}\t{tag.get('note')}"
                    )
        out = Path(sys.argv[sys.argv.index("--sheet") + 2]) if len(sys.argv) > sys.argv.index("--sheet") + 2 else None
        text_out = "\n".join(lines) + "\n"
        if out:
            out.write_text(text_out, encoding="utf-8")
            print("лист", out, "строк", len(lines))
        else:
            print(text_out)


if __name__ == "__main__":
    main()
