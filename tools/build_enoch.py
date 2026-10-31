"""Собирает данные 1 Еноха. Перевода нет.

Вход (только чтение): sources/enoch-bm, sources/dillmann-lexicon (zip),
sources/first1k-enoch, sources/smirnov-enoch, morph/enoch, corpus-input/enoch-verses.json.
Существующий enoch-verses.json не перезаписывается: его карта стихов важнее автоматики.

Выход: corpus/enoch/1En/NNN.json, corpus/enoch/books.json, corpus/geez-lexemes.json,
corpus/geez-occurrences.json, corpus/enoch-build-report.json.
Если карты стихов ещё нет, она создаётся один раз.
"""
import difflib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import geez

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
CORPUS = ROOT / "corpus"
MORPH = ROOT / "morph" / "enoch"
VERSES_PATH = ROOT / "corpus-input" / "enoch-verses.json"
VARIANTS_PATH = ROOT / "corpus-input" / "enoch-variants.json"
EXTRA_PATH = ROOT / "corpus-input" / "enoch-extra.json"
ZIP_NAME = "DillmannData-4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e.zip"

NS_ID = "{http://www.w3.org/XML/1998/namespace}id"
SKIP_TAGS = {"note", "pb", "lb", "cb", "gap", "figure"}
# Порог слабого выравнивания — наша отсечка для отчёта, не требование проекта.
WEAK_RATIO = 0.85
HEN_BOOKS = {"Hen", "Henoch", "En", "Enoch"}


def strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
        el.attrib = {k.split("}", 1)[-1]: v for k, v in el.attrib.items()}
    return root


def parse_xml_bytes(data):
    return strip_ns(ET.fromstring(data))


def parse_xml(path):
    return strip_ns(ET.parse(path).getroot())


