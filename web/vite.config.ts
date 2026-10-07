import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "/app/",
  build: {
    outDir: "../src/research_hub/workspace_static",
    emptyOutDir: true,
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
    restoreMocks: true,
  },
});
