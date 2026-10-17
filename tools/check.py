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

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
LEXICON = ROOT / "decisions" / "lexicon"
TRANSLATIONS = ROOT / "translations" / "ot"
INTERPRETATIONS = ROOT / "interpretations"

KINDS = {"word", "name", "divine", "function"}
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
    return any(s["prefix"] for s in word["segs"])


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
        if e.get("kind") == "word" and not e.get("senses"):
            rep.error(where, "у обычного слова нет ни одного значения")
        entries[key] = e
    return entries


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
                        rep.error(here, f"{w['tr']}: служебным может быть только приставка или служебное слово")
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
                        if sp["t"] != e["display"] and not sp.get("x"):
                            rep.error(here, f"латинская форма должна быть «{e['display']}» (словарь решений)")
                    else:
                        if e["kind"] in ("name", "divine"):
                            rep.error(here, f"{e['display']}: имена и титулы не переводятся (правила, раздел 2)")
                            continue
                        sid = sense_of(sp, wid)
                        sense = next((s for s in e.get("senses", []) if s["id"] == sid), None)
                        if sense is None and not sp.get("x"):
                            rep.error(here, f"значение «{sid}» не найдено в словаре для {e['display']}")
                        elif sense and not sp.get("x") and not any(st.lower() in sp["t"].lower() for st in sense["stems"]):
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
        for wid, place in v.get("places", {}).items():
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


def check_interpretations(rep):
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
        if not src.get("title") or not src.get("checked"):
            rep.error(where, "нет проверенного источника (название и дата проверки) — такую трактовку вносить нельзя")
        if not (src.get("page") or src.get("time") or src.get("url")):
            rep.error(where, "в источнике не указано место: страница, минута или ссылка")
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
