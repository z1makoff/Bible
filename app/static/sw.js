// Офлайн-режим сайта: всё, что уже открывалось, читается и без интернета.
// Сначала сеть (чтобы новые главы появлялись сразу), без сети — сохранённая копия.
// Подключается только на сайте (local.js); __VERSION__ подставляет tools/build_site.py.
"use strict";

const CACHE = "chitalka";
const SHELL = ["./", "index.html", "style.css", "morph.js", "local.js", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "data/books.json", "data/places.json"];

self.addEventListener("install", (e) => {
  // версия __VERSION__: новый файл заставляет браузер обновить оболочку
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })))));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const res = await fetch(req, { cache: "no-cache" });
      if (res.ok) cache.put(req, res.clone());
      return res;
    } catch (err) {
      const hit = await cache.match(req, { ignoreSearch: true });
      if (hit) return hit;
      throw err;
    }
  })());
});
