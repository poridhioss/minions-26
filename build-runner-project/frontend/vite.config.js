import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite dev server config: port 5173, proxy /api -> FastAPI on :8000
// This way the React app can call "/api/build" and Vite forwards to
// "http://localhost:8000/build" without CORS hassles in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        ws: true,  // also proxy WebSocket connections for /logs
      },
    },
  },
  build: {
    outDir: 'dist',
    // Relative base so the built files can be served from any path on FastAPI
    base: './',
  },
})
