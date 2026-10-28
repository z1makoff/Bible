// 3D-стол программы на компьютере (Three.js из app/static/vendor). На сайт не копируется:
// там и без WebGL работает двумерный стол из desk.js. Все текстуры рисуются на холсте, без картинок.
import * as THREE from "./vendor/three.module.min.js";

const GEEZ = "ቃለ፡ በረከት፡ ዘሄኖክ፡";
const HEBREW = "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ׃ וְהָאָרֶץ הָיְתָה תֹהוּ וָבֹהוּ וְחֹשֶׁךְ עַל־פְּנֵי תְהוֹם";
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

let desk = null;

export function mount(el, tracts, opts) {
  desk ??= new Desk3D();
  desk.attach(el, tracts, opts);
}

export function unmount() {
  if (desk) desk.detach();
}

// ---------- текстуры ----------

function canvas(w, h, paint) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  paint(c.getContext("2d"), w, h);
  return c;
}

function noise(g, w, h, n, light, dark) {
  for (let i = 0; i < n; i++) {
    g.fillStyle = Math.random() < 0.5 ? light : dark;
    g.fillRect(Math.random() * w, Math.random() * h, 1 + Math.random() * 2, 1 + Math.random() * 2);
  }
}

function paintWood(g, w, h, dark) {
  g.fillStyle = dark ? "#5a3a22" : "#9c6c42";
  g.fillRect(0, 0, w, h);
  for (let i = 0; i < 260; i++) {
    const y0 = Math.random() * h, amp = 2 + Math.random() * 7, f = 0.002 + Math.random() * 0.004, ph = Math.random() * 6;
    g.strokeStyle = Math.random() < 0.7 ? `rgba(35,18,6,${0.04 + Math.random() * 0.12})` : `rgba(255,220,170,${0.03 + Math.random() * 0.05})`;
    g.lineWidth = 0.8 + Math.random() * 3;
    g.beginPath();
    for (let x = 0; x <= w; x += 16) g.lineTo(x, y0 + Math.sin(x * f + ph) * amp);
    g.stroke();
  }
  g.fillStyle = "rgba(0,0,0,.35)";
  for (const y of [h * 0.25, h * 0.5, h * 0.75]) g.fillRect(0, y, w, 3);
  noise(g, w, h, 9000, "rgba(255,230,190,.05)", "rgba(20,10,0,.07)");
}

function paintLeather(g, w, h, color) {
  g.fillStyle = color;
  g.fillRect(0, 0, w, h);
  noise(g, w, h, w * h / 60, "rgba(255,255,255,.035)", "rgba(0,0,0,.08)");
}

function paintCover(g, w, h, color, title, sub) {
  paintLeather(g, w, h, color);
  g.strokeStyle = "#d9b26a";
  g.globalAlpha = 0.85;
  g.lineWidth = 7;
  g.strokeRect(34, 34, w - 68, h - 68);
  g.lineWidth = 2;
  g.strokeRect(52, 52, w - 104, h - 104);
  g.globalAlpha = 1;
  g.fillStyle = "#e2bd75";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `${Math.round(w * 0.12)}px Georgia, serif`;
  g.letterSpacing = `${Math.round(w * 0.02)}px`;
  g.fillText(title.toUpperCase(), w / 2, h * 0.42);
  g.letterSpacing = "0px";
  g.font = `italic ${Math.round(w * 0.055)}px Georgia, serif`;
  g.fillText(sub, w / 2, h * 0.53);
  g.beginPath();
  g.moveTo(w / 2 - 70, h * 0.62);
  g.lineTo(w / 2 + 70, h * 0.62);
  g.lineWidth = 2;
  g.strokeStyle = "#d9b26a";
  g.stroke();
}

function paintParchment(g, w, h) {
  g.fillStyle = "#efe3c8";
  g.fillRect(0, 0, w, h);
  noise(g, w, h, w * h / 90, "rgba(255,255,255,.08)", "rgba(120,90,50,.06)");
}

function textLines(g, x0, y0, x1, lines, lh, gap) {
  // строки «текста вдали»: серые полоски разной длины
  g.fillStyle = "rgba(70,50,30,.22)";
  for (let i = 0; i < lines; i++) {
    const len = (x1 - x0) * (i % 7 === 6 ? 0.45 : 0.85 + Math.random() * 0.15);
    g.fillRect(x1 - len, y0 + i * lh, len, gap);
  }
}

