"""Собирает читалку как статический сайт для телефона (GitHub Pages): папка site/.

Запуск: python tools/build_site.py   (нужен собранный корпус: python tools/build_corpus.py)
Всё, что сервер отдаёт для чтения (книги, главы, карточки слов), записывается в site/data/ готовыми файлами.
Заметки, решения и место чтения на сайте хранятся в браузере (app/static/local.js); перенос — экспорт и импорт файла.
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import server  # noqa: E402

SITE = ROOT / "site"
STATIC = ROOT / "app" / "static"


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def main():
    d = server.Data()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(STATIC, SITE)
    (SITE / ".nojekyll").write_text("")

    # страница: подключить хранилище в браузере, манифест и офлайн-режим
    index = (SITE / "index.html").read_text("utf-8")
    head = ('<link rel="manifest" href="manifest.webmanifest">\n'
            '<meta name="theme-color" content="#8a4b1f">\n'
            '<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">\n')
    index = index.replace("</head>", head + "</head>")
    index = index.replace("<!-- static-site -->", '<script src="local.js"></script>')
    (SITE / "index.html").write_text(index, "utf-8")

    version = os.environ.get("GITHUB_SHA", "")[:12] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    sw = (SITE / "sw.js").read_text("utf-8").replace("__VERSION__", version)
    (SITE / "sw.js").write_text(sw, "utf-8")

    prepared = {}
    for p in (ROOT / "translations" / "ot").glob("*/*.json"):
        prepared.setdefault(p.parent.name, {})[int(p.stem)] = server.read_json(p, {}).get("status", "draft")
    dump(SITE / "data" / "books.json", {"books": d.books, "prepared": prepared})

    chapters = 0
    for b in d.books:
        for n in range(1, b["chapters"] + 1):
            ch = d.chapter(b["id"], n)
            if ch is None:
                continue
            for k in ("userDecisions", "notes"):
                ch.pop(k)
            dump(SITE / "data" / "chapter" / b["id"] / f"{n:03d}.json", ch)
            chapters += 1

    # Трактовки, привязанные к словарной форме, кладутся в файл слова; трактовки без слов — по месту.
    # Порядок (_order) — как на сервере: по имени файла трактовки.
    by_lemma, by_place = {}, {}
    for i, p in enumerate(sorted((ROOT / "interpretations").glob("*.json"))):
        it = server.read_json(p)
        if not it:
            continue
        for s in it.get("support", []):
            s["gradeRu"] = server.RULE_GRADES.get(s.get("grade"), s.get("grade"))
        src = it.get("source") or {}
        book = d.library.get(src.get("book"))
        if book:
            src["title"] = book["title"]
            src["edition"] = ", ".join(str(x) for x in (book.get("publisher"), book.get("year")) if x)
        it["_order"] = i
        if it.get("lemmas"):
            for key in it["lemmas"]:
                by_lemma.setdefault(key, []).append(it)
        else:
            for ref in it.get("places", []):
                by_place.setdefault(ref, []).append(it)
    dump(SITE / "data" / "places.json", by_place)

    for key, info in d.lexemes.items():  # как Data.lexeme на сервере, без заметки пользователя
        occ = d.occurrences.get(key, [])
        by_book = {}
        for vref, _ in occ:
            by_book.setdefault(vref.split(".")[0], []).append(vref)
        dump(SITE / "data" / "lexeme" / f"{key}.json", {
            "key": key, "info": info, "decision": d.lexicon_entry(key),
            "occurrences": [{"book": b, "refs": sorted(set(r), key=lambda x: [int(p) for p in x.split(".")[1:]])}
                            for b, r in by_book.items()],
            "count": len(occ),
            "interpretations": by_lemma.get(key, []),
        })

    size = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"site/: {chapters} глав, {len(d.lexemes)} слов, {size / 1e6:.0f} МБ, версия {version}")


if __name__ == "__main__":
    main()
