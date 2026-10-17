"""Независимая проверка сопоставления еврейских и синодальных стихов по именам собственным.

Для каждого частого имени (OSHB: Np) находится русская основа, которая чаще всего стоит
в сопоставленных синодальных стихах (например, Навуходоносор). Затем ищутся участки,
где имя есть в еврейском стихе, но его нет в сопоставленном синодальном. Несколько таких
стихов подряд указывают на сдвиг сопоставления.

Запуск: python tools/audit_synodal.py   (нужен собранный корпус)
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "ot"


def stems(text):
    return {w[:4].lower() for w in re.findall(r"[А-ЯЁ][а-яё]{3,}", text)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    books = json.loads((CORPUS / "books.json").read_text("utf-8"))
    verses = []
    for b in books:
        for c in range(1, b["chapters"] + 1):
            ch = json.loads((CORPUS / b["id"] / f"{c:03d}.json").read_text("utf-8"))
            for v in ch["verses"]:
                names = {s["lemma"] for w in v["words"] for s in w["segs"]
                         if s["lemma"] and (s["morph"] or "").startswith("Np")}
                text = " ".join(s["text"] for s in v["syn"])
                verses.append((v["ref"], names, stems(text)))
    seen, together = Counter(), defaultdict(Counter)
    for _, names, st in verses:
        for n in names:
            seen[n] += 1
            together[n].update(st)
    russian = {}
    for n, total in seen.items():
        if total >= 5 and together[n]:
            stem, hits = together[n].most_common(1)[0]
            if hits / total >= 0.6:
                russian[n] = stem
    suspicious = []
    for ref, names, st in verses:
        known = [n for n in names if n in russian]
        if known and not any(russian[n] in st for n in known):
            suspicious.append(ref)
    # участки из трёх и более подозрительных стихов подряд
    order = {ref: i for i, (ref, _, _) in enumerate(verses)}
    runs, run = [], []
    for ref in suspicious:
        if run and order[ref] - order[run[-1]] <= 2:
            run.append(ref)
        else:
            if len(run) >= 3:
                runs.append(run)
            run = [ref]
    if len(run) >= 3:
        runs.append(run)
    print(f"имён с найденной русской основой: {len(russian)}; стихов, где имя не найдено: {len(suspicious)}")
    for r in runs:
        print(f"участок: {r[0]} … {r[-1]} ({len(r)} стихов)")


if __name__ == "__main__":
    main()
