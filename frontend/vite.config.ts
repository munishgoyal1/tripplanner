import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api -> FastAPI so the SPA and backend share an origin
// during development (avoids CORS friction and lets SSE stream cleanly).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Hot Module Replacement is OFF by default — code changes are picked up on a
    // manual browser refresh (Ctrl+R), not pushed live. Set VITE_HMR=1 to enable.
    hmr: process.env.VITE_HMR === "1",
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
