// EKONT SMART REPORT — service worker KILL-SWITCH.
// Eski PWA service worker'ları /grafana-api proxy isteklerini kesip tekrarlayan
// HTTP 401'e yol açıyordu (İzleme & Analitik "Panolar yüklenemedi"). Offline kabuk
// önbelleği bu localhost SCADA aracı için kritik değil; bu yüzden SW tamamen
// kaldırıldı. Bu dosya yalnızca kendini siler: önbellekleri temizler, kaydı kaldırır
// ve kontrol ettiği sayfaları bir kez yeniler ki ağ (proxy) doğrudan devreye girsin.
self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.map((k) => caches.delete(k)))
      await self.registration.unregister()
      const clients = await self.clients.matchAll({ type: 'window' })
      for (const client of clients) client.navigate(client.url)
    })(),
  )
})

// Hiçbir isteği elleme — her şey doğrudan ağa gitsin.
self.addEventListener('fetch', () => {})
