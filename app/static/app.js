"use strict";

const SECTIONS = [
  ["Пятикнижие", ["Gen", "Exod", "Lev", "Num", "Deut"]],
  ["Исторические книги", ["Josh", "Judg", "Ruth", "1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr", "Ezra", "Neh", "Esth"]],
  ["Учительные книги", ["Job", "Ps", "Prov", "Eccl", "Song"]],
  ["Пророки", ["Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel", "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal"]],
];
const STATUS = { draft: "черновик", ready: "подготовлена", reviewed: "проверена вами" };
const KIND = { word: "слово", name: "имя собственное", divine: "имя или титул божества", function: "служебное слово",
  keep: "не переводится нигде" };
const NO_SPACE_BEFORE = new Set([".", ",", ";", ":", "!", "?", "»", "“", "›", ")", "…"]);
const NO_SPACE_AFTER = new Set(["«", "„", "‹", "("]);

const state = { books: [], byId: {}, prepared: {}, progress: {}, settings: {}, chapter: null, selected: null, returnTo: null };
const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// На сайте без сервера (телефон) те же запросы обслуживает local.js.
const LOCAL = typeof LocalApi !== "undefined";

async function api(path, body) {
  if (LOCAL) return LocalApi.call(path, body);
  const res = await fetch(path, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "ошибка сервера");
  return data;
}

function times(n) {
  const d = n % 10, h = n % 100;
  return `${n} ${d >= 2 && d <= 4 && (h < 12 || h > 14) ? "раза" : "раз"}`;
}

function refLabel(ref) {
  const [b, c, v] = ref.split(".");
  const name = state.byId[b]?.name || b;
  return v ? `${name} ${c}:${v}` : `${name} ${c}`;
}

function refLink(ref) {
  const [b, c, v] = ref.split(".");
  return `<a href="#/${b}/${c}/${v}">${esc(refLabel(ref))}</a>`;
}

// ---------- библиотека ----------

function renderLibrary() {
  $("#where").hidden = true;
  $("#toggles").hidden = true;
  closeCard();
  const last = state.settings.last;
  let html = `<section class="library"><h1>Ветхий Завет</h1>`;
  if (last) {
    const [b, c, v] = last.split(".");
    html += `<p><a class="continue" href="#/${b}/${c}${v ? "/" + v : ""}">Продолжить: ${esc(refLabel(last))}</a></p>`;
  }
  for (const [title, ids] of SECTIONS) {
    html += `<h2>${title}</h2><div class="books">`;
    for (const id of ids) {
      const b = state.byId[id];
      const done = Object.keys(state.prepared[id] || {}).length;
      const read = readCount(id);
      const info = [done ? `подготовлено ${done} из ${b.chapters}` : `${b.chapters} гл.`, read ? `прочитано ${read}` : ""];
      html += `<a class="book${done ? " has" : ""}" href="#/${id}">${esc(b.name)}
        <small>${info.filter(Boolean).join(" · ")}</small></a>`;
    }
    html += `</div>`;
  }
  html += `<h2>Ваши данные</h2><p class="hint">${LOCAL
    ? "Заметки, решения, место чтения и отметки хранятся только в этом браузере. Чтобы перенести их на компьютер или на другой телефон, сохраните файл и загрузите его там."
    : "Чтобы перенести заметки, решения, место чтения и отметки на телефон (или вернуть их оттуда), сохраните файл и загрузите его на другом устройстве."}
    При загрузке ничего не стирается: из двух версий одной записи остаётся более новая.</p>
    <p class="data-actions"><button id="exportData">Сохранить в файл</button>
    <button id="importData">Загрузить из файла</button><input type="file" id="importFile" accept=".json,application/json" hidden></p>
    <p class="hint" id="dataResult"></p>`;
  $("#main").innerHTML = html + `</section>`;
  $("#exportData").onclick = exportData;
  $("#importData").onclick = () => $("#importFile").click();
  $("#importFile").onchange = (e) => importData(e.target.files[0]);
  document.title = "Читалка";
}

