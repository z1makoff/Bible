"""Разбор главы по словам для подготовки перевода.

Запуск: python tools/dump_chapter.py Gen 4 [1,2,3]   — вся глава или только перечисленные стихи
        python tools/dump_chapter.py 1En 1 [1,2]

Для ВЗ: еврейские слова, морфемы, решения словаря, Синодальный.
Для 1 Еноха: id, геэз, tr, лемма (n, head), статус разметки, gram, alts,
а по стиху — строки Смирнова и греческого.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dump_ot(root, book, chap, only):
    lexemes = json.loads((root / "corpus/lexemes.json").read_text("utf-8"))
    lex = {p.stem: json.loads(p.read_text("utf-8")) for p in (root / "decisions/lexicon").glob("*.json")}
    ch = json.loads((root / f"corpus/ot/{book}/{chap:03d}.json").read_text("utf-8"))
    for v in ch["verses"]:
        if only and v["n"] not in only:
            continue
        print(f"=== {v['n']}  SYN: " + " | ".join(s["text"] for s in v.get("syn", [])))
        for w in v["words"]:
            parts = []
            for s in w["segs"]:
                if s.get("lemma"):
                    k = s["lemma"]
                    e = lex.get(k)
                    d = f"{e['kind']}:{e['display']}[" + ",".join(f"{x['id']}={x['ru']}" for x in e["senses"]) + "]" if e else "NEW " + lexemes[k]["xlit"] + " «" + (lexemes[k].get("indexDef") or "") + "»"
                    parts.append(f"{k}={d} {s.get('morph') or ''}")
                else:
                    parts.append(f"<{s.get('prefix') or ''}{s.get('t')} {s.get('morph') or ''}>")
            extra = " KETIV" if w.get("ketiv") else ""
            print(f"  {w['id']} {w['tr']}{extra}: " + " ; ".join(parts))


def _article(lexemes, key):
    art = lexemes.get(key) or {}
    return f"{key} n={art.get('n')} head={art.get('head')}"


def dump_enoch(root, chap, only):
    lexemes = json.loads((root / "corpus/geez-lexemes.json").read_text("utf-8"))
    folder = root / "decisions/geez"
    decisions = {}
    if folder.exists():
        decisions = {p.stem: json.loads(p.read_text("utf-8")) for p in folder.glob("*.json")}
    morph_path = root / "morph/enoch" / f"{chap:03d}.json"
    morph = {}
    if morph_path.exists():
        morph = json.loads(morph_path.read_text("utf-8")).get("words") or {}
    ch = json.loads((root / "corpus/enoch/1En" / f"{chap:03d}.json").read_text("utf-8"))
    for v in ch["verses"]:
        if only and v["n"] not in only:
            continue
        print(f"=== {v.get('ref') or v['n']}")
        for row in v.get("smirnov") or []:
            print(f"  Смирнов {row.get('c')}:{row.get('v')}: {row.get('text')}")
        for row in v.get("grc") or []:
            print(f"  Греческий {row.get('edition')} {row.get('c')}:{row.get('v')}: {row.get('text')}")
        for w in v["words"]:
            mw = morph.get(w["id"]) or {}
            status = mw.get("status", w.get("status", ""))
            gram = mw.get("gram", w.get("gram", ""))
            segs = mw.get("segs") or w.get("segs") or []
            alts = mw.get("alts") if "alts" in mw else w.get("alts") or []
            print(f"  {w['id']} {w.get('text', '')} {w.get('tr', '')}  status={status}  gram={gram}")
            for s in segs:
                if s.get("lemma"):
                    dec = decisions.get(s["lemma"])
                    mark = f"  {dec['kind']}:{dec['display']}" if dec else ""
                    morph_code = f" {s.get('morph')}" if s.get("morph") else ""
                    print(f"    {_article(lexemes, s['lemma'])}{mark}{morph_code}")
                else:
                    print(f"    <{s.get('prefix') or ''}{s.get('t') or ''}>")
            if alts:
                print("    alts: " + "; ".join(_article(lexemes, a) for a in alts))


def dump_chapter(book, chap, only=None, root=None):
    root = Path(root) if root else ROOT
    if book == "1En":
        dump_enoch(root, chap, only)
    else:
        dump_ot(root, book, chap, only)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    book, chap = argv[0], int(argv[1])
    only = set(int(x) for x in argv[2].split(",")) if len(argv) > 2 else None
    dump_chapter(book, chap, only)


if __name__ == "__main__":
    main()
