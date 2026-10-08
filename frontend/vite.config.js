import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Porta do frontend: 3200 (dev e produção)
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3200,
    proxy: {
      // Em desenvolvimento o Vite repassa /api para o FastAPI (porta 3100)
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:3100",
        changeOrigin: true,
      },
      // WebSocket de mercado (/ws/market) — `ws: true` é obrigatório, senão
      // o Vite responde o handshake como página normal e a conexão morre.
      "/ws": {
        target: process.env.VITE_API_TARGET || "http://localhost:3100",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 3200,
  },
  build: {
    outDir: "dist",
  },
});
