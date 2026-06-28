import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Service worker KALDIRILDI. Eski SW'ler /grafana-api proxy'sini kesip tekrarlayan
// HTTP 401'e yol açıyordu (İzleme & Analitik "Panolar yüklenemedi"). Artık SW
// kaydetmiyoruz. Bu blok kalıcı, kendi kendini iyileştiren temizliği yapar:
//   1. Kayıtlı tüm SW'leri kaldır.
//   2. Tüm Cache Storage'ı sil (eski SW'nin cache'lediği 401 yanıtları dahil).
//   3. Sayfa hâlâ eski bir SW'nin kontrolündeyse (controller varsa) tek seferlik
//      reload yap — yoksa unregister ancak SONRAKİ yüklemede etki eder ve kullanıcı
//      bu yüklemede yine 401 görürdü (yarış durumu).
if ('serviceWorker' in navigator) {
  void (async () => {
    try {
      const regs = await navigator.serviceWorker.getRegistrations()
      await Promise.all(regs.map((r) => r.unregister()))
      if ('caches' in window) {
        const keys = await caches.keys()
        await Promise.all(keys.map((k) => caches.delete(k)))
      }
      // Bu sayfa bir SW tarafından kontrol ediliyorsa, ağ (proxy) doğrudan devreye
      // girsin diye bir kez yenile. sessionStorage bayrağı sonsuz reload'u önler.
      if (navigator.serviceWorker.controller && !sessionStorage.getItem('sw-killed')) {
        sessionStorage.setItem('sw-killed', '1')
        location.reload()
      }
    } catch {
      /* temizlik best-effort; başarısızsa ağ yine doğrudan çalışır */
    }
  })()
}
