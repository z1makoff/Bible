"""Мутационная проверка: пропустит ли tools/check.py явно неверный перевод, если в нём случайно есть короткая основа.
Копирует нужное во временную папку, портит одну главу и запускает проверку там. Проект не меняется."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CASES = [  # (глава, старый текст фрагмента, новый текст): новый — заведомо другое значение
    ("Gen/018.json", "дал", "предал"),        # natan [give], основа «да»
    ("Gen/024.json", "напоила", "попросила"),  # shaqah [give-drink], основа «по»
    ("Gen/015.json", "бойся", "богохульствуй"),  # yare [fear], основа «бо»
]
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    # tools копируется, а не связывается ссылкой: check.py ищет корень проекта от своего настоящего пути
    shutil.copytree(ROOT / "tools", tmp / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    if len(sys.argv) > 1:  # другая версия check.py, например из git: python … mutation_stems.py old_check.py
        shutil.copy(sys.argv[1], tmp / "tools" / "check.py")
    for d in ("decisions", "interpretations", "library", "corpus"):
        (tmp / d).symlink_to(ROOT / d)
    shutil.copy(ROOT / "ПРАВИЛА.md", tmp)
    shutil.copytree(ROOT / "translations", tmp / "translations")
    for rel, old, new in CASES:
        p = tmp / "translations/ot" / rel
        t = json.loads(p.read_text("utf-8")); done = False
        for v in t["verses"]:
            for sp in v["spans"]:
                if not done and sp["t"] == old and not sp.get("k"):
                    sp["t"] = new; done = f"{rel} {v['n']}"
        p.write_text(json.dumps(t, ensure_ascii=False), "utf-8")
        b, c = rel.split("/"); c = str(int(c[:3]))
        r = subprocess.run([sys.executable, str(tmp / "tools/check.py"), b, c], capture_output=True, text=True)
        tail = r.stdout.strip().splitlines()[-1]
        print(f"{done}: «{old}» → «{new}»: {'ПРОПУЩЕНО проверкой' if r.returncode == 0 else 'поймано'} ({tail})")
