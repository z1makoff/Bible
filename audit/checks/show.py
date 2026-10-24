"""Показать стих: еврейские слова, фрагменты перевода, разборы. python audit/checks/show.py Gen.26.29 ..."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for ref in sys.argv[1:]:
    b, c, n = ref.split("."); c, n = int(c), int(n)
    src = json.loads((ROOT / f"corpus/ot/{b}/{c:03d}.json").read_text("utf-8"))
    tr = json.loads((ROOT / f"translations/ot/{b}/{c:03d}.json").read_text("utf-8"))
    sv = next(v for v in src["verses"] if v["n"] == n); tv = next(v for v in tr["verses"] if v["n"] == n)
    print("=====", ref)
    print(" ".join(f"{w['tr']}[{w['id']}:{','.join(s['lemma'] or s['prefix'] or '-' for s in w['segs'])}]" for w in sv["words"]))
    print("RU:", " ".join(("[" + sp["t"] + "]") if sp.get("k") == "ins" else sp["t"] for sp in tv["spans"]))
    for sp in tv["spans"]:
        if sp.get("x") or sp.get("g"): print("  ", sp["t"], {k: sp[k] for k in ("x", "g", "s") if k in sp})
    for wid, p in tv.get("places", {}).items(): print("  place", wid, p.get("fits"), p["why"][:300])
    print("SYN:", " | ".join(s["text"] for s in sv["syn"]))