def plain(el):
    """Текст элемента без сносок и без номеров страниц."""
    if el.tag in SKIP_TAGS:
        return ""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in list(el):
        if child.tag in SKIP_TAGS:
            if child.tail:
                parts.append(child.tail)
            continue
        parts.append(plain(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def word_id(n):
    return f"e{n:05d}"


def tokenize(text):
    """Слова ed1/EOTC. ፡ и пробел только делят слова. ። — граница Дильмана, даже если вокруг пробелы.
    Прочая пунктуация (፤ ፣ …) пишется к предыдущему слову и сама словом не является.
    Квадратные скобки [ ] — пометы оцифровки, не слова: снимаются и возвращаются отдельно."""
    words = []
    stops = []
    other = []
    brackets = []
    buf = []

    def flush(stop, extra):
        if not buf:
            return False
        raw = "".join(buf)
        buf.clear()
        if "[" in raw or "]" in raw:
            brackets.append(raw)
            raw = raw.replace("[", "").replace("]", "")
        if not raw or raw in "[]":
            return False
        words.append(raw)
        stops.append(stop)
        other.append(extra)
        return True

    for ch in text:
        if ch in "[]":
            buf.append(ch)
            continue
        if ch == "።":
            if not flush(True, ""):
                if stops:
                    stops[-1] = True
            continue
        if ch in geez.SEPARATORS or ch.isspace():
            extra = "" if ch.isspace() or ch == "፡" or ch == "፠" else ch
            if not flush(False, extra) and extra and other:
                other[-1] += extra
            continue
        buf.append(ch)
    flush(False, "")
    return words, stops, other, brackets


def translit_word(word):
    try:
        return geez.transliterate(word)
    except ValueError as exc:
        return None, str(exc)


def chapters_of(edition_div):
    return [
        d for d in edition_div.iter("div")
        if d.attrib.get("type") == "textpart" and d.attrib.get("subtype") == "chapter"
    ]


def load_editions(path):
    root = parse_xml(path)
    editions = {}
    for div in root.iter("div"):
        if div.attrib.get("type") == "edition" and div.attrib.get("id"):
            editions[div.attrib["id"]] = div
    if "ed1" not in editions or "EOTCed" not in editions:
        raise SystemExit(f"в {path.name} нет ed1 или EOTCed, есть: {sorted(editions)}")
    ed1 = []
    for div in chapters_of(editions["ed1"]):
        n = div.attrib.get("n")
        ab = next((c for c in list(div) if c.tag == "ab"), None)
        raw = plain(ab) if ab is not None else ""
        words, stops, other, brackets = tokenize(raw)
        ed1.append({
            "n": int(n), "words": words, "stops": stops, "other": other,
            "brackets": brackets, "raw": raw,
        })
    eotc = []
    for div in chapters_of(editions["EOTCed"]):
        n = int(div.attrib.get("n"))
        verses = []
        for line in div.iter("l"):
            raw = collapse(plain(line))
            w, _s, _o, _b = tokenize(plain(line))
            verses.append({"n": line.attrib.get("n"), "text": raw, "words": w})
        eotc.append({"n": n, "verses": verses})
    return ed1, eotc


def align_chapter(ed_words, eotc_verses):
    """Номера стихов EOTC на слова ed1. Ключ — согласный скелет, без гласных."""
    eo_sk = []
    eo_v = []
    for verse in eotc_verses:
        try:
            vn = int(verse["n"])
        except (TypeError, ValueError):
            vn = verse["n"]
        for word in verse["words"]:
            eo_sk.append(geez.skeleton(word))
            eo_v.append(vn)
    ed_sk = [geez.skeleton(w) for w in ed_words]
    if not ed_sk:
        return [], 1.0, False
    matcher = difflib.SequenceMatcher(a=ed_sk, b=eo_sk, autojunk=False)
    assigned = [None] * len(ed_sk)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("equal", "replace") or j2 <= j1:
            continue
        span_e = i2 - i1
        span_o = j2 - j1
        for k in range(span_e):
            j = j1 + min(span_o - 1, k * span_o // span_e)
            assigned[i1 + k] = eo_v[j]
    prev = None
    for i, verse in enumerate(assigned):
        if verse is None:
            assigned[i] = prev
        else:
            prev = verse
    nxt = None
    for i in range(len(assigned) - 1, -1, -1):
        if assigned[i] is None:
            assigned[i] = nxt
        else:
            nxt = assigned[i]
    nonmono = False
    last = None
    for verse in assigned:
        if verse is None:
            continue
        if last is not None and isinstance(verse, int) and isinstance(last, int) and verse < last:
            nonmono = True
        last = verse
    return assigned, matcher.ratio(), nonmono


def starts_from_assigned(assigned):
    """Первое слово каждого номера стиха, в порядке появления."""
    starts = {}
    for i, verse in enumerate(assigned):
        if verse is None:
            continue
        key = str(verse)
        if key not in starts:
            starts[key] = i
    return starts


def load_verse_override():
    if not VERSES_PATH.exists():
        return None
    data = json.loads(VERSES_PATH.read_text(encoding="utf-8"))
    return {str(k): v for k, v in data.items() if str(k).isdigit()}


def partition(words, starts):
    """Режет список слов по началам стихов. Каждое слово ровно в одном стихе."""
    if not words:
        return []
    items = []
    for key, idx in starts.items():
        try:
            n = int(key)
        except ValueError:
            n = key
        items.append((idx, n, key))
    items.sort()
    if not items or items[0][0] != 0:
        # Слова до первой указанной границы остаются в первом стихе.
        if items:
            items[0] = (0, items[0][1], items[0][2])
        else:
            items = [(0, 1, "1")]
    verses = []
    for i, (idx, n, _key) in enumerate(items):
        end = items[i + 1][0] if i + 1 < len(items) else len(words)
        if end < idx:
            end = idx
        verses.append({"n": n, "words": words[idx:end]})
    # Хвост, если последняя граница смотрела мимо конца, уже включён.
    # Дыра из-за одинаковых индексов: пустые стихи не создаём, слова не пропадают,
    # потому что следующий стих с тем же индексом забирает тот же срез — это дубль.
    # Одинаковые индексы схлопываем.
    cleaned = []
    for verse in verses:
        if cleaned and verse["words"] and cleaned[-1]["words"] and verse["words"][0] is cleaned[-1]["words"][0]:
            continue
        if not verse["words"] and cleaned:
            continue
        cleaned.append(verse)
    return cleaned


def _inner_template(inner):
    name = inner.split("|", 1)[0].strip()
    # Сноски и номер главы в ярлыке. Текст стиха от этого не переписывается.
    if name in ("r", "roman", "примечания", "ПримВТ"):
        return ""
    parts = [p for p in inner.split("|")]
    return parts[-1] if len(parts) > 1 else ""


def wiki_plain(text):
    """Снимает вики-разметку. Слова Смирнова не заменяются другими словами."""
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\{\{([^{}]*)\}\}", lambda m: _inner_template(m.group(1)), text)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    return collapse(text)


def top_templates(text):
    """Внешние шаблоны {{...}}. Вложенные остаются внутри внешнего."""
    found = []
    i = 0
    while True:
        start = text.find("{{", i)
        if start < 0:
            break
        k = start + 2
        depth = 1
        while k < len(text) and depth:
            if text.startswith("{{", k):
                depth += 1
                k += 2
            elif text.startswith("}}", k):
                depth -= 1
                k += 2
            else:
                k += 1
        if depth:
            break
        found.append((start, k, text[start + 2:k - 2]))
        i = k
    return found


def _verse_blocks(block):
    """Нумерованные абзацы «1. …» второй серии Смирнова. Без номера — один кусок."""
    parts = re.split(r"(?:^|\n)\s*(\d+)\.\s+", block)
    if len(parts) == 1:
        text = wiki_plain(block)
        return [{"v": 1, "text": text}] if text else []
    out = []
    # parts[0] — текст до первой цифры
    head = wiki_plain(parts[0])
    if head:
        out.append({"v": 0, "text": head, "note": "текст отдела до первого номера"})
    it = iter(parts[1:])
    for num, chunk in zip(it, it):
        text = wiki_plain(chunk)
        if text:
            out.append({"v": int(num), "text": text})
    return out


def load_smirnov(path):
    """Две нумерации, обе сохраняются как у Смирнова.

    1) {{глава|N|ярлык}} и {{стих|N|V}} — главы 1–59, те же номера, что у современного деления.
       Текст шаблона глава — его стих 1.
    2) С десятого отдела {{глава|10}}…{{глава|20}} без ярлыка — это номер отдела, не глава 1 Ен.
       Стихи там — строки «1. 2. 3.». К главам 10–20 они не присоединяются: номера уже заняты первой серией.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    page = next(iter(data["query"]["pages"].values()))
    rev = page["revisions"][0]
    text = rev["slots"]["main"]["*"]
    cut = text.find("== Примечания ==")
    body = text if cut < 0 else text[:cut]
    marks = []
    for start, end, inner in top_templates(body):
        if inner.startswith("глава|") or inner.startswith("стих|"):
            marks.append((start, end, inner))
    verses = {}
    labels = []
    otdely = []
    for i, (start, end, inner) in enumerate(marks):
        kind, _, rest = inner.partition("|")
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        piece_raw = body[end:nxt]
        if kind == "стих":
            chap_s, _, verse_s = rest.partition("|")
            chap = int(chap_s)
            try:
                verse_n = int(verse_s.strip())
            except ValueError:
                verse_n = verse_s.strip()
            piece = wiki_plain(piece_raw)
            if piece:
                verses.setdefault((chap, verse_n), []).append(piece)
            continue
        # глава
        if "|" not in rest:
            # вторая серия: номер отдела
            otdel = int(rest.strip())
            otdely.append({"otdel": otdel, "verses": _verse_blocks(piece_raw)})
            continue
        chap_s, _, label = rest.partition("|")
        chap = int(chap_s)
        labels.append({"c": chap, "label": wiki_plain(label)})
        piece = wiki_plain(piece_raw)
        if piece:
            verses.setdefault((chap, 1), []).append(piece)
    meta = {
        "revid": rev.get("revid"),
        "parentid": rev.get("parentid"),
        "timestamp": rev.get("timestamp"),
        "user": rev.get("user"),
        "pageid": page.get("pageid"),
        "chars": len(text),
        "notesCut": cut >= 0,
        "labels": labels,
        "otdely": otdely,
    }
    return verses, meta


_GER_CUE = re.compile(
    r"(?:\b(?:der|die|das|und|den|dem|des|ein|eine|oder|nicht)\b)|(?:\bCap\.)",
    re.IGNORECASE,
)


def _token_kind(tok):
    """greek, если греческих букв не меньше латинских. Иначе latin или other."""
    greek = len(re.findall(r"[\u0370-\u03FF\u1F00-\u1FFF]", tok))
    latin = len(re.findall(r"[A-Za-zÄÖÜäöüß]", tok))
    if greek == 0 and latin == 0:
        return "other"
    if greek > 0 and greek >= latin:
        return "greek"
    if latin > 0:
        return "latin"
    return "other"


def german_spans(text):
    """Сплошной негреческий кусок, в котором есть немецкие слова или Cap. N.

    Кусок режется только по токенам. Греческое слово внутрь куска не входит.
    """
    tokens = list(re.finditer(r"\S+", text))
    spans = []
    index = 0
    while index < len(tokens):
        if _token_kind(tokens[index].group()) == "greek":
            index += 1
            continue
        end = index
        while end < len(tokens) and _token_kind(tokens[end].group()) != "greek":
            end += 1
        start_at = tokens[index].start()
        end_at = tokens[end - 1].end()
        chunk = text[start_at:end_at]
        if _GER_CUE.search(chunk):
            spans.append((start_at, end_at, chunk))
        index = end
    return spans


def strip_german(text):
    """Убрать немецкие абзацы. Греческие токены остаются теми же и в том же порядке.

    None вместо списка значит: вырезание съело бы греческий токен, текст не трогать.
    """
    spans = german_spans(text)
    if not spans:
        return text, []
    greek_before = [match.group() for match in re.finditer(r"\S+", text) if _token_kind(match.group()) == "greek"]
    out = text
    removed = []
    for start, end, raw in reversed(spans):
        left = out[:start].rstrip()
        right = out[end:].lstrip()
        if left and right:
            out = left + " " + right
        else:
            out = (left + right).strip()
        removed.append(raw)
    removed.reverse()
    greek_after = [match.group() for match in re.finditer(r"\S+", out) if _token_kind(match.group()) == "greek"]
    if greek_before != greek_after:
        return text, None
    return out, removed


def load_variants():
    """Список разночтений. Ключ — ref стиха."""
    if not VARIANTS_PATH.exists():
        return {}
    data = json.loads(VARIANTS_PATH.read_text(encoding="utf-8"))
    by_ref = {}
    for item in data:
        by_ref.setdefault(item["ref"], []).append({
            "wordIds": item.get("wordIds") or [],
            "witnesses": item.get("witnesses") or [],
        })
    return by_ref


def eotc_real_diffs(numbered, eotc):
    """Где EOTC расходится с ed1 не одной орфографией.

    Скелет с омофонами и краткими лабиовелярными. Равная свёртка в список не входит.
    Размер — сумма длин несовпавших кусков. В variants это не пишется.
    """
    eotc_by = {chapter["n"]: chapter for chapter in eotc}
    diffs = []
    for chapter in numbered:
        eo = eotc_by.get(chapter["chapter"])
        if not eo:
            continue
        eo_verses = {}
        for verse in eo["verses"]:
            try:
                number = int(verse["n"])
            except (TypeError, ValueError):
                number = verse["n"]
            eo_verses[number] = verse["words"]
        for verse in chapter["verses"]:
            eo_words = eo_verses.get(verse["n"])
            if not eo_words:
                continue
            ed_words = [word["text"] for word in verse["words"]]
            ed_sk = [geez.fold_skeleton(word) for word in ed_words]
            eo_sk = [geez.fold_skeleton(word) for word in eo_words]
            if ed_sk == eo_sk:
                continue
            matcher = difflib.SequenceMatcher(a=ed_sk, b=eo_sk, autojunk=False)
            score = 0
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal":
                    continue
                score += max(i2 - i1, j2 - j1)
            if score <= 0:
                continue
            diffs.append({
                "ref": verse["ref"],
                "score": score,
                "ed1": " ".join(ed_words),
                "eotc": " ".join(eo_words),
            })
    diffs.sort(key=lambda item: (-item["score"], item["ref"]))
    return {"count": len(diffs), "top": diffs[:100]}


def broken_tokens(text):
    """Явно битые куски OCR: скобки разметки, латиница внутри греческого, цифры в греческом слове.
    Ошибки, которые остаются греческими буквами (οἳτιωες), этот список не ловит."""
    found = []
    for tok in re.findall(r"\S+", text):
        greek = bool(re.search(r"[\u0370-\u03FF\u1F00-\u1FFF]", tok))
        latin = bool(re.search(r"[A-Za-z]", tok))
        if any(ch in tok for ch in "<>{}|_\\"):
            found.append(tok)
        elif greek and latin:
            found.append(tok)
        elif greek and re.search(r"\d", tok):
            found.append(tok)
    return found


def load_greek(path, edition):
    root = parse_xml(path)
    out = {}
    broken = []
    numbers = []
    for chap in chapters_of(root):
        raw_n = chap.attrib.get("n")
        try:
            cn = int(raw_n)
        except (TypeError, ValueError):
            cn = raw_n
        numbers.append(cn)
        for sec in chap.findall("div"):
            # Флемминг размечает стих как section, Свит и латинский отрывок — как verse.
            if sec.attrib.get("subtype") not in ("section", "verse"):
                continue
            raw_v = sec.attrib.get("n")
            try:
                vn = int(raw_v)
            except (TypeError, ValueError):
                vn = raw_v
            text = collapse(plain(sec))
            out.setdefault((cn, vn), []).append(text)
            for tok in broken_tokens(text):
                broken.append({"edition": edition, "c": cn, "v": vn, "token": tok})
    return out, broken, numbers


def own_text(el):
    parts = []
    if el.text:
        parts.append(el.text)
    for child in list(el):
        if child.tag in ("sense", "bibl", "note"):
            if child.tail:
                parts.append(child.tail)
            continue
        if child.tag == "ptr":
            if child.tail:
                parts.append(child.tail)
            continue
        parts.append(plain_keep(child))
        if child.tail:
            parts.append(child.tail)
    return collapse("".join(parts))


def plain_keep(el):
    if el.tag in ("bibl", "note", "ptr", "sense"):
        return ""
    parts = [el.text or ""]
    for child in list(el):
        if child.tag in ("bibl", "note", "ptr", "sense"):
            if child.tail:
                parts.append(child.tail)
            continue
        parts.append(plain_keep(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def gez_tokens(text):
    """Одно слово геэза. Словосочетание с ፡ не индексируется по частям."""
    text = text.strip().strip("፡።፣፤ ")
    if not text or any(ch in text for ch in "፡።፣፤ ") or any(ch.isspace() for ch in text):
        return []
    if not any("\u1200" <= ch <= "\u137F" for ch in text):
        return []
    return [text]


def normalize_hen(loc):
    refs = []
    if not loc:
        return refs
    for match in re.finditer(r"(\d+)\s*,\s*(\d+)(?:\s*[-–]\s*(\d+))?", loc):
        chap = int(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        if end < start or end - start > 40:
            refs.append(f"1En.{chap}.{start}")
            continue
        for verse in range(start, end + 1):
            refs.append(f"1En.{chap}.{verse}")
    # уникальные, в порядке появления
    seen = []
    for ref in refs:
        if ref not in seen:
            seen.append(ref)
    return seen


def load_lexicon(zip_path):
    lexemes = {}
    licence = Counter()
    no_licence = []
    rs_types = Counter()
    skipped = []
    with zipfile.ZipFile(zip_path) as zipped:
        names = sorted(n for n in zipped.namelist() if n.lower().endswith(".xml"))
        for name in names:
            raw = zipped.read(name)
            head = raw[:1800].decode("utf-8", errors="replace")
            found = re.findall(r'target="([^"]+)"', head)
            lic_hit = [t for t in found if "creativecommons" in t]
            if lic_hit:
                licence[lic_hit[0]] += 1
            else:
                no_licence.append(name.split("/")[-1])
            try:
                root = parse_xml_bytes(raw)
            except ET.ParseError:
                skipped.append(name)
                continue
            entry = root.find(".//entry")
            if entry is None:
                skipped.append(name)
                continue
            item = entry_to_lexeme(entry)
            if item["id"] in lexemes:
                skipped.append("duplicate:" + item["id"])
                continue
            lexemes[item["id"]] = item
    return lexemes, {"licenceTargets": dict(licence), "noLicence": no_licence, "skipped": skipped, "rsTypes": dict(rs_types)}


def entry_to_lexeme(entry):
    eid = entry.attrib.get("id")
    head_el = None
    for foreign in entry.findall("./form/foreign"):
        if foreign.attrib.get("lang") == "gez":
            head_el = foreign
            break
    head = collapse(plain(head_el)) if head_el is not None else ""
    head_word = head.strip("፡ ")
    tr, lat = (None, None)
    if head_word:
        tr, lat = translit_word(head_word)
        if tr is None:
            tr, lat = None, None
    rs = []
    root_flag = False
    for node in entry.findall("./form/rs"):
        kind = node.attrib.get("type")
        rs.append(kind)
        if kind == "root":
            root_flag = True
    pos = []
    for node in entry.iter("pos"):
        text = collapse(node.text or "")
        if text and text not in pos:
            pos.append(text)
    stems = []
    for node in entry.iter("subc"):
        text = collapse(plain(node))
        if text and text not in stems:
            stems.append(text)
    senses = []
    english = []
    transcriptions = []
    for sense in entry.iter("sense"):
        source = sense.attrib.get("source") or ""
        lang = sense.attrib.get("lang") or ""
        if source == "#traces" or (lang == "en" and source != "#dillmann"):
            text = own_text(sense)
            if text:
                english.append(text)
            continue
        if source == "#dillmann" or sense.attrib.get("id", "").startswith("D"):
            text = own_text(sense)
            if text:
                senses.append({"n": sense.attrib.get("n"), "text": text})
    for cit in entry.iter("cit"):
        if cit.attrib.get("type") == "transcription":
            quote = cit.find("quote")
            if quote is not None:
                text = collapse(plain(quote))
                if text and text not in transcriptions:
                    transcriptions.append(text)
    greek = []
    for foreign in entry.iter("foreign"):
        if foreign.attrib.get("lang") == "grc":
            text = collapse(plain(foreign))
            if text and text not in greek:
                greek.append(text)
    leslau = []
    for bibl in entry.iter("bibl"):
        ptr = bibl.find("ptr")
        if ptr is None:
            continue
        target = ptr.attrib.get("target", "")
        if "Leslau" not in target:
            continue
        page = ""
        cited = bibl.find("citedRange")
        if cited is not None:
            page = collapse(plain(cited))
        leslau.append({"target": target, "page": page})
    places = []
    enoch = []
    for ref in entry.iter("ref"):
        cref = ref.attrib.get("cRef")
        if not cref:
            continue
        loc = ref.attrib.get("loc") or ""
        raw = collapse(f"{cref} {loc}")
        book = cref.strip().rstrip(".").split()[0].rstrip(".")
        norm = normalize_hen(loc) if book in HEN_BOOKS else []
        places.append({"cRef": collapse(cref), "loc": collapse(loc), "raw": raw, "norm": norm})
        for item in norm:
            if item not in enoch:
                enoch.append(item)
    forms = []
    for token in gez_tokens(head_word):
        forms.append(token)
    for foreign in entry.iter("foreign"):
        if foreign.attrib.get("lang") != "gez" or foreign is head_el:
            continue
        for token in gez_tokens(collapse(plain(foreign))):
            if token not in forms:
                forms.append(token)
    parent = None
    for ref in entry.iter("ref"):
        target = ref.attrib.get("target") or ""
        if re.fullmatch(r"#?L[0-9a-fA-F]{8,}", target):
            parent = target.lstrip("#")
            break
    skel = geez.skeleton(head_word) if head_word else ""
    return {
        "id": eid,
        "n": entry.attrib.get("n"),
        "head": head_word,
        "tr": tr,
        "lat": lat,
        "transcription": transcriptions,
        "root": root_flag,
        "parent": parent,
        "rs": rs,
        "stem": stems,
        "pos": pos,
        "senses": senses,
        "en": english,
        "leslau": leslau,
        "places": places,
        "enoch": enoch,
        "greek": greek,
        "forms": forms,
        "skeleton": skel,
        "entryType": entry.attrib.get("type"),
    }


def merge_extra(lex_out):
    """Слова, которых нет у Дильмана: corpus-input/enoch-extra.json, ключ n-<lat>.

    Файл правится вручную и при каждой сборке вливается заново: zip словаря
    его не содержит. Совпавший с настоящей статьёй ключ не затирает её.
    """
    if not EXTRA_PATH.exists():
        return [], []
    extra = json.loads(EXTRA_PATH.read_text(encoding="utf-8"))
    defaults = {
        "n": None, "head": "", "tr": None, "lat": None, "transcription": [],
        "root": False, "parent": None, "rs": [], "stem": [], "pos": [],
        "senses": [], "en": [], "leslau": [], "places": [], "enoch": [],
        "greek": [], "forms": [], "skeleton": "", "entryType": None,
    }
    added, skipped = [], []
    for key in sorted(extra):
        raw = extra[key]
        if key in lex_out or not isinstance(raw, dict):
            skipped.append(key)
            continue
        item = {}
        for field, value in defaults.items():
            item[field] = list(value) if isinstance(value, list) else value
        item.update(raw)
        item["id"] = key
        item["notInDillmann"] = True
        if not item.get("skeleton") and item.get("head"):
            item["skeleton"] = geez.skeleton(item["head"])
        lex_out[key] = item
        added.append(key)
    return added, skipped


def load_morph(chapter):
    path = MORPH / f"{chapter:03d}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("words") or {}


def apply_morph(word, morph):
    if not morph:
        word["segs"] = [{"t": word["text"], "lemma": None, "prefix": None, "morph": None}]
        return
    word["segs"] = morph.get("segs") or [{"t": word["text"], "lemma": None, "prefix": None, "morph": None}]
    for key in ("status", "gram", "alts", "note"):
        if key in morph:
            word[key] = morph[key]


def boundary_report(words, stops, verses):
    """Граница стиха EOTC, которая не села на ። Дильмана."""
    problems = []
    offset = 0
    for verse in verses:
        if offset > 0 and offset <= len(stops) and not stops[offset - 1]:
            problems.append({
                "verse": verse["n"],
                "wordId": verse["words"][0]["id"] if verse["words"] else None,
                "prev": words[offset - 1]["text"] if offset else None,
                "word": verse["words"][0]["text"] if verse["words"] else None,
                "prevStop": False,
            })
        offset += len(verse["words"])
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tei_path = SOURCES / "enoch-bm" / "LIT1340EnochE.xml"
    zip_path = SOURCES / "dillmann-lexicon" / ZIP_NAME
    smirnov_path = SOURCES / "smirnov-enoch" / "Книга_Еноха.wikitext.json"
    greek_specs = [
        (SOURCES / "first1k-enoch" / "tlg1463.tlg001.1st1K-grc2.xml", "flemming1901"),
        (SOURCES / "first1k-enoch" / "tlg1463.tlg001.1st1K-grc1.xml", "swete1905"),
    ]
    latin_path = SOURCES / "first1k-enoch" / "tlg1463.tlg001.1st1K-lat1.xml"
    print("читаю ed1 и EOTC")
    ed1, eotc = load_editions(tei_path)
    eotc_by = {c["n"]: c for c in eotc}
    print("словарь Дильмана")
    lexemes, lex_meta = load_lexicon(zip_path)
    # rs types уже внутри статей
    rs_counter = Counter()
    for item in lexemes.values():
        for kind in item["rs"]:
            rs_counter[kind or ""] += 1
    lex_meta["rsTypes"] = dict(rs_counter)
    print("статей", len(lexemes))
    print("Смирнов и греческий")
    smirnov, smirnov_meta = load_smirnov(smirnov_path)
    greek = {}
    broken = []
    greek_chapters = {}
    for path, edition in greek_specs:
        mapping, bad, numbers = load_greek(path, edition)
        greek[edition] = mapping
        broken.extend(bad)
        greek_chapters[edition] = numbers
    latin_map, latin_broken, latin_chapters = load_greek(latin_path, "flemming1901-lat")
    override = load_verse_override()
    variants_by = load_variants()
    german_removed = []
    german_errors = []
    auto_map = {}
    numbered = []
    total = 0
    problems_tr = []
    gemination_hits = []
    rare_syllables = []
    editorial_brackets = []
    chapter_reports = []
    all_words = []
    weak = []
    not_on_stop = []
    nonmono = []
    leading_joined = []
    empty_verses = []
    for chapter in ed1:
        n = chapter["n"]
        records = []
        for text, stop, extra in zip(chapter["words"], chapter["stops"], chapter["other"]):
            total += 1
            tr, lat = translit_word(text)
            if tr is None:
                problems_tr.append({"id": word_id(total), "text": text, "error": lat})
                tr, lat = None, None
            if any(ch in text for ch in (geez.GEMINATION, geez.GEM_AND_LENGTH, geez.VOWEL_LENGTH)):
                gemination_hits.append(word_id(total))
            for ch in text:
                if ch in geez.SYLLABLE and geez.SYLLABLE[ch][5]:
                    rare_syllables.append({"id": word_id(total), "ch": ch, "name": __import__("unicodedata").name(ch)})
                    break
            records.append({
                "id": word_id(total),
                "text": text,
                "tr": tr,
                "lat": lat,
                "lang": "G",
                "stop": stop,
                "other": extra,
            })
        if chapter["brackets"]:
            editorial_brackets.append({"chapter": n, "tokens": chapter["brackets"]})
        eotc_ch = eotc_by.get(n)
        assigned, ratio, jumped = ([], 0.0, False)
        if eotc_ch:
            assigned, ratio, jumped = align_chapter(
                [r["text"] for r in records], eotc_ch["verses"]
            )
        auto_starts = starts_from_assigned(assigned)
        # в файл карты пишем id первого слова, не индекс
        auto_map[str(n)] = {}
        for key, idx in auto_starts.items():
            if 0 <= idx < len(records):
                auto_map[str(n)][key] = records[idx]["id"]
        use_manual = override is not None and str(n) in override
        if use_manual:
            id_to_index = {r["id"]: i for i, r in enumerate(records)}
            starts = {}
            bad_ids = []
            for key, wid in override[str(n)].items():
                if wid not in id_to_index:
                    bad_ids.append({"verse": key, "id": wid})
                else:
                    starts[str(key)] = id_to_index[wid]
            source = "manual"
        else:
            starts = {k: records.index(next(r for r in records if r["id"] == wid))
                      for k, wid in auto_map[str(n)].items()} if records else {}
            # индекс уже есть в auto_starts
            starts = auto_starts
            bad_ids = []
            source = "auto"
        if starts:
            first_idx = min(starts.values())
            if first_idx > 0:
                first_verse = min(starts, key=lambda k: (starts[k], str(k)))
                leading_joined.append({
                    "chapter": n,
                    "words": first_idx,
                    "joinedToVerse": str(first_verse),
                    "firstId": records[0]["id"],
                })
        slices = partition(records, starts)
        for verse in slices:
            if not verse["words"]:
                empty_verses.append({"chapter": n, "verse": verse["n"]})
        morph = load_morph(n)
        verses_out = []
        eotc_text = {}
        eotc_numbers = []
        if eotc_ch:
            for verse in eotc_ch["verses"]:
                try:
                    vn = int(verse["n"])
                except (TypeError, ValueError):
                    vn = verse["n"]
                eotc_text[vn] = verse["text"]
                eotc_numbers.append(vn)
        for verse in slices:
            words_out = []
            for rec in verse["words"]:
                word = {
                    "id": rec["id"],
                    "text": rec["text"],
                    "tr": rec["tr"],
                    "lat": rec["lat"],
                    "lang": "G",
                }
                apply_morph(word, morph.get(rec["id"]))
                words_out.append(word)
                all_words.append(word["id"])
            item = {"ref": f"1En.{n}.{verse['n']}", "n": verse["n"], "words": words_out}
            if verse["n"] in eotc_text:
                item["eotc"] = eotc_text[verse["n"]]
            sm = smirnov.get((n, verse["n"]))
            if sm:
                item["smirnov"] = [{"c": n, "v": verse["n"], "text": t} for t in sm]
            grc = []
            for edition, mapping in greek.items():
                for text in mapping.get((n, verse["n"]), []):
                    if edition == "flemming1901":
                        cleaned, parts = strip_german(text)
                        if parts is None:
                            german_errors.append({
                                "edition": edition, "c": n, "v": verse["n"],
                                "lengthBefore": len(text), "lengthAfter": len(text),
                                "text": text,
                                "error": "вырезание убрало бы греческий токен, стих оставлен как был",
                            })
                        elif parts:
                            for part in parts:
                                german_removed.append({
                                    "edition": edition,
                                    "c": n,
                                    "v": verse["n"],
                                    "text": part,
                                    "lengthBefore": len(text),
                                    "lengthAfter": len(cleaned),
                                })
                            text = cleaned
                    grc.append({"edition": edition, "c": n, "v": verse["n"], "text": text})
            if grc:
                item["grc"] = grc
            attached = variants_by.get(item["ref"])
            if attached:
                item["variants"] = attached
            verses_out.append(item)
        stops = [r["stop"] for r in records]
        bounds = boundary_report(
            [{"text": r["text"]} for r in records],
            stops,
            [{"n": v["n"], "words": v["words"]} for v in verses_out],
        )
        # boundary_report ждёт id внутри words — поправим вызов через verses_out
        bounds = []
        offset = 0
        for verse in verses_out:
            if offset > 0 and not stops[offset - 1]:
                bounds.append({
                    "chapter": n,
                    "verse": verse["n"],
                    "wordId": verse["words"][0]["id"],
                    "word": verse["words"][0]["text"],
                    "prev": records[offset - 1]["text"],
                })
            offset += len(verse["words"])
        if bounds:
            not_on_stop.extend(bounds)
        if ratio < WEAK_RATIO:
            weak.append({"chapter": n, "ratio": round(ratio, 4)})
        if jumped:
            nonmono.append(n)
        sm_nums = sorted({v for (c, v) in smirnov if c == n})
        grc_nums = {
            edition: sorted({v for (c, v) in mapping if c == n})
            for edition, mapping in greek.items()
        }
        chapter_reports.append({
            "chapter": n,
            "words": len(records),
            "dillmannStops": sum(1 for s in stops if s),
            "otherPunct": sum(1 for r in records if r["other"]),
            "eotcVerses": eotc_numbers,
            "ed1Verses": [v["n"] for v in verses_out],
            "smirnovVerses": sm_nums,
            "greekVerses": grc_nums,
            "ratio": round(ratio, 4),
            "nonmonotonic": jumped,
            "verseSource": source,
            "overrideProblems": bad_ids,
            "boundsNotOnStop": len(bounds),
        })
        numbered.append({"book": "1En", "chapter": n, "verses": verses_out})
    if override is None:
        VERSES_PATH.parent.mkdir(parents=True, exist_ok=True)
        VERSES_PATH.write_text(json.dumps(auto_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verse_file = "created"
    else:
        verse_file = "kept"
    out_dir = CORPUS / "enoch" / "1En"
    out_dir.mkdir(parents=True, exist_ok=True)
    for chapter in numbered:
        path = out_dir / f"{chapter['chapter']:03d}.json"
        path.write_text(json.dumps(chapter, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    books = [{"id": "1En", "name": "Енох", "chapters": len(numbered)}]
    (CORPUS / "enoch" / "books.json").write_text(
        json.dumps(books, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    # словарь: стабильный порядок ключей
    lex_out = {key: lexemes[key] for key in sorted(lexemes)}
    extra_added, extra_skipped = merge_extra(lex_out)
    lex_out = {key: lex_out[key] for key in sorted(lex_out)}
    (CORPUS / "geez-lexemes.json").write_text(
        json.dumps(lex_out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    occurrences = {}
    for item in lex_out.values():
        if item["enoch"]:
            occurrences[item["id"]] = {"words": [], "dillmann": item["enoch"]}
    for chapter in numbered:
        for verse in chapter["verses"]:
            for word in verse["words"]:
                for seg in word["segs"]:
                    lemma = seg.get("lemma")
                    if not lemma:
                        continue
                    bucket = occurrences.setdefault(lemma, {"words": [], "dillmann": []})
                    if word["id"] not in bucket["words"]:
                        bucket["words"].append(word["id"])
    for bucket in occurrences.values():
        bucket["words"].sort()
    occurrences = {key: occurrences[key] for key in sorted(occurrences)}
    (CORPUS / "geez-occurrences.json").write_text(
        json.dumps(occurrences, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    # покрытие разметки, если morph уже есть
    one = several = none = names = 0
    form_none = Counter()
    status_count = Counter()
    seg_mismatch = []
    for chapter in numbered:
        for verse in chapter["verses"]:
            for word in verse["words"]:
                joined = "".join((seg.get("t") or "") for seg in word["segs"])
                if joined != word["text"]:
                    seg_mismatch.append({"id": word["id"], "text": word["text"], "joined": joined})
                if "status" not in word:
                    continue
                status_count[word["status"]] += 1
                lemmas = [s.get("lemma") for s in word["segs"] if s.get("lemma")]
                alts = word.get("alts") or []
                note = word.get("note") or ""
                unlisted_name = (
                    word.get("gram") == "имя" and "в словаре нет" in note and not lemmas
                )
                if unlisted_name:
                    names += 1
                elif len(lemmas) == 1 and not alts:
                    one += 1
                elif lemmas or alts:
                    several += 1
                else:
                    none += 1
                    form_none[word["text"]] += 1
    tagged = one + several + none + names
    smirnov_only = []
    for (chap, verse), _texts in sorted(smirnov.items()):
        if not any(c["chapter"] == chap and any(v["n"] == verse for v in c["verses"]) for c in numbered):
            smirnov_only.append(f"1En.{chap}.{verse}" if isinstance(verse, int) else f"{chap}:{verse}")
    greek_unattached = []
    for edition, mapping in greek.items():
        for (chap, verse) in sorted(mapping, key=lambda x: (str(x[0]), str(x[1]))):
            if not any(c["chapter"] == chap and any(v["n"] == verse for v in c["verses"]) for c in numbered):
                greek_unattached.append({"edition": edition, "c": chap, "v": verse})
    report = {
        "book": "1En",
        "zipBytes": zip_path.stat().st_size,
        "verseFile": verse_file,
        "weakRatioThreshold": WEAK_RATIO,
        "transliteration": {
            "rule": "Шестой ряд внутри слова всегда ǝ, в конце слова без гласной. Удвоение не выводится, если в тексте нет знака ፟/፝.",
            "simpleForm": "Предварительно, не утверждено: ǝ→e, ā→a, без ʾ и ʿ, ḥ→h, ḫ→kh, ś→s, ṣ→ts, ḍ→ts, ṭ→t, ṗ→p.",
            "conventionalNotUsed": "መላእክት механически malāʾǝkǝt, не malāʾǝkt. እግዚአብሔር механически ʾǝgǝziʾabǝḥer. አምላክ механически ʾamǝlāk.",
            "unknownWords": problems_tr,
            "geminationMarks": gemination_hits,
            "editorialBrackets": editorial_brackets,
            "provisionalSyllables": rare_syllables[:50],
            "provisionalSyllableCount": len(rare_syllables),
        },
        "lexicon": {
            "entries": len(lexemes),
            "licenceTargets": lex_meta["licenceTargets"],
            "noLicenceFiles": lex_meta["noLicence"],
            "skipped": lex_meta["skipped"],
            "rsTypes": lex_meta["rsTypes"],
            "parentLinks": sum(1 for item in lexemes.values() if item["parent"]),
            "withEnochCref": sum(1 for item in lexemes.values() if item["enoch"]),
            "withLeslau": sum(1 for item in lexemes.values() if item["leslau"]),
            "withGreek": sum(1 for item in lexemes.values() if item["greek"]),
            "withEnglish": sum(1 for item in lexemes.values() if item["en"]),
            "extraLexemes": extra_added,
            "extraSkipped": extra_skipped,
            "note": "Родительской ссылки на другую статью в TEI нет (нет corresp, xr, link). rs type=root помечает саму статью как корневую, это не id родителя. subc (поле stem) — класс глагольной основы Дильмана (I,1 и т.п.), не корень.",
        },
        "counts": {
            "chapters": len(numbered),
            "words": total,
            "verses": sum(len(c["verses"]) for c in numbered),
            "ed1Chapters": [c["n"] for c in ed1],
            "eotcChapters": [c["n"] for c in eotc],
        },
        "smirnov": {
            "meta": {k: v for k, v in smirnov_meta.items() if k not in ("labels", "otdely")},
            "chapterLabels": smirnov_meta["labels"],
            "chapters": sorted({c for c, _v in smirnov}),
            "verseCount": len(smirnov),
            "notAttached": smirnov_only,
            "assumption": "Первая серия: текст после {{глава|N|ярлык}} — стих 1 главы N, далее {{стих|N|V}}. Эти номера совпадают с главами 1–59 и присоединены к тем же номерам. Вторая серия, с десятого отдела: {{глава|10}}…{{глава|20}} без ярлыка — это номер отдела. Стихи там написаны как «1. 2. 3.». К главам 1En.10–20 они не присоединены, потому что те номера уже заняты первой серией, а содержание — другие части книги (Ной, светила, видения, послание). Полный текст второй серии — в otdely. Раздел «Примечания» в слой не входит.",
            "otdely": smirnov_meta["otdely"],
        },
        "greek": {
            "chapters": greek_chapters,
            "unattached": greek_unattached,
            "brokenHeuristic": "Токен с < > { } | _ \\, или греческая буква вместе с латиницей или цифрой. Чисто греческие опечатки OCR в этот список не попадают.",
            "broken": broken,
            "latinChapters": latin_chapters,
            "latinNotAttached": "Латинский 1st1K-lat1 (гл. 106) не положен в слой grc и не в поле lat слова. Текст разобран и лежит в latin.",
            "latin": [
                {"c": c, "v": v, "text": t}
                for (c, v), texts in sorted(latin_map.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
                for t in texts
            ],
            "german": "tlg1463.tlg001.opp-ger1.xml скачан (немецкий перевод Флемминга). В корпус слоем не входит.",
            "germanRemoved": german_removed,
            "germanRemoveErrors": german_errors,
            "germanRule": "Из стиха Флемминга вынут сплошной негреческий кусок, если в нём есть der/die/das/und/den/dem/des/ein/eine/oder/nicht или Cap. Греческие токены не меняются. Свит не режется.",
        },
        "alignment": {
            "weak": weak,
            "nonmonotonic": nonmono,
            "leadingWordsJoined": leading_joined,
            "emptyVerses": empty_verses,
            "boundsNotOnStop": not_on_stop,
            "eotcBeyondOrthography": eotc_real_diffs(numbered, eotc),
            "chapters": chapter_reports,
        },
        "tagging": {
            "wordsWithMorph": tagged,
            "oneLemma": one,
            "several": several,
            "none": none,
            "names": names,
            "status": dict(status_count),
            "topUnanalyzed": form_none.most_common(100),
            "segMismatch": seg_mismatch,
        },
        "prefixCodesProposed": {
            "c": "ወ wa- «и»",
            "b": "በ/ብ ba-",
            "l": "ለ/ል la-",
            "m": "እም / እመ ʾǝm-",
            "k": "ከመ kama-, только если отделяется и остаток есть в словаре",
            "s": "ዘ za-",
            "i": "ኢ отрицание, если остаток есть в словаре, и እ перед ይ-. Код утверждён. Совпадение не по написанию auto не даёт.",
            "S1cs": "የ — местоимение 1 л. ኒ при глаголе тоже S1cs и лемма n=4755, auto не ставится.",
            "Enc-ni": "ኒ на имени и местоимении, лемма n=4756. На глагол без основания не ставится.",
            "S2ms": "ከ -ka",
            "S2fs": "ኪ -ki",
            "S2mp": "ክሙ -kǝmu",
            "S2fp": "ክን -kǝn",
            "S3ms": "ሁ -hu",
            "S3fs": "ሃ -hā",
            "S3mp": "ሆሙ / ኦሙ",
            "S3fp": "ሆን / ኦን",
            "S1cp": "ነ -na",
            "Enc-hi": "ሂ -hi, не местоимение, morph не начинается с S",
            "Enc-ssa": "ሣ, ሰ и ሳ — одна частица n=2428. ሰ и ሳ auto не дают: ሰ можно принять за часть основы, ሳ ещё сверять.",
            "enza": "እንዘ отдельным словом, приставкой не режется",
        },
    }
    (CORPUS / "enoch-build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"слов {total}, глав {len(numbered)}, стихов {report['counts']['verses']}, статей {len(lexemes)}")
    print(f"карта стихов: {verse_file}, слабых глав {len(weak)}, границ не на ። {len(not_on_stop)}")


if __name__ == "__main__":
    main()
