import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Widget is meant to be embedded via <iframe>, so it builds to a fully
// self-contained bundle (base: "./") that can be hosted at any path -
// e.g. served as static files from FastAPI at /widget/, or from a CDN.
export default defineConfig({
  plugins: [vue()],
  base: "./",
  server: { port: 5173 },
  build: {
    outDir: "dist",
  },
});