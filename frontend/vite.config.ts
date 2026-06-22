import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev 서버는 /api, /ws 를 dashboard-backend(8000)로 프록시한다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
