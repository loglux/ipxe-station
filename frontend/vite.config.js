import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy API requests to FastAPI backend on the same host (adjust port if needed)
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
