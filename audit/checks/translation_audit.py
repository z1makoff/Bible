"""Независимые проверки перевода, которых нет в tools/check.py.
Запуск: python audit/checks/translation_audit.py  (нужен собранный corpus/)
Печатает сводку и пишет подробности в audit/out/*.txt
"""
import json, re, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "audit" / "out"; OUT.mkdir(exist_ok=True)
lex = {p.stem: json.loads(p.read_text("utf-8")) for p in (ROOT / "decisions/lexicon").glob("*.json")}
corpus = {}
def chap(b, c):
    if (b, c) not in corpus:
        corpus[(b, c)] = json.loads((ROOT / f"corpus/ot/{b}/{c:03d}.json").read_text("utf-8"))
    return corpus[(b, c)]
def lemmas(w): return [s["lemma"] for s in w["segs"] if s["lemma"]]

files = sorted((ROOT / "translations/ot").glob("*/*.json"))
res = collections.defaultdict(list)
render = collections.defaultdict(collections.Counter)   # (key, sense) -> Counter(text)
ins = collections.Counter(); total_words = 0; lat_words = 0; tr_words = 0
for p in files:
    t = json.loads(p.read_text("utf-8")); b, c = p.parent.name, int(p.stem)
    src = {v["n"]: v for v in chap(b, c)["verses"]}
    for v in t["verses"]:
        sv = src[v["n"]]; ref = sv["ref"]
        words = {w["id"]: w for w in sv["words"]}
        for w in sv["words"]:
            for q in w.get("qere", []): words[q["id"]] = q
        places = v.get("places", {}); omit = v.get("omit", {})
        by = collections.defaultdict(list)
        for sp in v["spans"]:
            for wid in sp.get("w", []): by[wid].append(sp)
            if sp.get("k") == "ins": ins[sp["t"].lower()] += 1
            if sp.get("k") is None:
                for wid in sp.get("w", []):
                    if wid not in words: continue
                    for k in lemmas(words[wid]):
                        s = sp.get("s"); s = s.get(wid) if isinstance(s, dict) else s
                        render[(k, s)][sp["t"].lower()] += 1
        for wid, sps in by.items():
            w = words.get(wid)
            if not w: continue
            keys = lemmas(w); kinds = {lex.get(k, {}).get("kind") for k in keys}
            main = [s for s in sps if s.get("k") in (None, "lat")]
            pl = places.get(wid)
            if any(s.get("k") == "lat" for s in main) and "word" in kinds:
                lat_words += 1
                if not pl:
                    res["lat_word_no_place"].append(f"{ref} {wid} {w['tr']} → {[s['t'] for s in main]}")
                elif len(pl.get("fits", [])) == 1:
                    res["lat_but_one_fit"].append(f"{ref} {wid} {w['tr']} fits={pl['fits']} :: {pl['why'][:120]}")
            if any(s.get("k") is None for s in main):
                tr_words += 1
                if pl and len(pl.get("fits", [])) > 1:
                    res["translated_but_many_fits"].append(f"{ref} {wid} {w['tr']} «{main[0]['t']}» fits={pl['fits']} :: {pl['why'][:150]}")
            # приставка-предлог/местоим. окончание у латинского слова без служебного фрагмента
            if main and all(s.get("k") == "lat" for s in main) and "word" in kinds | {"name", "divine", "keep"}:
                pre = [s["prefix"] for s in w["segs"] if s["prefix"] in ("b", "l", "k", "m")]
                suf = [s for s in w["segs"] if (s["morph"] or "").startswith("S")]
                if (pre or suf) and not any(s.get("k") in ("fn",) for s in sps):
                    res["lost_affix"].append(f"{ref} {wid} {w['text']} ({w['tr']}) → {[s['t'] for s in sps]} prefix={pre} suffix={len(suf)}")
        total_words += len(sv["words"])
    for v in t["verses"]:
        for sp in v["spans"]:
            if sp.get("x"): res["exceptions"].append(f"{b}.{c}.{v['n']} «{sp['t']}» x={sp['x']}")
            if re.search(r"\b(Бог|Бож|Господ|Иегов|Вседерж|Всевышн|сотвор|ангел|дух\b|Дух)", sp["t"]) :
                res["theological_words"].append(f"{b}.{c}.{v['n']} k={sp.get('k')} «{sp['t']}»")

# правило 3: разные исходные слова — разные русские слова
ru_of = collections.defaultdict(set)
for k, e in lex.items():
    if e["kind"] != "word": continue
    for s in e.get("senses", []):
        ru_of[s["ru"].lower()].add(k)
coll = {r: ks for r, ks in ru_of.items() if len(ks) > 1}
# какие из совпадений реально использованы в переводе
used = collections.defaultdict(set)
for (k, s), cnt in render.items():
    e = lex.get(k)
    if not e: continue
    sense = next((x for x in e.get("senses", []) if x["id"] == s), None)
    if sense: used[sense["ru"].lower()].add(k)
for r, ks in sorted(coll.items()):
    u = used.get(r, set()) & ks
    names = ", ".join(f"{k}:{lex[k]['display']}" for k in sorted(ks))
    res["same_ru_diff_words" + ("_used" if len(u) > 1 else "_dict_only")].append(f"«{r}» ← {names}")
# короткие основы (риск ложного совпадения в проверке)
for k, e in lex.items():
    for s in e.get("senses", []):
        for st in s.get("stems", []):
            if len(st) <= 2: res["short_stems"].append(f"{k} {e['display']} {s['id']} ru={s['ru']} stem='{st}'")
# основа не является частью русского слова значения
for k, e in lex.items():
    for s in e.get("senses", []):
        if not any(st.lower() in s["ru"].lower() for st in s.get("stems", [])):
            res["stem_not_in_ru"].append(f"{k} {e['display']} {s['id']} ru={s['ru']} stems={s['stems']}")
# разнобой: одно значение — много разных русских форм (показываем топ)
for (k, s), cnt in render.items():
    if len(cnt) >= 6:
        res["many_forms"].append(f"{k} {lex.get(k,{}).get('display')} [{s}] {len(cnt)} форм: {', '.join(f'{x}×{n}' for x,n in cnt.most_common(12))}")
res["ins_top"] = [f"{t!r} ×{n}" for t, n in ins.most_common(150)]
for name, lines in res.items():
    (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n", "utf-8")
print(f"глав {len(files)}, еврейских слов {total_words}, слов-значений: переведено {tr_words}, латиницей {lat_words}")
for name, lines in sorted(res.items()): print(f"{name}: {len(lines)}")
