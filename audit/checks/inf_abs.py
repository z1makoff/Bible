"""Как передан инфинитив абсолютный (morph V?a) перед/после того же глагола — по всем готовым главам."""
import json, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
out = collections.Counter(); ex = collections.defaultdict(list)
for p in sorted((ROOT / "translations/ot").glob("*/*.json")):
    t = json.loads(p.read_text("utf-8")); b, c = p.parent.name, int(p.stem)
    src = {v["n"]: v for v in json.loads((ROOT / f"corpus/ot/{b}/{c:03d}.json").read_text("utf-8"))["verses"]}
    for v in t["verses"]:
        sv = src[v["n"]]; ws = sv["words"]
        for i, w in enumerate(ws):
            seg = [s for s in w["segs"] if s["lemma"]]
            if not seg or not (seg[0]["morph"] or "").startswith("V") or len(seg[0]["morph"]) < 3 or seg[0]["morph"][2] != "a":
                continue
            lem = seg[0]["lemma"]
            neigh = [x for x in ws[max(0, i-2):i+3] if x is not w and any(s["lemma"] == lem for s in x["segs"])]
            if not neigh: continue
            sps = [sp for sp in v["spans"] if w["id"] in sp.get("w", [])]
            kind = "omit" if w["id"] in v.get("omit", {}) else "+".join(f"{sp.get('k') or 'tr'}:{sp['t']}" for sp in sps)
            how = "merged" if any(len(sp.get("w", [])) > 1 for sp in sps) else ("omit" if kind == "omit" else "own")
            label = kind if how != "own" else sps[0]["t"] if sps else "?"
            out[how] += 1
            ex[how].append(f"{sv['ref']} {w['tr']} → {label} | {' '.join(sp['t'] for sp in v['spans'] if any(x in sp.get('w',[]) for x in [w['id']]+[n['id'] for n in neigh]))}")
print(out)
for h, l in ex.items():
    print("==", h); print("\n".join(l))
