/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // En développement local, les appels /api sont relayés vers l'API (évite la configuration CORS)
    // 127.0.0.1 et non « localhost » : Node peut résoudre localhost en IPv6 (::1) alors que l'API écoute en IPv4
    proxy: { "/api": process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000" },
  },
  test: { environment: "node" },
});
