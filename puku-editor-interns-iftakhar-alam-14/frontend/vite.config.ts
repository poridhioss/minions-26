import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite config: React plugin + a dev-server proxy so the SPA can
// call /api/* and /health on the same origin as the page (avoids CORS
// during `npm run dev`). In production, nginx serves both the SPA and
// the FastAPI backend, so this proxy is dev-only.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': 'http://localhost:8000',
      '/docs': 'http://localhost:8000',
      '/redoc': 'http://localhost:8000',
      '/openapi.json': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Produce a relatively flat bundle. Recharts is the heaviest dep
    // (~200KB gzipped); everything else is small.
    chunkSizeWarningLimit: 800,
  },
})
