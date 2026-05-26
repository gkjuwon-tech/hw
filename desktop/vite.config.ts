import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static operator UI. `npm run build` emits `dist/` which the on-device
// kiosk server (edge_agent) serves on the appliance's touch display.
// `base: "./"` keeps asset URLs relative so the bundle works when served
// under the kiosk server's `/kiosk/` path prefix. `npm run dev` serves it
// at http://localhost:5173/ for pure-frontend iteration.
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
