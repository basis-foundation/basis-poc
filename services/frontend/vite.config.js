import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy API and WebSocket calls through Vite so all traffic shares
    // the same origin (port 5173). This is essential in GitHub Codespaces:
    // each forwarded port has its own tunnel authentication cookie, so a
    // JavaScript WebSocket to wss://...-8000.app.github.dev fails because
    // the browser has no auth cookie for that port domain. Routing /ws
    // through Vite means the connection goes to the already-authenticated
    // 5173 origin and is proxied internally to the API container.
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: 'http://api:8000',
        changeOrigin: true,
        ws: true,   // upgrade HTTP → WebSocket; query string is preserved
      },
    },
  },
})
