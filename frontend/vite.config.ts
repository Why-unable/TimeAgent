import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  // `vite preview` serves only built static assets by default.  In this
  // repository Docker Compose exposes the complete backend through port 8080,
  // so proxy API calls there and preserve their same-origin cookie semantics.
  preview: {
    proxy: {
      "/api": "http://localhost:8080",
      "/health": "http://localhost:8080",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    css: true,
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