async function exportData() {
  const data = await api("/api/export");
  const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `chitalka-${data.exported.slice(0, 10)}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  $("#dataResult").textContent = `Файл ${a.download} сохранён в загрузки.`;
}

async function importData(f) {
  if (!f) return;
  let msg;
  try {
    const c = (await api("/api/import", JSON.parse(await f.text()))).counts;
    msg = `Загружено: заметок ${c.notes}, решений ${c.decisions}, отметок о прочтении ${c.progress}.`;
    const fresh = await api("/api/books");
    state.settings = fresh.state || {};
    state.progress = fresh.progress || {};
    state.returnTo = state.settings.returnTo || null;
    renderReturnButton();
    renderLibrary();
  } catch (e) {
    msg = `Не получилось: ${e instanceof SyntaxError ? "файл повреждён" : e.message}.`;
  }
  $("#dataResult").textContent = msg;
}

function renderBook(id) {
  const b = state.byId[id];
  $("#where").hidden = true;
  $("#toggles").hidden = true;
  closeCard();
  let html = `<section class="library"><h1>${esc(b.name)}</h1><div class="chapters">`;
  for (let c = 1; c <= b.chapters; c++) {
    const st = (state.prepared[id] || {})[c];
    const rd = state.progress[`${id}.${c}`];
    const title = [st ? STATUS[st] : "не подготовлена", rd ? `прочитана ${dateRu(rd.date)}` : ""].filter(Boolean).join(", ");
    html += `<a class="ch${st ? " has" : ""}${rd ? " read" : ""}" href="#/${id}/${c}" title="${title}">${c}</a>`;
  }
  $("#main").innerHTML = html + `</div><p class="hint">Выделены подготовленные главы; ✓ — прочитанные вами.</p></section>`;
  document.title = b.name;
}

// ---------- глава ----------

async function openChapter(book, chapter, verse, lookup = false) {
  const b = state.byId[book];
  if (!b || chapter < 1 || chapter > b.chapters) return renderLibrary();
  const data = await api(`/api/chapter/${book}/${chapter}`);
  state.chapter = data;
  $("#where").hidden = false;
  $("#toggles").hidden = false;
  $("#bookName").innerHTML = `<a href="#/${book}">${esc(b.name)}</a>`;
  const sel = $("#chapterSelect");
  sel.innerHTML = Array.from({ length: b.chapters }, (_, i) =>
    `<option value="${i + 1}"${i + 1 === chapter ? " selected" : ""}>${i + 1}</option>`).join("");
  document.title = `${b.name} ${chapter}`;
  renderChapter();
  if (verse) {
    const el = document.getElementById(`v${verse}`);
    if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); }
  } else {
    window.scrollTo(0, 0);
  }
  if (!lookup) saveState({ last: `${book}.${chapter}${verse ? "." + verse : ""}` });
  reopenPendingCard();
}

function translatedVerses() {
  const tr = state.chapter.translation;
  const out = {};
  for (const v of tr?.verses || []) out[v.n] = v;
  return out;
}

function userDecision(ref, wid) {
  return state.chapter.userDecisions[`${ref}:${wid}`];
}

function renderRussian(v, tv) {
  const parts = [];
  let prevNoSpace = true;
  const overridden = new Set();
  for (const sp of tv.spans) {
    const k = sp.k || "tr";
    const ids = sp.w || [];
    let text = sp.t;
    let cls = `sp sp-${k}`;
    const owner = ids.find((wid) => k !== "fn" && userDecision(v.ref, wid) && !overridden.has(wid));
    if (owner) {
      overridden.add(owner);
      text = userDecision(v.ref, owner).text;
      cls += " user";
    }
    const space = prevNoSpace || (k === "p" && NO_SPACE_BEFORE.has(sp.t)) ? "" : " ";
    prevNoSpace = k === "p" && NO_SPACE_AFTER.has(sp.t);
    const mark = sp.g ? `<sup class="gmark" title="Грамматический выбор">◇</sup>` : "";
    const attrs = ids.length ? ` data-w="${esc(ids.join(" "))}" tabindex="0"` : "";
    parts.push(`${space}<span class="${cls}"${attrs}>${esc(text)}${mark}</span>`);
  }
  return `<p class="ru">${parts.join("")}</p>`;
}

function renderHebrew(v) {
  const words = v.words.map((w) => {
    const ket = w.ketiv ? `<sup class="ketiv" title="Кетив: так написано; масореты велят читать иначе">к</sup>` : "";
    return `<span class="hw" data-w="${esc(w.id)}" tabindex="0">${esc(w.text)}${ket}</span>${w.maqqef ? "־" : " "}`;
  }).join("");
  return `<p class="he" dir="rtl" lang="he">${words}</p>`;
}

function renderSynodal(v) {
  if (!v.syn.length) return `<p class="syn empty">В Синодальном (по этому источнику) этого текста нет.</p>`;
  const [book, ch, n] = v.ref.split(".");
  return v.syn.map((s) => {
    const same = s.exact && String(s.c) === ch && String(s.v) === n;
    const label = same ? "" : `<span class="synref" title="${s.exact ? "Другой номер стиха" : "Границы стихов не совпадают"}">${s.exact ? "" : "≈ "}${s.c}:${s.v}</span> `;
    return `<p class="syn">${label}${esc(s.text)}</p>`;
  }).join("");
}

function renderSynOnly(v) {
  if (!v.synOnly.length) return "";
  const first = v.synOnly[0], last = v.synOnly[v.synOnly.length - 1];
  const range = first === last ? `${first.c}:${first.v}` : `${first.c}:${first.v} – ${last.c}:${last.v}`;
  const body = v.synOnly.map((s) => `<p class="syn"><span class="synref">${s.c}:${s.v}</span> ${esc(s.text)}</p>`).join("");
  return `<details class="synonly"><summary>Только в Синодальном (${range}): этого текста нет в еврейском, он взят из греческого перевода</summary>${body}</details>`;
}

function renderChapter() {
  const ch = state.chapter;
  const b = state.byId[ch.book];
  const tr = ch.translation;
  const tvs = translatedVerses();
  const showHe = state.settings.showHebrew || !tr;
  const showSyn = state.settings.showSynodal || !tr;
  $("#showHebrew").checked = !!state.settings.showHebrew;
  $("#showSynodal").checked = !!state.settings.showSynodal;
  let html = `<article class="chapter"><h1>${esc(b.name)} ${ch.chapter}</h1>`;
  if (!tr) {
    html += `<p class="status">Глава ещё не подготовлена. Показаны еврейский текст и Синодальный; слова в еврейском можно нажимать.</p>`;
  } else {
    html += `<p class="status">${esc(STATUS[tr.status] || tr.status)} · правила ${esc(tr.rules)}</p>`;
  }
  html += readButton(ch);
  for (const v of ch.verses) {
    const tv = tvs[v.n];
    html += `<section class="verse${v.break ? " brk-" + v.break : ""}" id="v${v.n}">`;
    html += `<a class="vn" href="#/${ch.book}/${ch.chapter}/${v.n}" title="Запомнить место">${v.n}</a>`;
    html += `<div class="vt">`;
    if (tv) html += renderRussian(v, tv);
    else if (tr) html += `<p class="ru pending">Стих ещё не подготовлен.</p>`;
    if (showHe || (tr && !tv)) html += renderHebrew(v);
    if (showSyn || (tr && !tv)) html += renderSynodal(v);
    html += renderSynOnly(v) + `</div></section>`;
  }
  const n = ch.chapter;
  html += `<div class="read-end">${readButton(ch)}</div>`;
  html += `<nav class="bottom">${n > 1 ? `<a href="#/${ch.book}/${n - 1}">‹ Глава ${n - 1}</a>` : "<span></span>"}`;
  html += n < b.chapters ? `<a href="#/${ch.book}/${n + 1}">Глава ${n + 1} ›</a>` : "<span></span>";
  $("#main").innerHTML = html + `</nav></article>`;
  if (state.selected) highlight(state.selected.wid);
}

function dateRu(iso) {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

function readCount(book) {
  return Object.keys(state.progress).filter((k) => k.startsWith(book + ".")).length;
}

function readButton(ch) {
  const rd = state.progress[`${ch.book}.${ch.chapter}`];
  return rd
    ? `<button class="readmark done" title="Снять отметку">✓ Прочитано ${dateRu(rd.date)}</button>`
    : `<button class="readmark" title="Отметить главу прочитанной">Отметить главу прочитанной</button>`;
}

async function toggleRead() {
  const ch = state.chapter;
  const key = `${ch.book}.${ch.chapter}`;
  const res = await api("/api/progress", { chapter: key, read: !state.progress[key] });
  if (res.progress) state.progress[key] = res.progress; else delete state.progress[key];
  document.querySelectorAll(".readmark").forEach((b) => { b.outerHTML = readButton(ch); });
}

// ---------- карточка слова ----------

function findWord(wid) {
  for (const v of state.chapter.verses) {
    for (const w of v.words) {
      if (w.id === wid) return { v, w };
      for (const q of w.qere || []) if (q.id === wid) return { v, w: q, ketiv: w };
    }
  }
  return null;
}

function contentLemmas(w) {
  return w.segs.filter((s) => s.lemma).map((s) => s.lemma);
}

function highlight(wid) {
  document.querySelectorAll(".sel").forEach((el) => el.classList.remove("sel"));
  document.querySelectorAll("[data-w]").forEach((el) => {
    if (el.dataset.w.split(" ").includes(wid)) el.classList.add("sel");
  });
}

function closeCard() {
  $("#card").hidden = true;
  document.body.classList.remove("with-card");
  state.selected = null;
  document.querySelectorAll(".sel").forEach((el) => el.classList.remove("sel"));
}

function placeExplanation(v, w, lex) {
  const tv = translatedVerses()[v.n];
  if (!state.chapter.translation) return `<p class="muted">Глава ещё не подготовлена: решения для этого места нет.</p>`;
  if (!tv) return `<p class="muted">Стих ещё не подготовлен.</p>`;
  const spans = tv.spans.filter((s) => (s.w || []).includes(w.id));
  const place = (tv.places || {})[w.id];
  let html = "";
  const main = spans.find((s) => s.k !== "fn") || spans[0];
  if (tv.omit && tv.omit[w.id]) {
    html += `<p>Отдельным русским словом не передаётся: ${esc(tv.omit[w.id] === "et" ? "это метка прямого дополнения" : tv.omit[w.id])}.</p>`;
  } else if (main && main.k === "lat") {
    html += `<p><b>Не переведено</b> — оставлено как <i>${esc(main.t)}</i>.</p>`;
  } else if (main) {
    const sid = typeof main.s === "object" ? main.s?.[w.id] : main.s;
    const sense = lex?.decision?.senses?.find((s) => s.id === sid);
    html += `<p><b>Переведено:</b> «${esc(main.t)}»${sense ? ` — значение «${esc(sense.ru)}»` : ""}.</p>`;
    if (main.x) html += `<p><b>Исключение из словаря решений:</b> ${esc(main.x)}</p>`;
  }
  if (main?.g) html += `<p><span class="gmark">◇</span> <b>Грамматический выбор:</b> ${esc(main.g)}</p>`;
  if (place) {
    if (place.fits?.length) {
      const names = place.fits.map((f) => lex?.decision?.senses?.find((s) => s.id === f)?.ru || f);
      html += `<p>Подходят здесь: ${names.map((n) => `«${esc(n)}»`).join(", ")}.</p>`;
    }
    html += `<p>${esc(place.why)}</p>`;
  }
  return html;
}

function decisionBlock(lex) {
  const d = lex.decision;
  if (!d) return `<p class="muted">Решения в словаре пока нет.</p>`;
  let html = `<p>${esc(KIND[d.kind] || d.kind)} · в тексте: <i>${esc(d.display)}</i>${d.status === "approved" ? " · подтверждено вами" : " · черновик"}</p>`;
  if (d.notes) html += `<p>${esc(d.notes)}</p>`;
  if (d.senses?.length) {
    html += `<ul class="senses">` + d.senses.map((s) =>
      `<li><b>«${esc(s.ru)}»</b>${s.gloss ? ` — ${esc(s.gloss)}` : ""}<br><small>Видно в: ${s.evidence.map(refLink).join(", ")}</small></li>`).join("") + `</ul>`;
  }
  return html;
}

// Трактовки к этому месту — сразу; трактовки того же слова к другим местам — свёрнуты, каждая под своей строкой
function interpretationsBlock(lex, ref) {
  if (!lex.interpretations.length) return "";
  const here = lex.interpretations.filter((it) => (it.places || []).includes(ref));
  const order = (r) => { const [b, c, v] = (r || "").split("."); return [state.books.findIndex((x) => x.id === b), +c, +v]; };
  const byPlace = (a, b) => {
    const x = order(a.places?.[0]), y = order(b.places?.[0]);
    return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
  };
  const other = lex.interpretations.filter((it) => !(it.places || []).includes(ref)).sort(byPlace);
  let html = `<h3>Трактовки</h3>`;
  if (here.length) html += here.map(interpretationBlock).join("");
  else html += `<p class="muted">К этому месту трактовок нет.</p>`;
  if (other.length) {
    html += `<details class="interp-other"><summary>Трактовки этого слова к другим местам <small>${other.length}</small></summary>` +
      other.map((it) => `<details><summary>${esc(it.tradition.replace(/ \(.*\)$/, ""))} · ${esc((it.places || []).map(refLabel).join(", "))}
        <br><small>${esc(it.claim.length > 120 ? it.claim.slice(0, 120) + "…" : it.claim)}</small></summary>
        <p class="refs">К местам: ${(it.places || []).map(refLink).join(", ")}</p>${interpretationBlock(it)}</details>`).join("") +
      `</details>`;
  }
  return html;
}

function interpretationBlock(it) {
  const src = it.source || {};
  const where = [src.chapter && `глава «${esc(src.chapter)}»`, src.section && esc(src.section), src.page && `с. ${esc(src.page)}`, src.time && esc(src.time),
    src.url && `<a href="${esc(src.url)}" target="_blank" rel="noopener">ссылка</a>`].filter(Boolean).join(", ");
  const quote = src.quote ? `<blockquote class="quote">«${esc(src.quote)}»${src.quoteRu ? `<br><small>${esc(src.quoteRu)}</small>` : ""}</blockquote>` : "";
  return `<div class="interp"><p><b>${esc(it.tradition)}:</b> ${esc(it.claim)}</p>
    <ul>${(it.support || []).map((s) => `<li><span class="grade">${esc(s.gradeRu)}</span> — ${esc(s.claim)}
      ${s.for?.length ? `<br><small>за: ${s.for.map(refLink).join(", ")}</small>` : ""}
      ${s.against?.length ? `<br><small>против: ${s.against.map(refLink).join(", ")}</small>` : ""}
      ${s.note ? `<br><small>${esc(s.note)}</small>` : ""}</li>`).join("")}</ul>
    <p class="src">Источник: <i>${esc(src.title)}</i>${src.edition ? `, ${esc(src.edition)}` : ""}${where ? `, ${where}` : ""}</p>${quote}</div>`;
}

function occurrencesBlock(lex) {
  const books = lex.occurrences.map((o) =>
    `<details><summary>${esc(state.byId[o.book]?.name || o.book)} <small>${o.refs.length}</small></summary>
      <p class="refs">${o.refs.map(refLink).join(" · ")}</p></details>`).join("");
  return `<h3>Где ещё встречается <small>${times(lex.count)}</small></h3>${books}`;
}

function dictionariesBlock(info) {
  const parts = [];
  if (info.bdb) parts.push(`<p><b>BDB:</b> ${info.bdb.senses ? info.bdb.senses.map(esc).join("; ") : esc(info.bdb.text)}</p>`);
  if (info.strong?.meaning) parts.push(`<p><b>Strong:</b> ${esc(info.strong.meaning)}</p>`);
  if (info.step) parts.push(`<p><b>STEPBible:</b> ${esc(info.step.gloss)}${info.step.meaning ? ` — ${esc(info.step.meaning)}` : ""}</p>`);
  if (!parts.length) return "";
  return `<details class="dicts"><summary>Что пишут словари (подсказка, не доказательство)</summary>${parts.join("")}</details>`;
}

async function openCard(wid) {
  const found = findWord(wid);
  if (!found) return;
  const { v, w, ketiv } = found;
  state.selected = { wid, ref: v.ref };
  highlight(wid);
  const card = $("#card");
  card.hidden = false;
  document.body.classList.add("with-card");
  const sel = document.querySelector("#main .sel");
  if (sel && matchMedia("(max-width: 600px)").matches) {  // на телефоне карточка снизу: слово — над ней
    window.scrollBy(0, sel.getBoundingClientRect().top - $(".bar").offsetHeight - 16);
  }
  const grammar = w.segs.map((s) => `<li><span class="he-inline" lang="he">${esc(s.t.replace(/[֑-֯]/g, ""))}</span> — ${esc(MORPH.segment(s.morph, w.lang))}</li>`).join("");
  const keys = contentLemmas(w);
  const lexes = await Promise.all(keys.map((k) => api(`/api/lexeme/${k}?ref=${encodeURIComponent(v.ref)}`).catch(() => null)));
  let html = `<button class="close" title="Закрыть (Esc)" aria-label="Закрыть">×</button>
    <p class="word" lang="he" dir="rtl">${esc(w.text)}</p><p class="tr">${esc(w.tr)}</p>
    <p class="ref">${esc(refLabel(v.ref))}${w.lang === "A" ? " · арамейский" : ""}</p>`;
  if (w.ketiv) {
    const q = (w.qere || []).map((x) => esc(x.text)).join(" ");
    html += `<p class="note">Так <b>написано</b> (кетив). Масореты велят <b>читать</b>: <span lang="he">${q || "— (не читать)"}</span>.</p>`;
  }
  if (ketiv) html += `<p class="note">Это <b>чтение</b> (кере) к написанному <span lang="he">${esc(ketiv.text)}</span>.</p>`;
  html += `<h3>Грамматика</h3><ul class="grammar">${grammar}</ul>`;
  const lex = lexes.find(Boolean);
  html += `<h3>Почему здесь так</h3>${placeExplanation(v, w, lex)}`;
  const ud = userDecision(v.ref, w.id);
  html += `<h3>Ваше решение для этого места</h3>
    <form class="decision"><input name="text" placeholder="Как передать здесь" value="${esc(ud?.text || "")}">
    <input name="reason" placeholder="Почему (по желанию)" value="${esc(ud?.reason || "")}">
    <button>Сохранить</button>${ud ? `<small>сохранено ${esc(ud.date.replace("T", " "))}; Claude учтёт его при подготовке следующих глав</small>` : ""}</form>`;
  for (const lx of lexes) {
    if (!lx) continue;
    html += `<section class="lexeme"><h2><span lang="he">${esc(lx.info.lemma || "")}</span> <i>${esc(lx.info.xlit || lx.key)}</i></h2>`;
    html += decisionBlock(lx) + interpretationsBlock(lx, v.ref) + occurrencesBlock(lx) + dictionariesBlock(lx.info);
    html += `<h3>Ваша заметка к слову</h3><form class="note-form" data-target="lexeme:${esc(lx.key)}">
      <textarea name="text" rows="3" placeholder="Мысли, наблюдения, вопросы">${esc(lx.note?.text || "")}</textarea>
      <button>Сохранить</button></form></section>`;
  }
  if (!keys.length) html += `<p class="muted">У этого слова нет словарной формы в разметке.</p>`;
  card.innerHTML = html;
  card.scrollTop = 0;
  card.querySelector(".close").onclick = closeCard;
  card.querySelector(".decision").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const res = await api("/api/decision", { place: `${v.ref}:${w.id}`, text: f.text.value, reason: f.reason.value });
    const key = `${v.ref}:${w.id}`;
    if (res.decision) state.chapter.userDecisions[key] = res.decision; else delete state.chapter.userDecisions[key];
    renderChapter();
    openCard(wid);
  };
  card.querySelectorAll(".note-form").forEach((f) => {
    f.onsubmit = async (e) => {
      e.preventDefault();
      await api("/api/note", { target: f.dataset.target, text: f.text.value });
      f.querySelector("button").textContent = "Сохранено";
      setTimeout(() => { f.querySelector("button").textContent = "Сохранить"; }, 1500);
    };
  });
}

// ---------- состояние и навигация ----------

function saveState(patch) {
  Object.assign(state.settings, patch);
  api("/api/state", patch).catch(() => {});
}

// Переход по ссылке из карточки — это справка, а не чтение: место чтения не меняется,
// а в шапке появляется кнопка возврата к слову, с которого начались переходы.
function rememberReturn() {
  if (!state.returnTo && state.selected) {
    state.returnTo = { ref: state.selected.ref, wid: state.selected.wid };
    saveState({ returnTo: state.returnTo });
  }
  state.lookup = true;
  renderReturnButton();
}

function renderReturnButton() {
  const btn = $("#backToReading");
  btn.hidden = !state.returnTo;
  if (state.returnTo) btn.textContent = `← Вернуться: ${refLabel(state.returnTo.ref)}`;
}

function goBack() {
  const r = state.returnTo;
  if (!r) return;
  state.returnTo = null;
  saveState({ returnTo: null });
  state.pendingCard = r.wid;
  renderReturnButton();
  const [b, c, v] = r.ref.split(".");
  const target = `#/${b}/${c}/${v}`;
  if (location.hash === target) route(); else location.hash = target;
}

