import { defineConfig, configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    // e2e/ holds Playwright specs (also *.spec.ts) — keep them out of vitest.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
