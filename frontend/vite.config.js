import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser calls /api/... on the Vite server, which forwards to the bot.
// This avoids CORS, so the bot code does not need to change.
const BOT_URL = process.env.BOT_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: BOT_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
