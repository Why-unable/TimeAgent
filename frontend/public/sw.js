// Time Agent service worker: PWA offline shell + Web Push.
// One SW controls the page scope, so both concerns live here.

const CACHE_VERSION = "v3";
const APP_SHELL_CACHE = `time-agent-shell-${CACHE_VERSION}`;
const RUNTIME_CACHE = `time-agent-runtime-${CACHE_VERSION}`;

// Minimal shell precached on install. Hashed build assets are cached at
// runtime on first request instead of being enumerated here.
const APP_SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(APP_SHELL_CACHE)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== APP_SHELL_CACHE && key !== RUNTIME_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isCacheableAsset(url) {
  // Same-origin static build output only.
  return (
    url.origin === self.location.origin &&
    /\.(?:js|css|woff2?|ttf|otf|png|jpg|jpeg|svg|gif|webp|ico|json)$/.test(url.pathname) &&
    !url.pathname.startsWith("/api") &&
    !url.pathname.startsWith("/health")
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Never intercept API, health, or release downloads. APK requests must reach
  // Nginx directly and must never fall back to or poison the cached SPA shell.
  if (
    url.pathname.startsWith("/api") ||
    url.pathname.startsWith("/health") ||
    url.pathname.startsWith("/releases/")
  ) {
    return;
  }

  // SPA navigations: network-first, fall back to cached shell when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const contentType = response.headers.get("content-type") || "";
          if (response.ok && contentType.includes("text/html")) {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put("/index.html", copy));
          }
          return response;
        })
        .catch(() =>
          caches
            .match(request)
            .then((cached) => cached || caches.match("/index.html"))
            .then((cached) => cached || caches.match("/")),
        ),
    );
    return;
  }

  // Static assets: cache-first with lazy runtime population.
  if (isCacheableAsset(url)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok && response.type === "basic") {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        });
      }),
    );
  }
});

// --- Web Push (unchanged behaviour) ---------------------------------------

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { title: "Time Agent", body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "Time Agent", {
      body: payload.body || "你有一条新通知",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: payload.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((items) => {
      const existing = items.find((client) => client.url === target);
      return existing ? existing.focus() : clients.openWindow(target);
    }),
  );
});
