"""Собирает перевод главы из краткой записи в translations/ot/<Книга>/<ггг>.json.

Запуск: python tools/compile_chapter.py Gen 4 путь/к/gen004.txt [draft|ready]
После сборки обязательно: python tools/check.py Gen 4

Spec format (one verse per block):
  @ 7
  Разве/01bmL:fn не/01bmL:fn :  если/01DK9:fn будешь_поступать_хорошо/017vQ:do-well — поднятие/01JoL:lifting ?
  g 01JoL текст грамматического выбора (на первый не-служебный фрагмент с этим словом)
  x 01JoL причина исключения
  o 01JoL причина пропуска
  p 01JoL fit1,fit2 | почему
Tokens: текст/ид[+ид]:вид — вид: fn, lat или id значения (для нескольких слов: s1+s2).
[текст] — вставка (серым). Токен без «/» — знак препинания. «_» в тексте — пробел.
Неупомянутые слова с меткой et (853) пропускаются автоматически с причиной «et».
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parent.parent
book, chap, spec_path = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
status = sys.argv[4] if len(sys.argv) > 4 else "draft"
corpus = json.loads((root / f"corpus/ot/{book}/{chap:03d}.json").read_text("utf-8"))
src = {v["n"]: v for v in corpus["verses"]}

verses, cur = [], None
for raw in spec_path.read_text("utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("@"):
        cur = {"n": int(line[1:]), "spans": []}
        verses.append(cur)
        continue
    m = re.match(r"^([gxop]) (\w+) (.*)$", line)
    if m and not re.match(r"^\S+/", line):
        kind, wid, rest = m.groups()
        if kind == "o":
            cur.setdefault("omit", {})[wid] = rest
        elif kind == "p":
            fits, why = rest.split("|", 1)
            cur.setdefault("places", {})[wid] = {"fits": [f for f in fits.strip().split(",") if f], "why": why.strip()}
        else:
            cands = [s for s in cur["spans"] if wid in s.get("w", [])]
            if not cands:
                sys.exit(f"{cur['n']}: {kind} для {wid}, но фрагмента нет")
            if kind == "g":
                target = next((s for s in cands if s.get("k") != "fn"), cands[0])
                target["g"] = rest
            else:
                for s in cands:
                    if s.get("k") not in ("fn", "lat"):
                        s["x"] = rest
        continue
    for tok in line.split():
        if tok.startswith("[") and tok.endswith("]"):
            cur["spans"].append({"t": tok[1:-1].replace("_", " "), "k": "ins"})
        elif "/" not in tok:
            if any(ch.isalnum() for ch in tok):
                sys.exit(f"{cur['n']}: слово «{tok}» без номера еврейского слова (вставку пишите в [ ])")
            cur["spans"].append({"t": tok, "k": "p"})
        else:
            text, rest = tok.split("/", 1)
            ids, tag = rest.split(":", 1)
            ids = ids.split("+")
            sp = {"t": text.replace("_", " "), "w": ids}
            if tag in ("fn", "lat"):
                sp["k"] = tag
            elif "+" in tag:
                sp["s"] = dict(zip(ids, tag.split("+")))
            else:
                sp["s"] = tag
            cur["spans"].append(sp)

for v in verses:
    used = {w for s in v["spans"] for w in s.get("w", [])} | set(v.get("omit", {}))
    for w in src[v["n"]]["words"]:
        if w["id"] not in used and any(s.get("lemma") == "853" for s in w["segs"]):
            v.setdefault("omit", {})[w["id"]] = "et"
    order = ["n", "spans", "omit", "places"]
    v_sorted = {k: v[k] for k in order if k in v}
    v.clear()
    v.update(v_sorted)

out = {"book": book, "chapter": chap, "rules": "1.1", "status": status, "verses": verses}
path = root / f"translations/ot/{book}/{chap:03d}.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
print(f"{path.name}: стихов {len(verses)}")