function reopenPendingCard() {
  const wid = state.pendingCard;
  state.pendingCard = null;
  if (wid) openCard(wid);
}

function route() {
  const lookup = state.lookup;
  state.lookup = false;
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (!parts.length) return renderLibrary();
  const [book, ch, v] = parts;
  if (!state.byId[book]) return renderLibrary();
  if (!ch) return renderBook(book);
  const sameChapter = state.chapter && state.chapter.book === book && state.chapter.chapter === +ch && $("#where").hidden === false;
  if (sameChapter && v) {
    const el = document.getElementById(`v${v}`);
    if (el) { el.scrollIntoView({ block: "center" }); el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
    if (!lookup) saveState({ last: `${book}.${ch}.${v}` });
    reopenPendingCard();
    return;
  }
  openChapter(book, +ch, v ? +v : null, lookup).catch((e) => { $("#main").innerHTML = `<p class="error">${esc(e.message)}</p>`; });
}

function step(delta) {
  const ch = state.chapter;
  if (!ch || $("#where").hidden) return;
  const n = ch.chapter + delta;
  if (n >= 1 && n <= state.byId[ch.book].chapters) location.hash = `#/${ch.book}/${n}`;
}

document.addEventListener("click", (e) => {
  const link = e.target.closest('#card a[href^="#/"]');
  if (link && link.getAttribute("href") !== location.hash) rememberReturn();
  if (e.target.closest(".readmark")) toggleRead();
  const w = e.target.closest("[data-w]");
  if (w && $("#main").contains(w)) openCard(w.dataset.w.split(" ")[0]);
});
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) return;
  if (e.altKey || e.ctrlKey || e.metaKey) return;  // Alt+← — «назад» браузера, не листание глав
  if (e.key === "Backspace" && state.returnTo) { e.preventDefault(); goBack(); }
  if (e.key === "Escape") closeCard();
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
  if (e.key === "Enter" && e.target.dataset?.w) openCard(e.target.dataset.w.split(" ")[0]);
});
$("#backToReading").onclick = goBack;
$("#prev").onclick = () => step(-1);
$("#next").onclick = () => step(1);
$("#chapterSelect").onchange = (e) => { location.hash = `#/${state.chapter.book}/${e.target.value}`; };
$("#showHebrew").onchange = (e) => { saveState({ showHebrew: e.target.checked }); renderChapter(); };
$("#showSynodal").onchange = (e) => { saveState({ showSynodal: e.target.checked }); renderChapter(); };
window.addEventListener("hashchange", route);

(async function start() {
  const data = await api("/api/books");
  state.books = data.books;
  state.byId = Object.fromEntries(data.books.map((b) => [b.id, b]));
  state.prepared = data.prepared;
  state.settings = data.state || {};
  state.progress = data.progress || {};
  state.returnTo = state.settings.returnTo || null;
  renderReturnButton();
  route();
})();
