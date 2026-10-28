// Стол — стартовый экран: на нём лежат трактаты (Танах, Книга Еноха, …).
// Выбранный трактат анимацией выезжает, раскрывается и переходит в страницу чтения;
// при возврате на стол та же анимация идёт обратно.
// На сайте и телефоне стол двумерный с перспективой (CSS), в программе на компьютере — 3D (desk3d.js, Three.js);
// без WebGL программа тоже показывает двумерный стол.
"use strict";

const Desk = (() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const EASE = "cubic-bezier(.2,.7,.2,1)";
  const GEEZ = "ቃለ፡ በረከት፡ ዘሄኖክ፡";
  const HEBREW = "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ";
  let token = 0;  // каждый показ или уход со стола отменяет незаконченную анимацию
  let d3 = null;  // модуль desk3d.js, если загружен

  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function webgl() {
    try {
      const c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch { return false; }
  }

  function show(main, tracts, opts) {
    const my = ++token;
    if (!opts.local && webgl()) {
      main.innerHTML = `<div class="desk"></div>`;
      import("./desk3d.js")
        .then((m) => {
          if (my !== token) return;
          d3 = m;
          m.mount(main.firstChild, tracts, { ...opts, live: () => my === token, reduce: reduce.matches });
        })
        .catch((e) => {
          console.warn("3D-стол недоступен, показан обычный:", e);
          if (my === token) show2d(main, tracts, opts, my);
        });
      return;
    }
    show2d(main, tracts, opts, my);
  }

  function hide() {
    token++;
    if (d3) d3.unmount();
  }

  // ---------- 2.5D ----------

  function item(t) {
    const obj = t.kind === "scroll"
      ? `<div class="obj scroll" style="--rz:4deg"><div class="roller"></div><div class="paper"><span>${GEEZ}</span></div><div class="roller"></div></div>`
      : `<div class="obj codex${t.later ? " small" : ""}" style="--rz:${t.later ? 9 : -5}deg"><div class="pages">${HEBREW}</div>
         <div class="cover"><div class="c-front"><b>${h(t.title)}</b><small>${h(t.sub)}</small></div><div class="c-back"></div></div>${t.cont ? `<div class="ribbon"></div>` : ""}</div>`;
    return `<div class="tract-item" data-id="${t.id}">
      <button class="t-open"${t.later ? " disabled" : ""} aria-label="${h(t.later ? `${t.title} — позже` : `Открыть: ${t.title}`)}">
        ${obj}<span class="t-label"><b>${h(t.title)}</b><small>${h(t.info)}</small></span></button>
      ${t.cont ? `<button class="t-cont">${h(t.cont.label)}</button>` : ""}</div>`;
  }

  function show2d(main, tracts, opts, my) {
    main.innerHTML = `<div class="desk"><div class="desk-top"></div>
      <div class="desk-head"><h1>Читалка</h1><p>Выберите трактат</p></div>
      <div class="desk-items">${tracts.map(item).join("")}</div><div class="desk-veil"></div></div>`;
    const desk = main.firstChild;
    let busy = false;
    const open = async (t, href) => {
      if (busy) return;
      busy = true;
      const ok = await run(plan(desk, t), my);
      if (ok) opts.onOpen(href);
    };
    for (const t of tracts) {
      const el = desk.querySelector(`[data-id="${t.id}"]`);
      el.querySelector(".t-open").onclick = () => { if (!t.later) open(t, t.href); };
      const cont = el.querySelector(".t-cont");
      if (cont) cont.onclick = () => open(t, t.cont.href);
    }
    const from = tracts.find((t) => t.id === opts.from);
    if (from) close(desk, from, my);
  }

  // Шаги открытия: группы анимаций [элемент, кадры, длительность], группы идут друг за другом.
  function plan(desk, t) {
    const el = desk.querySelector(`[data-id="${t.id}"]`);
    const obj = el.querySelector(".obj");
    const rest = getComputedStyle(obj).transform;
    obj.style.transition = "none";
    obj.style.transform = "none";
    const r = obj.getBoundingClientRect();
    obj.style.transform = "";
    void obj.offsetWidth;
    obj.style.transition = "";
    const s = desk.getBoundingClientRect();
    const dx = s.left + s.width / 2 - (r.left + r.width / 2);
    const dy = s.top + s.height / 2 - (r.top + r.height / 2);
    const k = Math.min(s.height * 0.5 / r.height, s.width * 0.8 / r.width, 2.4);
    const mid = `translate(${dx}px, ${dy}px) rotateX(0deg) rotateZ(0deg) scale(${k})`;
    const near = `translate(${dx}px, ${dy}px) rotateX(0deg) rotateZ(0deg) scale(${k * 2.4})`;
    const fade = (e) => [e, [{ opacity: getComputedStyle(e).opacity }, { opacity: 0 }], 320];
    const others = [...desk.querySelectorAll(".tract-item, .desk-head")].filter((e) => e !== el)
      .concat([...el.querySelectorAll(".t-label, .t-cont")]);
    let unfold;
    if (t.kind === "scroll") {
      const w = Math.max(60, Math.min(s.width * 0.88 / k - 52, 460));
      unfold = [[el.querySelector(".paper"), [{ width: "8px" }, { width: `${w}px` }], 850],
        [el.querySelector(".paper span"), [{ opacity: 0 }, { opacity: 1 }], 850]];
    } else {
      unfold = [[el.querySelector(".cover"), [{ transform: "translateZ(4px) rotateY(0deg)" }, { transform: "translateZ(4px) rotateY(-165deg)" }], 800]];
    }
    return [
      others.map(fade),
      [[obj, [{ transform: rest }, { transform: mid }], 700]],
      unfold,
      [[obj, [{ transform: mid }, { transform: near }], 520], [desk.querySelector(".desk-veil"), [{ opacity: 0 }, { opacity: 1 }], 520]],
    ];
  }

  async function run(steps, my) {
    for (const group of steps) {
      await Promise.all(group.map(([el, frames, ms]) =>
        el.animate(frames, { duration: reduce.matches ? 1 : ms, easing: EASE, fill: "forwards" }).finished));
      if (my !== token) return false;
    }
    return true;
  }

  // Возврат на стол: трактат сразу показан раскрытым и затем закрывается обратным ходом.
  async function close(desk, t, my) {
    const steps = plan(desk, t);
    for (const group of steps)
      for (const [el, frames] of group) el.animate([frames[1], frames[1]], { duration: 0, fill: "forwards" });
    const back = steps.reverse().map((g) => g.map(([el, frames, ms]) => [el, [...frames].reverse(), ms]));
    if (!(await run(back, my))) return;
    for (const el of desk.querySelectorAll("*")) for (const a of el.getAnimations()) a.cancel();
  }

  return { show, hide };
})();
