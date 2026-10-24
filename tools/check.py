"""Проверка решений, переводов и трактовок по правилам (ПРАВИЛА.md, DATA.md).

Запуск: python tools/check.py            — всё
        python tools/check.py Gen 1      — одна глава (и весь словарь)
Код возврата 1, если есть ошибки. Предупреждения главу не останавливают.
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import books

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
LEXICON = ROOT / "decisions" / "lexicon"
TRANSLATIONS = ROOT / "translations" / "ot"
INTERPRETATIONS = ROOT / "interpretations"

KINDS = {"word", "name", "divine", "function", "keep"}
SPAN_KINDS = {None, "lat", "fn", "ins", "p"}
GRADES = {"entailed", "strong", "supported", "plausible", "compatible", "speculative", "contradicted"}
OMIT_REASONS = {"et": "метка прямого дополнения"}
STATUSES = {"draft", "approved"}
CHAPTER_STATUSES = {"draft", "ready", "reviewed"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def rules_version():
    m = re.search(r"Версия (\d+\.\d+)", (ROOT / "ПРАВИЛА.md").read_text("utf-8"))
    return m.group(1) if m else None


@lru_cache(maxsize=None)
def lexemes():
    return json.loads((CORPUS / "lexemes.json").read_text("utf-8"))


@lru_cache(maxsize=None)
def occurrence_verses():
    occ = json.loads((CORPUS / "occurrences.json").read_text("utf-8"))
    return {k: {ref for ref, _ in v} for k, v in occ.items()}


@lru_cache(maxsize=None)
def corpus_chapter(book, chapter):
    path = CORPUS / "ot" / book / f"{chapter:03d}.json"
    return json.loads(path.read_text("utf-8")) if path.exists() else None


def ref_exists(ref):
    m = re.fullmatch(r"([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)", ref)
    if not m:
        return False
    ch = corpus_chapter(m.group(1), int(m.group(2)))
    return bool(ch) and any(v["n"] == int(m.group(3)) for v in ch["verses"])


def content_lemmas(word):
    return [s["lemma"] for s in word["segs"] if s["lemma"]]


def has_prefix(word):
    """Приставка или местоименное окончание: их можно передать отдельным служебным словом."""
    return any(s["prefix"] or (s["morph"] or "").startswith("S") for s in word["segs"])


def load_lexicon(rep):
    entries = {}
    for path in sorted(LEXICON.glob("*.json")):
        where = f"словарь/{path.name}"
        try:
            e = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            rep.error(where, f"файл не читается как JSON ({exc})")
            continue
        key = e.get("key")
        if key != path.stem:
            rep.error(where, f"ключ «{key}» не совпадает с именем файла")
        if key not in lexemes():
            rep.error(where, f"слова «{key}» нет в корпусе")
        if e.get("kind") not in KINDS:
            rep.error(where, f"неизвестный вид слова «{e.get('kind')}»")
        if not e.get("display"):
            rep.error(where, "нет латинской формы (display)")
        if e.get("status") not in STATUSES:
            rep.error(where, f"неизвестный статус «{e.get('status')}»")
        if not e.get("history"):
            rep.error(where, "нет истории изменений")
        ids = set()
        for s in e.get("senses", []):
            sid = s.get("id")
            if sid in ids:
                rep.error(where, f"значение «{sid}» повторяется")
            ids.add(sid)
            if not s.get("ru") or not s.get("stems"):
                rep.error(where, f"у значения «{sid}» нет русского слова или основ для проверки")
            if not s.get("evidence"):
                rep.error(where, f"у значения «{sid}» нет ни одного места-свидетельства")
            for ref in s.get("evidence", []):
                if not ref_exists(ref):
                    rep.error(where, f"значение «{sid}»: места {ref} нет в корпусе")
                elif ref not in occurrence_verses().get(key, set()):
                    rep.error(where, f"значение «{sid}»: в {ref} этого слова нет")
        if e.get("kind") == "keep" and not e.get("notes"):
            rep.error(where, "у слова без перевода не объяснено, почему оно не переводится")
        if e.get("kind") == "word" and not e.get("senses"):
            rep.error(where, "у обычного слова нет ни одного значения")
        entries[key] = e
    return entries


def stem_found(stem, text):
    """Основа должна начинать русское слово: «дел» узнаёт «делай», но не «отдел» (приставочные формы
    перечисляются в словаре отдельно: «сдел»). Основа короче трёх букв засчитывается только целым словом."""
    stem = stem.lower()
    end = r"(?![а-яёa-z])" if len(stem) < 3 else ""
    return re.search(rf"(?<![а-яёa-z]){re.escape(stem)}{end}", text.lower()) is not None


def sense_of(span, wid):
    s = span.get("s")
    return s.get(wid) if isinstance(s, dict) else s


def check_chapter(path, lex, rep, version):
    book, chapter = path.parent.name, int(path.stem)
    where0 = f"{book} {chapter}"
    try:
        tr = json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        rep.error(where0, f"файл не читается как JSON ({exc})")
        return
    src = corpus_chapter(book, chapter)
    if src is None:
        rep.error(where0, "такой главы нет в корпусе")
        return
    if (tr.get("book"), tr.get("chapter")) != (book, chapter):
        rep.error(where0, "книга или глава внутри файла не совпадают с путём")
    if tr.get("rules") != version:
        rep.warn(where0, f"подготовлена по правилам {tr.get('rules')}, действуют {version}")
    if tr.get("status") not in CHAPTER_STATUSES:
        rep.error(where0, f"неизвестный статус «{tr.get('status')}»")
    src_verses = {v["n"]: v for v in src["verses"]}
    done = {v.get("n") for v in tr.get("verses", [])}
    if done != set(src_verses):
        missing = sorted(set(src_verses) - done)
        if tr.get("status") == "draft":
            rep.warn(where0, f"не подготовлены стихи {missing}")
        else:
            rep.error(where0, f"глава отмечена готовой, но нет стихов {missing}")
    for v in tr.get("verses", []):
        where = f"{book} {chapter}:{v.get('n')}"
        sv = src_verses.get(v.get("n"))
        if sv is None:
            rep.error(where, "такого стиха нет в корпусе")
            continue
        words = {w["id"]: w for w in sv["words"]}
        alt_of = {q["id"]: w["id"] for w in sv["words"] for q in w.get("qere", [])}
        alt_words = {q["id"]: q for w in sv["words"] for q in w.get("qere", [])}
        all_words = words | alt_words
        omit = v.get("omit", {})
        rendered = set()  # слова, чьё значимое слово передано переводом или транслитерацией
        touched = set(omit)
        for i, sp in enumerate(v.get("spans", [])):
            k = sp.get("k")
            here = f"{where}, фрагмент {i + 1} «{sp.get('t')}»"
            if k not in SPAN_KINDS:
                rep.error(here, f"неизвестный вид фрагмента «{k}»")
                continue
            if not sp.get("t"):
                rep.error(here, "пустой текст")
            ids = sp.get("w", [])
            if k in ("ins", "p"):
                if ids:
                    rep.error(here, "вставка или знак препинания не должны ссылаться на еврейские слова")
                continue
            if not ids:
                rep.error(here, "не указано, какие еврейские слова переданы")
            for wid in ids:
                if wid not in all_words:
                    rep.error(here, f"слова {wid} нет в этом стихе")
                    continue
                touched.add(alt_of.get(wid, wid))
                w = all_words[wid]
                keys = content_lemmas(w)
                if k == "fn":
                    if not has_prefix(w) and not any(lex.get(c, {}).get("kind") == "function" for c in keys):
                        rep.error(here, f"{w['tr']}: служебным может быть только приставка, окончание или служебное слово")
                    for c in keys:
                        if lex.get(c, {}).get("kind") == "function":
                            rendered.add(alt_of.get(wid, wid))
                    continue
                for c in keys:
                    e = lex.get(c)
                    if e is None:
                        rep.error(here, f"{w['tr']}: для слова {c} нет решения в словаре")
                        continue
                    if k == "lat":
                        allowed = [e["display"]] + e.get("displayForms", [])
                        if sp["t"] not in allowed and not sp.get("x"):
                            rep.error(here, f"латинская форма должна быть «{'» или «'.join(allowed)}» (словарь решений)")
                    else:
                        if e["kind"] in ("name", "divine"):
                            rep.error(here, f"{e['display']}: имена и титулы не переводятся (правила, раздел 2)")
                            continue
                        if e["kind"] == "keep":
                            rep.error(here, f"{e['display']}: по словарю решений это слово не переводится")
                            continue
                        sid = sense_of(sp, wid)
                        sense = next((s for s in e.get("senses", []) if s["id"] == sid), None)
                        if sense is None and not sp.get("x"):
                            rep.error(here, f"значение «{sid}» не найдено в словаре для {e['display']}")
                        elif sense and not sp.get("x") and not any(stem_found(st, sp["t"]) for st in sense["stems"]):
                            rep.error(here, f"для значения «{sid}» по словарю решений ожидается «{sense['ru']}»; "
                                            "если здесь иначе, нужно исключение с причиной (x)")
                rendered.add(alt_of.get(wid, wid))
            if sp.get("x") is not None and not str(sp.get("x")).strip():
                rep.error(here, "исключение без причины")
        for wid, reason in omit.items():
            if wid not in all_words:
                rep.error(where, f"пропущенного слова {wid} нет в стихе")
            elif not str(reason).strip():
                rep.error(where, f"слово {wid} пропущено без причины")
            rendered.add(alt_of.get(wid, wid))
        for wid, w in words.items():
            if wid not in touched:
                rep.error(where, f"слово {w['tr']} ({wid}) не передано и не указано как пропущенное")
            elif content_lemmas(w) and wid not in rendered:
                rep.error(where, f"слово {w['tr']} ({wid}) передано только служебной частью")
        # Союз ve- везде передаётся как «и» (правила, раздел 4); иначе нужна причина в x или omit
        by_word = {}
        for sp in v.get("spans", []):
            for wid in sp.get("w", []):
                by_word.setdefault(alt_of.get(wid, wid), []).append(sp)
        for wid, w in words.items():
            segs = w.get("segs") or [{}]
            if segs[0].get("prefix") != "c" or wid in omit:
                continue
            sps = by_word.get(wid, [])
            # причина (x) засчитывается только на служебном фрагменте самого союза, а не на любом фрагменте слова
            if not any(sp["t"].lower() == "и" or (sp.get("x") and sp.get("k") == "fn") for sp in sps):
                rep.error(where, f"{w['tr']}: союз ve- не передан как «и» (правила, раздел 4); иначе нужна причина (x)")
        # Главное правило (раздел 1): латиница — с разбором места; перевод — если подходит одно значение
        # или русское слово сохраняет все подходящие (covers)
        places = v.get("places", {})
        for wid, sps in by_word.items():
            if wid not in all_words:
                continue
            w = all_words[wid]
            if not any(lex.get(c, {}).get("kind") == "word" for c in content_lemmas(w)):
                continue
            place = places.get(wid)
            if any(sp.get("k") == "lat" for sp in sps) and not place:
                rep.error(where, f"{w['tr']} ({wid}): слово оставлено латиницей, но нет разбора места (places)")
            fits = (place or {}).get("fits", [])
            if (any(sp.get("k") is None and not sp.get("x") for sp in sps) and len(fits) > 1
                    and not place.get("covers")):
                rep.error(where, f"{w['tr']} ({wid}): по разбору места подходят {len(fits)} значения, а слово переведено; "
                                 "нужна латиница или отметка covers (русское слово сохраняет их все)")
        for wid, place in places.items():
            if wid not in all_words:
                rep.error(where, f"разбор места: слова {wid} нет в стихе")
                continue
            keys = content_lemmas(all_words[wid])
            senses = {s["id"] for c in keys for s in lex.get(c, {}).get("senses", [])}
            for f in place.get("fits", []):
                if f not in senses:
                    rep.error(where, f"разбор места {all_words[wid]['tr']}: значения «{f}» нет в словаре")
            if not place.get("why"):
                rep.error(where, f"разбор места {all_words[wid]['tr']}: не объяснено решение")


def check_source(src, where, rep):
    """Источник трактовки (правила, раздел 6): книга из каталога и дословный отрывок, найденный в ней."""
    if not src.get("checked"):
        rep.error(where, "нет проверенного источника (дата проверки) — такую трактовку вносить нельзя")
    kind = src.get("kind")
    if kind == "book":
        b = books.book(src.get("book", ""))
        if not b:
            rep.error(where, f"книги «{src.get('book')}» нет в каталоге library/books.json")
            return
        quote = src.get("quote", "")
        if not quote:
            rep.error(where, "нет отрывка цитаты из книги")
            return
        if books.quote_words(quote) > books.MAX_QUOTE_WORDS:
            rep.error(where, f"отрывок длиннее {books.MAX_QUOTE_WORDS} слов")
        if b.get("lang") != "ru" and not src.get("quoteRu"):
            rep.error(where, "нет русского перевода отрывка (quoteRu)")
        if src.get("page") and not b.get("pages"):
            rep.error(where, "в этом издании нет печатных страниц — страницу не указывают")
        found = books.find_quote(b["id"], quote)
        if found is False:
            rep.error(where, f"отрывок не найден в книге «{b['title']}»")
        elif found is None:
            rep.warn(where, f"отрывок не проверен: книги «{b['title']}» нет на диске или PDF нечем прочитать")
    elif kind == "video":
        if not (src.get("title") and src.get("url") and src.get("time")):
            rep.error(where, "у видео нужны название, ссылка и минута")
    elif kind == "web":
        if not (src.get("title") and src.get("url")):
            rep.error(where, "у страницы нужны название и ссылка")
    else:
        rep.error(where, f"неизвестный вид источника «{kind}» (book, video, web)")


def check_interpretations(rep):
    used_books = set()
    for path in sorted(INTERPRETATIONS.glob("*.json")):
        where = f"трактовка/{path.name}"
        try:
            it = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            rep.error(where, f"файл не читается как JSON ({exc})")
            continue
        if it.get("id") != path.stem:
            rep.error(where, "id не совпадает с именем файла")
        for field in ("tradition", "claim"):
            if not it.get(field):
                rep.error(where, f"не заполнено поле {field}")
        src = it.get("source") or {}
        check_source(src, where, rep)
        if src.get("kind") == "book" and books.book(src.get("book", "")):
            used_books.add(src["book"])
        for c in it.get("lemmas", []):
            if c not in lexemes():
                rep.error(where, f"слова {c} нет в корпусе")
        for ref in it.get("places", []):
            if not ref_exists(ref):
                rep.error(where, f"места {ref} нет в корпусе")
        if not it.get("support"):
            rep.error(where, "нет оценки, на чём держится трактовка")
        for s in it.get("support", []):
            if s.get("grade") not in GRADES:
                rep.error(where, f"неизвестная оценка «{s.get('grade')}»")
            for ref in s.get("for", []) + s.get("against", []):
                if not ref_exists(ref):
                    rep.error(where, f"места {ref} нет в корпусе")
    for book_id in sorted(used_books):
        if books.file_matches(books.book(book_id)) is False:
            rep.warn(f"книга/{book_id}", "файл на диске не совпадает с каталогом (SHA-256): другое издание или копия")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not (CORPUS / "lexemes.json").exists():
        print("Корпус не собран: python tools/build_corpus.py")
        sys.exit(1)
    rep = Report()
    version = rules_version()
    lex = load_lexicon(rep)
    if len(sys.argv) == 3:
        paths = [TRANSLATIONS / sys.argv[1] / f"{int(sys.argv[2]):03d}.json"]
    else:
        paths = sorted(TRANSLATIONS.glob("*/*.json"))
    for path in paths:
        if path.exists():
            check_chapter(path, lex, rep, version)
        else:
            rep.error(path.name, "файла перевода нет")
    check_interpretations(rep)
    for w in rep.warnings:
        print("предупреждение —", w)
    for e in rep.errors:
        print("ошибка —", e)
    print(f"\nправила {version}; словарь: {len(lex)} слов; глав: {len(paths)}; "
          f"ошибок: {len(rep.errors)}, предупреждений: {len(rep.warnings)}")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
