import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  // GRAFANA_* env (non-VITE prefix) — sadece dev proxy icin sunucu tarafinda
  // kullanilir, tarayiciya sizmaz.
  const env = loadEnv(mode, process.cwd(), '')
  const grafanaUser = env.GRAFANA_USER || 'admin'
  const grafanaPassword = env.GRAFANA_PASSWORD || 'admin'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true, ws: true },
        '/health': { target: 'http://127.0.0.1:8001', changeOrigin: true },
        // Grafana dashboard listesini same-origin cekmek icin (CORS yok). Sadece
        // dev; prod'da gercek reverse-proxy gerekir. iframe'ler dogrudan :3000.
        // Basic-auth ile gider, boylece Grafana anon Viewer kapali olsa da
        // /api/search 401 vermez (bkz. docs/grafana-windows-service.md).
        '/grafana-api': {
          target: 'http://127.0.0.1:3000',
          changeOrigin: true,
          auth: `${grafanaUser}:${grafanaPassword}`,
          rewrite: (p) => p.replace(/^\/grafana-api/, ''),
        },
      },
    },
  }
})
