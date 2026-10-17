"""Собирает корпус Ветхого Завета из sources/ в corpus/.

Запуск: python tools/build_corpus.py
Результат полностью определяется исходниками: повторная сборка даёт те же файлы.
  corpus/ot/books.json          — книги, русские названия, число глав
  corpus/ot/<Книга>/<ггг>.json  — глава: стихи, слова, морфемы, транслитерация
  corpus/lexemes.json           — словарные слова: BDB, Strong, STEPBible, число употреблений
  corpus/occurrences.json       — где встречается каждое словарное слово
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hebrew import translit  # noqa: E402
from versification import SYNODAL_CORRECTIONS, compose, load_rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"
OUT = ROOT / "corpus"
OSIS = "{http://www.bibletechnologies.net/2003/OSIS/namespace}"
LEX = "{http://openscriptures.github.com/morphhb/namespace}"

BOOKS = [
    "Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth", "1Sam", "2Sam",
    "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh", "Esth", "Job", "Ps", "Prov",
    "Eccl", "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel", "Amos",
    "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal",
]
PREFIXES = {"b", "c", "d", "i", "k", "l", "m", "s"}


def lemma_key(part):
    """'1254 a' → '1254a', '1177+' → '1177'. Префиксы и пустые части → None."""
    part = part.replace(" ", "").rstrip("+")
    return part if re.fullmatch(r"\d+[a-z]?", part) else None


def parse_word(w):
    text = w.text or ""
    morph = w.get("morph", "")
    lang, morph_parts = (morph[0], morph[1:].split("/")) if morph else ("H", [])
    text_parts = text.split("/")
    lemma_parts = w.get("lemma", "").split("/")
    segs = []
    for i, t in enumerate(text_parts):
        lp = lemma_parts[i] if i < len(lemma_parts) else None
        segs.append({
            "t": t,
            "lemma": lemma_key(lp) if lp else None,
            "prefix": lp if lp in PREFIXES else None,
            "morph": morph_parts[i] if i < len(morph_parts) else None,
        })
    word = {"id": w.get("id"), "text": text.replace("/", ""), "tr": translit(text), "lang": lang, "segs": segs}
    if len(text_parts) != len(morph_parts):
        word["warn"] = "число морфем в тексте и в разметке не совпадает"
    return word


def parse_verse(v):
    """Кетив (написанное) и кере (то, что масореты велят читать) хранятся вместе:
    у слова-кетив поле qere — список прочитываемых слов (бывает 0, 1 или 2)."""
    words, brk = [], None
    for el in v:
        tag = el.tag.replace(OSIS, "")
        if tag == "w":
            word = parse_word(el)
            if el.get("type") == "x-ketiv":
                word["ketiv"] = True
            words.append(word)
        elif tag == "note" and words:
            kind = el.get("type")
            if kind == "variant":
                rdg = el.find(f"{OSIS}rdg")
                qere = [parse_word(w) for w in rdg.findall(f"{OSIS}w")] if rdg is not None else []
                target = next((w for w in reversed(words) if w.get("ketiv") and "qere" not in w), None)
                if target is None:
                    target = words[-1]
                    target["qereWithoutKetiv"] = True
                target["qere"] = qere
            elif kind == "exegesis":
                words[-1]["sourceNote"] = " ".join("".join(el.itertext()).split())
        elif tag == "seg":
            kind = el.get("type")
            if kind == "x-maqqef" and words:
                words[-1]["maqqef"] = True
            elif kind in ("x-pe", "x-samekh"):
                brk = kind[2:]
    return words, brk


def lexicon_tables():
    aug = {e.get("aug"): e.text for e in ET.parse(SRC / "oshb-lexicon/AugIndex.xml").getroot()}
    li = {}
    for e in ET.parse(SRC / "oshb-lexicon/LexicalIndex.xml").getroot().iter(f"{LEX}entry"):
        w, x = e.find(f"{LEX}w"), e.find(f"{LEX}xref")
        li[e.get("id")] = {
            "lemma": w.text if w is not None else None,
            "xlit": w.get("xlit") if w is not None else None,
            "pos": (e.findtext(f"{LEX}pos") or None),
            "def": (e.findtext(f"{LEX}def") or None),
            "bdb": x.get("bdb") if x is not None else None,
            "strong": x.get("strong") if x is not None else None,
        }
    bdb = {}
    for e in ET.parse(SRC / "oshb-lexicon/BrownDriverBriggs.xml").getroot().iter(f"{LEX}entry"):
        senses = [" ".join("".join(s.itertext()).split()) for s in e.findall(f"{LEX}sense")]
        head = " ".join("".join(t for t in e.itertext()).split())[:400]
        bdb[e.get("id")] = {"pos": e.findtext(f"{LEX}pos"), "senses": senses or None, "text": head}
    strong = {}
    for e in ET.parse(SRC / "oshb-lexicon/HebrewStrong.xml").getroot().iter(f"{LEX}entry"):
        m, u = e.find(f"{LEX}meaning"), e.find(f"{LEX}usage")
        strong[e.get("id")] = {
            "meaning": " ".join("".join(m.itertext()).split()) if m is not None else None,
            "usage": " ".join("".join(u.itertext()).split()) if u is not None else None,
        }
    tbesh = {}
    for line in (SRC / "stepbible/TBESH.txt").read_text("utf-8-sig").splitlines():
        cols = line.split("\t")
        if len(cols) < 8 or not re.fullmatch(r"H\d{4}[a-z]?", cols[0]):
            continue
        key = cols[0][1:].lstrip("0")
        own = cols[1].split(" ")[0].upper() == cols[0].upper()
        if key not in tbesh or (own and not tbesh[key]["own"]):
            tbesh[key] = {"own": own, "gloss": cols[6], "translit": cols[4], "pos": cols[5],
                          "meaning": re.sub(r"<[^>]+>", " ", cols[7]).strip()}
    return aug, li, bdb, strong, tbesh


def load_synodal():
    """Книги 1–39 Синодального: названия, тексты стихов и длины глав в синодальной нумерации."""
    data = json.loads((SRC / "synodal/synodal.json").read_text("utf-8-sig"))
    names, texts, lengths = {}, {}, {}
    for b in data["books"]:
        names[b["nr"]] = b["name"]
        if b["nr"] > len(BOOKS):
            continue
        book = BOOKS[b["nr"] - 1]
        for ch in b["chapters"]:
            lengths[(book, ch["chapter"])] = max(v["verse"] for v in ch["verses"])
            for v in ch["verses"]:
                texts[(book, ch["chapter"], v["verse"])] = v["text"].strip()
    return names, texts, lengths


def synodal_mapping(chapters, syn_texts, syn_lengths, errors):
    heb_lengths = {(c["book"], c["chapter"]): len(c["verses"]) for c in chapters}
    heb_verses = [(c["book"], c["chapter"], v["n"]) for c in chapters for v in c["verses"]]
    vdir = SRC / "jsword-versification"
    heb_rules = load_rules(vdir / "Leningrad.properties", heb_lengths, errors)
    syn_rules = load_rules(vdir / "Synodal.properties", syn_lengths, errors, SYNODAL_CORRECTIONS)
    return compose(heb_verses, heb_rules, sorted(syn_texts), syn_rules)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    names, syn_texts, syn_lengths = load_synodal()
    occurrences = defaultdict(list)
    forms = defaultdict(set)
    books, warnings, total, all_chapters = [], [], 0, []
    for nr, book in enumerate(BOOKS, 1):
        root = ET.parse(SRC / f"oshb-wlc/{book}.xml").getroot()
        chapters = root.findall(f".//{OSIS}chapter")
        (OUT / "ot" / book).mkdir(parents=True, exist_ok=True)
        for ch in chapters:
            cnum = int(ch.get("osisID").split(".")[1])
            verses = []
            for v in ch.findall(f"{OSIS}verse"):
                ref = v.get("osisID")
                words, brk = parse_verse(v)
                for w in words:
                    total += 1
                    if "warn" in w:
                        warnings.append(f"{ref} {w['id']}: {w['warn']}")
                    for s in w["segs"]:
                        if s["lemma"]:
                            occurrences[s["lemma"]].append([ref, w["id"]])
                            forms[s["lemma"]].add(s["t"])
                verse = {"ref": ref, "n": int(ref.split(".")[2]), "words": words}
                if brk:
                    verse["break"] = brk
                verses.append(verse)
            all_chapters.append({"book": book, "chapter": cnum, "verses": verses})
        books.append({"id": book, "nr": nr, "name": names[nr], "chapters": len(chapters)})

    # Синодальный: каждому еврейскому стиху — пересекающиеся синодальные стихи.
    # exact — границы стихов совпадают; иначе стих делится или объединяется по-разному.
    map_errors = []
    mapping, syn_only = synodal_mapping(all_chapters, syn_texts, syn_lengths, map_errors)
    for chapter in all_chapters:
        for v in chapter["verses"]:
            v["syn"] = [{"c": s[1], "v": s[2], "text": syn_texts[s], "exact": exact}
                        for s, exact in mapping[(chapter["book"], chapter["chapter"], v["n"])]]
        path = OUT / "ot" / chapter["book"] / f"{chapter['chapter']:03d}.json"
        path.write_text(json.dumps(chapter, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    synodal_only = [{"book": s[0], "c": s[1], "v": s[2], "text": syn_texts[s]} for s in syn_only]

    aug, li, bdb, strong, tbesh = lexicon_tables()
    lexemes, missing = {}, []
    for key in sorted(occurrences, key=lambda k: (int(re.match(r"\d+", k).group()), k)):
        entry = li.get(aug.get(key)) if aug.get(key) else None
        num = re.match(r"\d+", key).group()
        if entry is None:
            missing.append(key)
        lexemes[key] = {
            "lemma": entry["lemma"] if entry else None,
            "xlit": entry["xlit"] if entry else None,
            "pos": entry["pos"] if entry else None,
            "count": len(occurrences[key]),
            "forms": len(forms[key]),
            "indexDef": entry["def"] if entry else None,
            "bdb": (bdb.get(entry["bdb"]) | {"id": entry["bdb"]}) if entry and entry["bdb"] in bdb else None,
            "strong": strong.get(f"H{num}"),
            "step": {k: v for k, v in (tbesh.get(key) or tbesh.get(num) or {}).items() if k != "own"} or None,
        }
    (OUT / "ot" / "books.json").write_text(json.dumps(books, ensure_ascii=False, indent=1) + "\n", "utf-8")
    (OUT / "lexemes.json").write_text(json.dumps(lexemes, ensure_ascii=False, indent=0) + "\n", "utf-8")
    (OUT / "occurrences.json").write_text(json.dumps(occurrences, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    (OUT / "ot" / "synodal-only.json").write_text(
        json.dumps(synodal_only, ensure_ascii=False, indent=1) + "\n", "utf-8")
    report = {
        "words": total,
        "versesWithoutSynodal": [c["book"] + f".{c['chapter']}.{v['n']}" for c in all_chapters
                                 for v in c["verses"] if not v["syn"]],
        "versesWithInexactSynodal": sum(1 for c in all_chapters for v in c["verses"]
                                        if v["syn"] and not (len(v["syn"]) == 1 and v["syn"][0]["exact"])),
        "synodalOnlyVerses": len(synodal_only),
        "versificationErrors": map_errors,
        "lexemes": len(lexemes),
        "lexemesWithoutIndexEntry": missing,
        "lexemesWithoutBdb": [k for k, v in lexemes.items() if v["bdb"] is None],
        "lexemesWithoutStep": [k for k, v in lexemes.items() if v["step"] is None],
        "warnings": warnings,
    }
    (OUT / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"слов: {total}, словарных слов: {len(lexemes)}")
    print(f"стихов без синодального: {len(report['versesWithoutSynodal'])} {report['versesWithoutSynodal']}, "
          f"с неточными границами: {report['versesWithInexactSynodal']}, "
          f"только в синодальном: {len(synodal_only)}, ошибок таблиц: {len(map_errors)}")
    print(f"без индекса: {len(missing)}, без BDB: {len(report['lexemesWithoutBdb'])}, "
          f"без STEPBible: {len(report['lexemesWithoutStep'])}, предупреждений: {len(warnings)}")


if __name__ == "__main__":
    main()
