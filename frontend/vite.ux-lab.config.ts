import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    emptyOutDir: true,
    outDir: "dist-ux-lab",
    rollupOptions: {
      input: resolve(__dirname, "ux-lab.html"),
    },
  },
});