function paintPage(g, w, h) {
  paintParchment(g, w, h);
  g.fillStyle = "#4a3624";
  g.direction = "rtl";
  g.textAlign = "right";
  g.font = `${Math.round(w * 0.05)}px "Times New Roman", "SBL Hebrew", serif`;
  let line = "", y = h * 0.12;
  for (const word of HEBREW.split(" ")) {
    const t = line ? `${line} ${word}` : word;
    if (g.measureText(t).width > w * 0.78) { g.fillText(line, w * 0.9, y); line = word; y += w * 0.075; } else line = t;
  }
  g.fillText(line, w * 0.9, y);
  textLines(g, w * 0.1, y + w * 0.07, w * 0.9, 13, w * 0.065, w * 0.018);
}

function paintEdge(g, w, h) {
  g.fillStyle = "#eadcbd";
  g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y += 2) {
    g.fillStyle = `rgba(110,80,40,${0.05 + Math.random() * 0.12})`;
    g.fillRect(0, y, w, 1);
  }
}

function paintScroll(g, w, h) {
  paintParchment(g, w, h);
  const cols = 3, pad = w * 0.06, cw = (w - pad * (cols + 1)) / cols;
  for (let c = 0; c < cols; c++) {
    const x0 = pad + c * (cw + pad);
    if (c === 1) {
      // начало книги, как в эфиопских рукописях — красными чернилами
      g.fillStyle = "#9b2a1e";
      g.textAlign = "left";
      g.font = `${Math.round(h * 0.06)}px Ebrima, Nyala, "Abyssinica SIL", serif`;
      g.fillText(GEEZ, x0, h * 0.14);
      g.direction = "ltr";
    }
    g.fillStyle = "rgba(60,40,25,.22)";
    for (let i = c === 1 ? 2 : 0; i < 15; i++) {
      const len = cw * (i % 6 === 5 ? 0.5 : 0.88 + Math.random() * 0.12);
      g.fillRect(x0, h * 0.1 + i * h * 0.054, len, h * 0.016);
    }
  }
}

// ---------- сцена ----------

