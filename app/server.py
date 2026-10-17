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
        self.book_ids = {b["id"] for b in self.books}
        self.lexemes = read_json(CORPUS / "lexemes.json")
        self.occurrences = read_json(CORPUS / "occurrences.json")
        self.library = {b["id"]: b for b in read_json(ROOT / "library" / "books.json", {"books": []})["books"]}
        self.syn_only = {}
        for s in read_json(CORPUS / "ot" / "synodal-only.json", []):
            self.syn_only.setdefault(s["after"], []).append(s)

    def chapter(self, book, n):
        src = read_json(CORPUS / "ot" / book / f"{n:03d}.json")
        if src is None:
            return None
        tr = read_json(ROOT / "translations" / "ot" / book / f"{n:03d}.json")
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
        return read_json(ROOT / "decisions" / "lexicon" / f"{key}.json")

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
            done = {}
            for p in (ROOT / "translations" / "ot").glob("*/*.json"):
                tr = read_json(p, {})
                done.setdefault(p.parent.name, {})[int(p.stem)] = tr.get("status", "draft")
            state = read_json(USER / "state.json", {})
            progress = read_json(USER / "progress.json", {})
            return self.send_json({"books": d.books, "prepared": done, "state": state, "progress": progress})
        m = re.fullmatch(r"/api/chapter/([1-3]?[A-Za-z]+)/(\d+)", path)
        if m and m.group(1) in d.book_ids:
            ch = d.chapter(m.group(1), int(m.group(2)))
            return self.send_json(ch) if ch else self.send_json({"error": "нет такой главы"}, 404)
        m = re.fullmatch(r"/api/lexeme/(\d+[a-z]?)", path)
        if m:
            ref = parse_qs(urlparse(self.path).query).get("ref", [""])[0]
            lx = d.lexeme(m.group(1), ref)
            return self.send_json(lx) if lx else self.send_json({"error": "нет такого слова"}, 404)
        if path.startswith("/api/"):
            return self.send_json({"error": "неизвестный запрос"}, 404)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        if length > 100_000:
            return self.send_json({"error": "слишком большой запрос"}, 413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "неверный запрос"}, 400)
        now = datetime.now().isoformat(timespec="seconds")
        with LOCK:
            if path == "/api/note":
                target, text = str(body.get("target", "")), str(body.get("text", "")).strip()
                if not re.fullmatch(r"(lexeme:\d+[a-z]?|place:[1-3]?[A-Za-z]+\.\d+\.\d+:\w+|verse:[1-3]?[A-Za-z]+\.\d+\.\d+)", target):
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
                for k in ("showHebrew", "showSynodal"):
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
