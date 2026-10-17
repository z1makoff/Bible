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
