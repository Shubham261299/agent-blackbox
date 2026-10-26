/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { injectDemoMeta } from "./src/lib/demoMeta";

// The UI calls "/api/..."; in dev, Vite forwards that to the FastAPI backend (no CORS needed).
// BLACKBOX_API points it at another backend when port 8000 is taken.
const apiTarget = process.env.BLACKBOX_API ?? "http://127.0.0.1:8000";
// `vite build --mode demo` makes the static site for GitHub Pages: relative paths, so it works under a project URL, and the
// recorded data from public/demo-data (the live build does not carry it).
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "./" : "/",
  publicDir: mode === "demo" ? "public" : false,
  build: { outDir: mode === "demo" ? "dist-demo" : "dist" },
  plugins: [
    react(),
    // Only the recorded demo gets its own title and link-preview tags; the live app's page is left as it is.
    { name: "demo-meta", transformIndexHtml: (html: string) => (mode === "demo" ? injectDemoMeta(html) : html) },
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: false,
  },
}));
