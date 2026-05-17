// vite.config.js
import { defineConfig } from "file:///sessions/wonderful-vibrant-volta/mnt/basis-poc/services/frontend/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/wonderful-vibrant-volta/mnt/basis-poc/services/frontend/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
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
      "/api": {
        target: "http://api:8000",
        changeOrigin: true
        // No path rewrite — FastAPI routes all live under /api/
      },
      "/ws": {
        target: "http://api:8000",
        changeOrigin: true,
        ws: true
        // upgrade HTTP → WebSocket; query string is preserved
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvd29uZGVyZnVsLXZpYnJhbnQtdm9sdGEvbW50L2Jhc2lzLXBvYy9zZXJ2aWNlcy9mcm9udGVuZFwiO2NvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9maWxlbmFtZSA9IFwiL3Nlc3Npb25zL3dvbmRlcmZ1bC12aWJyYW50LXZvbHRhL21udC9iYXNpcy1wb2Mvc2VydmljZXMvZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtjb25zdCBfX3ZpdGVfaW5qZWN0ZWRfb3JpZ2luYWxfaW1wb3J0X21ldGFfdXJsID0gXCJmaWxlOi8vL3Nlc3Npb25zL3dvbmRlcmZ1bC12aWJyYW50LXZvbHRhL21udC9iYXNpcy1wb2Mvc2VydmljZXMvZnJvbnRlbmQvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJ1xuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICBwbHVnaW5zOiBbcmVhY3QoKV0sXG4gIHNlcnZlcjoge1xuICAgIGhvc3Q6ICcwLjAuMC4wJyxcbiAgICBwb3J0OiA1MTczLFxuICAgIC8vIFByb3h5IEFMTCBiYWNrZW5kIHRyYWZmaWMgdGhyb3VnaCBWaXRlIHNvIGV2ZXJ5IHJlcXVlc3Qgc2hhcmVzIHRoZVxuICAgIC8vIHNhbWUgb3JpZ2luIChwb3J0IDUxNzMpLiBUaGlzIGlzIGVzc2VudGlhbCBpbiBHaXRIdWIgQ29kZXNwYWNlczpcbiAgICAvLyBlYWNoIGZvcndhcmRlZCBwb3J0IGhhcyBpdHMgb3duIHR1bm5lbCBhdXRoZW50aWNhdGlvbiBjb29raWUuIEFcbiAgICAvLyBkaXJlY3QgZmV0Y2gvV2ViU29ja2V0IHRvIC4uLi04MDAwLmFwcC5naXRodWIuZGV2IGZhaWxzIGJlY2F1c2UgdGhlXG4gICAgLy8gYnJvd3NlciBoYXMgbm8gYXV0aCBjb29raWUgZm9yIHRoYXQgcG9ydCBkb21haW4uIFJvdXRpbmcgZXZlcnl0aGluZ1xuICAgIC8vIHRocm91Z2ggcG9ydCA1MTczIGtlZXBzIGFsbCB0cmFmZmljIG9uIGEgc2luZ2xlIGF1dGhlbnRpY2F0ZWQgb3JpZ2luLlxuICAgIC8vXG4gICAgLy8gL2FwaSAgXHUyMDE0IFJFU1QgY2FsbHMuIEZhc3RBUEkgbW91bnRzIGFsbCByb3V0ZXMgdW5kZXIgL2FwaS8gc28gdGhlIHBhdGhcbiAgICAvLyAgICAgICAgIGlzIGZvcndhcmRlZCBhcy1pcyAobm8gcmV3cml0ZSkuIEEgcmV3cml0ZSBzdHJpcHBpbmcgL2FwaSB3b3VsZFxuICAgIC8vICAgICAgICAgY2F1c2UgNDA0cyBiZWNhdXNlIHRoZSBGYXN0QVBJIHJvdXRlcnMgdXNlIHByZWZpeD1cIi9hcGlcIi5cbiAgICAvL1xuICAgIC8vIC93cyAgIFx1MjAxNCBXZWJTb2NrZXQgdXBncmFkZS4gcXVlcnkgc3RyaW5nICh0b2tlbj0uLi4pIGlzIHByZXNlcnZlZC5cbiAgICBwcm94eToge1xuICAgICAgJy9hcGknOiB7XG4gICAgICAgIHRhcmdldDogJ2h0dHA6Ly9hcGk6ODAwMCcsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgICAgLy8gTm8gcGF0aCByZXdyaXRlIFx1MjAxNCBGYXN0QVBJIHJvdXRlcyBhbGwgbGl2ZSB1bmRlciAvYXBpL1xuICAgICAgfSxcbiAgICAgICcvd3MnOiB7XG4gICAgICAgIHRhcmdldDogJ2h0dHA6Ly9hcGk6ODAwMCcsXG4gICAgICAgIGNoYW5nZU9yaWdpbjogdHJ1ZSxcbiAgICAgICAgd3M6IHRydWUsICAgLy8gdXBncmFkZSBIVFRQIFx1MjE5MiBXZWJTb2NrZXQ7IHF1ZXJ5IHN0cmluZyBpcyBwcmVzZXJ2ZWRcbiAgICAgIH0sXG4gICAgfSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQXFYLFNBQVMsb0JBQW9CO0FBQ2xaLE9BQU8sV0FBVztBQUVsQixJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUEsRUFDakIsUUFBUTtBQUFBLElBQ04sTUFBTTtBQUFBLElBQ04sTUFBTTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBO0FBQUE7QUFBQTtBQUFBLElBYU4sT0FBTztBQUFBLE1BQ0wsUUFBUTtBQUFBLFFBQ04sUUFBUTtBQUFBLFFBQ1IsY0FBYztBQUFBO0FBQUEsTUFFaEI7QUFBQSxNQUNBLE9BQU87QUFBQSxRQUNMLFFBQVE7QUFBQSxRQUNSLGNBQWM7QUFBQSxRQUNkLElBQUk7QUFBQTtBQUFBLE1BQ047QUFBQSxJQUNGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
