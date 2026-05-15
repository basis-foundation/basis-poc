import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy ALL backend traffic through Vite so every request shares the
    // same origin (port 5173). This is essential in GitHub Codespaces:
    // each forwarded port has its own tunnel authentication cookie. A
    // direct fetch/WebSocket to ...-8000.app.github.dev fails because the
    // browser has no auth cookie for that port domain. Routing everything
    // through port 5173 keeps all traffic on a single authenticated origin.
    //
    // /api  — REST calls. FastAPI mounts all routes under /api/ so the path
    //         is forwarded as-is (no rewrite). A rewrite stripping /api would
    //         cause 404s because the FastAPI routers use prefix="/api".
    //
    // /ws   — WebSocket upgrade. query string (token=...) is preserved.
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        // No path rewrite — FastAPI routes all live under /api/
      },
      '/ws': {
        target: 'http://api:8000',
        changeOrigin: true,
        ws: true,   // upgrade HTTP → WebSocket; query string is preserved
      },
    },
  },
})
