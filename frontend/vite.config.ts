import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/static/",
  plugins: [react()],
  build: {
    outDir: "../autometa/static",
    emptyOutDir: true,
    assetsDir: "assets",
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8016",
    },
  },
});
