import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      // Grafana dashboard listesini same-origin cekmek icin (CORS yok). Sadece
      // dev; prod'da gercek reverse-proxy gerekir. iframe'ler dogrudan :3000.
      '/grafana-api': {
        target: 'http://127.0.0.1:3000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/grafana-api/, ''),
      },
    },
  },
})
