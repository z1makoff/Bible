"""Разбор главы по словам для подготовки перевода: еврейские слова, морфемы, решения словаря, Синодальный.

Запуск: python tools/dump_chapter.py Gen 4 [1,2,3]   — вся глава или только перечисленные стихи
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
book, chap = sys.argv[1], int(sys.argv[2])
L = json.loads((ROOT / "corpus/lexemes.json").read_text("utf-8"))
lex = {p.stem: json.loads(p.read_text("utf-8")) for p in (ROOT / "decisions/lexicon").glob("*.json")}
ch = json.loads((ROOT / f"corpus/ot/{book}/{chap:03d}.json").read_text("utf-8"))
only = set(int(x) for x in sys.argv[3].split(",")) if len(sys.argv) > 3 else None
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
                d = f"{e['kind']}:{e['display']}[" + ",".join(f"{x['id']}={x['ru']}" for x in e["senses"]) + "]" if e else "NEW " + L[k]["xlit"] + " «" + (L[k].get("indexDef") or "") + "»"
                parts.append(f"{k}={d} {s.get('morph') or ''}")
            else:
                parts.append(f"<{s.get('prefix') or ''}{s.get('t')} {s.get('morph') or ''}>")
        extra = " KETIV" if w.get("ketiv") else ""
        print(f"  {w['id']} {w['tr']}{extra}: " + " ; ".join(parts))
