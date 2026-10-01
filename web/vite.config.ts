import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    // two pages: the live game, and the standalone replay viewer (T33) that needs no server
    rollupOptions: { input: { main: "index.html", replay: "replay.html" } },
  },
});
