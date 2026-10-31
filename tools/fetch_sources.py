"""Скачивает исходные данные зафиксированных версий и пишет паспорт каждого источника.

Запуск: python tools/fetch_sources.py
Файлы в sources/ после загрузки не редактируются. Повторный запуск перекачивает
только отсутствующие файлы и сверяет контрольные суммы уже скачанных.
"""
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"

MORPHHB_REF = "3d15126fb1ef74867fc1434be1942e837932691f"
LEXICON_REF = "21c9add13bc727d3a951361778e97e3ff7afd1ce"
STEP_REF = "94802ced31e63882ab42a86d79eb0017df4545e3"
JSWORD_REF = "c0b3b52aaaee5a2b88e84d57537cf153917ff1b8"

WLC_BOOKS = [
    "Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth", "1Sam", "2Sam",
    "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh", "Esth", "Job", "Ps", "Prov",
    "Eccl", "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel", "Amos",
    "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal",
]


def gh(repo, ref, path):
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{urllib.parse.quote(path)}"


CATALOG = [
    {
        "id": "oshb-wlc",
        "title": "Open Scriptures Hebrew Bible — Westminster Leningrad Codex 4.20 с морфологией",
        "role": "Базовый текст Ветхого Завета; лемматизация и морфология — аннотации",
        "language": "hbo, arc",
        "witness": "Цифровая транскрипция Ленинградского кодекса (рукопись около 1008 г. н. э.)",
        "license": "Текст WLC — общественное достояние; морфология и лемматизация — CC BY 4.0",
        "attribution": "Original work of the Open Scriptures Hebrew Bible available at https://github.com/openscriptures/morphhb",
        "origin": f"https://github.com/openscriptures/morphhb/tree/{MORPHHB_REF}",
        "version": MORPHHB_REF,
        "files": {f"{b}.xml": gh("openscriptures/morphhb", MORPHHB_REF, f"wlc/{b}.xml") for b in WLC_BOOKS}
        | {
            "VerseMap.xml": gh("openscriptures/morphhb", MORPHHB_REF, "wlc/VerseMap.xml"),
            "LICENSE.md": gh("openscriptures/morphhb", MORPHHB_REF, "LICENSE.md"),
        },
    },
    {
        "id": "oshb-lexicon",
        "title": "OSHB Hebrew Lexicon — BDB, Strong, лексический индекс",
        "role": "Словарные значения (аннотации, не доказательство сами по себе)",
        "language": "en",
        "witness": "Словари XIX — начала XX в. (Brown–Driver–Briggs 1906, Strong 1890) в цифровой разметке",
        "license": "Тексты BDB и Strong — общественное достояние; разметка — CC BY 4.0",
        "attribution": "Open Scriptures Hebrew Bible Project, https://github.com/openscriptures/HebrewLexicon",
        "origin": f"https://github.com/openscriptures/HebrewLexicon/tree/{LEXICON_REF}",
        "version": LEXICON_REF,
        "files": {
            name: gh("openscriptures/HebrewLexicon", LEXICON_REF, name)
            for name in ["BrownDriverBriggs.xml", "HebrewStrong.xml", "LexicalIndex.xml", "AugIndex.xml", "readme.md"]
        },
    },
    {
        "id": "stepbible",
        "title": "STEPBible Data — краткий еврейский словарь (TBESH) и таблица версификаций (TVTMS)",
        "role": "Словарные значения с различением омонимов; соответствие нумерации стихов",
        "language": "en",
        "witness": "Современная справочная разметка Tyndale House / STEPBible",
        "license": "CC BY 4.0 (авторы просят не распространять данные дальше самостоятельно, а ссылаться на github.com/STEPBible)",
        "attribution": "STEPBible.org, Tyndale House Cambridge — https://github.com/STEPBible/STEPBible-Data",
        "origin": f"https://github.com/STEPBible/STEPBible-Data/tree/{STEP_REF}",
        "version": STEP_REF,
        "files": {
            "TBESH.txt": gh("STEPBible/STEPBible-Data", STEP_REF,
                            "Lexicons/TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt"),
            "TVTMS.txt": gh("STEPBible/STEPBible-Data", STEP_REF,
                            "Versification/TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt"),
            "README.md": gh("STEPBible/STEPBible-Data", STEP_REF, "README.md"),
        },
    },
    {
        "id": "jsword-versification",
        "title": "CrossWire JSword — таблицы соответствия нумерации стихов (Ленинградский кодекс, Синодальный → KJV)",
        "role": "Сопоставление еврейских стихов с синодальными через общую нумерацию KJV",
        "language": "—",
        "witness": "Справочные таблицы CrossWire Bible Society (2013–2016), по XulSword и правкам TyndaleSTEP",
        "license": "LGPL 2.1 или новее",
        "attribution": "CrossWire Bible Society, https://github.com/crosswire/jsword",
        "origin": f"https://github.com/crosswire/jsword/tree/{JSWORD_REF}/src/main/resources/org/crosswire/jsword/versification",
        "version": JSWORD_REF,
        "files": {
            name: gh("crosswire/jsword", JSWORD_REF, f"src/main/resources/org/crosswire/jsword/versification/{name}")
            for name in ["Leningrad.properties", "Synodal.properties"]
        },
    },
    {
        "id": "synodal",
        "title": "Синодальный перевод (1876), модуль CrossWire 1.9.1 в формате getBible v2",
        "role": "Контрольный традиционный перевод; не доказательство",
        "language": "ru",
        "witness": "Русский перевод XIX в. с собственной (синодальной) нумерацией стихов",
        "license": "Общественное достояние (по паспорту модуля CrossWire)",
        "attribution": "CrossWire Bible Society; getBible.net",
        "origin": "https://api.getbible.net/v2/synodal.json",
        "version": "getBible v2, файл от 12.09.2026, checksum 3c969cf9943fa9c199fedc7c33ab479008df0693",
        "files": {"synodal.json": "https://api.getbible.net/v2/synodal.json"},
    },
    {
        "id": "enoch-bm",
        "title": "Beta maṣāḥǝft — LIT1340EnochE, эфиопская Книга Еноха (ed1 Дильман 1851 и EOTCed)",
        "role": "Базовый текст Книги Еноха (ed1) и церковный вариант (EOTCed)",
        "language": "gez",
        "witness": "ed1: издание Дильмана 1851, оцифровка Ерабека 1995; EOTCed: печатная Библия Эфиопской церкви",
        "license": "Файл TEI: «This file is licensed under the Creative Commons Attribution-ShareAlike 4.0.» (http://creativecommons.org/licenses/by-sa/4.0/). Текст edition 1: «1995 Library of Ethiopian Texts, created and maintained by Michal Jerabek, Prague. Permission to use, copy, and distribute this text, for any NONCOMMERCIAL purpose is hereby granted without fee, provided that the copyright notice and this permission notice appear in all copies of this text. This text cannot be sold under any circumstances.»",
        "attribution": "Beta maṣāḥǝft, Hiob-Ludolf-Zentrum für Äthiopistik; ed1: Michal Jerabek, 1995 Library of Ethiopian Texts; Unicode: Ran HaCohen. Уведомление Ерабека сохраняется при любой копии.",
        "origin": "https://github.com/BetaMasaheft/Works/blob/e99e697ce7f56b34a2ba740c078c257fd0e175d9/1001-2000/LIT1340EnochE.xml",
        "version": "e99e697ce7f56b34a2ba740c078c257fd0e175d9",
        "files": {
            "LIT1340EnochE.xml": gh("BetaMasaheft/Works", "e99e697ce7f56b34a2ba740c078c257fd0e175d9", "1001-2000/LIT1340EnochE.xml"),
        },
    },
    {
        "id": "dillmann-lexicon",
        "title": "Дильман, Lexicon linguae aethiopicae (1865), TEI TraCES / Beta maṣāḥǝft",
        "role": "Словарь геэза: латинские значения, английский слой TraCES, ссылки на места; аннотация, не доказательство",
        "language": "gez, la, en",
        "witness": "August Dillmann, Lexicon linguae aethiopicae, Leipzig 1865, цифровая разметка TraCES",
        "license": "В заголовке статей дословно одна формулировка: «This file is licensed under the Creative Commons Attribution-ShareAlike Non Commercial 4.0.» Адрес в том же заголовке у 12453 файлов: http://creativecommons.org/licenses/by-sa-nc/4.0/ ; у 1278 файлов: https://creativecommons.org/licenses/by-sa-nc/4.0/ (не стандартный by-nc-sa). У build.xml, expath-pkg.xml, repo.xml и schema/Dillmann.xml элемента licence нет. Других формулировок в XML нет.",
        "attribution": "TraCES project, Hiob-Ludolf-Zentrum für Äthiopistik, Hamburg. https://www.traces.uni-hamburg.de/",
        "origin": "https://github.com/BetaMasaheft/DillmannData/tree/4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e",
        "version": "4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e",
        "files": {
            "DillmannData-4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e.zip": "https://codeload.github.com/BetaMasaheft/DillmannData/zip/4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e",
            "README.md": gh("BetaMasaheft/DillmannData", "4b1cf257e7a51e72f509d8cb2d61d7d823e4ed3e", "README.md"),
        },
    },
    {
        "id": "first1k-enoch",
        "title": "First1KGreek — греческий Енох (Флемминг–Радермахер 1901, Свит 1905) и латинский отрывок",
        "role": "Греческий свидетель глав, которые есть в открытой оцифровке; текст распознан, ошибки OCR не правятся",
        "language": "grc, lat",
        "witness": "Flemming–Radermacher 1901 (tlg1463.tlg001.1st1K-grc2); Swete 1905 (1st1K-grc1); латинский отрывок гл. 106 (1st1K-lat1)",
        "license": "В файлах изданий дословно: «Available under a Creative Commons Attribution-ShareAlike 4.0 International License» (https://creativecommons.org/licenses/by-sa/4.0/). Полный текст лицензии репозитория — license.md.",
        "attribution": "Open Greek and Latin / First1KGreek; University of Leipzig; Harvard College Library. Редакторы изданий: Johannes Flemming, Ludwig Radermacher; Henry Barclay Swete.",
        "origin": "https://github.com/OpenGreekAndLatin/First1KGreek/tree/f47b6d42a1343a8a6dca500001d1fb27e5cce5ca/data/tlg1463/tlg001",
        "version": "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca",
        "files": {
            "__cts__.xml": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "data/tlg1463/tlg001/__cts__.xml"),
            "tlg1463.tlg001.1st1K-grc1.xml": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "data/tlg1463/tlg001/tlg1463.tlg001.1st1K-grc1.xml"),
            "tlg1463.tlg001.1st1K-grc2.xml": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "data/tlg1463/tlg001/tlg1463.tlg001.1st1K-grc2.xml"),
            "tlg1463.tlg001.1st1K-lat1.xml": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "data/tlg1463/tlg001/tlg1463.tlg001.1st1K-lat1.xml"),
            "tlg1463.tlg001.opp-ger1.xml": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "data/tlg1463/tlg001/tlg1463.tlg001.opp-ger1.xml"),
            "license.md": gh("OpenGreekAndLatin/First1KGreek", "f47b6d42a1343a8a6dca500001d1fb27e5cce5ca", "license.md"),
        },
    },
    {
        "id": "smirnov-enoch",
        "title": "А. В. Смирнов, Книга Еноха (Казань, 1888), Викитека",
        "role": "Контрольный русский перевод; нумерация Смирнова сохраняется как есть",
        "language": "ru",
        "witness": "Смирнов А. В. Книга Еноха: историко-критическое исследование. Православный собеседник, Казань, 1888",
        "license": "Шаблон Викитеки PD-old-70, дословно: «Это произведение перешло в общественное достояние в России согласно ст. 1281 ГК РФ, и в странах, где срок охраны авторского права действует на протяжении жизни автора плюс 70 лет или менее, или оно было обнародовано анонимно или под псевдонимом и личность автора не была раскрыта в этот срок. Если произведение является переводом, или иным производным произведением, или создано в соавторстве, то срок действия исключительного авторского права истёк для всех авторов оригинала и перевода.»",
        "attribution": "Александр Васильевич Смирнов, 1888. Текст с Викитеки, ревизия oldid 5634067 (2025-09-03), формат wikitext через API.",
        "origin": "https://ru.wikisource.org/wiki/Книга_Еноха",
        "version": "oldid:5634067",
        "files": {
            "Книга_Еноха.wikitext.json": "https://ru.wikisource.org/w/api.php?action=query&format=json&prop=revisions&revids=5634067&rvslots=main&rvprop=ids|timestamp|content|user|comment",
        },
    },
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "bible-reader-fetch"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    problems = []
    for src in CATALOG:
        folder = SOURCES / src["id"]
        folder.mkdir(parents=True, exist_ok=True)
        passport_path = folder / "passport.json"
        old = json.loads(passport_path.read_text("utf-8")) if passport_path.exists() else {}
        old_sums = {f["name"]: f["sha256"] for f in old.get("files", [])}
        files = []
        for name, url in src["files"].items():
            dest = folder / name
            if not dest.exists():
                print(f"скачиваю {src['id']}/{name}")
                download(url, dest)
            digest = sha256(dest)
            if name in old_sums and old_sums[name] != digest:
                problems.append(f"{src['id']}/{name}: контрольная сумма изменилась")
            files.append({"name": name, "url": url, "bytes": dest.stat().st_size, "sha256": digest})
        passport = {k: v for k, v in src.items() if k != "files"} | {"files": files}
        passport_path.write_text(json.dumps(passport, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"{src['id']}: {len(files)} файлов")
    if problems:
        print("\n".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main()
