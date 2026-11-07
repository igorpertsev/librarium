/*
 * Little Dragon service worker: the app opens offline and books' covers stay available.
 *
 * - Pages: network first; offline, the last saved copy of the app is shown (it then explains
 *   that the catalogue needs a connection).
 * - /assets/*: built files with a hash in the name never change, so the saved copy is used.
 * - Images from this site (uploaded covers): shown from the cache and refreshed in the
 *   background; at most MAX_IMAGES are kept. Other sites' images are not stored (the browser
 *   cannot see their size and would count them as very large).
 * - The API is never cached: loans and availability must be current.
 */
const VERSION = 1;
const SHELL = `shell-v${VERSION}`;
const ASSETS = `assets-v${VERSION}`;
const IMAGES = `images-v${VERSION}`;
const MAX_IMAGES = 200;
const MAX_ASSETS = 80;

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.add('/')).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  const keep = new Set([SHELL, ASSETS, IMAGES]);
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter((name) => !keep.has(name)).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

async function trim(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  await Promise.all(keys.slice(0, Math.max(0, keys.length - max)).map((key) => cache.delete(key)));
}

async function page(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const copy = response.clone();
      caches.open(SHELL).then((cache) => cache.put('/', copy));
    }
    return response;
  } catch {
    const saved = await caches.match('/', { cacheName: SHELL });
    return saved ?? Response.error();
  }
}

async function asset(request) {
  const saved = await caches.match(request, { cacheName: ASSETS });
  if (saved) return saved;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(ASSETS);
    await cache.put(request, response.clone());
    trim(ASSETS, MAX_ASSETS);
  }
  return response;
}

async function image(request) {
  const cache = await caches.open(IMAGES);
  const saved = await cache.match(request);
  const fresh = fetch(request)
    .then((response) => {
      if (response.ok && response.type === 'basic') {
        cache.put(request, response.clone()).then(() => trim(IMAGES, MAX_IMAGES));
      }
      return response;
    })
    .catch(() => saved ?? Response.error());
  return saved ?? fresh;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;
  if (sameOrigin && url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate' && sameOrigin) {
    event.respondWith(page(request));
  } else if (sameOrigin && url.pathname.startsWith('/assets/')) {
    event.respondWith(asset(request));
  } else if (sameOrigin && request.destination === 'image') {
    event.respondWith(image(request));
  }
});
