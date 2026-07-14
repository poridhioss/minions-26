import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/jobs':       { target: 'http://localhost:3000', changeOrigin: true, ws: true },
      '/healthz':    { target: 'http://localhost:3000', changeOrigin: true },
    },
  },
});
