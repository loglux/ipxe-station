import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API requests to FastAPI backend on the same host (adjust port if needed)
export default defineConfig({
  plugins: [react()],
  base: '/ui/',
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
