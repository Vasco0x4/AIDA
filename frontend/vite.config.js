import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    include: ['src/**/*.test.jsx'],
    css: false,
    restoreMocks: true,
  },
  server: {
    host: '0.0.0.0',
    // Allow the dev server to be reached by hostname/IP other than localhost
    // (LAN access from another device).
    allowedHosts: true,
    // Colima/Lima mounts the source over virtiofs, where inotify file-change
    // events don't reach the container — so native watching misses edits and
    // Vite serves stale modules. Polling reliably picks up host edits for HMR.
    watch: { usePolling: true, interval: 300 },
    // Allow the Vite HMR websocket to work when the app is reached via the
    // host port mapping (:5174 -> container 5173), from localhost or the LAN IP.
    hmr: { clientPort: Number(globalThis.process?.env.VITE_HMR_CLIENT_PORT || 5174) },
    proxy: {
      // Primary path: VITE_API_URL=/api — the browser always talks to the
      // Vite server's origin (localhost or LAN IP), and this proxy forwards
      // to the in-container "backend" service on aida-dev-network. ws:true
      // covers the /api/ws WebSocket channel.
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
