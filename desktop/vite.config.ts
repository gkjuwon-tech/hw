import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Renderer entry. The Electron main process loads `dist/index.html` from this
// build in production, or `http://localhost:5173/` when running `npm run dev`.
export default defineConfig({
  plugins: [react()],
  root: ".",
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2022",
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
