import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API requests to FastAPI backend on the same host (adjust port if needed)
export default defineConfig({
  plugins: [react()],
  base: '/ui/',
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    globals: true,
    exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'],
  },
  build: {
    // Output directly into app/ so a single volume mount (./app:/app) covers both
    // backend code and built frontend — no nested Docker mounts needed.
    outDir: '../app/frontend/dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
