// Читалка без сервера (сайт на телефоне): те же запросы, что к app/server.py, но текст берётся
// из готовых файлов data/ (tools/build_site.py), а заметки, решения и место чтения — из памяти браузера.
// Подключается только на сайте; на компьютере читалка работает через сервер.
"use strict";

const LocalApi = (() => {
  const PREFIX = "chitalka.";
  const memory = {};  // если память браузера недоступна — хотя бы до закрытия страницы

  function load(name, empty) {
    try {
      const raw = localStorage.getItem(PREFIX + name);
      if (raw !== null) return JSON.parse(raw);
    } catch (e) { /* приватный режим или повреждённая запись */ }
    return memory[name] ?? empty;
  }

  function save(name, value) {
    memory[name] = value;
    try { localStorage.setItem(PREFIX + name, JSON.stringify(value)); } catch (e) { /* остаётся в memory */ }
  }

  function now() {  // как datetime.now().isoformat(timespec="seconds") на сервере
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  function logChange(kind, target, before, after) {
    const history = load("history", []);
    history.push({ date: now(), kind, target, before: before ?? null, after: after ?? null });
    save("history", history);
  }

  async function file(path) {
    const res = await fetch(path);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error("не удалось загрузить данные — нет интернета?");
    return res.json();
  }

  let places = null;

  const REF_PLACE = /^[1-3]?[A-Za-z]+\.\d+\.\d+:\w+$/;
  const NOTE_TARGET = /^(lexeme:\d+[a-z]?|place:[1-3]?[A-Za-z]+\.\d+\.\d+:\w+|verse:[1-3]?[A-Za-z]+\.\d+\.\d+)$/;

  async function get(path, query) {
    if (path === "/api/books") {
      const data = await file("data/books.json");
      return { ...data, state: load("state", {}), progress: load("progress", {}) };
    }
    let m = path.match(/^\/api\/chapter\/([1-3]?[A-Za-z]+)\/(\d+)$/);
    if (m) {
      const ch = await file(`data/chapter/${m[1]}/${String(+m[2]).padStart(3, "0")}.json`);
      if (!ch) throw new Error("нет такой главы");
      const prefix = `${m[1]}.${+m[2]}.`;
      const pick = (obj, test) => Object.fromEntries(Object.entries(obj).filter(([k]) => test(k)));
      ch.userDecisions = pick(load("decisions", {}), (k) => k.startsWith(prefix));
      ch.notes = pick(load("notes", {}), (k) => k.startsWith(`place:${prefix}`) || k.startsWith(`verse:${prefix}`));
      return ch;
    }
    m = path.match(/^\/api\/lexeme\/(\d+[a-z]?)$/);
    if (m) {
      const lx = await file(`data/lexeme/${m[1]}.json`);
      if (!lx) throw new Error("нет такого слова");
      places = places || await file("data/places.json") || {};
      const ref = query.get("ref") || "";
      lx.interpretations = [...lx.interpretations, ...(places[ref] || [])].sort((a, b) => a._order - b._order);
      lx.note = load("notes", {})[`lexeme:${m[1]}`] ?? null;
      return lx;
    }
    if (path === "/api/export") return exportData();
    throw new Error("неизвестный запрос");
  }

  function post(path, body) {
    if (path === "/api/note") {
      const target = String(body.target ?? ""), text = String(body.text ?? "").trim();
      if (!NOTE_TARGET.test(target)) throw new Error("неверная цель заметки");
      const notes = load("notes", {});
      const before = notes[target];
      if (text) notes[target] = { text, date: now() }; else delete notes[target];
      save("notes", notes);
      logChange("note", target, before, notes[target]);
      return { ok: true, note: notes[target] ?? null };
    }
    if (path === "/api/decision") {
      const key = String(body.place ?? "");
      if (!REF_PLACE.test(key)) throw new Error("неверное место");
      const text = String(body.text ?? "").trim(), reason = String(body.reason ?? "").trim();
      const decisions = load("decisions", {});
      const before = decisions[key];
      if (text) decisions[key] = { text, reason, date: now(), seenByClaude: false }; else delete decisions[key];
      save("decisions", decisions);
      logChange("decision", key, before, decisions[key]);
      return { ok: true, decision: decisions[key] ?? null };
    }
    if (path === "/api/state") {
      const st = load("state", {});
      if (/^[1-3]?[A-Za-z]+\.\d+(\.\d+)?$/.test(String(body.last ?? ""))) st.last = body.last;
      for (const k of ["showHebrew", "showSynodal"]) if (typeof body[k] === "boolean") st[k] = body[k];
      if ("returnTo" in body) {
        const r = body.returnTo;
        if (r === null) delete st.returnTo;
        else if (r && /^[1-3]?[A-Za-z]+\.\d+\.\d+$/.test(String(r.ref)) && /^\w+$/.test(String(r.wid))) st.returnTo = { ref: r.ref, wid: r.wid };
      }
      save("state", st);
      return { ok: true };
    }
    if (path === "/api/progress") {
      const chapter = String(body.chapter ?? "");
      if (!/^[1-3]?[A-Za-z]+\.\d+$/.test(chapter) || typeof body.read !== "boolean") throw new Error("неверная глава");
      const progress = load("progress", {});
      const before = progress[chapter];
      if (body.read) progress[chapter] = before || { date: now() }; else delete progress[chapter];
      save("progress", progress);
      if (JSON.stringify(before) !== JSON.stringify(progress[chapter])) logChange("progress", chapter, before, progress[chapter]);
      return { ok: true, progress: progress[chapter] ?? null };
    }
    if (path === "/api/import") return importData(body);
    throw new Error("неизвестный запрос");
  }

  function exportData() {
    return { format: "chitalka-user", version: 1, exported: now(),
      notes: load("notes", {}), decisions: load("decisions", {}), progress: load("progress", {}),
      state: load("state", {}), history: load("history", []) };
  }

  // Слияние — так же, как /api/import на сервере: из двух записей остаётся более новая по дате.
  function importData(data) {
    if (data?.format !== "chitalka-user") throw new Error("это не файл с данными читалки");
    const counts = {};
    for (const name of ["notes", "decisions", "progress"]) {
      const mine = load(name, {});
      let n = 0;
      for (const [k, v] of Object.entries(data[name] || {})) {
        if (!v || typeof v.date !== "string") continue;
        if (!mine[k] || v.date > mine[k].date) { mine[k] = v; n++; }
      }
      save(name, mine);
      counts[name] = n;
    }
    const st = load("state", {});
    for (const [k, v] of Object.entries(data.state || {})) if (!(k in st)) st[k] = v;
    save("state", st);
    const history = load("history", []);
    const seen = new Set(history.map((h) => JSON.stringify(h)));
    for (const h of data.history || []) if (!seen.has(JSON.stringify(h))) { history.push(h); seen.add(JSON.stringify(h)); }
    history.sort((a, b) => String(a.date).localeCompare(String(b.date)));
    save("history", history);
    return { ok: true, counts };
  }

  // Просим браузер не стирать данные читалки при нехватке места.
  navigator.storage?.persist?.().catch(() => {});
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

  return {
    async call(path, body) {
      const url = new URL(path, location.href);
      return body ? post(url.pathname, body) : get(url.pathname, url.searchParams);
    },
  };
})();
