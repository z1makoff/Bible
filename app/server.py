"""Локальный сервер читалки: http://127.0.0.1:8795

Запуск: python app/server.py [--no-browser]
Отдаёт страницу из app/static и данные из corpus/, decisions/, translations/, interpretations/.
Пишет только в user/: заметки, решения пользователя, место чтения и журнал всех изменений.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
CORPUS = ROOT / "corpus"
USER = Path(os.environ.get("READER_USER_DIR") or ROOT / "user")  # другая папка — только для проверок
HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", 8795))
LOCK = threading.Lock()

RULE_GRADES = {
    "entailed": "Следует из текста", "strong": "Сильно подтверждается", "supported": "Подтверждается",
    "plausible": "Правдоподобно", "compatible": "Совместимо", "speculative": "Спекулятивно",
    "contradicted": "Противоречит тексту",
}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except FileNotFoundError:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    os.replace(tmp, path)


class Data:
    def __init__(self):
        if not (CORPUS / "lexemes.json").exists():
            print("Собираю корпус (один раз, около минуты)…")
            subprocess.run([sys.executable, str(ROOT / "tools" / "build_corpus.py")], check=True)
        self.books = read_json(CORPUS / "ot" / "books.json")
        self.enoch_books = read_json(CORPUS / "enoch" / "books.json", [])
        self.book_ids = {b["id"] for b in self.books} | {b["id"] for b in self.enoch_books}
        self.lexemes = read_json(CORPUS / "lexemes.json")
        self.occurrences = read_json(CORPUS / "occurrences.json")
        self._geez_lexemes = None
        self._geez_occurrences = None
        self._enoch_word_refs = None
        self.library = {b["id"]: b for b in read_json(ROOT / "library" / "books.json", {"books": []})["books"]}
        self.syn_only = {}
        for s in read_json(CORPUS / "ot" / "synodal-only.json", []):
            self.syn_only.setdefault(s["after"], []).append(s)

    def chapter(self, book, n):
        if book == "1En":
            src = read_json(CORPUS / "enoch" / "1En" / f"{n:03d}.json")
            tr = read_json(ROOT / "translations" / "1En" / f"{n:03d}.json")
        else:
            src = read_json(CORPUS / "ot" / book / f"{n:03d}.json")
            tr = read_json(ROOT / "translations" / "ot" / book / f"{n:03d}.json")
        if src is None:
            return None
        if book != "1En":
            for v in src["verses"]:
                v["synOnly"] = self.syn_only.get(v["ref"], [])
        decisions = read_json(USER / "decisions.json", {})
        notes = read_json(USER / "notes.json", {})
        prefix = f"{book}.{n}."
        return {
            "book": book, "chapter": n, "verses": src["verses"], "translation": tr,
            "userDecisions": {k: v for k, v in decisions.items() if k.startswith(prefix)},
            "notes": {k: v for k, v in notes.items()
                      if k.startswith(f"place:{prefix}") or k.startswith(f"verse:{prefix}")},
        }

    def lexicon_entry(self, key):
        folder = "geez" if str(key).startswith("L") else "lexicon"
        return read_json(ROOT / "decisions" / folder / f"{key}.json")

    def geez_lexemes(self):
        if self._geez_lexemes is None:
            self._geez_lexemes = read_json(CORPUS / "geez-lexemes.json", {})
        return self._geez_lexemes

    def geez_occurrences(self):
        if self._geez_occurrences is None:
            self._geez_occurrences = read_json(CORPUS / "geez-occurrences.json", {})
        return self._geez_occurrences

    def enoch_word_refs(self):
        """Номер слова e… → стих 1En.c.v. Считается один раз, когда открывают карточку геэза."""
        if self._enoch_word_refs is None:
            refs = {}
            folder = CORPUS / "enoch" / "1En"
            if folder.exists():
                for path in folder.glob("*.json"):
                    chapter = read_json(path, {})
                    for verse in chapter.get("verses", []):
                        for word in verse.get("words", []):
                            refs[word["id"]] = verse["ref"]
            self._enoch_word_refs = refs
        return self._enoch_word_refs

    def geez_refs(self, key):
        occ = self.geez_occurrences().get(key) or {}
        index = self.enoch_word_refs()
        refs, seen = [], set()
        for wid in occ.get("words") or []:
            ref = index.get(wid)
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
        refs.sort(key=lambda ref: [int(part) for part in ref.split(".")[1:]])
        return refs

    def geez_public(self, key):
        info = self.geez_lexemes().get(key)
        if info is None:
            return None
        refs = self.geez_refs(key)
        return {
            "key": key,
            "info": {
                "geez": True,
                "lemma": info.get("head") or "",
                "xlit": info.get("tr") or "",
                "lat": info.get("lat") or "",
                "n": info.get("n"),
                "pos": info.get("pos") or [],
                "senses": info.get("senses") or [],
                "en": info.get("en") or [],
                "greek": info.get("greek") or [],
            },
            "decision": self.lexicon_entry(key),
            "occurrences": [{"book": "1En", "refs": refs}] if refs else [],
            "count": len((self.geez_occurrences().get(key) or {}).get("words") or []),
        }

    def interpretations(self, key, ref):
        out = []
        for p in sorted((ROOT / "interpretations").glob("*.json")):
            it = read_json(p)
            # трактовка слова — по словарной форме; трактовка без слов — по месту
            if it and (key in it.get("lemmas", []) or (not it.get("lemmas") and ref in it.get("places", []))):
                for s in it.get("support", []):
                    s["gradeRu"] = RULE_GRADES.get(s.get("grade"), s.get("grade"))
                src = it.get("source") or {}
                book = self.library.get(src.get("book"))
                if book:
                    src["title"] = book["title"]
                    src["edition"] = ", ".join(str(x) for x in (book.get("publisher"), book.get("year")) if x)
                out.append(it)
        return out

    def lexeme(self, key, ref):
        if str(key).startswith("L"):
            base = self.geez_public(key)
            if base is None:
                return None
            notes = read_json(USER / "notes.json", {})
            base["interpretations"] = self.interpretations(key, ref)
            base["note"] = notes.get(f"lexeme:{key}")
            return base
        info = self.lexemes.get(key)
        if info is None:
            return None
        occ = self.occurrences.get(key, [])
        by_book = {}
        for vref, _ in occ:
            b = vref.split(".")[0]
            by_book.setdefault(b, []).append(vref)
        notes = read_json(USER / "notes.json", {})
        return {
            "key": key, "info": info, "decision": self.lexicon_entry(key),
            "occurrences": [{"book": b, "refs": sorted(set(r), key=lambda x: [int(p) for p in x.split(".")[1:]])}
                            for b, r in by_book.items()],
            "count": len(occ),
            "interpretations": self.interpretations(key, ref),
            "note": notes.get(f"lexeme:{key}"),
        }


def log_change(kind, target, before, after):
    USER.mkdir(exist_ok=True)
    entry = {"date": datetime.now().isoformat(timespec="seconds"), "kind": kind,
             "target": target, "before": before, "after": after}
    with open(USER / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup_user_data():
    """Раз в день при запуске копирует файлы пользователя в user/backups/<дата>/ (ничего не удаляет)."""
    files = [p for p in USER.glob("*") if p.suffix in (".json", ".jsonl")]
    target = USER / "backups" / datetime.now().strftime("%Y-%m-%d")
    if not files or target.exists():
        return
    target.mkdir(parents=True)
    for p in files:
        shutil.copy2(p, target / p.name)


def read_history():
    try:
        lines = (USER / "history.jsonl").read_text("utf-8").splitlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines if line.strip()]


def prepared_chapters():
    """Статусы подготовленных глав: ВЗ по книге, 1 Енох — ключ «1En»."""
    done = {}
    ot = ROOT / "translations" / "ot"
    if ot.exists():
        for path in ot.glob("*/*.json"):
            done.setdefault(path.parent.name, {})[int(path.stem)] = read_json(path, {}).get("status", "draft")
    enoch = ROOT / "translations" / "1En"
    if enoch.exists():
        for path in enoch.glob("*.json"):
            done.setdefault("1En", {})[int(path.stem)] = read_json(path, {}).get("status", "draft")
    return done


def export_user_data():
    """Файл для переноса на телефон (сайт) и обратно; формат тот же, что в app/static/local.js."""
    return {"format": "chitalka-user", "version": 1, "exported": datetime.now().isoformat(timespec="seconds"),
            **{name: read_json(USER / f"{name}.json", {}) for name in ("notes", "decisions", "progress", "state")},
            "history": read_history()}


def import_user_data(data):
    """Сливает файл с телефона: ничего не удаляет, из двух версий записи оставляет более новую по дате.
    Перед слиянием копирует текущие данные в user/backups/import-<время>/."""
    USER.mkdir(exist_ok=True)
    files = [p for p in USER.glob("*") if p.suffix in (".json", ".jsonl")]
    if files:
        target = USER / "backups" / ("import-" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        target.mkdir(parents=True, exist_ok=True)
        for p in files:
            shutil.copy2(p, target / p.name)
    counts = {}
    for name in ("notes", "decisions", "progress"):
        mine = read_json(USER / f"{name}.json", {})
        n = 0
        for k, v in (data.get(name) or {}).items():
            if not isinstance(v, dict) or not isinstance(v.get("date"), str):
                continue
            if k not in mine or v["date"] > mine[k].get("date", ""):
                mine[k] = v
                n += 1
        if n:
            write_json(USER / f"{name}.json", mine)
        counts[name] = n
    state = read_json(USER / "state.json", {})
    new_state = {k: v for k, v in (data.get("state") or {}).items() if k not in state}
    if new_state:
        write_json(USER / "state.json", {**state, **new_state})
    seen = {json.dumps(h, ensure_ascii=False, sort_keys=True) for h in read_history()}
    with open(USER / "history.jsonl", "a", encoding="utf-8") as f:
        for h in data.get("history") or []:
            s = json.dumps(h, ensure_ascii=False, sort_keys=True)
            if isinstance(h, dict) and s not in seen:
                seen.add(s)
                f.write(json.dumps(h, ensure_ascii=False) + "\n")
    return counts


class Handler(SimpleHTTPRequestHandler):
    data: Data = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        d = self.data
        if path == "/api/books":
            state = read_json(USER / "state.json", {})
            progress = read_json(USER / "progress.json", {})
            return self.send_json({"books": d.books, "enoch": d.enoch_books, "prepared": prepared_chapters(),
                                   "state": state, "progress": progress})
        m = re.fullmatch(r"/api/chapter/([1-3]?[A-Za-z]+)/(\d+)", path)
        if m and m.group(1) in d.book_ids:
            ch = d.chapter(m.group(1), int(m.group(2)))
            return self.send_json(ch) if ch else self.send_json({"error": "нет такой главы"}, 404)
        m = re.fullmatch(r"/api/lexeme/(L[0-9a-fA-F]+|\d+[a-z]?)", path)
        if m:
            ref = parse_qs(urlparse(self.path).query).get("ref", [""])[0]
            lx = d.lexeme(m.group(1), ref)
            return self.send_json(lx) if lx else self.send_json({"error": "нет такого слова"}, 404)
        if path == "/api/export":
            return self.send_json(export_user_data())
        if path.startswith("/api/"):
            return self.send_json({"error": "неизвестный запрос"}, 404)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        if length > (20_000_000 if path == "/api/import" else 100_000):
            return self.send_json({"error": "слишком большой запрос"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "неверный запрос"}, 400)
        now = datetime.now().isoformat(timespec="seconds")
        with LOCK:
            if path == "/api/note":
                target, text = str(body.get("target", "")), str(body.get("text", "")).strip()
                if not re.fullmatch(r"(lexeme:(?:\d+[a-z]?|L[0-9a-fA-F]+)|place:[1-3]?[A-Za-z]+\.\d+\.\d+:\w+|verse:[1-3]?[A-Za-z]+\.\d+\.\d+)", target):
                    return self.send_json({"error": "неверная цель заметки"}, 400)
                notes = read_json(USER / "notes.json", {})
                before = notes.get(target)
                if text:
                    notes[target] = {"text": text, "date": now}
                else:
                    notes.pop(target, None)
                write_json(USER / "notes.json", notes)
                log_change("note", target, before, notes.get(target))
                return self.send_json({"ok": True, "note": notes.get(target)})
            if path == "/api/decision":
                key = str(body.get("place", ""))
                if not re.fullmatch(r"[1-3]?[A-Za-z]+\.\d+\.\d+:\w+", key):
                    return self.send_json({"error": "неверное место"}, 400)
                text, reason = str(body.get("text", "")).strip(), str(body.get("reason", "")).strip()
                decisions = read_json(USER / "decisions.json", {})
                before = decisions.get(key)
                if text:
                    decisions[key] = {"text": text, "reason": reason, "date": now, "seenByClaude": False}
                else:
                    decisions.pop(key, None)
                write_json(USER / "decisions.json", decisions)
                log_change("decision", key, before, decisions.get(key))
                return self.send_json({"ok": True, "decision": decisions.get(key)})
            if path == "/api/state":
                state = read_json(USER / "state.json", {})
                if re.fullmatch(r"[1-3]?[A-Za-z]+\.\d+(\.\d+)?", str(body.get("last", ""))):
                    state["last"] = body["last"]
                for k in ("showHebrew", "showSynodal", "showGeez", "showSmirnov", "showGreek"):
                    if isinstance(body.get(k), bool):
                        state[k] = body[k]
                if "returnTo" in body:
                    r = body["returnTo"]
                    if r is None:
                        state.pop("returnTo", None)
                    elif (isinstance(r, dict) and re.fullmatch(r"[1-3]?[A-Za-z]+\.\d+\.\d+", str(r.get("ref", "")))
                          and re.fullmatch(r"\w+", str(r.get("wid", "")))):
                        state["returnTo"] = {"ref": r["ref"], "wid": r["wid"]}
                write_json(USER / "state.json", state)
                return self.send_json({"ok": True})
            if path == "/api/progress":
                chapter = str(body.get("chapter", ""))
                if not re.fullmatch(r"[1-3]?[A-Za-z]+\.\d+", chapter) or not isinstance(body.get("read"), bool):
                    return self.send_json({"error": "неверная глава"}, 400)
                progress = read_json(USER / "progress.json", {})
                before = progress.get(chapter)
                if body["read"]:
                    progress[chapter] = before or {"date": now}
                else:
                    progress.pop(chapter, None)
                write_json(USER / "progress.json", progress)
                if before != progress.get(chapter):
                    log_change("progress", chapter, before, progress.get(chapter))
                return self.send_json({"ok": True, "progress": progress.get(chapter)})
            if path == "/api/import":
                if not isinstance(body, dict) or body.get("format") != "chitalka-user":
                    return self.send_json({"error": "это не файл с данными читалки"}, 400)
                return self.send_json({"ok": True, "counts": import_user_data(body)})
        return self.send_json({"error": "неизвестный запрос"}, 404)


def already_running():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, PORT)) == 0


def main():
    if sys.stdout is None:  # запуск без консоли (pythonw): сообщения и ошибки — в журнал
        USER.mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(USER / "server.log", "a", encoding="utf-8", buffering=1)
        print(f"--- запуск {datetime.now().isoformat(timespec='seconds')}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    url = f"http://{HOST}:{PORT}/"
    open_browser = "--no-browser" not in sys.argv
    if already_running():
        if open_browser:
            webbrowser.open(url)
        return
    backup_user_data()
    Handler.data = Data()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    print(f"Читалка: {url}")
    server.serve_forever()


if __name__ == "__main__":
    main()