class Desk3D {
  constructor() {
    this.dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const r = (this.renderer = new THREE.WebGLRenderer({ antialias: true }));
    r.setPixelRatio(Math.min(devicePixelRatio, 2));
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = this.dark ? 1.05 : 1.15;
    this.aniso = r.capabilities.getMaxAnisotropy();
    this.scene = new THREE.Scene();
    const bg = new THREE.Color(this.dark ? "#17120e" : "#d6ccbc");
    this.scene.background = bg;
    this.scene.fog = new THREE.Fog(bg, 12, 24);
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 60);
    this.base = { pos: new THREE.Vector3(0, 5.3, 8.0), look: new THREE.Vector3(0.2, 0, 0.3) };
    this.home = { pos: this.base.pos.clone(), look: this.base.look.clone() };
    this.cam = { pos: this.home.pos.clone(), look: this.home.look.clone(), par: 1 };
    this.mouse = new THREE.Vector2(0, 0);
    this.ray = new THREE.Raycaster();
    this.tweens = [];
    this.objs = {};
    this.hover = null;
    this.build();
    this.loop = this.loop.bind(this);
    const cv = r.domElement;
    cv.addEventListener("pointermove", (e) => this.pointer(e));
    cv.addEventListener("pointerleave", () => { this.hover = null; this.mouse.set(0, 0); });
    cv.addEventListener("click", () => { if (this.hover) this.open(this.hover, this.tract(this.hover).href); });
    this.resizer = new ResizeObserver(() => this.resize());
  }

  tex(w, h, paint) {
    const t = new THREE.CanvasTexture(canvas(w, h, paint));
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = this.aniso;
    return t;
  }

  mesh(geo, mat, shadow = true) {
    const m = new THREE.Mesh(geo, mat);
    m.castShadow = shadow;
    m.receiveShadow = true;
    return m;
  }

  rod(a, b, r, mat) {
    const d = new THREE.Vector3().subVectors(b, a);
    const m = this.mesh(new THREE.CylinderGeometry(r, r, d.length(), 16), mat);
    m.position.copy(a).addScaledVector(d, 0.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
    return m;
  }

  build() {
    const s = this.scene, dark = this.dark;
    s.add(new THREE.HemisphereLight(dark ? "#ffe6c4" : "#fff5e6", dark ? "#24180e" : "#7d6a55", dark ? 0.6 : 1.1));

    // настольная лампа: тёплое пятно света и мягкие тени
    const lamp = new THREE.Vector3(-3.0, 2.1, -2.4), aim = new THREE.Vector3(-0.4, 0, 0.6);
    const spot = new THREE.SpotLight("#ffd39c", dark ? 60 : 24, 0, 0.8, 0.7, 2);
    spot.position.copy(lamp);
    spot.target.position.copy(aim);
    spot.castShadow = true;
    spot.shadow.mapSize.set(2048, 2048);
    spot.shadow.bias = -0.0004;
    spot.shadow.normalBias = 0.02;
    spot.shadow.camera.near = 1;
    spot.shadow.camera.far = 14;
    s.add(spot, spot.target);
    if (!dark) {
      const sun = new THREE.DirectionalLight("#fff2dd", 1.7);
      sun.position.set(5, 9, 6);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 6, bottom: -6, near: 1, far: 25 });
      sun.shadow.bias = -0.0004;
      s.add(sun);
    }

    // столешница
    const wood = this.tex(2048, 1024, (g, w, h) => paintWood(g, w, h, dark));
    const top = this.mesh(new THREE.BoxGeometry(14, 0.5, 9), new THREE.MeshStandardMaterial({ map: wood, roughness: 0.55 }), false);
    top.position.set(0, -0.25, 0.9);
    s.add(top);

    // лампа
    const brass = new THREE.MeshStandardMaterial({ color: "#8a6a3a", metalness: 0.75, roughness: 0.35 });
    const foot = new THREE.Vector3(-3.9, 0, -3.0), knee = new THREE.Vector3(-3.9, 2.0, -3.1);
    const base = this.mesh(new THREE.CylinderGeometry(0.45, 0.55, 0.12, 40), brass);
    base.position.copy(foot).setY(0.06);
    s.add(base, this.rod(foot, knee, 0.05, brass), this.rod(knee, lamp.clone().add(new THREE.Vector3(0, 0.25, 0)), 0.04, brass));
    const shadeGeo = new THREE.ConeGeometry(0.62, 0.7, 48, 1, true);
    shadeGeo.rotateX(-Math.PI / 2);
    const shade = this.mesh(shadeGeo, new THREE.MeshStandardMaterial({ color: "#2f4a3a", metalness: 0.3, roughness: 0.45, side: THREE.DoubleSide }), false);
    shade.position.copy(lamp);
    shade.lookAt(aim);
    shade.translateZ(-0.12);
    const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.15, 24, 16), new THREE.MeshBasicMaterial({ color: "#fff1c9" }));
    bulb.position.copy(lamp);
    s.add(shade, bulb);

    // чернильница с пером
    const ink = this.mesh(new THREE.CylinderGeometry(0.3, 0.36, 0.42, 32), new THREE.MeshStandardMaterial({ color: "#1c2330", roughness: 0.12, metalness: 0.2 }));
    ink.position.set(4.1, 0.21, -1.5);
    const neck = this.mesh(new THREE.CylinderGeometry(0.13, 0.15, 0.12, 24), brass);
    neck.position.set(4.1, 0.48, -1.5);
    const quill = this.mesh(new THREE.ConeGeometry(0.07, 1.7, 8), new THREE.MeshStandardMaterial({ color: "#efe9dc", roughness: 0.8 }));
    quill.position.set(4.35, 1.15, -1.75);
    quill.rotation.set(-0.35, 0, -0.45);
    s.add(ink, neck, quill);

    this.parchment = new THREE.MeshStandardMaterial({ map: this.tex(512, 512, paintParchment), roughness: 0.9 });
  }

  codex(t, x, z, rot, scale, color) {
    const W = 1.7, D = 2.3, T = 0.42;
    const leather = new THREE.MeshStandardMaterial({ map: this.tex(512, 512, (g, w, h) => paintLeather(g, w, h, color)), roughness: 0.6 });
    const cover = new THREE.MeshStandardMaterial({ map: this.tex(680, 920, (g, w, h) => paintCover(g, w, h, color, t.title, t.sub)), roughness: 0.55 });
    const edge = new THREE.MeshStandardMaterial({ map: this.tex(64, 256, paintEdge), roughness: 0.9 });
    const page = new THREE.MeshStandardMaterial({ map: this.tex(680, 920, paintPage), roughness: 0.9 });
    const group = new THREE.Group();
    const back = this.mesh(new THREE.BoxGeometry(W, 0.05, D), leather);
    back.position.y = 0.025;
    const block = this.mesh(new THREE.BoxGeometry(W - 0.1, T - 0.1, D - 0.12), [edge, leather, page, edge, edge, edge]);
    block.position.set(0.03, 0.05 + (T - 0.1) / 2, 0);
    const spine = this.mesh(new THREE.BoxGeometry(0.08, T, D), leather);
    spine.position.set(-W / 2 + 0.04, T / 2, 0);
    const pivot = new THREE.Group();
    pivot.position.set(-W / 2, T - 0.025, 0);
    const lid = this.mesh(new THREE.BoxGeometry(W, 0.05, D), [leather, leather, cover, this.parchment, leather, leather]);
    lid.position.x = W / 2;
    pivot.add(lid);
    group.add(back, block, spine, pivot);
    if (t.cont) {
      const ribbon = this.mesh(new THREE.BoxGeometry(0.09, 0.008, 0.6), new THREE.MeshStandardMaterial({ color: "#9e2328", roughness: 0.5 }));
      ribbon.position.set(0.35, T * 0.45, D / 2 + 0.12);
      ribbon.rotation.x = 0.75;
      group.add(ribbon);
    }
    group.scale.setScalar(scale);
    group.position.set(x, 0, z);
    group.rotation.y = rot;
    this.scene.add(group);
    return {
      group, kind: "codex", base: { x, z, rot }, center: -W / 2 * scale, anchor: D / 2 * scale + 0.25,
      unfold: (k) => { pivot.rotation.z = k * Math.PI * 0.985; },
    };
  }

  scroll(t, x, z, rot) {
    const L = 1.75, rr = 0.2, GMAX = 2.9;
    const sheetTex = this.tex(2400, 1400, paintScroll);
    const roll = new THREE.MeshStandardMaterial({ map: this.tex(256, 256, paintEdge), roughness: 0.85 });
    const woodMat = new THREE.MeshStandardMaterial({ color: "#5b3a1f", roughness: 0.5 });
    const group = new THREE.Group();
    const roller = () => {
      const r = new THREE.Group();
      const paper = this.mesh(new THREE.CylinderGeometry(rr, rr, L, 40), roll);
      paper.rotation.x = Math.PI / 2;
      const rodMesh = this.mesh(new THREE.CylinderGeometry(0.05, 0.05, L + 0.5, 16), woodMat);
      rodMesh.rotation.x = Math.PI / 2;
      r.add(paper, rodMesh);
      for (const s of [-1, 1]) {
        const knob = this.mesh(new THREE.SphereGeometry(0.085, 16, 12), woodMat);
        knob.position.z = s * (L / 2 + 0.27);
        r.add(knob);
      }
      r.userData.paper = paper;
      r.position.y = rr;
      group.add(r);
      return r;
    };
    const left = roller(), right = roller();
    const sheet = this.mesh(new THREE.PlaneGeometry(1, L), new THREE.MeshStandardMaterial({ map: sheetTex, roughness: 0.9 }), false);
    sheet.rotation.x = -Math.PI / 2;
    sheet.position.y = 0.012;
    group.add(sheet);
    const gap = (g) => {
      left.position.x = -(g / 2 + rr);
      right.position.x = g / 2 + rr;
      left.rotation.z = g / 2 / rr;
      right.rotation.z = -g / 2 / rr;
      const shrink = 1 - 0.3 * g / GMAX;
      for (const r of [left, right]) r.userData.paper.scale.set(shrink, 1, shrink);
      sheet.scale.x = Math.max(g, 0.001);
      sheetTex.repeat.x = g / GMAX;
      sheetTex.offset.x = (1 - sheetTex.repeat.x) / 2;
    };
    gap(0.02);
    group.position.set(x, 0, z);
    group.rotation.y = rot;
    this.scene.add(group);
    return { group, kind: "scroll", base: { x, z, rot }, center: 0, anchor: L / 2 + 0.45, unfold: (k) => gap(0.02 + k * (GMAX - 0.02)) };
  }

  setup(tracts) {
    if (this.objs.ot) return;
    const [ot, enoch, jub] = tracts;
    this.objs.ot = this.codex(ot, -1.6, 0.55, 0.14, 1, "#5a2e17");
    this.objs.enoch = this.scroll(enoch, 1.75, 0.5, -0.12);
    this.objs.jub = this.codex(jub, 4.1, 1.15, -0.45, 0.66, "#45433e");
    for (const [id, o] of Object.entries(this.objs)) {
      o.lift = 0;
      o.y = 0;
      o.group.traverse((m) => { m.userData.tract = id; });
    }
  }

  // ---------- подключение к странице ----------

  attach(el, tracts, opts) {
    this.el = el;
    this.tracts = tracts;
    this.opts = opts;
    this.reduce = opts.reduce;
    this.setup(tracts);
    this.reset();
    const later = (t) => t.later ? " dim" : "";
    el.innerHTML = `<div class="d3-ui"><div class="desk-head"><h1>Читалка</h1><p>Выберите трактат</p></div>
      ${tracts.map((t) => `<div class="d3-label${later(t)}" data-id="${t.id}">
        <button class="t-open"${t.later ? " disabled" : ""}><span class="t-label"><b>${esc(t.title)}</b><small>${esc(t.info)}</small></span></button>
        ${t.cont ? `<button class="t-cont">${esc(t.cont.label)}</button>` : ""}</div>`).join("")}</div>
      <div class="desk-veil"></div>`;
    el.prepend(this.renderer.domElement);
    this.ui = el.querySelector(".d3-ui");
    this.veil = el.querySelector(".desk-veil");
    this.labels = {};
    for (const t of tracts) {
      const lab = el.querySelector(`.d3-label[data-id="${t.id}"]`);
      this.labels[t.id] = lab;
      if (t.later) continue;
      lab.querySelector(".t-open").onclick = () => this.open(t.id, t.href);
      lab.addEventListener("mouseenter", () => { this.hover = t.id; });
      lab.addEventListener("mouseleave", () => { this.hover = null; });
      const cont = lab.querySelector(".t-cont");
      if (cont) cont.onclick = () => this.open(t.id, t.cont.href);
    }
    this.resizer.observe(el);
    this.resize();
    this.running = true;
    this.last = performance.now();
    this.raf = requestAnimationFrame(this.loop);
    if (this.objs[opts.from]) this.close(opts.from);
  }

  detach() {
    this.running = false;
    cancelAnimationFrame(this.raf);
    this.resizer.disconnect();
    this.tweens = [];
    this.renderer.domElement.remove();
  }

  reset() {
    this.busy = false;
    this.hover = null;
    this.tweens = [];
    for (const o of Object.values(this.objs)) {
      o.unfold(0);
      o.y = 0;
      o.lift = 0;
      o.group.position.set(o.base.x, 0, o.base.z);
      o.group.rotation.y = o.base.rot;
    }
    this.cam.pos.copy(this.home.pos);
    this.cam.look.copy(this.home.look);
    this.cam.par = 1;
  }

  tract(id) {
    return this.tracts.find((t) => t.id === id);
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    // узкое окно: камера отъезжает, чтобы стол помещался
    const fit = Math.max(1, 1.5 / this.camera.aspect);
    this.home.pos.copy(this.base.look).add(new THREE.Vector3().subVectors(this.base.pos, this.base.look).multiplyScalar(fit));
    if (!this.busy) this.cam.pos.copy(this.home.pos);
  }

  pointer(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    this.mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    if (this.busy) return;
    this.ray.setFromCamera(this.mouse, this.camera);
    const hit = this.ray.intersectObjects(Object.values(this.objs).map((o) => o.group), true)[0];
    const id = hit?.object.userData.tract;
    this.hover = id && !this.tract(id)?.later ? id : null;
    this.renderer.domElement.style.cursor = this.hover ? "pointer" : "";
  }

  tween(ms, fn) {
    if (this.reduce) { fn(1); return Promise.resolve(); }
    return new Promise((res) => this.tweens.push({ t0: performance.now(), ms, fn, res }));
  }

  // Плавно переводит камеру, предмет и раскрытие из текущего положения в заданное.
  move(id, ms, { pos, look, y, rot, unfold, par, veil }) {
    const o = this.objs[id], c = this.cam;
    const p0 = c.pos.clone(), l0 = c.look.clone(), y0 = o.y, r0 = o.group.rotation.y, u0 = o.k ?? 0, par0 = c.par;
    const v0 = +this.veil.style.opacity || 0;
    return this.tween(ms, (k) => {
      const e = ease(k);
      if (pos) c.pos.lerpVectors(p0, pos, e);
      if (look) c.look.lerpVectors(l0, look, e);
      if (y !== undefined) o.y = y0 + (y - y0) * e;
      if (rot !== undefined) o.group.rotation.y = r0 + (rot - r0) * e;
      if (unfold !== undefined) { o.k = u0 + (unfold - u0) * e; o.unfold(o.k); }
      if (par !== undefined) c.par = par0 + (par - par0) * e;
      if (veil !== undefined) this.veil.style.opacity = String(v0 + (veil - v0) * e);
    });
  }

  shots(id) {
    const o = this.objs[id];
    const look = new THREE.Vector3(o.base.x + o.center, 0.55, o.base.z);
    return {
      lift: { pos: look.clone().add(new THREE.Vector3(0, 4.7, 1.9)), look, y: 0.55, rot: 0, par: 0 },
      dive: { pos: look.clone().add(new THREE.Vector3(0, 1.15, 0.3)), look },
    };
  }

  async open(id, href) {
    if (this.busy) return;
    this.busy = true;
    this.hover = null;
    this.ui.classList.add("gone");
    const s = this.shots(id);
    await this.move(id, 1000, s.lift);
    await this.move(id, 1000, { unfold: 1 });
    await this.move(id, 650, { ...s.dive, veil: 1 });
    if (this.running && this.opts.live()) this.opts.onOpen(href);
  }

  async close(id) {
    this.busy = true;
    this.ui.classList.add("gone");
    const s = this.shots(id), o = this.objs[id], c = this.cam;
    c.pos.copy(s.dive.pos);
    c.look.copy(s.dive.look);
    c.par = 0;
    o.y = 0.55;
    o.group.rotation.y = 0;
    o.k = 1;
    o.unfold(1);
    this.veil.style.opacity = "1";
    await this.move(id, 700, { pos: s.lift.pos, look: s.lift.look, veil: 0 });
    await this.move(id, 900, { unfold: 0 });
    this.ui.classList.remove("gone");
    await this.move(id, 1000, { pos: this.home.pos, look: this.home.look, y: 0, rot: o.base.rot, par: 1 });
    this.busy = false;
  }

  // ---------- кадр ----------

  loop(now) {
    if (!this.running) return;
    this.raf = requestAnimationFrame(this.loop);
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    for (const tw of [...this.tweens]) {
      const k = Math.min(1, (now - tw.t0) / tw.ms);
      tw.fn(k);
      if (k === 1) { this.tweens.splice(this.tweens.indexOf(tw), 1); tw.res(); }
    }
    for (const [id, o] of Object.entries(this.objs)) {
      o.lift += ((this.hover === id ? 0.14 : 0) - o.lift) * Math.min(1, dt * 10);
      o.group.position.y = o.y + o.lift;
    }
    this.render();
  }

  render() {
    const c = this.cam;
    this.camera.position.set(c.pos.x + this.mouse.x * 0.45 * c.par, c.pos.y + this.mouse.y * 0.25 * c.par, c.pos.z);
    this.camera.lookAt(c.look);
    this.renderer.render(this.scene, this.camera);
    if (this.busy) return;
    const w = this.el.clientWidth, h = this.el.clientHeight, v = new THREE.Vector3();
    for (const [id, o] of Object.entries(this.objs)) {
      const lab = this.labels[id];
      if (!lab) continue;
      v.set(0, 0, o.anchor).applyAxisAngle(new THREE.Vector3(0, 1, 0), o.group.rotation.y).add(o.group.position).project(this.camera);
      lab.style.left = `${((v.x + 1) / 2) * w}px`;
      lab.style.top = `${((1 - v.y) / 2) * h}px`;
      lab.classList.toggle("hot", this.hover === id);
    }
  }
}
