import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const apiTarget = process.env.GIVVI_E2E_API_TARGET || 'http://127.0.0.1:5000'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: { '/api': apiTarget },
  },
  build: {
    rollupOptions: {
      input: {
        app: fileURLToPath(new URL('./index.html', import.meta.url)),
        bootstrapPreview: fileURLToPath(new URL('./bootstrap-preview.html', import.meta.url)),
      },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
})
