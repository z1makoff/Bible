"""Черновик разметки 1 Еноха по словарю Дильмана.

auto — одна нарезка и одна статья. Сюда входит точное написание заголовка,
напечатанная форма и форма, построенная от заголовка (сильный перфект, класс
субъюнктива, имя). Омофон и напечатанная парадигма (Imperf./Subj. и их лица)
остаются unsure. Совпадение только через омофон — тоже unsure. Ссылка Дильмана
на стих сама по себе лемму не выбирает. Отсылка «vid. sub» не становится леммой.

Главы 1–16 не перезаписываются без --force: в них ручная разметка.
В главах 17–108 повторный прогон обновляет auto и чужой unsure.
Слово со статусом checked и слово с пометой «Ручное:» остаются как были.
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
_ANTE_PRON_RE = re.compile(r"ante pron\. suff\. ([\u1200-\u135A]+)")
# Частица ኔ n=4758 — только в этих двух словах (статья Дильмана).
_NE_HOSTS = {"እስከኔ", "አሐተኔ"}
_RARE_CHARS = 300
_FOLD_GROUPS = (
    {"h", "ḥ", "ḫ"},
    {"s", "ś"},
    {"ʾ", "ʿ"},
    {"ṣ", "ḍ"},
)
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
    # «II,1 cognoscere» — глагол, даже если в pos попало pron.
    # n. pr. не перебиваем: иначе имя, чья статья начинается с класса, строит глагол.
    if (
        re.match(r"(?:IV|III|II|I),\d", blob.strip())
        and "n. pr" not in " ".join(pos)
        and "n.pr" not in " ".join(pos)
    ):
        return True
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
    # «part. II,2 …» без Subj./Imperf. — причастие. Иначе личная форма
    # с ያ- садится на чужой корень: ያማስኑ (ሰ) на መሠንይ (ሠ).
    if blob.strip().startswith("part.") and not has_paradigm:
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
# Одна приставка с начала, самая длинная. Второй раз не снимаем:
# после ይ радикал ን — это корень, не ещё одна приставка.
# ያስተ и ይት идут раньше ያ и ይ.
_ROOT_PREFIXES = (
    "አስተ", "ኣስተ", "ያስተ", "ታስተ",
    "ይት", "ትት", "እት", "ንት",
    "ያ", "ታ", "ና", "የ", "ይ", "ት", "እ", "ን", "አ", "ኣ", "ተ",
)
# Приставка породы на форме. Голые አ и ተ не трогаем: አኀዘ и ተርፈ — это
# заголовок I основы, а не сигнал бросить её. Задание этапа 3 — ያ / ይት / ያስተ
# (и их лица ታ ና, ትት እት ንት, አስተ).
_DERIV_PREFIX = (
    ("አስተ", "IV"), ("ኣስተ", "IV"),
    ("ያስተ", "IV"), ("ታስተ", "IV"),
    ("ይት", "III"), ("ትት", "III"), ("እት", "III"), ("ንት", "III"),
    ("ያ", "II"), ("ታ", "II"), ("ና", "II"),
)
_DERIV_ALWAYS = {
    "አስተ", "ኣስተ", "ያስተ", "ታስተ", "ይት", "ትት", "እት", "ንት", "ያ", "ታ", "ና",
}
_DERIV_NAME = {"II": "II", "III": "III", "IV": "IV"}
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
    """Снимает одну приставку ይ ት እ ን ያ የ አ አስተ ተ с начала формы.

    Целиком, один раз. Иначе из ይንፍቅ после ይ съедается радикал ን.
    """
    if syllables(word) < 2:
        return word
    for pref in _ROOT_PREFIXES:
        if word.startswith(pref) and len(word) > len(pref):
            return word[len(pref):]
    return word


def _match_root_raw(head_cons, form_cons):
    """Как _match_root, но без свёртки s/ś и ṣ/ḍ. Гортанные можно пропустить."""
    optional = _OPTIONAL_CONS | _GUTTURAL
    if not head_cons or not form_cons:
        return False
    i = 0
    j = 0
    while i < len(head_cons):
        if j >= len(form_cons):
            return all(cons in optional for cons in head_cons[i:])
        if head_cons[i] == form_cons[j]:
            i += 1
            j += 1
            continue
        if head_cons[i] in optional:
            i += 1
            continue
        if form_cons[j] in optional:
            j += 1
            continue
        return False
    return True


def _fold_same(left, right):
    if left == right:
        return True
    return any(left in group and right in group for group in _FOLD_GROUPS)


def _spelling_variant(head, token):
    """То же слово, что заголовок, с заменой только омофонной буквы."""
    head_cons = _raw_cons(head)
    token_cons = _raw_cons(token)
    if not head_cons or len(head_cons) != len(token_cons):
        return False
    return all(_fold_same(a, b) for a, b in zip(head_cons, token_cons))


def _raw_root_ok(head, form):
    """Корень без омофонов. ሠዋዒ не подтверждает статью на ስ."""
    if not head or not form:
        return False
    pairs = (
        (_raw_cons(head), _raw_cons(form)),
        (_raw_cons(head), _raw_cons(_strip_root_prefix(form))),
        (_raw_cons(_strip_root_prefix(head)), _raw_cons(_strip_root_prefix(form))),
        (_raw_cons(_strip_root_prefix(head)), _raw_cons(form)),
    )
    return any(h and f and _match_root_raw(h, f) for h, f in pairs)


def _match_root(head_cons, form_cons):
    """Согласные корня идут по форме. Слабые можно пропустить.

    Лишние согласные допустимы только после корня (окончание).
    Согласная из середины чужого слова корень не подтверждает.
    """
    if not head_cons or not form_cons:
        return False
    i = 0
    j = 0
    while i < len(head_cons):
        if j >= len(form_cons):
            return all(cons in _OPTIONAL_CONS for cons in head_cons[i:])
        if head_cons[i] == form_cons[j]:
            i += 1
            j += 1
            continue
        if head_cons[i] in _OPTIONAL_CONS:
            i += 1
            continue
        if form_cons[j] in _OPTIONAL_CONS:
            j += 1
            continue
        return False
    return True


def _leftover_strong(head, form):
    """Сколько сильных согласных формы осталось после корня. -1, если корень не читается."""
    best = None
    raw_head = _cons_of(head)
    raw_form = _cons_of(form)
    cut_head = _cons_of(_strip_root_prefix(head))
    cut_form = _cons_of(_strip_root_prefix(form))
    for head_cons, form_cons in (
        (raw_head, raw_form),
        (raw_head, cut_form),
        (cut_head, cut_form),
        (cut_head, raw_form),
    ):
        if not _match_root(head_cons, form_cons):
            continue
        # Повторяем проход и считаем хвост.
        i = 0
        j = 0
        while i < len(head_cons):
            if j >= len(form_cons):
                break
            if head_cons[i] == form_cons[j]:
                i += 1
                j += 1
                continue
            if head_cons[i] in _OPTIONAL_CONS:
                i += 1
                continue
            if form_cons[j] in _OPTIONAL_CONS:
                j += 1
                continue
            break
        tail = sum(1 for cons in form_cons[j:] if cons not in _OPTIONAL_CONS)
        if best is None or tail < best:
            best = tail
    return -1 if best is None else best


def _cited_form_ok(head, form):
    """Форма из поля forms. Корень есть, хвост не длиннее окончания.

    Одна приставка ለ/በ/ወ/እም/ዘ может быть написана слитно: ለዓለም при заголовке ዓለም.
    """
    candidates = [form]
    for pref in ("እም", "በ", "ለ", "ወ", "ዘ"):
        if form.startswith(pref) and len(form) > len(pref) + 1:
            candidates.append(form[len(pref):])
    for cand in candidates:
        if _form_has_root(head, cand) and 0 <= _leftover_strong(head, cand) <= 4:
            return True
    return False


def _form_has_root(head, form):
    """В форме есть согласные корня заголовка.

    Слабые w/y и гортанные могут отсутствовать. Окончание не мешает.
    Приставка снимается и с формы, и с заголовка породы (ተ, አ, አስተ).
    Чужое слово из цитаты, в котором корня нет, сюда не проходит.
    """
    if not head or not form:
        return False
    raw_head = _cons_of(head)
    raw_form = _cons_of(form)
    cut_head = _cons_of(_strip_root_prefix(head))
    cut_form = _cons_of(_strip_root_prefix(form))
    pairs = (
        (raw_head, raw_form),
        (raw_head, cut_form),
        (cut_head, cut_form),
        (cut_head, raw_form),
    )
    return any(_match_root(h, f) for h, f in pairs)


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
    """Напечатанное Pl. «Pl. ዕፀወ አርዝ» — это не множественное заголовка.

    Первое слово после Pl. берём, только если дальше не стоит сам заголовок
    или у слова есть согласные этого заголовка.
    """
    head = item.get("head") or ""
    text = _article_text(item)
    found = []
    for match in re.finditer(r"Pl\.\s*([\u1200-\u137F]+)", text):
        tok = match.group(1).strip("፡።፣፤፥፦፧፨")
        if not is_single(tok) or syllables(tok) < 2 or tok in found:
            continue
        nxt = re.match(r"[\s፡።፣፤፥፦፧፨:.,;]*([\u1200-\u137F]+)", text[match.end():])
        nxt_word = nxt.group(1).strip("፡።፣፤፥፦፧፨") if nxt else ""
        if nxt_word == head and not _form_has_root(head, tok):
            continue
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


def _possessive_u(item):
    """3 м. ед. -u на последнем слоге: ዘርእ → ዘርኡ.

    Пустая статья не строит форму. Иначе n. pr. без смысла
    загораживает одноимённое имя.
    """
    if not _nominal_article(item) or not _has_dillmann_sense(item):
        return None
    head = item.get("head") or ""
    if not head or not is_single(head):
        return None
    form = _swap_last(head, "u")
    if not form or form == head:
        return None
    return form


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
        # Голое Pl. сюда не кладём: አባግዕ печатают две статьи, ውሉድ — ещё и свой
        # заголовок. Такое Pl. добавляет второй проход, и только если оно
        # ничьё заглавное слово со смыслом.
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
            his = _possessive_u(item)
            if his:
                out.append(his)
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


def _stem_classes(item):
    found = []
    for label in item.get("stem") or []:
        match = re.match(r"(IV|III|II|I)(?:,|$)", str(label))
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


def _class_root_word(head, klass):
    """Заголовок без приставки своей породы. I остаётся как есть."""
    rest = head or ""
    if klass == "IV":
        prefs = ("አስተ", "ኣስተ")
    elif klass == "II":
        prefs = ("አ", "ኣ")
    elif klass == "III":
        prefs = ("ተ",)
    else:
        prefs = ()
    for pref in prefs:
        if rest.startswith(pref) and len(rest) > len(pref):
            return rest[len(pref):]
    return rest


def _key_cons(word):
    """Согласные корня. Слабые w/y выпадают, гортанные остаются: иначе b-r
    склеивает አብርሀ и አኅበረ."""
    return tuple(cons for cons in _cons_of(word) if cons not in {"w", "y"})


def _class_strong(head, klass):
    return _key_cons(_class_root_word(head, klass))


def _strip_plural_alef(word):
    """ኡ/ኦ в конце имперфекта — гласный, не согласная корня."""
    if len(word) >= 2 and word.endswith(("ኡ", "ኦ")):
        return word[:-1]
    return word


def _has_dillmann_sense(item):
    return any((sense.get("text") or "").strip() for sense in (item.get("senses") or []))


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
        self.form_weak = {}
        self.by_class_strong = {}
        self.by_bare = {}
        self.printed_pl = {}
        self.cite = {}
        self.verbal = set()
        self.by_n = {}
        self.suffix_stem = {}
        self.by_printed_morph = {}
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
                if not is_single(form):
                    continue
                # Форма из цитаты даёт лемму только если в ней корень заголовка.
                # Иначе статья остаётся слабым кандидатом, не auto.
                # Короткий заголовок (ለ, በ) сидит внутри любого длинного слова.
                # Хвост длиннее окончания — чужая цитата, не форма статьи.
                # Односложный обломок длинного заголовка (ቦ у ኀበ) — не форма.
                if head and syllables(head) >= 2 and syllables(form) == 1:
                    continue
                if head and len(_cons_of(head)) >= 2 and _cited_form_ok(head, form):
                    bucket = self.by_form.setdefault(form, [])
                    if eid not in bucket:
                        bucket.append(eid)
                    folded = geez.fold_form(form)
                    fold_bucket = self.by_fold_form.setdefault(folded, [])
                    if eid not in fold_bucket:
                        fold_bucket.append(eid)
                    self._remember_bare(eid, form)
                elif head and syllables(form) >= 2 and _related(item, form):
                    weak = self.form_weak.setdefault(form, [])
                    if eid not in weak:
                        weak.append(eid)
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
            if head and is_verb(item):
                for tok in _article_tokens(item):
                    if syllables(tok) < 2 or not _cited_form_ok(head, tok):
                        continue
                    self._remember_bare(eid, tok)
            if is_verb(item):
                self.verbal.add(eid)
                for klass in _stem_classes(item):
                    strong = _class_strong(head, klass)
                    if not strong:
                        continue
                    key = (klass, strong)
                    bucket = self.by_class_strong.setdefault(key, [])
                    if eid not in bucket:
                        bucket.append(eid)
        for eid, item in items.items():
            for plural in _plural_tokens(item):
                bucket = self.printed_pl.setdefault(plural, [])
                if eid not in bucket:
                    bucket.append(eid)
        # Голое Pl. — форма статьи, только если это не чужой заголовок со смыслом.
        # Корень обязателен, когда ту же форму печатают несколько статей (አባግዕ).
        # Одна статья (መዳልው у መድሎት, መዋዕል у ሞዐልት) берётся и без целого корня:
        # ломаное множественное корень часто не держит.
        for plural, eids in self.printed_pl.items():
            heads = self.by_head.get(plural) or []
            if any(_has_dillmann_sense(self.items.get(hid) or {}) for hid in heads):
                continue
            rooted = [
                eid for eid in eids
                if _form_has_root((self.items.get(eid) or {}).get("head") or "", plural)
            ]
            use = rooted or (eids if len(eids) == 1 else [])
            for eid in use:
                self._add_built(eid, plural)
        # -u не перекрывает чужой заголовок со смыслом. ኵሉ — своя статья
        # («ኵል c. pron. suff.»), а не построенная форма от ኵል.
        for form, eids in list(self.built.items()):
            heads = self.by_head.get(form) or []
            if not any(_has_dillmann_sense(self.items.get(hid) or {}) for hid in heads):
                continue
            drop = [
                eid for eid in eids
                if _possessive_u(self.items.get(eid) or {}) == form
            ]
            if not drop:
                continue
            kept = [eid for eid in eids if eid not in drop]
            folded = geez.fold_form(form)
            if kept:
                self.built[form] = kept
            else:
                self.built.pop(form, None)
            if not folded:
                continue
            for eid in drop:
                still = any(
                    eid in ids and geez.fold_form(other) == folded
                    for other, ids in self.built.items()
                )
                if still:
                    continue
                fold_bucket = self.built_fold.get(folded)
                if fold_bucket and eid in fold_bucket:
                    fold_bucket.remove(eid)
                    if not fold_bucket:
                        self.built_fold.pop(folded, None)
        for bucket in (
            self.by_head, self.by_form, self.by_skel, self.by_fold_head,
            self.by_fold_form, self.by_fold_skel, self.paradigm, self.built,
            self.built_fold, self.func_unsure, self.form_weak, self.by_class_strong,
            self.by_bare,
        ):
            for key in bucket:
                bucket[key] = sorted(set(bucket[key]))
        self._index_printed()

    def _index_printed(self):
        """Напечатанный гласный падежа и «ante pron. suff.».

        В индекс попадает только замена последнего гласного заголовка,
        которую статья реально печатает. Чужая цитата с тем же написанием
        (ወለደ при токене ወልደ, አርስዐ при ርእሳ) сюда не входит.
        """
        for eid, item in self.items.items():
            text = _article_text(item)
            match = _ANTE_PRON_RE.search(text)
            if match:
                stem = match.group(1)
                if is_single(stem):
                    bucket = self.suffix_stem.setdefault(stem, [])
                    if eid not in bucket:
                        bucket.append(eid)
            head = item.get("head") or ""
            if not is_single(head) or syllables(head) < 2 or _is_letter_item(item):
                continue
            seen = set()
            for tok in _article_tokens(item):
                if tok in seen or tok == head or not _last_vowel_variant(head, tok):
                    continue
                # ኵሉ и አቡ — свои статьи. Напечатанный гласный чужой статьи их не забирает.
                if any(
                    _has_dillmann_sense(self.items.get(hid) or {})
                    for hid in (self.by_head.get(tok) or [])
                ):
                    continue
                if not _form_has_root(head, tok):
                    continue
                seen.add(tok)
                bucket = self.by_printed_morph.setdefault(tok, [])
                if eid not in bucket:
                    bucket.append(eid)
        for bucket in (self.suffix_stem, self.by_printed_morph):
            for key in bucket:
                bucket[key] = sorted(set(bucket[key]))

    def _remember_bare(self, eid, form):
        """Поверхность и она же без ዘ/ኢ/ወ в начале цитаты.

        В выбор лемм не входит. Нужна, только чтобы ጸ не уступил статье на ፀ,
        если Дильман уже напечатал это написание.
        """
        for bare in _clitic_bares(form):
            bucket = self.by_bare.setdefault(bare, [])
            if eid not in bucket:
                bucket.append(eid)

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
        if not form or not is_single(form):
            return
        # Односложное — только явная парадигма ለ/በ (ቦ «есть» / «в нём»).
        # Иначе ቦ из ኀበ и любой односложный обломок снова становятся формой.
        head = (self.items.get(eid) or {}).get("head") or ""
        if syllables(form) < 2 and form not in _FUNCTION_LIST.get(head, ()):
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


def _radix_inusitata(lex, eid):
    """Статья «radix inusitata»: корень назван, слова от него нет."""
    text = _article_text(lex.items.get(eid) or "").strip().lower()
    return text.startswith("rad. inus")


def _content_over_unused_root(lex, stem):
    """Отсылка на неиспользуемый корень не прячет статью, которая печатает форму.

    መንገለ — заголовок n=1410 «vid. sub ነገለ». Цель n=5184 — radix inusitata.
    Форма መንገለ напечатана у предлога መንገል n=5185: винительный и сопряжённое.
    Чужое слово в списке (እምነ перечисляет другие предлоги) не берётся:
    его заголовок не вариант последнего гласного этой формы.
    """
    heads = lex.by_head.get(stem) or []
    if not heads:
        return None
    if any(pointer_targets(lex, eid) is None for eid in heads):
        return None
    for eid in heads:
        targets = pointer_targets(lex, eid) or []
        if not targets or not all(_radix_inusitata(lex, tid) for tid in targets):
            return None
    found = []
    for eid in lex.by_form.get(stem, []):
        if pointer_targets(lex, eid) is not None or _radix_inusitata(lex, eid):
            continue
        if _is_stub(lex, eid):
            continue
        head = (lex.items.get(eid) or {}).get("head") or ""
        if not _last_vowel_variant(head, stem):
            continue
        if eid not in found:
            found.append(eid)
    if len(found) == 1:
        return found[0]
    return None


def _plural_override(lex, stem):
    """Пустой заголовок уступает одной статье, где это напечатанное Pl.

    መዋዕል n=12572 без смысла не забирает множественное от ሞዐልት.
    Заголовок со смыслом (ውሉድ, አፈው) не трогаем.
    """
    heads = lex.by_head.get(stem) or []
    if not heads:
        return None
    if any(_has_dillmann_sense(lex.items.get(eid) or {}) for eid in heads):
        return None
    extra = [eid for eid in lex.built.get(stem, []) if eid not in heads]
    if len(extra) == 1:
        return extra[0]
    return None


def exact_hits(text, lex):
    """Точные написания. Заглавное слово важнее процитированной формы.

    Построенная форма, которая совпала с чужим заголовком, auto не даёт.
    """
    if text in lex.by_head:
        printed = _content_over_unused_root(lex, text)
        if printed:
            return [_hit((), text, None, [printed], "form", False)]
        over = _plural_override(lex, text)
        if over:
            return [_hit((), text, None, [over], "built", False)]
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
                printed = _content_over_unused_root(lex, stem)
                if printed:
                    hits.append(_hit(pieces, stem, suf, [printed], "form", ambiguous))
                else:
                    over = _plural_override(lex, stem)
                    if over:
                        hits.append(_hit(pieces, stem, suf, [over], "built", ambiguous))
                    else:
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


def _is_letter_item(item):
    """Однобуквенная статья алфавита. Не лемма сегмента."""
    head = (item or {}).get("head") or ""
    if syllables(head) != 1:
        return False
    return "litera alphabeti" in _article_text(item)


def _is_letter(lex, eid):
    return _is_letter_item(lex.items.get(eid) or {})


def _is_stub(lex, eid):
    """Пустая статья, отсылка или короткий q.v. Содержательная статья остаётся."""
    item = lex.items.get(eid) or {}
    if pointer_targets(lex, eid) is not None:
        return True
    text = _article_text(item).strip()
    if not text:
        return True
    if len(text) < 80 and re.search(r"q\.v\.|vid\.", text, re.I):
        return True
    return False


def _last_vowel_variant(head, form):
    """Та же основа, другой гласный последнего слога. Не чужое слово."""
    hs = _syls(head)
    fs = _syls(form)
    if len(hs) < 2 or len(hs) != len(fs) or hs[:-1] != fs[:-1]:
        return False
    if hs[-1] == fs[-1]:
        return False
    return geez.SYLLABLE[hs[-1]][0] == geez.SYLLABLE[fs[-1]][0]


def _ne_host(text):
    """(приставки, основа) если слово — እስከኔ или አሐተኔ, иначе None."""
    prefs = []
    core = text
    for surf, code in (("ወ", "c"), ("በ", "b"), ("ለ", "l")):
        if core.startswith(surf) and core[len(surf):] in _NE_HOSTS:
            prefs.append((surf, code))
            core = core[len(surf):]
            break
    if core not in _NE_HOSTS:
        return None
    return tuple(prefs), core


def _suf_ambiguous(hit):
    if not hit["suf"]:
        return False
    return any(hit["suf"][0] == surf and amb for surf, _morph, amb in SUFFIXES)


def _article_len(lex, eid):
    return len(_article_text(lex.items.get(eid) or {}))


def _token_set(lex, eid):
    cache = lex.__dict__.setdefault("_tok_cache", {})
    if eid not in cache:
        cache[eid] = set(_article_tokens(lex.items.get(eid) or {}))
    return cache[eid]


def _prints_surface(lex, eid, text):
    """Статья претендует на это написание: заголовок, напечатанный гласный или форма."""
    if _is_stub(lex, eid) or _is_letter(lex, eid):
        return False
    item = lex.items.get(eid) or {}
    if text == (item.get("head") or ""):
        return True
    if eid in (lex.by_printed_morph.get(text) or []):
        return True
    if eid in (lex.by_form.get(text) or []):
        return True
    if eid in (lex.built.get(text) or []) or eid in (lex.paradigm.get(text) or []):
        if text in _token_set(lex, eid):
            return True
    return False


def _content_lemmas(lex, eids):
    return [eid for eid in eids if not _is_stub(lex, eid) and not _is_letter(lex, eid)]


def _drop_empty_lemmas(hit, lex):
    """Буква алфавита и пустая отсылка не остаются рядом с содержательной статьёй."""
    if not hit["lemmas"]:
        return False
    kept = []
    changed = False
    for eid in hit["lemmas"]:
        item = lex.items.get(eid) or {}
        number = str(item.get("n") or "")
        if _is_letter(lex, eid):
            changed = True
            continue
        if number == "4758" and _ne_host(hit.get("_text") or "") is None:
            changed = True
            continue
        kept.append(eid)
    if not changed:
        return True
    if not kept:
        return False
    hit["lemmas"] = kept
    if len(kept) == 1 and not _suf_ambiguous(hit):
        hit["ambiguous"] = False
    return True


def _retarget_abu(hit, lex):
    """አቡ + суффикс — አብ «отец», не n. peregr. с заголовком አቡ."""
    if not hit["suf"]:
        return
    owners = [
        eid for eid in (lex.suffix_stem.get(hit["stem"]) or [])
        if not _is_stub(lex, eid)
    ]
    if not owners:
        return
    kept = []
    replaced = False
    for eid in hit["lemmas"]:
        head = (lex.items.get(eid) or {}).get("head") or ""
        if head == hit["stem"] and eid not in owners:
            replaced = True
            continue
        if eid not in kept:
            kept.append(eid)
    if not replaced:
        return
    for eid in owners:
        if eid not in kept:
            kept.append(eid)
    hit["lemmas"] = kept
    hit["kind"] = "form"
    if len(kept) == 1 and not _suf_ambiguous(hit):
        hit["ambiguous"] = False


def _force_bo(hit, lex):
    """ቦ — «есть» n=3741. ኀበ сюда не входит, n=3740 остаётся в примечании."""
    if hit["stem"] != "ቦ":
        return
    chosen = lex.by_n.get("3741")
    haba = lex.by_n.get("4534")
    if not chosen:
        return
    if haba and haba in hit["lemmas"] or chosen in hit["lemmas"] or hit["kind"] == "form":
        hit["lemmas"] = [chosen]
        hit["ambiguous"] = False
        hit["kind"] = "form"
        hit["bo"] = True


def _filter_stubs(hit, lex):
    if len(hit["lemmas"]) < 2:
        return
    content = _content_lemmas(lex, hit["lemmas"])
    if not content or len(content) == len(hit["lemmas"]):
        return
    hit["lemmas"] = content
    if len(content) == 1 and not _suf_ambiguous(hit):
        hit["ambiguous"] = False


def _joined(hit):
    return (
        "".join(surf for surf, _code in hit["pieces"])
        + hit["stem"]
        + (hit["suf"][0] if hit["suf"] else "")
    )


def _part_count(hit):
    return len(hit["pieces"]) + 1 + (1 if hit["suf"] else 0)


def _same_lemma_split(confident):
    """Одна лемма и та же поверхность: оставить нарезку с приставкой и суффиксом.

    Иначе форма ወይእዜኒ из списка n=7767 прячет ወ + ይእዜ + ኒ.
    """
    ids = []
    for hit in confident:
        if len(hit["lemmas"]) != 1:
            return None
        eid = hit["lemmas"][0]
        if eid not in ids:
            ids.append(eid)
    if len(ids) != 1:
        return None
    best = None
    best_rank = None
    for hit in confident:
        surf = _joined(hit)
        if not any(
            other is not hit and _joined(other) == surf and _part_count(other) < _part_count(hit)
            for other in confident
        ):
            continue
        rank = (
            _part_count(hit),
            len(hit["suf"][0]) if hit["suf"] else 0,
            -len(hit["pieces"]),
        )
        if best is None or rank > best_rank:
            best = hit
            best_rank = rank
    return best


def _relative_head(hit, lex):
    """ዘ + заголовок обычной статьи. Склейка «ዘመን + -u» её не отменяет."""
    if lex is None or len(hit.get("lemmas") or []) != 1 or hit.get("suf"):
        return False
    pieces = hit.get("pieces") or ()
    if len(pieces) != 1 or pieces[0][1] != "s":
        return False
    eid = hit["lemmas"][0]
    if _is_stub(lex, eid) or _is_letter(lex, eid):
        return False
    if _article_len(lex, eid) < _RARE_CHARS:
        return False
    head = (lex.items.get(eid) or {}).get("head") or ""
    return bool(head) and hit["stem"] == head


def _deeper_other_pos(shallow, confident, lex):
    """Редкое имя на малой глубине не прячет обычный глагол глубже.

    ወፈርሁ: ን 6894 и ፈርሀ n=9884 оба реальны. Винительный ወልድ — длинная
    статья, более глубокое ልድ она по-прежнему закрывает.
    """
    if lex is None or len(shallow["lemmas"]) != 1:
        return False
    eid = shallow["lemmas"][0]
    if _article_len(lex, eid) >= _RARE_CHARS:
        return False
    shallow_verb = eid in lex.verbal or is_verb(lex.items.get(eid) or {})
    for hit in confident:
        if len(hit["pieces"]) <= len(shallow["pieces"]):
            continue
        for oid in hit["lemmas"]:
            if oid == eid or _article_len(lex, oid) < _RARE_CHARS:
                continue
            other_verb = oid in lex.verbal or is_verb(lex.items.get(oid) or {})
            if shallow_verb != other_verb:
                return True
    return False


def _prefer_confident(hits, lex=None):
    """Меньше приставок выигрывает у более глубокой нарезки.

    Заголовок на большей глубине не прячет короткую нарезку: иначе буква ደ
    забирала винительный ወልድ, а частица ኔ — форму እምነ.
    На одной глубине разные леммы не прячутся. Одна лемма схлопывается
    в нарезку со суффиксом (እምኔ + ሆሙ).
    """
    confident = [hit for hit in hits if not hit["ambiguous"]]
    weak = [hit for hit in hits if hit["ambiguous"]]
    if len(confident) <= 1:
        return hits
    split = _same_lemma_split(confident)
    if split is not None:
        return [split] + weak
    best_depth = min(len(hit["pieces"]) for hit in confident)
    shallow = [hit for hit in confident if len(hit["pieces"]) == best_depth]
    deeper = any(len(hit["pieces"]) > best_depth for hit in confident)
    if (
        len(shallow) == 1
        and len(shallow[0]["lemmas"]) == 1
        and deeper
        and not _deeper_other_pos(shallow[0], confident, lex)
    ):
        shallow_id = shallow[0]["lemmas"][0]
        extra = [
            hit for hit in confident
            if hit not in shallow
            and hit["lemmas"]
            and hit["lemmas"][0] != shallow_id
            and _relative_head(hit, lex)
        ]
        if extra:
            return shallow + extra + weak
        return shallow + weak
    return hits


def _nominal_eid(lex, eid):
    if eid in lex.verbal or is_verb(lex.items.get(eid) or {}):
        return False
    return _positively_nominal(lex, eid)


def _add_weak(hits, pieces, stem, lemmas):
    lemmas = list(dict.fromkeys(lemmas))
    if not lemmas or not stem:
        return
    for hit in hits:
        if hit["pieces"] == pieces and hit["stem"] == stem and not hit["suf"]:
            for eid in lemmas:
                if eid not in hit["lemmas"]:
                    hit["lemmas"].append(eid)
            hit["ambiguous"] = True
            return
    hits.append(_hit(pieces, stem, None, lemmas, "head", True))


def _vowel_mates(text, hits, lex):
    """Глагол с суффиксом и имя с тем же остовом. Никто не напечатал слово — не auto.

    Слабый hit на той же глубине закрывает auto. Редкая статья, которая
    совпала со всем словом, уступает короткой нарезке ወ + имя.
    """
    confident = [hit for hit in hits if not hit["ambiguous"] and hit["lemmas"]]
    if any(
        _prints_surface(lex, eid, text)
        for hit in confident
        for eid in hit["lemmas"]
    ):
        return
    for hit in list(confident):
        if len(hit["lemmas"]) != 1:
            continue
        eid = hit["lemmas"][0]
        if _is_letter(lex, eid):
            continue
        chars = _syls(hit["stem"])
        targets = []
        if chars and geez.SYLLABLE[chars[-1]][1] in {"o", "ā"}:
            targets.append(hit["stem"])
        if hit["pieces"]:
            full = "".join(surf for surf, _code in hit["pieces"]) + hit["stem"]
            full += hit["suf"][0] if hit["suf"] else ""
            fchars = _syls(full)
            head = (lex.items.get(eid) or {}).get("head") or ""
            if fchars and geez.SYLLABLE[fchars[-1]][1] in {"o", "ā"} and hit["stem"] == head:
                targets.append(full)
        for src in targets:
            base = _swap_last(src, "ǝ")
            if not base or base == src or base == hit["stem"]:
                continue
            mates = [
                tid for tid in _content_lemmas(lex, lex.by_head.get(base) or [])
                if tid != eid and not _prints_surface(lex, tid, text)
            ]
            # ወ+ልዳ не тащит короткое ልድ: под приставкой берём только обычную статью.
            if src == hit["stem"] and hit["pieces"]:
                mates = [tid for tid in mates if _article_len(lex, tid) >= _RARE_CHARS]
            if not mates:
                continue
            pieces = () if src != hit["stem"] else hit["pieces"]
            _add_weak(hits, pieces, base, mates)
        # ኩ/ከ/ነ — подлежащее перфекта. ሁ — притяжательное, не лицо глагола.
        if (
            hit["suf"]
            and hit["suf"][0] in set(_PERF_CONSONANT)
            and not _prints_surface(lex, eid, text)
        ):
            cite = _swap_last(hit["stem"], "a")
            if cite and cite != hit["stem"]:
                mates = []
                cur_verb = eid in lex.verbal or is_verb(lex.items.get(eid) or {})
                for tid in lex.by_head.get(cite) or []:
                    if tid == eid or _is_stub(lex, tid) or _is_letter(lex, tid):
                        continue
                    mate_verb = tid in lex.verbal or is_verb(lex.items.get(tid) or {})
                    if mate_verb == cur_verb or _prints_surface(lex, tid, text):
                        continue
                    mates.append(tid)
                if mates:
                    rest = hit["stem"] + hit["suf"][0]
                    _add_weak(hits, hit["pieces"], rest, mates)
        if hit["stem"].endswith(("ዋ", "ዎ")) and len(hit["stem"]) > 1:
            noun = hit["stem"][:-1]
            mates = [
                tid for tid in _content_lemmas(lex, lex.by_head.get(noun) or [])
                if tid != eid and _nominal_eid(lex, tid) and not _prints_surface(lex, tid, text)
            ]
            if mates:
                _add_weak(hits, hit["pieces"], noun, mates)


def _drop_rare_long(text, hits, lex):
    """Редкая статья на всё слово уступает ወ/በ/ለ + обычному имени.

    Глагол на большей глубине не отбрасывается: оба чтения реальны.
    """
    confident = [hit for hit in hits if not hit["ambiguous"] and len(hit["lemmas"]) == 1]
    drop = set()
    for rare in confident:
        eid = rare["lemmas"][0]
        if _prints_surface(lex, eid, text) or _article_len(lex, eid) >= _RARE_CHARS:
            continue
        if _is_stub(lex, eid):
            continue
        for other in confident:
            if other is rare or len(other["pieces"]) <= len(rare["pieces"]):
                continue
            if not other["pieces"] or other["pieces"][0][1] not in {"c", "b", "l"}:
                continue
            oid = other["lemmas"][0]
            if not _nominal_eid(lex, oid) or _is_stub(lex, oid):
                continue
            if _article_len(lex, oid) < _RARE_CHARS:
                continue
            drop.add(id(rare))
            break
    if not drop:
        return hits
    return [hit for hit in hits if id(hit) not in drop]


def _narrow_printed(text, hits, lex):
    """Кто напечатал это слово, тот и остаётся. Ненапечатанный сосед отпадает."""
    confident = [hit for hit in hits if not hit["ambiguous"]]
    printers = []
    for hit in confident:
        if any(_prints_surface(lex, eid, text) for eid in hit["lemmas"]):
            printers.append(hit)
    if not printers or len(printers) == len(confident):
        return hits
    kept = list(printers)
    for hit in confident:
        if hit not in kept and _relative_head(hit, lex):
            kept.append(hit)
    weak = [hit for hit in hits if hit["ambiguous"]]
    return kept + weak


def prepare_hits(text, hits, lex):
    """Кластеры этапа 3б: буква, ኔ, አቡ, ቦ, напечатанная форма, редкая статья."""
    prepared = []
    for hit in hits:
        hit["_text"] = text
        if not _drop_empty_lemmas(hit, lex):
            continue
        _retarget_abu(hit, lex)
        _force_bo(hit, lex)
        _filter_stubs(hit, lex)
        if hit["lemmas"]:
            prepared.append(hit)
    printed = _content_lemmas(lex, lex.by_printed_morph.get(text) or [])
    if printed and not any(
        hit["pieces"] == () and hit["stem"] == text and not hit["suf"]
        and set(hit["lemmas"]) >= set(printed)
        for hit in prepared
    ):
        prepared.append(_hit((), text, None, printed, "form", len(printed) != 1))
    host = _ne_host(text)
    particle = lex.by_n.get("4758")
    if host and host[1] == "አሐተኔ" and particle:
        prefs, _core = host
        pieces = tuple(prefs) + (("አሐተ", None),)
        if not any(particle in hit["lemmas"] for hit in prepared):
            prepared.append(_hit(pieces, "ኔ", None, [particle], "head", False))
    prepared = _narrow_printed(text, prepared, lex)
    prepared = _drop_rare_long(text, prepared, lex)
    _vowel_mates(text, prepared, lex)
    for hit in prepared:
        hit.pop("_text", None)
        hit.pop("bo", None)
    return prepared


def _unsplit_same_lemma(weak, chosen, lex):
    """በመንገለ напечатано у n=5185 и не спорит с нарезкой በ + መንገለ.

    Для прочих статей целая форма по-прежнему не даёт auto: иначе ለክሙ
    и ለዓለም молча теряли бы второе чтение.
    """
    if weak.get("pieces") or weak.get("suf") or chosen.get("lemmas") != weak.get("lemmas"):
        return False
    if len(chosen.get("lemmas") or []) != 1:
        return False
    number = str((lex.items.get(chosen["lemmas"][0]) or {}).get("n") or "")
    if number != "5185":
        return False
    joined = "".join(surf for surf, _code in chosen["pieces"]) + chosen["stem"]
    if chosen.get("suf"):
        joined += chosen["suf"][0]
    return weak["stem"] == joined


def _blocks_auto(chosen, weak, lex):
    """Слабый hit на той же или меньшей глубине не даёт auto. Более глубокий — нет."""
    depth = len(chosen["pieces"])
    for hit in weak:
        if len(hit["pieces"]) > depth:
            continue
        if _unsplit_same_lemma(hit, chosen, lex):
            continue
        return True
    return False


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


def _raw_cons(word):
    out = []
    for ch in word or "":
        if ch not in geez.SYLLABLE:
            continue
        cons = geez.SYLLABLE[ch][0]
        if cons.endswith("ʷ"):
            cons = cons[:-1]
        out.append(cons)
    return out


def _attested_cons(lex, eid):
    """Согласные, которые статья пишет сама, без свёртки омофонов."""
    item = lex.items.get(eid) or {}
    head = item.get("head") or ""
    words = [head]
    for form in item.get("forms") or []:
        if is_single(form):
            words.append(form)
    for tok in _token_set(lex, eid):
        # Вариант заголовка (ወጽአ при ወፅአ) пишет свою букву. Чужое слово
        # той же статьи (ሠዋዒ при ተዐስየ) — нет: длина согласных другая.
        if head and _spelling_variant(head, tok):
            words.append(tok)
            continue
        if head and abs(syllables(tok) - syllables(head)) > 3:
            continue
        if head and not _raw_root_ok(head, tok):
            continue
        words.append(tok)
    found = set()
    for word in words:
        found.update(_raw_cons(word))
    return found


def _spelling_unattested(text, lex, eid):
    """В слове есть ሠ/ሐ/ዐ/ፀ, а статья знает только свёрнутый омофон."""
    attested = _attested_cons(lex, eid)
    used = set(_raw_cons(text))
    for group in _FOLD_GROUPS:
        here = used & group
        there = attested & group
        if here and there and not here <= there:
            return True
    return False


def _sade_mismatch(text, lex, eid):
    """В слове ጸ, а статья пишет только ፀ, или наоборот.

    Свёртка ṣ/ḍ находит кандидата. Она не выбирает лемму, если рядом
    есть статья, которая пишет букву этого слова.
    """
    group = {"ṣ", "ḍ"}
    here = set(_raw_cons(text)) & group
    there = _attested_cons(lex, eid) & group
    return bool(here and there and not here <= there)


# Только показатели перед цитатой. ተ не снимаем: это приставка породы.
_BARE_CLITICS = ("እም", "ዘ", "ኢ", "ወ", "በ", "ለ")


def _clitic_bares(form):
    """Форма и она же без начальных ዘ/ኢ/ወ. ዘኢይትፌጸም даёт и ይትፌጸም."""
    found = []
    seen = set()
    stack = [form]
    while stack:
        cur = stack.pop()
        if cur in seen or not is_single(cur) or syllables(cur) < 2:
            continue
        seen.add(cur)
        found.append(cur)
        for pref in _BARE_CLITICS:
            if cur.startswith(pref) and len(cur) > len(pref) + 1:
                stack.append(cur[len(pref):])
    return found


def _singular_u(surface):
    """ይትፌጸሙ → ይትፌጸም. Только гласный u последнего слога, не чужое окончание."""
    chars = _syls(surface)
    if not chars or geez.SYLLABLE[chars[-1]][1] != "u":
        return None
    sixth = _as_sixth(chars[-1])
    if not sixth:
        return None
    return "".join(chars[:-1]) + sixth


def _printed_owners(lex, surface):
    """Статьи, где Дильман напечатал эту поверхность, в том числе после ዘ/ኢ."""
    if not surface:
        return []
    found = list(lex.by_bare.get(surface) or [])
    singular = _singular_u(surface)
    if singular and singular != surface:
        for eid in lex.by_bare.get(singular) or []:
            if eid not in found:
                found.append(eid)
    return found


def _sade_head_variant(lex, left, right):
    """Два заголовка различаются только ጸ/ፀ. ተፈጸመ и ተፈፅመ — такая пара."""
    h1 = (lex.items.get(left) or {}).get("head") or ""
    h2 = (lex.items.get(right) or {}).get("head") or ""
    c1 = _raw_cons(h1)
    c2 = _raw_cons(h2)
    if not c1 or len(c1) != len(c2):
        return False
    differ = False
    for a, b in zip(c1, c2):
        if a == b:
            continue
        if {a, b} <= {"ṣ", "ḍ"}:
            differ = True
            continue
        return False
    return differ


def _twin_claims(lex, twin, chosen, stem, head):
    """Вторая статья с тем же заголовком претендует на эту форму.

    Не на любую личную форму глагола: n=1777 «nectere» не печатает ይሠርቅ,
    и Сонет оставил n=1768. Иначе 15 слов ሠረቀ и 67 слов ለ стали бы unsure.
    """
    del chosen
    if stem == head:
        return True
    return twin in (lex.by_form.get(stem) or []) or twin in (lex.built.get(stem) or [])


def _target_claims_head(lex, target, head):
    item = lex.items.get(target) or {}
    if target not in lex.verbal and not is_verb(item):
        return False
    if head in (item.get("forms") or []):
        return True
    return head in _token_set(lex, target)


def _homonym_twins(lex, eid, stem, head):
    twins = []
    for tid in lex.by_head.get(head) or []:
        if tid == eid or _is_letter(lex, tid):
            continue
        targets = pointer_targets(lex, tid)
        if targets is not None:
            for target in targets:
                if target == eid or target in twins:
                    continue
                if _target_claims_head(lex, target, head):
                    twins.append(target)
            continue
        if _is_stub(lex, tid):
            continue
        if _twin_claims(lex, tid, eid, stem, head) and tid not in twins:
            twins.append(tid)
    return twins


def _strip_letter_lemmas(lex, rec):
    """Буква алфавита не остаётся леммой и не остаётся кандидатом."""
    for seg in rec.get("segs") or []:
        eid = seg.get("lemma")
        if eid and _is_letter(lex, eid):
            seg["lemma"] = None
            rec["status"] = "unsure"
            rec["gram"] = None
    rec["alts"] = [eid for eid in (rec.get("alts") or []) if not _is_letter(lex, eid)]
    return rec


def _apply_homonyms(text, lex, rec):
    """Две содержательные статьи с одним заголовком не выбираются молча.

    Пустая и отсылочная не мешают. ቦ уже решён как n=3741, не как омоним n=3740.
    """
    if rec.get("status") != "auto":
        return rec
    lemma = _lemma_id(rec)
    if not lemma:
        return rec
    item = lex.items.get(lemma) or {}
    if str(item.get("n") or "") == "3741":
        stem_bo = next((seg.get("t") for seg in rec["segs"] if seg.get("lemma") == lemma), "")
        if stem_bo == "ቦ":
            return rec
    stem = None
    for seg in rec.get("segs") or []:
        if seg.get("lemma") == lemma:
            stem = seg.get("t")
            break
    head = item.get("head") or ""
    if not stem or not head:
        return rec
    twins = _homonym_twins(lex, lemma, stem, head)
    if not twins:
        return rec
    for seg in rec["segs"]:
        if seg.get("lemma") == lemma:
            seg["lemma"] = None
    alts = [lemma]
    for tid in twins:
        if tid not in alts:
            alts.append(tid)
    rec["status"] = "unsure"
    rec["gram"] = None
    rec["alts"] = alts
    bit = "одноимённые статьи, не выбираю молча: " + _names(lex, alts[:6])
    note = rec.get("note") or ""
    rec["note"] = (note + "; " + bit).strip("; ")
    return rec


def _note_cuts(hits):
    cuts = []
    for hit in hits:
        parts = [surf for surf, _code in hit["pieces"]]
        parts.append(hit["stem"])
        if hit["suf"]:
            parts.append(hit["suf"][0])
        cuts.append("+".join(parts))
    return "нарезки: " + " | ".join(cuts[:6])


def _peel_numbered_mengel(text):
    """Число, приклеенное к መንገለ: ፫መንገለ, ወ፫መንገለ, ፩ወ፫መንገለ.

    Возвращает сегменты до основы или None. Голое መንገለ и приставки без числа
    разбирает обычный путь.
    """
    core = "መንገለ"
    if not text.endswith(core) or len(text) <= len(core):
        return None
    rest = text[: -len(core)]
    if not any(ch in geez.NUMBER for ch in rest):
        return None
    segs = []
    pos = 0
    if rest.startswith("ወ") and len(rest) > 1 and rest[1] in geez.NUMBER:
        segs.append(("ወ", "c"))
        pos = 1
    if pos >= len(rest) or rest[pos] not in geez.NUMBER:
        return None
    start = pos
    while pos < len(rest) and rest[pos] in geez.NUMBER:
        pos += 1
    while (
        pos < len(rest)
        and rest[pos] == "ወ"
        and pos + 1 < len(rest)
        and rest[pos + 1] in geez.NUMBER
    ):
        pos += 1
        while pos < len(rest) and rest[pos] in geez.NUMBER:
            pos += 1
    segs.append((rest[start:pos], None))
    if rest.startswith("ኢ", pos):
        segs.append(("ኢ", "i"))
        pos += len("ኢ")
    for surf, code in (("እም", "m"), ("ዘ", "s"), ("በ", "b"), ("ለ", "l")):
        if rest.startswith(surf, pos):
            segs.append((surf, code))
            pos += len(surf)
            break
    if pos != len(rest):
        return None
    return segs


def _mengel_note(lex, verse, lemma):
    note = "форма መንገለ напечатана у መንገል n=5185; n=5184 ነገለ — radix inusitata, не лемма"
    if lemma and _cited(lex, verse, [lemma]):
        note += "; Дильман ссылается на этот стих"
    return note


def _mengel_record(text, pieces, lex, verse):
    """pieces — сегменты перед основой መንገለ. Лемма всегда n=5185."""
    lemma = lex.by_n.get("5185")
    segs = [
        {"t": surf, "lemma": None, "prefix": code, "morph": None}
        for surf, code in pieces
    ]
    segs.append({"t": "መንገለ", "lemma": lemma, "prefix": None, "morph": None})
    if "".join(seg["t"] for seg in segs) != text or not lemma:
        return None
    return {
        "status": "auto",
        "segs": segs,
        "gram": "предлог",
        "alts": [],
        "note": _mengel_note(lex, verse, lemma),
    }


def _finish_mengel(verse, lex, rec):
    """Предлог n=5185. Отсылку n=1410 и пустой корень n=5184 в лемму не оставляем."""
    lemma = _lemma_id(rec)
    if str((lex.items.get(lemma) or {}).get("n") or "") != "5185":
        return rec
    if not any(seg.get("t") == "መንገለ" for seg in rec.get("segs") or []):
        return rec
    if rec.get("status") != "auto":
        return rec
    rec["gram"] = "предлог"
    rec["alts"] = []
    rec["note"] = _mengel_note(lex, verse, lemma)
    return rec


def analyze(text, verse, lex):
    """verse — (глава, стих) или None. Возвращает запись morph для одного слова."""
    text = unicodedata.normalize("NFC", text)
    numbered = _peel_numbered_mengel(text)
    if numbered is not None:
        rec = _mengel_record(text, numbered, lex, verse)
        if rec is not None:
            return rec
    if is_number(text):
        return {
            "status": "unsure",
            "segs": [{"t": text, "lemma": None, "prefix": None, "morph": None}],
            "gram": "число",
            "alts": [],
            "note": "эфиопское число; нет в словаре Дильмана",
        }
    hits = _prefer_confident(_dedupe(prepare_hits(text, exact_hits(text, lex), lex)), lex)
    confident = [hit for hit in hits if not hit["ambiguous"]]
    weak = [hit for hit in hits if hit["ambiguous"]]
    note = []
    gram = None
    alts = []
    status = "unsure"
    chosen = None
    lemma = None
    if len(confident) == 1 and len(confident[0]["lemmas"]) == 1 and not _blocks_auto(confident[0], weak, lex):
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
            if str((lex.items.get(lemma) or {}).get("n") or "") == "3741" and chosen["stem"] == "ቦ":
                note.append("ቦ — «есть» n=3741; n=3740 тоже пишет ቦ как «в нём», не выбран")
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
            alts = [eid for eid in alts if not _is_letter(lex, eid)]
            cited_ids = [eid for eid in cited_ids if not _is_letter(lex, eid)]
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
    rec = {
        "status": status,
        "segs": _segs(text, chosen, lemma),
        "gram": gram,
        "alts": alts,
        "note": "; ".join(note),
    }
    rec = _apply_deriv(text, lex, rec)
    rec = _apply_homonyms(text, lex, rec)
    rec = _strip_letter_lemmas(lex, rec)
    rec = _add_rootless_form(text, lex, rec)
    return _finish_mengel(verse, lex, rec)


def _lemma_id(rec):
    for seg in rec.get("segs") or []:
        if seg.get("lemma"):
            return seg["lemma"]
    return None


def _deriv_splits(text):
    """(приставки предложения, остаток, приставка породы, класс, тело без неё)."""
    found = []
    for pieces, rest in chains(text, allow_k=True):
        for pref, klass in _DERIV_PREFIX:
            if rest.startswith(pref) and len(rest) > len(pref):
                found.append((pieces, rest, pref, klass, rest[len(pref):]))
                break
    return found


def _stem_articles(lex, klass, body):
    """Статьи этой породы, чей корень совпал с телом формы."""
    found = []
    for variant in (body, _strip_plural_alef(body)):
        key = _key_cons(variant)
        if not key:
            continue
        for eid in lex.by_class_strong.get((klass, key), []):
            if eid not in found:
                found.append(eid)
    return found


def _nonverb_candidate(rec, lex):
    ids = []
    lemma = _lemma_id(rec)
    if lemma:
        ids.append(lemma)
    ids.extend(rec.get("alts") or [])
    for eid in ids:
        item = lex.items.get(eid) or {}
        if eid in lex.verbal or is_verb(item):
            continue
        if item.get("head"):
            return True
    return False


def _verb_class(lex, eid):
    item = lex.items.get(eid) or {}
    if eid not in lex.verbal and not is_verb(item):
        return None
    classes = _stem_classes(item)
    return classes[0] if classes else None


def _pack_deriv(text, lex, pieces, surface, suf, eids, klass, pref):
    """Одна статья этой породы может быть auto. Несколько — только unsure."""
    ambiguous = len(eids) != 1 or (suf is not None and suf[2])
    status = "unsure" if ambiguous or len(eids) != 1 else "auto"
    lemma = eids[0] if len(eids) == 1 else None
    alts = [] if lemma else list(eids)
    hit = _hit(pieces, surface, (suf[0], suf[1]) if suf else None, eids, "stem", status != "auto")
    if lemma and suf and suf[0] == "ኒ":
        hit = _apply_particle(hit, lex) or hit
        status = "unsure"
    segs = _segs(text, hit, lemma)
    if "".join(seg["t"] for seg in segs) != text:
        return None
    gram = coarse_gram(lex.items[lemma]) if lemma and status == "auto" else None
    if len(eids) == 1:
        note = f"приставка {pref}: статья {_DERIV_NAME[klass]} основы"
    else:
        note = f"приставка {pref}: несколько статей {_DERIV_NAME[klass]} основы"
    if status == "auto" and lemma and _spelling_unattested(text, lex, lemma):
        for seg in segs:
            if seg.get("lemma") == lemma:
                seg["lemma"] = None
        status = "unsure"
        gram = None
        alts = [lemma]
        lemma = None
        note += "; написание отличается омофоном, в статье этой буквы нет"
    return {
        "status": status,
        "segs": segs,
        "gram": gram,
        "alts": alts,
        "note": note,
    }


def _clear_wrong_class(rec, lex, klass):
    """Чужая основа не остаётся леммой и не остаётся единственным кандидатом."""
    kept = []
    for eid in rec.get("alts") or []:
        cur = _verb_class(lex, eid)
        if cur and cur != klass:
            continue
        kept.append(eid)
    for seg in rec.get("segs") or []:
        eid = seg.get("lemma")
        if not eid:
            continue
        cur = _verb_class(lex, eid)
        if cur and cur != klass:
            seg["lemma"] = None
    rec["status"] = "unsure"
    rec["gram"] = None
    rec["alts"] = kept
    rec["note"] = f"приставка основы {_DERIV_NAME[klass]}: такой статьи нет"
    return rec


def _t_initial_head(pref, lex, lemma):
    """ይትርፍ у ተርፈ — приставка лица плюс радикал t, не порода III.

    У III заголовок тоже на ተ. Это приставка породы, не радикал: иначе
    чужая статья III (ተፈፅመ при тексте на ጸ) не отдаёт место своей.
    """
    if pref not in {"ይት", "ትት", "እት", "ንት"} or not lemma:
        return False
    if _verb_class(lex, lemma) == "III":
        return False
    head = (lex.items.get(lemma) or {}).get("head") or ""
    return head.startswith("ተ")


def _apply_deriv(text, lex, rec):
    """ያ-/ይት-/ያስተ- берут статью своей породы. Нет такой статьи — не I основа."""
    splits = _deriv_splits(text)
    if not splits:
        return rec
    lemma = _lemma_id(rec)
    splits = [split for split in splits if not _t_initial_head(split[2], lex, lemma)]
    if not splits:
        return rec
    if not lemma and _nonverb_candidate(rec, lex):
        # ታሕቱ — имя с «его», не каузатив от другого корня.
        return rec
    # Омофон ṣ/ḍ уже мог выбрать статью с чужой буквой (ይትፌጸም → ተፈፅመ).
    # Тогда ищем статью той же породы, которая пишет букву слова.
    retry_sade = False
    if lemma:
        cur = _verb_class(lex, lemma)
        if cur is None:
            return rec
        same = any(klass == cur and pref in _DERIV_ALWAYS for _p, _r, pref, klass, _b in splits)
        if same and not _sade_mismatch(text, lex, lemma):
            return rec
        if same:
            retry_sade = True
    matches = []
    for pieces, _rest, pref, klass, body in splits:
        if pref not in _DERIV_ALWAYS:
            if not lemma or _verb_class(lex, lemma) in (None, klass):
                continue
        options = list(_stem_options(body, SUFFIXES))
        for stem, suf, _amb in _stem_options(body, EXTRA_SUFFIXES):
            if suf is not None:
                options.append((stem, suf, True))
        for stem, suf, amb in options:
            eids = _stem_articles(lex, klass, stem)
            if not eids:
                continue
            if pref not in _DERIV_ALWAYS and len(eids) != 1:
                continue
            surface = pref + stem
            packed_suf = None if suf is None else (suf[0], suf[1], amb)
            matches.append((len(pieces), pieces, surface, packed_suf, eids, klass, pref))
    if not matches:
        if retry_sade:
            return rec
        if lemma and _verb_class(lex, lemma) not in (None,):
            # Приставка есть, а лемма — глагол другой породы.
            klasses = [klass for _p, _r, pref, klass, _b in splits if pref in _DERIV_ALWAYS or lemma]
            klass = next((k for _p, _r, pref, k, _b in splits if pref in _DERIV_ALWAYS), None)
            if klass and _verb_class(lex, lemma) != klass:
                return _clear_wrong_class(rec, lex, klass)
            if any(pref not in _DERIV_ALWAYS for _p, _r, pref, _k, _b in splits):
                klass = next(k for _p, _r, pref, k, _b in splits if pref not in _DERIV_ALWAYS)
                if _verb_class(lex, lemma) != klass:
                    return _clear_wrong_class(rec, lex, klass)
        elif not lemma:
            klass = next((k for _p, _r, pref, k, _b in splits if pref in _DERIV_ALWAYS), None)
            if klass:
                return _clear_wrong_class(rec, lex, klass)
        return rec
    matches.sort(key=lambda item: (item[0], len(item[4]), 0 if item[3] is not None else 1))
    best_depth = matches[0][0]
    pool = [item for item in matches if item[0] == best_depth]
    eids = []
    for item in pool:
        for eid in item[4]:
            if eid not in eids:
                eids.append(eid)
    # ጸ/ፀ одного корня: остаётся статья, где строка напечатана.
    # Сосед с другой буквой отпадает. Чужой корень в том же списке (ያፀምኡ) остаётся.
    if any(_sade_mismatch(text, lex, eid) for eid in eids):
        decided = None
        decided_item = None
        for item in pool:
            if item[3] is not None:
                continue
            owners = [eid for eid in _printed_owners(lex, item[2]) if eid in item[4]]
            if len(owners) != 1:
                continue
            owner = owners[0]
            rest = [eid for eid in item[4] if eid != owner]
            if rest and all(_sade_head_variant(lex, owner, eid) for eid in rest):
                decided = owner
                decided_item = item
                break
        if decided is not None:
            pool = [(
                decided_item[0], decided_item[1], decided_item[2], decided_item[3],
                [decided], decided_item[5], decided_item[6],
            )]
            eids = [decided]
    if retry_sade and (not eids or lemma in eids):
        return rec
    # Окончание, которое снимается однозначно, предпочтительнее целого слова.
    clean = [
        item for item in pool
        if item[4] == eids and (item[3] is None or not item[3][2])
    ]
    use = clean[0] if clean else pool[0]
    pieces, surface, suf, klass, pref = use[1], use[2], use[3], use[5], use[6]
    packed = _pack_deriv(text, lex, pieces, surface, suf, eids, klass, pref)
    return packed or rec


def _add_rootless_form(text, lex, rec):
    """Форма из чужой статьи без корня не становится леммой. Только alt."""
    if rec.get("status") == "auto" or _lemma_id(rec):
        return rec
    extra = []
    for eid in lex.form_weak.get(text, []):
        if eid not in extra and eid not in (rec.get("alts") or []):
            extra.append(eid)
    if not extra:
        return rec
    rec["alts"] = list(rec.get("alts") or []) + extra
    bit = "форма из цитаты без корня заголовка; не auto: " + _names(lex, extra[:4])
    note = rec.get("note") or ""
    rec["note"] = (note + "; " + bit).strip("; ")
    rec["status"] = "unsure"
    return rec


def _manual(path):
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    for word in (data.get("words") or {}).values():
        if word.get("status") not in ("auto", "unsure"):
            return True
    return False


def _manual_word(word):
    """Решение сверки. Повторный прогон тегера его не заменяет."""
    if not word:
        return False
    if word.get("status") == "checked":
        return True
    return str(word.get("note") or "").startswith("Ручное:")


def _keep_manual_words(path, data):
    """В главах 17–108 оставляет checked и помету «Ручное:». Остальное — новый разбор."""
    if not path.exists():
        return data, 0
    old = json.loads(path.read_text(encoding="utf-8"))
    kept = 0
    for wid, word in data.get("words", {}).items():
        prev = (old.get("words") or {}).get(wid)
        if not _manual_word(prev):
            continue
        old_surf = "".join(seg.get("t") or "" for seg in prev.get("segs") or [])
        new_surf = "".join(seg.get("t") or "" for seg in word.get("segs") or [])
        if old_surf != new_surf:
            continue
        data["words"][wid] = prev
        kept += 1
    return data, kept


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
        if number < 17 and _manual(path) and not force:
            print(f"глава {number}: оставлен ручной файл")
            continue
        data = tag_chapter(chapter, lex)
        if number >= 17 and path.exists() and not force:
            data, kept = _keep_manual_words(path, data)
            if kept and kept == len(data.get("words") or {}):
                print(f"глава {number}: ручные решения сохранены, файл не переписан")
                continue
            if kept:
                print(f"глава {number}: сохранено ручных слов {kept}")
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
