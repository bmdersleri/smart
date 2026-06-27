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
// HTTP 401'e yol açıyordu (İzleme & Analitik panoları yüklenemiyordu). Artık SW
// kaydetmiyoruz; /sw.js bir kill-switch'e dönüştü (kendini siler). Daha önce SW
// kaydetmiş tarayıcılar bir sonraki yüklemede güncel /sw.js'i çekip kaydı kaldırır.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    for (const r of regs) r.unregister()
  })
}
