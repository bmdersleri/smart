// SCADA Reporter — minimal service worker (uygulama kabuğu offline önbelleği).
// API çağrıları ASLA önbelleklenmez (canlı veri); yalnız statik kabuk + navigasyon.
const CACHE = 'scada-shell-v1'
const SHELL = ['/', '/index.html', '/icon.svg', '/manifest.webmanifest']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // API / health / metrics — daima ağ, önbellek yok
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/health') || url.pathname.startsWith('/metrics')) {
    return
  }
  if (request.method !== 'GET') return

  // Navigasyon (SPA): ağ-önce, çevrimdışıysa kabuk
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/index.html')))
    return
  }

  // Statik varlıklar: önbellek-önce, ardından ağ
  event.respondWith(
    caches.match(request).then((cached) =>
      cached ||
      fetch(request).then((resp) => {
        if (resp.ok && url.origin === self.location.origin) {
          const copy = resp.clone()
          caches.open(CACHE).then((c) => c.put(request, copy))
        }
        return resp
      })
    )
  )
})
