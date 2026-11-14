"""Собирает перевод главы из краткой записи.

Запуск: python tools/compile_chapter.py Gen 4 путь/к/gen004.txt [draft|ready]
        python tools/compile_chapter.py 1En 1 путь/к/1en001.txt [draft|ready]
После сборки обязательно: python tools/check.py Gen 4   или   python tools/check.py 1En 1

ВЗ пишется в translations/ot/<Книга>/<ггг>.json, 1 Енох — в translations/1En/<ггг>.json.
Корпус Еноха: corpus/enoch/1En. Формат записи тот же.

Spec format (one verse per block):
  @ 7
  Разве/01bmL:fn не/01bmL:fn :  если/01DK9:fn будешь_поступать_хорошо/017vQ:do-well — поднятие/01JoL:lifting ?
  g 01JoL текст грамматического выбора (на первый не-служебный фрагмент с этим словом)
  x 01JoL причина исключения
  o 01JoL причина пропуска
  p 01JoL fit1,fit2 | почему
  n 01JoL пояснение к слову (идиома, игра слов, разночтение) — в «Почему здесь так», без значка ◇
Tokens: текст/ид[+ид]:вид — вид: fn, lat или id значения (для нескольких слов: s1+s2).
[текст] — вставка (серым). Токен без «/» — знак препинания. «_» в тексте — пробел.
Для ВЗ неупомянутые слова с меткой et (853) пропускаются автоматически с причиной «et».
Для 1 Еноха приставки ወ በ ለ ዘ እም пишутся как fn; номер слова — e00001.
"""
import json
import re
import sys
from pathlib import Path


def rules_version(root):
    path = Path(root) / "ПРАВИЛА.md"
    if not path.exists():
        return "1.4"
    m = re.search(r"Версия (\d+\.\d+)", path.read_text("utf-8"))
    return m.group(1) if m else "1.4"


def compile_chapter(book, chap, spec_path, status="draft", root=None):
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    spec_path = Path(spec_path)
    if book == "1En":
        corpus_path = root / "corpus" / "enoch" / "1En" / f"{chap:03d}.json"
        out_path = root / "translations" / "1En" / f"{chap:03d}.json"
        word_name = "геэза"
    else:
        corpus_path = root / "corpus" / "ot" / book / f"{chap:03d}.json"
        out_path = root / "translations" / "ot" / book / f"{chap:03d}.json"
        word_name = "еврейского"
    corpus = json.loads(corpus_path.read_text("utf-8"))
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
        if cur is None:
            sys.exit("перед строкой нужна глава стиха: @ 1")
        m = re.match(r"^([gxopn]) (\w+) (.*)$", line)
        if m and not re.match(r"^\S+/", line):
            kind, wid, rest = m.groups()
            if kind == "n":
                cands = [s for s in cur["spans"] if wid in s.get("w", [])]
                content = next((s for s in cands if s.get("k") is None and "s" in s), None)
                sense = content and (content["s"].get(wid) if isinstance(content["s"], dict) else content["s"])
                place = cur.setdefault("places", {}).setdefault(wid, {"fits": [sense] if sense else [], "why": ""})
                place["why"] = (place["why"] + " " + rest).strip()
                continue
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
                    sys.exit(f"{cur['n']}: слово «{tok}» без номера {word_name} слова (вставку пишите в [ ])")
                cur["spans"].append({"t": tok, "k": "p"})
            else:
                text, rest = tok.split("/", 1)
                if ":" not in rest:
                    sys.exit(f"{cur['n']}: «{tok}» — нужно текст/номер:значение")
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
        if v["n"] not in src:
            sys.exit(f"{v['n']}: такого стиха нет в корпусе")
        used = {w for s in v["spans"] for w in s.get("w", [])} | set(v.get("omit", {}))
        if book != "1En":
            for w in src[v["n"]]["words"]:
                if w["id"] not in used and any(s.get("lemma") == "853" for s in w["segs"]):
                    v.setdefault("omit", {})[w["id"]] = "et"
        order = ["n", "spans", "omit", "places"]
        v_sorted = {k: v[k] for k in order if k in v}
        v.clear()
        v.update(v_sorted)

    out = {"book": book, "chapter": chap, "rules": rules_version(root), "status": status, "verses": verses}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return out_path


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    book, chap, spec_path = argv[0], int(argv[1]), Path(argv[2])
    status = argv[3] if len(argv) > 3 else "draft"
    path = compile_chapter(book, chap, spec_path, status)
    print(f"{path.name}: стихов {len(json.loads(path.read_text('utf-8'))['verses'])}")


if __name__ == "__main__":
    main()
