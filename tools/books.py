"""Книги-источники трактовок: каталог library/books.json и поиск цитаты в тексте книги.

Сами книги лежат вне репозитория (папка folder в каталоге). Текст книги извлекается один раз
и кэшируется в .cache/books/ в виде одних букв и цифр: так цитата находится, даже если в книге
перенос слова, лишний пробел, другие кавычки или разрыв строки посреди фразы.

Тексты в общественном достоянии хранятся прямо в проекте (library/texts/, поле path в каталоге).

EPUB и TXT читаются стандартной библиотекой. Для PDF нужен PyMuPDF (pymupdf) или программа pdftotext;
если ни того ни другого нет, цитата из PDF считается непроверенной (не ошибкой).

Запуск: python tools/books.py <id книги> "<цитата>"   — проверить цитату вручную
"""
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "library" / "books.json"
CACHE = ROOT / ".cache" / "books"
MAX_QUOTE_WORDS = 15


@lru_cache(maxsize=None)
def catalog():
    if not CATALOG.exists():
        return {"folder": "", "books": []}
    return json.loads(CATALOG.read_text("utf-8"))


def book(book_id):
    return next((b for b in catalog()["books"] if b["id"] == book_id), None)


def book_path(b):
    """Книга в общей папке (folder + file) или файл внутри проекта (path, от корня проекта)."""
    if b.get("path"):
        return (ROOT / b["path"]).resolve()
    return (ROOT / catalog()["folder"] / b["file"]).resolve()


def letters(text):
    """Только буквы и цифры в нижнем регистре, без диакритики: «dell’ac-\\nqua» → «dellacqua»."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if ch.isalnum() and not unicodedata.combining(ch))


def epub_text(path):
    z = zipfile.ZipFile(path)
    opf_name = next(n for n in z.namelist() if n.endswith(".opf"))
    opf = z.read(opf_name).decode("utf-8", "replace")
    base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
    manifest = {}
    for tag in re.findall(r"<item\b[^>]*>", opf):
        i, h = re.search(r'\bid="([^"]+)"', tag), re.search(r'\bhref="([^"]+)"', tag)
        if i and h:
            manifest[i.group(1)] = html.unescape(h.group(1))
    parts = []
    for idref in re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf):
        name = base + manifest.get(idref, "")
        if name in z.namelist():
            raw = z.read(name).decode("utf-8", "replace")
            parts.append(html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    return "\n".join(parts)


def pdf_text(path):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            pymupdf = None
    if pymupdf:
        with pymupdf.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, check=True)
        return out.stdout.decode("utf-8", "replace")
    return None


def book_letters(b):
    """Текст книги одними буквами; None — файла нет или PDF нечем прочитать."""
    path = book_path(b)
    if not path.exists():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{b['id']}.txt"
    stamp = CACHE / f"{b['id']}.stamp"
    st = path.stat()
    digest = f"{st.st_size}:{st.st_mtime_ns}"
    if cached.exists() and stamp.exists() and stamp.read_text().strip() == digest:
        return cached.read_text("utf-8")
    suffix = path.suffix.lower()
    if suffix == ".epub":
        text = epub_text(path)
    elif suffix == ".txt":
        text = path.read_text("utf-8")
    else:
        text = pdf_text(path)
    if text is None:
        return None
    norm = letters(text)
    cached.write_text(norm, "utf-8")
    stamp.write_text(digest)
    return norm


def file_matches(b):
    """True — файл совпадает с каталогом по SHA-256; None — файла нет."""
    path = book_path(b)
    if not path.exists():
        return None
    return not b.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() == b["sha256"]


def find_quote(book_id, quote):
    """True / False — найдена ли цитата; None — книгу проверить нечем."""
    b = book(book_id)
    text = book_letters(b) if b else None
    if text is None:
        return None
    return letters(quote) in text


def quote_words(quote):
    return len(re.findall(r"\w+", quote))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    found = find_quote(sys.argv[1], sys.argv[2])
    print({True: "найдено", False: "не найдено", None: "книгу проверить нечем"}[found])
