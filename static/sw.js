/**
 * static/sw.js - Service Worker for Timesheet AI PWA
 *
 * Strategy:
 *   - Static assets (CSS/JS/icons): cache-first
 *   - API calls (/api/*): network-first with cache fallback
 *   - HTML pages: network-first with offline fallback
 *   - Don't cache POST/PATCH/DELETE (always go network)
 */

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `timesheet-ai-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `timesheet-ai-dynamic-${CACHE_VERSION}`;

// Files to pre-cache on install (the shell)
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/offline.html',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// ============ INSTALL ============
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker');
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        // Some assets might not exist yet (e.g. icons not generated)
        console.warn('[SW] Some assets failed to cache:', err);
      });
    }).then(() => {
      // Activate immediately without waiting for tabs to close
      return self.skipWaiting();
    })
  );
});

// ============ ACTIVATE ============
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker');
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== DYNAMIC_CACHE)
          .map((k) => {
            console.log('[SW] Deleting old cache:', k);
            return caches.delete(k);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// ============ FETCH ============
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Skip non-GET requests (POST/PATCH/DELETE go straight to network)
  if (request.method !== 'GET') {
    return;
  }

  // Skip non-http requests (chrome-extension://, etc.)
  if (!request.url.startsWith('http')) {
    return;
  }

  // Skip cross-origin
  if (url.origin !== self.location.origin) {
    return;
  }

  // Strategy 1: Static assets (cache-first)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Strategy 2: API calls (network-first, no cache fallback for safety)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkOnly(request));
    return;
  }

  // Strategy 3: HTML pages (network-first with offline fallback)
  event.respondWith(networkFirstWithOffline(request));
});

// ============ STRATEGIES ============

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return new Response('', { status: 503 });
  }
}

async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (err) {
    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function networkFirstWithOffline(request) {
  try {
    const response = await fetch(request);
    // Cache successful page responses for offline fallback
    if (response && response.ok && response.type !== 'opaqueredirect') {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // Offline: try cache, otherwise show offline page
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match('/static/offline.html');
    return offline || new Response('You are offline', { status: 503, headers: { 'Content-Type': 'text/html' } });
  }
}

// ============ Optional: Listen for messages from page ============
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});